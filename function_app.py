#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Azure Functions 入口（Python v2 编程模型）。

- TimerTrigger：按 ZJMF_CRON（默认每 10 分钟）自动执行一轮监控。
- HttpTrigger（catch-all）：提供状态页、管理后台与 JSON API。

路由说明（host.json 中 routePrefix 设为 ""）：
  GET  /                     状态页
  GET  /admin                管理后台
  GET  /api/status           公开状态 JSON
  GET  /api/admin/config     读取配置（需 X-Admin-Token）
  POST /api/admin/config     更新服务商/全局设置
  POST /api/admin/server     添加/更新服务器
  DEL  /api/admin/server     删除服务器
  POST /api/admin/server/toggle  启用/停用
  POST /api/admin/discover   自动发现
  POST /api/admin/run        立即检测一次
"""

import os
import json
import logging

import azure.functions as func

from monitor_core import MonitorEngine
from state_store import load_config, save_config
from webui import STATUS_PAGE, ADMIN_PAGE

app = func.FunctionApp()

CRON = os.environ.get("ZJMF_CRON", "0 */10 * * * *")  # 每 10 分钟


# ========== 定时监控 ==========
@app.timer_trigger(schedule=CRON, arg_name="timer", run_on_startup=False, use_monitor=True)
def monitor_timer(timer: func.TimerRequest):
    logging.info("定时监控触发")
    _run_monitor()


def _run_monitor():
    cfg = load_config()
    engine = MonitorEngine(cfg)
    summary = engine.run_once()
    save_config(cfg)
    logging.info("监控完成：%s", summary)
    return summary


# ========== HTTP：状态页 / 管理后台 / API ==========
def _json(data, status=200):
    return func.HttpResponse(
        json.dumps(data, ensure_ascii=False),
        status_code=status,
        mimetype="application/json",
    )


def _html(body):
    return func.HttpResponse(body, mimetype="text/html")


def _check_admin(req: func.HttpRequest) -> bool:
    expected = os.environ.get("ADMIN_TOKEN", "admin")
    got = req.headers.get("X-Admin-Token", "")
    return bool(expected) and got == expected


def _public_status(cfg):
    servers = []
    state = cfg.get("state", {})
    for s in cfg.get("servers", []):
        sid = str(s.get("id"))
        st = state.get(sid, {})
        servers.append({
            "id": sid,
            "name": s.get("name") or st.get("name") or sid,
            "ip": s.get("ip", st.get("ip", "-")),
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


@app.route(route="{*path}", methods=["GET", "POST", "DELETE"],
           auth_level=func.AuthLevel.ANONYMOUS)
def web(req: func.HttpRequest) -> func.HttpResponse:
    path = (req.route_params.get("path") or "").strip("/")
    method = req.method.upper()

    # --- 页面 ---
    if path in ("", "index", "status.html") and method == "GET":
        return _html(STATUS_PAGE)
    if path == "admin" and method == "GET":
        return _html(ADMIN_PAGE)

    # --- 公开 API ---
    if path == "api/status" and method == "GET":
        return _json(_public_status(load_config()))

    # --- 管理 API（需鉴权）---
    if path.startswith("api/admin"):
        if not _check_admin(req):
            return _json({"error": "unauthorized"}, 401)

        cfg = load_config()

        if path == "api/admin/config":
            if method == "GET":
                out = dict(cfg)
                # 不回传密钥
                out["provider"] = {k: v for k, v in cfg.get("provider", {}).items() if k != "api_key"}
                return _json(out)
            if method == "POST":
                body = req.get_json()
                prov = body.get("provider", {})
                for k in ("base_url", "account", "api_key"):
                    if prov.get(k):
                        cfg.setdefault("provider", {})[k] = prov[k]
                for k, v in body.get("settings", {}).items():
                    cfg.setdefault("settings", {})[k] = v
                save_config(cfg)
                return _json({"ok": True})

        if path == "api/admin/server":
            body = req.get_json()
            sid = str(body.get("id", "")).strip()
            if not sid:
                return _json({"error": "missing id"}, 400)
            servers = cfg.setdefault("servers", [])
            if method == "DELETE":
                cfg["servers"] = [s for s in servers if str(s.get("id")) != sid]
                cfg.get("state", {}).pop(sid, None)
                save_config(cfg)
                return _json({"ok": True})
            # POST 添加/更新
            existing = next((s for s in servers if str(s.get("id")) == sid), None)
            if existing:
                existing.update({"name": body.get("name") or existing.get("name"),
                                 "ip": body.get("ip") or existing.get("ip"),
                                 "enabled": body.get("enabled", existing.get("enabled", True))})
            else:
                servers.append({"id": sid, "name": body.get("name") or sid,
                                "ip": body.get("ip", "-"), "enabled": True})
            save_config(cfg)
            return _json({"ok": True})

        if path == "api/admin/server/toggle" and method == "POST":
            sid = str(req.get_json().get("id", "")).strip()
            for s in cfg.get("servers", []):
                if str(s.get("id")) == sid:
                    s["enabled"] = not s.get("enabled", True)
            save_config(cfg)
            return _json({"ok": True})

        if path == "api/admin/discover" and method == "POST":
            engine = MonitorEngine(cfg)
            before = len(cfg.get("servers", []))
            try:
                engine.api.ensure_login()
                for h in engine.api.list_hosts():
                    hid = str(h.get("id", "")).strip()
                    if hid and not any(str(s.get("id")) == hid for s in cfg["servers"]):
                        cfg["servers"].append({
                            "id": hid,
                            "name": h.get("name") or h.get("product_name") or hid,
                            "ip": h.get("ip", "-"), "enabled": True,
                        })
            except Exception as e:
                return _json({"error": str(e)}, 500)
            save_config(cfg)
            return _json({"ok": True, "added": len(cfg["servers"]) - before})

        if path == "api/admin/run" and method == "POST":
            try:
                summary = _run_monitor()
            except Exception as e:
                logging.exception("手动检测失败")
                return _json({"error": str(e)}, 500)
            return _json({"ok": True, "summary": summary})

    return _json({"error": "not found", "path": path}, 404)
