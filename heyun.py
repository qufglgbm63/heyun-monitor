#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
魔方财务云服务器监控 —— 本地独立运行版。

复用 monitor_core.py 中的 API 客户端与监控引擎（含 token 失效自动重新登录、
5 状态机、自动开机/重启）。适合在自己的电脑/服务器上长时间运行。

如需网页版 + Azure Functions 部署，见同目录 function_app.py 与 README.md。

使用方式：
    python heyun.py            # 持续监控
    python heyun.py --once     # 只检测一轮
"""

import os
import sys
import time
import logging

from monitor_core import MonitorEngine


# ========== 基础配置（本地运行直接改这里，或用环境变量覆盖）==========
# 提示：不要把真实账号/密钥提交到公开仓库！建议用环境变量：
#   PowerShell:  $env:ZJMF_ACCOUNT="账号"; $env:ZJMF_API_KEY="密钥"
BASE_URL = os.environ.get("ZJMF_BASE_URL", "https://www.heyunidc.cn")
ACCOUNT = os.environ.get("ZJMF_ACCOUNT", "")
API_KEY = os.environ.get("ZJMF_API_KEY", "")

# on = 关机自动开机；hard_reboot = 异常自动硬重启
ACTION = "on"

# True = 只检测不执行动作；False = 自动执行
DRY_RUN = False

# 每轮检测间隔（秒）
CHECK_INTERVAL = 600

# 连续异常多少次判定宕机
SUSPECT_THRESHOLD = 3

# 需要监控的服务器 ID 列表；留空则自动发现账户下全部服务器
SERVER_IDS: list[str] = []


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def build_config() -> dict:
    servers = [{"id": sid, "name": f"host-{sid}", "enabled": True} for sid in SERVER_IDS]
    return {
        "provider": {"base_url": BASE_URL, "account": ACCOUNT, "api_key": API_KEY},
        "settings": {
            "action": ACTION,
            "dry_run": DRY_RUN,
            "suspect_threshold": SUSPECT_THRESHOLD,
            "reboot_cooldown": 600,
            "recover_timeout": 300,
            "reboot_limit": 5,
            "reboot_limit_window": "hour",
            "webhook_url": "",
            "webhook_type": "custom",
        },
        "servers": servers,
        "state": {},
        "events": [],
    }


def main():
    once = "--once" in sys.argv
    engine = MonitorEngine(build_config())

    while True:
        try:
            summary = engine.run_once()
            logging.info("本轮完成：%s", summary)
        except KeyboardInterrupt:
            logging.info("收到退出信号，程序结束")
            break
        except Exception as e:
            logging.exception("本轮监控异常：%s", e)

        if once:
            break

        logging.info("等待 %s 秒后进入下一轮检测", CHECK_INTERVAL)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
