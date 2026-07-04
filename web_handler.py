# -*- coding: utf-8 -*-
"""
Web 请求处理。

本地版（heyun.py 里的 http.server）和 Serverless 入口（function_app.py）都调
dispatch()，这样两边的状态页、后台、API 行为完全一致，逻辑只有一份。
"""

import os
import json

from monitor_core import MonitorEngine
from state_store import load_config, save_config
from webui import STATUS_PAGE, ADMIN_PAGE

HTML = "text/html"
JSON = "application/json"


def run_monitor_once():
    cfg = load_config()
    summary = MonitorEngine(cfg).run_once()
    save_config(cfg)
    return summary


def _public_status(cfg):
    state = cfg.get("state", {})
    servers = []
    for s in cfg.get("servers", []):
        sid = str(s.get("id"))
        st = state.get(sid, {})
        servers.append({
            "id": sid,
            "name": s.get("name") or st.get("name") or sid,
            "ip": s.get("ip") or st.get("ip", "-"),
            "enabled": s.get("enabled", True),
            "state": st.get("state", "healthy"),
            "online": st.get("online"),
            "status_text": st.get("status_text", "-"),
            "last_check": st.get("last_check", "-"),
        })
    return {
        "last_run": cfg.get("last_run"),
        "servers": servers,
        "events": cfg.get("events", [])[:50],
    }


def _authorized(token):
    expected = os.environ.get("ADMIN_TOKEN", "admin")
    return bool(expected) and token == expected


def dispatch(method, path, admin_token="", body_bytes=b""):
    """统一分发，返回 (status_code, content_type, body_text)。"""
    path = (path or "").strip("/")
    method = (method or "GET").upper()

    def js(data, code=200):
        return code, JSON, json.dumps(data, ensure_ascii=False)

    def body():
        if not body_bytes:
            return {}
        try:
            return json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return {}

    # 页面
    if method == "GET" and path in ("", "index", "status.html"):
        return 200, HTML, STATUS_PAGE
    if method == "GET" and path in ("manage", "admin", "panel"):
        return 200, HTML, ADMIN_PAGE

    # 公开状态
    if method == "GET" and path == "api/status":
        return js(_public_status(load_config()))

    if not path.startswith("api/admin"):
        return js({"error": "not found", "path": path}, 404)

    # 以下都要鉴权
    if not _authorized(admin_token):
        return js({"error": "unauthorized"}, 401)

    cfg = load_config()

    if path == "api/admin/config":
        if method == "GET":
            out = dict(cfg)
            out["provider"] = {k: v for k, v in cfg.get("provider", {}).items() if k != "api_key"}
            out["provider"]["api_key_set"] = bool(cfg.get("provider", {}).get("api_key"))
            return js(out)
        if method == "POST":
            data = body()
            for k in ("base_url", "account", "api_key"):
                if data.get("provider", {}).get(k):
                    cfg.setdefault("provider", {})[k] = data["provider"][k]
            cfg.setdefault("settings", {}).update(data.get("settings", {}))
            save_config(cfg)
            return js({"ok": True})

    if path == "api/admin/server":
        data = body()
        sid = str(data.get("id", "")).strip()
        if not sid:
            return js({"error": "missing id"}, 400)
        servers = cfg.setdefault("servers", [])
        if method == "DELETE":
            cfg["servers"] = [s for s in servers if str(s.get("id")) != sid]
            cfg.get("state", {}).pop(sid, None)
            save_config(cfg)
            return js({"ok": True})
        existing = next((s for s in servers if str(s.get("id")) == sid), None)
        if existing:
            existing["name"] = data.get("name") or existing.get("name")
            existing["ip"] = data.get("ip") or existing.get("ip")
            existing["enabled"] = data.get("enabled", existing.get("enabled", True))
        else:
            servers.append({"id": sid, "name": data.get("name") or sid,
                           "ip": data.get("ip", "-"), "enabled": True})
        save_config(cfg)
        return js({"ok": True})

    if path == "api/admin/server/toggle" and method == "POST":
        sid = str(body().get("id", "")).strip()
        for s in cfg.get("servers", []):
            if str(s.get("id")) == sid:
                s["enabled"] = not s.get("enabled", True)
        save_config(cfg)
        return js({"ok": True})

    if path == "api/admin/discover" and method == "POST":
        try:
            added = MonitorEngine(cfg).discover()
        except Exception as e:
            return js({"error": str(e)}, 500)
        save_config(cfg)
        return js({"ok": True, "added": added})

    if path == "api/admin/run" and method == "POST":
        try:
            return js({"ok": True, "summary": run_monitor_once()})
        except Exception as e:
            return js({"error": str(e)}, 500)

    return js({"error": "not found", "path": path}, 404)


# --- 通用 WSGI 入口 ---
# 给 Azure 之外的 Serverless 用：Google Cloud Functions / Vercel 直接认 WSGI
# app；AWS Lambda 套个 aws-wsgi/apig-wsgi 之类的适配器也能跑。
def wsgi_app(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    token = environ.get("HTTP_X_ADMIN_TOKEN", "")
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    body = environ["wsgi.input"].read(length) if length else b""

    code, mimetype, text = dispatch(method, path, token, body)
    data = text.encode("utf-8")
    start_response(f"{code} ", [
        ("Content-Type", f"{mimetype}; charset=utf-8"),
        ("Content-Length", str(len(data))),
    ])
    return [data]


# 有的平台习惯把 WSGI 可调用对象命名为 application
application = wsgi_app
