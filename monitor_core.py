#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
魔方财务云服务器监控核心模块。

包含：
- MofangAPI：魔方财务 API 客户端，token 失效（401/403/405/未登录）自动重新登录。
- MonitorEngine：监控引擎，内置 5 状态机（healthy/suspect/down/rebooting/recovering），
  检测到关机/异常自动开机（或硬重启）。

该模块不依赖 Azure，可被本地脚本、Azure Functions 等任何入口复用。
"""

import json
import time
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests


# ========== 状态判定关键词 ==========
OFF_KEYWORDS = {
    "off", "poweroff", "power_off", "shutdown", "stopped", "halted", "closed",
    "关机", "已关机", "关闭",
}
ON_KEYWORDS = {
    "on", "poweron", "power_on", "running", "active", "online",
    "开机", "运行中", "在线", "已开机",
}
# 登录态失效提示（命中任意一个即触发重新登录）
NOT_LOGGED_IN_KEYWORDS = ("未登录", "未登陆", "请登录", "请重新登录", "登录失效", "登录已失效")

# 5 状态机
STATE_HEALTHY = "healthy"
STATE_SUSPECT = "suspect"
STATE_DOWN = "down"
STATE_REBOOTING = "rebooting"
STATE_RECOVERING = "recovering"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def now_ts() -> float:
    return time.time()


class MofangAPI:
    """魔方财务 API 客户端。"""

    def __init__(self, base_url: str, account: str, api_key: str, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.account = account
        self.api_key = api_key
        self.timeout = timeout
        self.jwt: Optional[str] = None
        self.jwt_time: float = 0.0
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + path

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.jwt:
            headers["authorization"] = f"JWT {self.jwt}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        retry_login: bool = True,
    ) -> Any:
        url = self._url(path)
        resp = self.session.request(
            method=method,
            url=url,
            headers=self._headers(),
            params=params,
            json=json_body,
            timeout=self.timeout,
        )

        # token 失效的几种情况，统一触发自动重新登录：
        # 1) HTTP 401 / 403：未授权
        # 2) HTTP 405：登录态失效后接口常返回该状态
        # 3) 响应正文包含“未登录”等提示
        body_text = resp.text or ""
        not_logged_in = any(kw in body_text for kw in NOT_LOGGED_IN_KEYWORDS)

        if (resp.status_code in (401, 403, 405) or not_logged_in) and retry_login:
            logging.warning(
                "检测到登录态失效（HTTP %s%s），重新登录后重试：%s %s",
                resp.status_code,
                "，含未登录提示" if not_logged_in else "",
                method, path,
            )
            self.login()
            return self._request(
                method, path, params=params, json_body=json_body, retry_login=False
            )

        try:
            data = resp.json()
        except Exception:
            raise RuntimeError(
                f"接口返回非 JSON：{method} {path}, HTTP {resp.status_code}, "
                f"body={resp.text[:500]}"
            )

        if resp.status_code >= 400:
            raise RuntimeError(
                f"接口 HTTP 错误：{method} {path}, HTTP {resp.status_code}, response={data}"
            )
        return data

    @staticmethod
    def _unwrap(data: Any) -> Any:
        if isinstance(data, dict):
            for key in ("data", "result"):
                if key in data and isinstance(data[key], (dict, list)):
                    return data[key]
        return data

    def login(self) -> str:
        """POST /v1/login_api，成功返回 jwt。"""
        data = self._request(
            "POST",
            "/v1/login_api",
            json_body={"account": self.account, "password": self.api_key},
            retry_login=False,
        )
        raw = self._unwrap(data)
        jwt = raw.get("jwt") if isinstance(raw, dict) else None
        if not jwt and isinstance(data, dict):
            jwt = data.get("jwt")
        if not jwt:
            raise RuntimeError(f"登录成功但未找到 jwt，返回内容：{data}")
        self.jwt = jwt
        self.jwt_time = now_ts()
        logging.info("登录成功，已获取 JWT")
        return jwt

    def ensure_login(self, max_age: int = 6000):
        """JWT 缺失或超过 max_age 秒（默认约 100 分钟）时提前重新登录。"""
        if not self.jwt or (now_ts() - self.jwt_time) > max_age:
            self.login()

    def list_hosts(self) -> List[Dict[str, Any]]:
        """获取产品/主机列表（用于自动发现）。"""
        hosts: List[Dict[str, Any]] = []
        # 优先尝试 /v1/hosts，其次回退 /v1/tickets/page
        for path, kw in (("/v1/hosts", {"page": 1, "limit": 100}), ("/v1/tickets/page", None)):
            try:
                data = self._request("GET", path, params=kw)
            except Exception as e:
                logging.debug("列表接口 %s 调用失败：%s", path, e)
                continue
            raw = self._unwrap(data)
            if isinstance(raw, dict):
                for key in ("host", "_host", "list", "data"):
                    if isinstance(raw.get(key), list):
                        hosts = raw[key]
                        break
            elif isinstance(raw, list):
                hosts = raw
            if hosts:
                break
        return hosts

    def get_host_power_status(self, host_id: int) -> Dict[str, Any]:
        """GET /v1/hosts/:id/module/status?type=host。"""
        data = self._request(
            "GET", f"/v1/hosts/{host_id}/module/status", params={"type": "host"}
        )
        return data if isinstance(data, dict) else {"raw": data}

    def power_on(self, host_id: int) -> Dict[str, Any]:
        """PUT /v1/hosts/:id/module/on 开机。"""
        return self._request("PUT", f"/v1/hosts/{host_id}/module/on")

    def hard_reboot(self, host_id: int) -> Dict[str, Any]:
        """PUT /v1/hosts/:id/module/hard_reboot 硬重启。"""
        return self._request("PUT", f"/v1/hosts/{host_id}/module/hard_reboot")


# ========== 状态文本解析 ==========
def find_status_text(obj: Any) -> str:
    status_keys = {
        "status", "power_status", "power", "state", "host_status",
        "server_status", "desc", "message", "msg",
    }
    found: List[str] = []

    def walk(x: Any):
        if isinstance(x, dict):
            for k, v in x.items():
                if str(k).lower() in status_keys:
                    found.append(str(v))
                walk(v)
        elif isinstance(x, list):
            for item in x:
                walk(item)

    walk(obj)
    return " ".join(found).strip()


def is_power_on(status_response: Dict[str, Any]) -> bool:
    text = find_status_text(status_response).lower()
    if not text:
        text = json.dumps(status_response, ensure_ascii=False).lower()
    return any(kw.lower() in text for kw in ON_KEYWORDS)


def is_power_off(status_response: Dict[str, Any]) -> bool:
    text = find_status_text(status_response).lower()
    if not text:
        text = json.dumps(status_response, ensure_ascii=False).lower()
    return any(kw.lower() in text for kw in OFF_KEYWORDS)


# ========== 监控引擎 ==========
class MonitorEngine:
    """
    监控引擎：根据配置对每台服务器执行一次检测，推进状态机并在需要时开机/重启。

    config 结构（由 state_store 提供并持久化）：
    {
      "provider": {"base_url", "account", "api_key"},
      "settings": {
          "suspect_threshold": 3,      # 连续异常多少次判定 down
          "reboot_cooldown": 600,      # 两次动作最小间隔（秒）
          "recover_timeout": 300,      # 触发动作后多久没恢复重新判 down
          "reboot_limit": 5,           # 统计窗口内最大动作次数（0=不限）
          "reboot_limit_window": "hour", # hour / day
          "action": "on",             # on=开机 / hard_reboot=硬重启
          "dry_run": false,
          "webhook_url": "",
          "webhook_type": "custom"     # custom / pushplus
      },
      "servers": [
          {"id": "4075", "name": "我的服务器", "ip": "1.2.3.4", "enabled": true}
      ],
      "state": { "<id>": {...运行时状态...} },
      "events": [ {...事件日志...} ]
    }
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.config.setdefault("servers", [])
        self.config.setdefault("state", {})
        self.config.setdefault("events", [])
        self.settings = config.setdefault("settings", {})
        prov = config.get("provider", {})
        self.api = MofangAPI(
            base_url=prov.get("base_url", "https://www.heyunidc.cn"),
            account=prov.get("account", ""),
            api_key=prov.get("api_key", ""),
        )

    # ---- 设置读取 ----
    def _s(self, key: str, default):
        return self.settings.get(key, default)

    def _log_event(self, server_id: str, name: str, level: str, message: str):
        event = {
            "time": now_iso(),
            "server_id": server_id,
            "name": name,
            "level": level,
            "message": message,
        }
        self.config["events"].insert(0, event)
        # 只保留最近 200 条
        self.config["events"] = self.config["events"][:200]
        log_fn = {"critical": logging.error, "warning": logging.warning}.get(level, logging.info)
        log_fn("[%s] %s", name, message)
        self._notify(level, name, message)

    def _notify(self, level: str, name: str, message: str):
        url = self._s("webhook_url", "")
        if not url:
            return
        wtype = self._s("webhook_type", "custom")
        try:
            if wtype == "pushplus":
                requests.post(
                    "https://www.pushplus.plus/send",
                    json={"token": url, "title": f"服务器监控 - {name}", "content": message},
                    timeout=10,
                )
            else:  # custom
                requests.post(
                    url,
                    json={"level": level, "name": name, "message": message, "time": now_iso()},
                    timeout=10,
                )
        except Exception as e:
            logging.warning("通知发送失败：%s", e)

    def _reboot_window_seconds(self) -> int:
        return 86400 if self._s("reboot_limit_window", "hour") == "day" else 3600

    def _count_recent_actions(self, st: Dict[str, Any]) -> int:
        window = self._reboot_window_seconds()
        cutoff = now_ts() - window
        history = [t for t in st.get("action_history", []) if t >= cutoff]
        st["action_history"] = history
        return len(history)

    def _do_action(self, server_id: str, name: str, st: Dict[str, Any]) -> bool:
        """执行开机 / 硬重启，返回是否成功发送。"""
        if self._s("dry_run", False):
            self._log_event(server_id, name, "warning", "DRY_RUN 开启，仅模拟不执行动作")
            return False

        # 冷却检查
        last = st.get("last_action_ts", 0)
        cooldown = self._s("reboot_cooldown", 600)
        if last and (now_ts() - last) < cooldown:
            self._log_event(server_id, name, "warning",
                            f"处于冷却期（{cooldown}s），本轮不执行动作")
            return False

        # 次数上限检查
        limit = self._s("reboot_limit", 5)
        if limit and self._count_recent_actions(st) >= limit:
            self._log_event(server_id, name, "critical",
                            f"已达动作次数上限（{limit}/{self._s('reboot_limit_window','hour')}），本轮不执行")
            return False

        action = self._s("action", "on")
        try:
            if action == "hard_reboot":
                result = self.api.hard_reboot(int(server_id))
                verb = "硬重启"
            else:
                result = self.api.power_on(int(server_id))
                verb = "开机"
        except Exception as e:
            self._log_event(server_id, name, "critical", f"{action} 指令发送失败：{e}")
            return False

        # 二次验证提示
        raw = MofangAPI._unwrap(result)
        if isinstance(raw, dict) and ("second_verify" in raw or "_second_verify" in raw):
            self._log_event(server_id, name, "critical",
                            f"{verb}需要二次验证，脚本无法自动处理：{raw}")
            return False

        st["last_action_ts"] = now_ts()
        st.setdefault("action_history", []).append(now_ts())
        self._log_event(server_id, name, "critical", f"已发送{verb}指令：{result}")
        return True

    def _transition(self, st: Dict[str, Any], new_state: str, server_id: str, name: str, reason: str):
        old = st.get("state", STATE_HEALTHY)
        if old != new_state:
            level = {
                STATE_DOWN: "critical",
                STATE_REBOOTING: "critical",
                STATE_RECOVERING: "warning",
                STATE_HEALTHY: "info",
                STATE_SUSPECT: "info",
            }.get(new_state, "info")
            self._log_event(server_id, name, level, f"{old} → {new_state}（{reason}）")
        st["state"] = new_state

    def check_server(self, server: Dict[str, Any]):
        server_id = str(server.get("id", "")).strip()
        name = server.get("name") or server.get("product_name") or f"host-{server_id}"
        if not server_id:
            return
        if not server.get("enabled", True):
            return

        st = self.config["state"].setdefault(server_id, {
            "state": STATE_HEALTHY,
            "fail_count": 0,
            "last_action_ts": 0,
            "action_history": [],
        })

        # 查询状态
        try:
            status_resp = self.api.get_host_power_status(int(server_id))
        except Exception as e:
            st["last_check"] = now_iso()
            st["status_text"] = f"查询失败：{e}"
            st["online"] = None
            self._log_event(server_id, name, "warning", f"状态查询失败：{e}")
            return

        status_text = find_status_text(status_resp) or "-"
        online = is_power_on(status_resp)
        offline = is_power_off(status_resp)
        st["last_check"] = now_iso()
        st["status_text"] = status_text
        st["online"] = online
        st["ip"] = server.get("ip", st.get("ip", "-"))
        st["name"] = name

        threshold = self._s("suspect_threshold", 3)
        state = st.get("state", STATE_HEALTHY)

        if online:
            # 恢复正常
            st["fail_count"] = 0
            if state in (STATE_REBOOTING, STATE_RECOVERING, STATE_DOWN, STATE_SUSPECT):
                self._transition(st, STATE_HEALTHY, server_id, name, "恢复正常")
            else:
                st["state"] = STATE_HEALTHY
            return

        # 非在线（关机或异常）
        st["fail_count"] = st.get("fail_count", 0) + 1

        if state == STATE_RECOVERING:
            # 动作后仍未恢复，检查是否超时
            recover_timeout = self._s("recover_timeout", 300)
            if now_ts() - st.get("last_action_ts", 0) > recover_timeout:
                self._transition(st, STATE_DOWN, server_id, name, "恢复超时")
                state = STATE_DOWN
            else:
                return  # 等待恢复中

        if state == STATE_HEALTHY:
            self._transition(st, STATE_SUSPECT, server_id, name, "检测到异常")
            state = STATE_SUSPECT

        if state == STATE_SUSPECT and st["fail_count"] >= threshold:
            self._transition(st, STATE_DOWN, server_id, name, f"连续 {st['fail_count']} 次异常确认宕机")
            state = STATE_DOWN

        if state == STATE_DOWN:
            self._transition(st, STATE_REBOOTING, server_id, name,
                             "触发开机/重启" if not self._s("dry_run", False) else "触发（DRY_RUN）")
            ok = self._do_action(server_id, name, st)
            if ok:
                self._transition(st, STATE_RECOVERING, server_id, name, "指令已发送，等待恢复")
            else:
                # 未能执行动作，退回 down 等下轮
                st["state"] = STATE_DOWN

    def run_once(self) -> Dict[str, Any]:
        """执行一轮检测，返回本轮摘要。"""
        self.api.ensure_login()

        servers = [s for s in self.config.get("servers", []) if s.get("enabled", True)]

        # 未配置服务器时自动发现
        if not servers:
            discovered = self.api.list_hosts()
            for h in discovered:
                hid = str(h.get("id", "")).strip()
                if hid and not any(str(s.get("id")) == hid for s in self.config["servers"]):
                    self.config["servers"].append({
                        "id": hid,
                        "name": h.get("name") or h.get("product_name") or f"host-{hid}",
                        "ip": h.get("ip", "-"),
                        "enabled": True,
                    })
            servers = [s for s in self.config.get("servers", []) if s.get("enabled", True)]
            logging.info("自动发现 %s 台服务器", len(servers))

        for server in servers:
            try:
                self.check_server(server)
            except Exception as e:
                logging.exception("检测服务器 %s 出错：%s", server.get("id"), e)

        self.config["last_run"] = now_iso()
        return {
            "last_run": self.config["last_run"],
            "total": len(servers),
        }
