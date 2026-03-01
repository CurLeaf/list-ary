"""
开机自启管理 — 通过 Windows 注册表实现
注册表路径: HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
"""

import os
import sys

APP_NAME = "ListaryTools"

# 注册表路径
_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _get_exe_command() -> str:
    """获取启动命令（兼容 EXE 和源码模式）"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # 源码模式：用 pythonw 运行 hub.py（无控制台窗口）
    python = sys.executable
    pythonw = python.replace("python.exe", "pythonw.exe")
    if os.path.exists(pythonw):
        python = pythonw
    hub_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hub.py")
    return f'"{python}" "{hub_path}"'


def is_autostart_enabled() -> bool:
    """检查是否已设置开机自启"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, APP_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def enable_autostart() -> bool:
    """启用开机自启"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE)
        cmd = _get_exe_command()
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def disable_autostart() -> bool:
    """禁用开机自启"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False
