# -*- coding: utf-8 -*-
"""
配置与运行状态的持久化。

配置就是一个 JSON。存哪儿取决于环境，自动挑一个能用的后端：

  1. 显式指定文件      —— 设了 MONITOR_DATA_FILE，直接用本地文件（本地运行走这条）。
  2. Azure Blob 存储   —— 装了 azure-storage-blob 且有连接串（AzureWebJobsStorage
                          或 MONITOR_BLOB_CONNECTION）。这是真正 Serverless 的正道：
                          实例随时被回收、文件系统随时清空也不丢状态。
  3. 本地文件回退      —— 上面都不满足，就写 $HOME/data 或当前目录。

首次运行的默认值来自环境变量。所有读写都过一把进程内锁，够用了。
"""

import os
import json
import logging
import threading

log = logging.getLogger("state")
_lock = threading.RLock()


def _defaults():
    env = os.environ.get
    return {
        "provider": {
            "base_url": env("ZJMF_BASE_URL", "https://www.heyunidc.cn"),
            "account": env("ZJMF_ACCOUNT", ""),
            "api_key": env("ZJMF_API_KEY", ""),
        },
        "settings": {
            "suspect_threshold": int(env("ZJMF_SUSPECT_THRESHOLD", "3")),
            "reboot_cooldown": int(env("ZJMF_REBOOT_COOLDOWN", "600")),
            "recover_timeout": int(env("ZJMF_RECOVER_TIMEOUT", "300")),
            "reboot_limit": int(env("ZJMF_REBOOT_LIMIT", "5")),
            "reboot_limit_window": env("ZJMF_REBOOT_LIMIT_WINDOW", "hour"),
            "action": env("ZJMF_ACTION", "on"),
            "dry_run": env("ZJMF_DRY_RUN", "false").lower() == "true",
            "webhook_url": env("ZJMF_WEBHOOK_URL", ""),
            "webhook_type": env("ZJMF_WEBHOOK_TYPE", "custom"),
        },
        "servers": [],
        "state": {},
        "events": [],
    }


def _merge_defaults(cfg):
    """补齐缺失字段，并用环境变量填上空着的凭据（方便只在云端配环境变量）。"""
    base = _defaults()
    cfg.setdefault("provider", {})
    for k, v in base["provider"].items():
        if not cfg["provider"].get(k):
            cfg["provider"][k] = v
    cfg.setdefault("settings", {})
    for k, v in base["settings"].items():
        cfg["settings"].setdefault(k, v)
    for k in ("servers", "events"):
        cfg.setdefault(k, [])
    cfg.setdefault("state", {})
    return cfg


class _FileStore:
    def __init__(self, path):
        self.path = path

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log.warning("读取配置失败，用默认值: %s", e)
        return None

    def save(self, cfg):
        # 先写临时文件再替换，避免写一半崩了留个坏文件
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)


class _BlobStore:
    def __init__(self, conn, container, blob):
        from azure.storage.blob import BlobServiceClient  # 延迟导入，缺包时才报错
        svc = BlobServiceClient.from_connection_string(conn)
        try:
            svc.create_container(container)
        except Exception:
            pass  # 已存在
        self.client = svc.get_blob_client(container, blob)

    def load(self):
        from azure.core.exceptions import ResourceNotFoundError
        try:
            raw = self.client.download_blob().readall()
        except ResourceNotFoundError:
            return None
        except Exception as e:
            log.warning("读取 Blob 状态失败，用默认值: %s", e)
            return None
        try:
            return json.loads(raw)
        except Exception as e:
            log.warning("Blob 内容不是合法 JSON: %s", e)
            return None

    def save(self, cfg):
        self.client.upload_blob(
            json.dumps(cfg, ensure_ascii=False, indent=2).encode("utf-8"),
            overwrite=True,
        )


def _build_store():
    # 1. 显式文件优先
    explicit = os.environ.get("MONITOR_DATA_FILE")
    if explicit:
        return _FileStore(explicit)

    # 2. 有连接串就试 Blob（Serverless 首选）
    conn = os.environ.get("MONITOR_BLOB_CONNECTION") or os.environ.get("AzureWebJobsStorage")
    if conn and "UseDevelopmentStorage" not in conn:
        try:
            store = _BlobStore(
                conn,
                os.environ.get("MONITOR_BLOB_CONTAINER", "monitor"),
                os.environ.get("MONITOR_BLOB_NAME", "monitor_data.json"),
            )
            log.info("状态持久化: Azure Blob")
            return store
        except Exception as e:
            log.warning("Blob 存储不可用（%s），回退到本地文件", e)

    # 3. 本地文件回退
    home = os.environ.get("HOME")
    if home and os.path.isdir(home):
        data_dir = os.path.join(home, "data")
        try:
            os.makedirs(data_dir, exist_ok=True)
            return _FileStore(os.path.join(data_dir, "monitor_data.json"))
        except Exception:
            pass
    return _FileStore("monitor_data.json")


_store = None


def _get_store():
    global _store
    if _store is None:
        _store = _build_store()
    return _store


def load_config():
    with _lock:
        cfg = _get_store().load()
        if cfg is None:
            cfg = _defaults()
            _get_store().save(cfg)
            return cfg
        return _merge_defaults(cfg)


def save_config(cfg):
    with _lock:
        try:
            _get_store().save(cfg)
        except Exception as e:
            log.error("保存配置失败: %s", e)
