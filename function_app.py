# -*- coding: utf-8 -*-
"""
Azure Functions 入口（Python v2 模型）。

- 定时器：按 ZJMF_CRON（默认每 10 分钟）跑一轮监控。
- HTTP：状态页 / 管理后台 / JSON API（host.json 里 routePrefix 设成了 ""）。

  GET  /                 状态页
  GET  /manage           管理后台（/admin 在 Azure 是保留字，所以用 /manage）
  GET  /api/status       公开状态
  *    /api/admin/...    管理接口，需带 X-Admin-Token 头

状态默认存到 AzureWebJobsStorage 对应的 Blob，实例被回收也不丢，才算真的 Serverless。
"""

import os
import logging

import azure.functions as func

from web_handler import dispatch, run_monitor_once

app = func.FunctionApp()

CRON = os.environ.get("ZJMF_CRON", "0 */10 * * * *")


@app.timer_trigger(schedule=CRON, arg_name="timer",
                   run_on_startup=False, use_monitor=True)
def monitor_timer(timer: func.TimerRequest):
    try:
        logging.info("定时监控: %s", run_monitor_once())
    except Exception:
        logging.exception("定时监控出错")


@app.route(route="{*path}", methods=["GET", "POST", "DELETE"],
           auth_level=func.AuthLevel.ANONYMOUS)
def web(req: func.HttpRequest) -> func.HttpResponse:
    code, mimetype, text = dispatch(
        req.method,
        req.route_params.get("path") or "",
        req.headers.get("X-Admin-Token", ""),
        req.get_body() or b"",
    )
    return func.HttpResponse(text, status_code=code, mimetype=mimetype)
