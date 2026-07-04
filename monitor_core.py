# -*- coding: utf-8 -*-
"""
监控核心：魔方财务(ZJMF) API 客户端 + 状态机引擎。

这里不碰任何 Azure / Web 的东西，纯逻辑，方便本地脚本和 Serverless 入口共用。
只用标准库，别引第三方 http 库——部署到 Serverless 时少一个装不上的理由。
"""

import json
import time
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger("monitor")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _http(method, url, headers=None, params=None, json_body=None, timeout=15):
    """发一个 HTTP 请求，返回 (status_code, text)。

    4xx/5xx 不抛异常，照常返回状态码和正文——调用方要靠状态码判断登录态。
    只有连不上（DNS/超时/拒绝）才抛 RuntimeError。
    """
    if params:
        sep = "&" if "?" in url else "?"
        url = url + sep + urllib.parse.urlencode(params)

    data = json.dumps(json_body).encode() if json_body is not None else None
    req = urllib.request.Request(url, data=data, method=method.upper())
    for k, v in (headers or {}).items():
        req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode("utf-8", "replace")
        except Exception:
            return e.code, ""
    except urllib.error.URLError as e:
        raise RuntimeError(f"{method} {url} 请求失败: {e.reason}")


# --- 电源状态关键词 ---
ON_WORDS = ("on", "poweron", "power_on", "running", "active", "online",
            "开机", "运行中", "在线", "已开机")
OFF_WORDS = ("off", "poweroff", "power_off", "shutdown", "stopped", "halted",
             "closed", "关机", "已关机", "关闭")
# 命中任意一个就说明登录态没了，需要重新登录
LOGOUT_HINTS = ("未登录", "未登陆", "请登录", "请重新登录", "登录失效", "登录已失效", "token")

POWER_ON = "on"
POWER_OFF = "off"
POWER_UNKNOWN = "unknown"

# 状态机
HEALTHY = "healthy"
SUSPECT = "suspect"
DOWN = "down"
REBOOTING = "rebooting"
RECOVERING = "recovering"


class MofangAPI:
    """魔方财务 API 客户端。JWT 失效时自动重登一次再重试。"""

    def __init__(self, base_url, account, api_key, timeout=15):
        self.base_url = (base_url or "").rstrip("/")
        self.account = account
        self.api_key = api_key
        self.timeout = timeout
        self.jwt = None
        self.jwt_at = 0.0

    def _headers(self):
        h = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.jwt:
            h["authorization"] = f"JWT {self.jwt}"
        return h

    def _call(self, method, path, params=None, json_body=None, allow_relogin=True):
        if not path.startswith("/"):
            path = "/" + path
        code, text = _http(method, self.base_url + path, self._headers(),
                            params, json_body, self.timeout)

        # 登录态失效有好几种表现：401/403、有时 405，或者正文里带“未登录”
        logged_out = any(w in text for w in LOGOUT_HINTS)
        if allow_relogin and (code in (401, 403, 405) or logged_out):
            log.warning("登录态失效 (HTTP %s)，重新登录后重试 %s %s", code, method, path)
            self.login()
            return self._call(method, path, params, json_body, allow_relogin=False)

        try:
            data = json.loads(text) if text.strip() else {}
        except ValueError:
            raise RuntimeError(f"接口返回的不是 JSON: {method} {path} HTTP {code} -> {text[:300]}")

        if code >= 400:
            raise RuntimeError(f"接口报错: {method} {path} HTTP {code} -> {data}")
        return data

    @staticmethod
    def unwrap(data):
        """魔方的返回常包一层 data/result，剥掉方便取值。"""
        if isinstance(data, dict):
            for key in ("data", "result"):
                inner = data.get(key)
                if isinstance(inner, (dict, list)):
                    return inner
        return data

    def login(self):
        data = self._call("POST", "/v1/login_api",
                          json_body={"account": self.account, "password": self.api_key},
                          allow_relogin=False)
        inner = self.unwrap(data)
        jwt = (inner.get("jwt") if isinstance(inner, dict) else None) \
            or (data.get("jwt") if isinstance(data, dict) else None)
        if not jwt:
            raise RuntimeError(f"登录没拿到 jwt，返回: {data}")
        self.jwt, self.jwt_at = jwt, time.time()
        log.info("登录成功")
        return jwt

    def ensure_login(self, max_age=6000):
        """JWT 缺失或快过期（默认 100 分钟）就提前刷一次，省得每个请求都撞 401。"""
        if not self.jwt or time.time() - self.jwt_at > max_age:
            self.login()

    def list_hosts(self):
        """拉主机列表，用于自动发现。不同版本字段不一样，挨个 key 试。"""
        for path, params in (("/v1/hosts", {"page": 1, "limit": 100}),
                             ("/v1/tickets/page", None)):
            try:
                inner = self.unwrap(self._call("GET", path, params=params))
            except Exception as e:
                log.debug("列表接口 %s 失败: %s", path, e)
                continue
            if isinstance(inner, list):
                return inner
            if isinstance(inner, dict):
                for key in ("host", "_host", "list", "data"):
                    if isinstance(inner.get(key), list):
                        return inner[key]
        return []

    def power_status(self, host_id):
        data = self._call("GET", f"/v1/hosts/{host_id}/module/status",
                          params={"type": "host"})
        return data if isinstance(data, dict) else {"raw": data}

    def power_on(self, host_id):
        return self._call("PUT", f"/v1/hosts/{host_id}/module/on")

    def hard_reboot(self, host_id):
        return self._call("PUT", f"/v1/hosts/{host_id}/module/hard_reboot")


