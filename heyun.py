# -*- coding: utf-8 -*-
"""
本地运行版：一个进程搞定后台监控 + 网页界面。

    python heyun.py          # 后台每隔 CHECK_INTERVAL 秒检测一次，同时开网页
    python heyun.py --once   # 只检测一轮就退出（方便试跑/配 crontab）

    状态页    http://localhost:8000/
    管理后台  http://localhost:8000/manage   （用下面的 ADMIN_PASSWORD 登录）

只用标准库，不需要 Azure、func 或任何 pip 包。改改下面的账号密钥就能跑。
"""

import os
import sys
import time
import logging
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# ===== 改这里 =====
BASE_URL = "https://www.heyunidc.cn"
ACCOUNT = "你的账号(手机号或邮箱)"
API_KEY = "你的API密钥"

# 想固定盯某几台就填 ID（字符串）；留空则自动发现账户下全部服务器
SERVER_IDS = []

ACTION = "on"            # on=关机自动开机 / hard_reboot=异常硬重启
DRY_RUN = False          # True=只检测不动手
CHECK_INTERVAL = 600     # 每轮间隔（秒）
SUSPECT_THRESHOLD = 3    # 连续几次异常才判宕机
WEB_PORT = 8000
ADMIN_PASSWORD = "admin"  # 管理后台密码，务必改掉
# ==================

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")

# 环境变量要在导入下面两个模块之前设好：state_store 读它们当默认值
os.environ.setdefault("ADMIN_TOKEN", ADMIN_PASSWORD)
os.environ.setdefault("MONITOR_DATA_FILE", "monitor_data.json")  # 本地固定用文件

from state_store import load_config, save_config      # noqa: E402
from web_handler import dispatch, run_monitor_once     # noqa: E402


def seed_config():
    """把本文件顶部的配置写进 monitor_data.json（凭据占位符不覆盖已有值）。"""
    cfg = load_config()
    if ACCOUNT and not ACCOUNT.startswith("你的"):
        cfg["provider"]["account"] = ACCOUNT
    if API_KEY and not API_KEY.startswith("你的"):
        cfg["provider"]["api_key"] = API_KEY
    cfg["provider"]["base_url"] = BASE_URL
    cfg["settings"].update(action=ACTION, dry_run=DRY_RUN,
                           suspect_threshold=SUSPECT_THRESHOLD)

    known = {str(s.get("id")) for s in cfg["servers"]}
    for sid in map(lambda x: str(x).strip(), SERVER_IDS):
        if sid and sid not in known:
            cfg["servers"].append({"id": sid, "name": f"host-{sid}", "enabled": True})
    save_config(cfg)


class Handler(BaseHTTPRequestHandler):
    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        code, mimetype, text = dispatch(
            self.command,
            urlparse(self.path).path,
            self.headers.get("X-Admin-Token", ""),
            self.rfile.read(length) if length else b"",
        )
        data = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{mimetype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_DELETE = _handle

    def log_message(self, *args):
        pass  # 别把每条 HTTP 访问都刷屏


def monitor_loop(once):
    while True:
        try:
            logging.info("本轮检测完成: %s", run_monitor_once())
        except Exception:
            logging.exception("本轮监控异常")
        if once:
            return
        time.sleep(CHECK_INTERVAL)


def main():
    seed_config()
    once = "--once" in sys.argv

    if once:
        monitor_loop(once=True)
        return

    threading.Thread(target=monitor_loop, args=(False,), daemon=True).start()

    server = ThreadingHTTPServer(("0.0.0.0", WEB_PORT), Handler)
    logging.info("已启动，状态页 http://localhost:%s/ ，管理后台 /manage（密码: %s）",
                 WEB_PORT, ADMIN_PASSWORD)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("退出")
        server.shutdown()


if __name__ == "__main__":
    main()
