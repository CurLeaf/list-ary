"""
工具函数 — 资源路径处理（兼容 PyInstaller EXE 和源码运行）
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def get_app_dir() -> str:
    """获取应用根目录（EXE 模式下为 EXE 所在目录，源码模式下为项目根目录）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_dir() -> str:
    """获取打包资源目录（PyInstaller _MEIPASS 或项目根目录）"""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def get_data_dir() -> str:
    """获取数据目录（用于存放 SQLite、servers.json 等可变数据）
    EXE 模式下放在 %APPDATA%/ListaryTools/ 下，避免只读目录权限问题
    源码模式下就在项目根目录
    """
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        data = os.path.join(appdata, "ListaryTools")
        os.makedirs(data, exist_ok=True)
        return data
    return get_app_dir()


def setup_logger(name: str = "listary") -> logging.Logger:
    """配置结构化日志，写到数据目录下 listary.log（2MB 滚动）"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    # 文件 handler
    log_path = os.path.join(get_data_dir(), "listary.log")
    fh = RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024, backupCount=1, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(fh)
    # 控制台 handler（仅源码模式）
    if not getattr(sys, "frozen", False):
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(ch)
    return logger


log = setup_logger()


def get_config_path(filename: str) -> str:
    """获取配置文件路径（servers.json 等）"""
    # 优先从数据目录找（用户可能修改过）
    data_path = os.path.join(get_data_dir(), filename)
    if os.path.exists(data_path):
        return data_path
    # 回退到资源目录（打包时的默认文件）
    res_path = os.path.join(get_resource_dir(), filename)
    if os.path.exists(res_path):
        return res_path
    # 都不存在，返回数据目录路径（供新建使用）
    return data_path