def _collect_status_text(obj) -> str:
    """从任意嵌套结构里把可能表示状态的字段值拼起来。"""
    keys = {"status", "power_status", "power", "state", "host_status",
            "server_status", "desc", "message", "msg"}
    parts = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if str(k).lower() in keys:
                    parts.append(str(v))
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(obj)
    return " ".join(parts).strip()


def classify_power(resp) -> str:
    """把接口返回归类成 on / off / unknown。

    识别不出来（两边关键词都没命中，或者同时命中互相矛盾）就算 unknown，
    交给上层去决定要不要硬重启。
    """
    text = _collect_status_text(resp).lower()
    if not text:
        text = json.dumps(resp, ensure_ascii=False).lower()
    on = any(w in text for w in ON_WORDS)
    off = any(w in text for w in OFF_WORDS)
    if on and not off:
        return POWER_ON
    if off and not on:
        return POWER_OFF
    return POWER_UNKNOWN


class MonitorEngine:
    """按配置跑一轮监控：查状态、推状态机、该开机开机、该重启重启。

    config 由 state_store 提供并持久化，结构见 README。运行时状态放在
    config["state"][server_id]，事件日志放 config["events"]。
    """

    def __init__(self, config):
        self.config = config
        config.setdefault("servers", [])
        config.setdefault("state", {})
        config.setdefault("events", [])
        self.settings = config.setdefault("settings", {})
        p = config.get("provider", {})
        self.api = MofangAPI(p.get("base_url", "https://www.heyunidc.cn"),
                             p.get("account", ""), p.get("api_key", ""))

    def _get(self, key, default):
        return self.settings.get(key, default)

    # ---- 事件与通知 ----
    def _event(self, sid, name, level, message):
        self.config["events"].insert(0, {
            "time": now_iso(), "server_id": sid, "name": name,
            "level": level, "message": message,
        })
        del self.config["events"][200:]
        {"critical": log.error, "warning": log.warning}.get(level, log.info)("[%s] %s", name, message)
        self._notify(level, name, message)

    def _notify(self, level, name, message):
        url = self._get("webhook_url", "")
        if not url:
            return
        try:
            if self._get("webhook_type", "custom") == "pushplus":
                _http("POST", "https://www.pushplus.plus/send",
                      json_body={"token": url, "title": f"服务器监控 - {name}",
                                 "content": message}, timeout=10)
            else:
                _http("POST", url,
                      json_body={"level": level, "name": name,
                                 "message": message, "time": now_iso()}, timeout=10)
        except Exception as e:
            log.warning("通知发送失败: %s", e)

    def _transition(self, st, new, sid, name, reason):
        old = st.get("state", HEALTHY)
        if old == new:
            return
        level = {DOWN: "critical", REBOOTING: "critical",
                 RECOVERING: "warning"}.get(new, "info")
        self._event(sid, name, level, f"{old} → {new}（{reason}）")
        st["state"] = new

    # ---- 动作次数限制 ----
    def _recent_actions(self, st):
        window = 86400 if self._get("reboot_limit_window", "hour") == "day" else 3600
        cutoff = time.time() - window
        st["action_history"] = [t for t in st.get("action_history", []) if t >= cutoff]
        return len(st["action_history"])

    def _resolve_action(self, st):
        """决定这次该做什么动作。

        - 服务器明确处于关机 → 用配置里的动作（默认开机）。
        - 状态识别不出来 (unknown) → 一律硬重启，把它从不确定的状态里拽出来。
        """
        if st.get("problem") == POWER_UNKNOWN:
            return "hard_reboot"
        return self._get("action", "on")

    def _do_action(self, sid, name, st):
        """执行开机/硬重启，返回是否真的发出了指令。"""
        if self._get("dry_run", False):
            self._event(sid, name, "warning", "DRY_RUN 已开启，只报警不动手")
            return False

        cooldown = self._get("reboot_cooldown", 600)
        last = st.get("last_action_ts", 0)
        if last and time.time() - last < cooldown:
            self._event(sid, name, "warning", f"还在 {cooldown}s 冷却期内，这轮先不动")
            return False

        limit = self._get("reboot_limit", 5)
        if limit and self._recent_actions(st) >= limit:
            self._event(sid, name, "critical",
                        f"已达动作上限（{limit}/{self._get('reboot_limit_window', 'hour')}），暂停自动操作")
            return False

        action = self._resolve_action(st)
        verb = "硬重启" if action == "hard_reboot" else "开机"
        try:
            fn = self.api.hard_reboot if action == "hard_reboot" else self.api.power_on
            result = fn(int(sid))
        except Exception as e:
            self._event(sid, name, "critical", f"{verb}指令发送失败: {e}")
            return False

        inner = MofangAPI.unwrap(result)
        if isinstance(inner, dict) and ("second_verify" in inner or "_second_verify" in inner):
            self._event(sid, name, "critical", f"{verb}需要二次验证，脚本处理不了: {inner}")
            return False

        st["last_action_ts"] = time.time()
        st.setdefault("action_history", []).append(time.time())
        self._event(sid, name, "critical", f"已发送{verb}指令: {result}")
        return True

    def check_server(self, server):
        sid = str(server.get("id", "")).strip()
        if not sid or not server.get("enabled", True):
            return
        name = server.get("name") or server.get("product_name") or f"host-{sid}"

        st = self.config["state"].setdefault(sid, {
            "state": HEALTHY, "fail_count": 0, "last_action_ts": 0, "action_history": [],
        })
        st["name"] = name
        st["ip"] = server.get("ip", st.get("ip", "-"))
        st["last_check"] = now_iso()

        try:
            resp = self.api.power_status(int(sid))
        except Exception as e:
            # 查询本身失败多半是网络/接口问题，不代表机器坏了，只记一笔不升级
            st["status_text"] = f"查询失败: {e}"
            st["online"] = None
            self._event(sid, name, "warning", f"状态查询失败: {e}")
            return

        power = classify_power(resp)
        st["status_text"] = _collect_status_text(resp) or power
        st["online"] = True if power == POWER_ON else (False if power == POWER_OFF else None)

        if power == POWER_ON:
            st["fail_count"] = 0
            st["problem"] = None
            self._transition(st, HEALTHY, sid, name, "恢复正常")
            st["state"] = HEALTHY
            return

        # 到这里说明是关机或状态不明，都算异常
        st["fail_count"] += 1
        st["problem"] = power  # off / unknown，供 _resolve_action 用
        state = st.get("state", HEALTHY)

        # 已经在等恢复：给足恢复时间，超时才重新判宕机
        if state == RECOVERING:
            if time.time() - st.get("last_action_ts", 0) <= self._get("recover_timeout", 300):
                return
            self._transition(st, DOWN, sid, name, "恢复超时，重新处理")
            state = DOWN

        if state == HEALTHY:
            reason = "关机" if power == POWER_OFF else "状态未知"
            self._transition(st, SUSPECT, sid, name, f"检测到异常（{reason}）")
            state = SUSPECT

        if state == SUSPECT and st["fail_count"] >= self._get("suspect_threshold", 3):
            self._transition(st, DOWN, sid, name, f"连续 {st['fail_count']} 次异常，确认宕机")
            state = DOWN

        if state == DOWN:
            self._transition(st, REBOOTING, sid, name, "开始尝试拉起")
            if self._do_action(sid, name, st):
                self._transition(st, RECOVERING, sid, name, "指令已下发，等待恢复")
            else:
                st["state"] = DOWN  # 没动成，下一轮再来

    def run_once(self):
        self.api.ensure_login()
        servers = [s for s in self.config["servers"] if s.get("enabled", True)]

        # 一台都没配就自动发现
        if not servers:
            self.discover()
            servers = [s for s in self.config["servers"] if s.get("enabled", True)]

        for s in servers:
            try:
                self.check_server(s)
            except Exception:
                log.exception("检测服务器 %s 出错", s.get("id"))

        self.config["last_run"] = now_iso()
        return {"last_run": self.config["last_run"], "total": len(servers)}

    def discover(self):
        """从账户拉取主机并合并进配置，返回新增数量。"""
        self.api.ensure_login()
        known = {str(s.get("id")) for s in self.config["servers"]}
        added = 0
        for h in self.api.list_hosts():
            hid = str(h.get("id", "")).strip()
            if hid and hid not in known:
                self.config["servers"].append({
                    "id": hid,
                    "name": h.get("name") or h.get("product_name") or f"host-{hid}",
                    "ip": h.get("ip", "-"), "enabled": True,
                })
                known.add(hid)
                added += 1
        if added:
            log.info("自动发现新增 %s 台服务器", added)
        return added
