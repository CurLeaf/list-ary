"""
Listary 工具集 — 全局配置
所有常量和用户设置集中管理，各模块 from config import XXX
"""

import json
import os
import socket

from utils import get_data_dir

# ─── 默认常量 ───
PORT = 9000
STUCK_TIMEOUT_MINUTES = 5
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 700
SERVER_READY_TIMEOUT = 6  # 秒
SESSION_EXPIRE_DAYS = 7
SSH_PING_INTERVAL = 60  # 秒
SSH_PING_TIMEOUT = 1  # 秒


def _settings_path() -> str:
    return os.path.join(get_data_dir(), "settings.json")


def load_settings() -> dict:
    p = _settings_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_settings(settings: dict):
    p = _settings_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def get_port() -> int:
    return load_settings().get("port", PORT)


def get_stuck_timeout() -> int:
    return load_settings().get("stuck_timeout", STUCK_TIMEOUT_MINUTES)


def get_session_expire_days() -> int:
    return load_settings().get("session_expire_days", SESSION_EXPIRE_DAYS)


def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def find_free_port(start: int = PORT, max_tries: int = 6) -> int:
    for offset in range(max_tries):
        p = start + offset
        if is_port_free(p):
            return p
    raise RuntimeError(f"端口 {start}-{start + max_tries - 1} 全部被占用")
