#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
配置与运行状态持久化。

- 在 Azure（设置了 AzureWebJobsStorage 且安装了 azure-storage-blob）时，
  使用 Blob 存储保存单个 JSON（容器 zjmf-monitor / blob config.json）。
- 本地运行时回退到当前目录的 monitor_data.json 文件。

配置初始值来源（首次运行时）：环境变量 provider/settings，或本地默认值。
"""

import os
import json
import logging
import threading
from typing import Any, Dict

_LOCAL_FILE = os.environ.get("MONITOR_DATA_FILE", "monitor_data.json")
_CONTAINER = "zjmf-monitor"
_BLOB = "config.json"
_lock = threading.Lock()


def _default_config() -> Dict[str, Any]:
    return {
        "provider": {
            "base_url": os.environ.get("ZJMF_BASE_URL", "https://www.heyunidc.cn"),
            "account": os.environ.get("ZJMF_ACCOUNT", ""),
            "api_key": os.environ.get("ZJMF_API_KEY", ""),
        },
        "settings": {
            "suspect_threshold": int(os.environ.get("ZJMF_SUSPECT_THRESHOLD", "3")),
            "reboot_cooldown": int(os.environ.get("ZJMF_REBOOT_COOLDOWN", "600")),
            "recover_timeout": int(os.environ.get("ZJMF_RECOVER_TIMEOUT", "300")),
            "reboot_limit": int(os.environ.get("ZJMF_REBOOT_LIMIT", "5")),
            "reboot_limit_window": os.environ.get("ZJMF_REBOOT_LIMIT_WINDOW", "hour"),
            "action": os.environ.get("ZJMF_ACTION", "on"),  # on / hard_reboot
            "dry_run": os.environ.get("ZJMF_DRY_RUN", "false").lower() == "true",
            "webhook_url": os.environ.get("ZJMF_WEBHOOK_URL", ""),
            "webhook_type": os.environ.get("ZJMF_WEBHOOK_TYPE", "custom"),
        },
        "servers": [],
        "state": {},
        "events": [],
    }


def _blob_client():
    """返回 (BlobClient) 或 None（不可用时）。"""
    conn = os.environ.get("AzureWebJobsStorage") or os.environ.get("STORAGE_CONNECTION_STRING")
    if not conn or conn == "UseDevelopmentStorage=true" and not os.environ.get("USE_AZURITE"):
        # 明确未配置真实存储时使用本地文件
        if not conn:
            return None
    try:
        from azure.storage.blob import BlobServiceClient
    except Exception:
        logging.debug("azure-storage-blob 未安装，使用本地文件存储")
        return None
    try:
        svc = BlobServiceClient.from_connection_string(conn)
        container = svc.get_container_client(_CONTAINER)
        try:
            container.create_container()
        except Exception:
            pass  # 已存在
        return container.get_blob_client(_BLOB)
    except Exception as e:
        logging.warning("初始化 Blob 存储失败，回退本地文件：%s", e)
        return None


def load_config() -> Dict[str, Any]:
    with _lock:
        blob = _blob_client()
        if blob is not None:
            try:
                if blob.exists():
                    raw = blob.download_blob().readall()
                    cfg = json.loads(raw.decode("utf-8"))
                    return _merge_defaults(cfg)
            except Exception as e:
                logging.warning("读取 Blob 配置失败：%s", e)
            cfg = _default_config()
            _save_blob(blob, cfg)
            return cfg

        # 本地文件
        if os.path.exists(_LOCAL_FILE):
            try:
                with open(_LOCAL_FILE, "r", encoding="utf-8") as f:
                    return _merge_defaults(json.load(f))
            except Exception as e:
                logging.warning("读取本地配置失败，使用默认：%s", e)
        cfg = _default_config()
        _save_local(cfg)
        return cfg


def save_config(cfg: Dict[str, Any]):
    with _lock:
        blob = _blob_client()
        if blob is not None:
            _save_blob(blob, cfg)
        else:
            _save_local(cfg)


def _save_blob(blob, cfg: Dict[str, Any]):
    try:
        blob.upload_blob(json.dumps(cfg, ensure_ascii=False, indent=2).encode("utf-8"),
                         overwrite=True)
    except Exception as e:
        logging.error("写入 Blob 配置失败：%s", e)


def _save_local(cfg: Dict[str, Any]):
    try:
        with open(_LOCAL_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error("写入本地配置失败：%s", e)


def _merge_defaults(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """确保关键字段存在，并用环境变量补齐空的凭据。"""
    base = _default_config()
    cfg.setdefault("provider", {})
    for k, v in base["provider"].items():
        if not cfg["provider"].get(k):
            cfg["provider"][k] = v
    cfg.setdefault("settings", {})
    for k, v in base["settings"].items():
        cfg["settings"].setdefault(k, v)
    cfg.setdefault("servers", [])
    cfg.setdefault("state", {})
    cfg.setdefault("events", [])
    return cfg
