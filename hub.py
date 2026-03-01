#!/usr/bin/env python3
"""
Listary 个人自动化工具集 — 主入口
默认启动 GUI 面板（pywebview 原生窗口），也支持 CLI 快捷命令。

用法：
  python hub.py                  # 启动 GUI 面板
  python hub.py kill 3000        # CLI: 直接杀端口
  python hub.py ssh 1            # CLI: 直接连服务器
"""

import os
import sys
import threading

# Windows 控制台强制 UTF-8 编码
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 确保项目根目录在 sys.path 中
if getattr(sys, "frozen", False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


# ─── GUI 面板模式 ───

_actual_port = 9000  # 运行时实际端口，供 launch_gui 读取

def start_server(port: int):
    """在后台线程启动 FastAPI 服务"""
    try:
        import uvicorn
        from dashboard.server import app
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            log_config=None,
        )
    except Exception as e:
        import traceback
        from utils import log
        log.error(f"FastAPI 服务启动失败: {e}\n{traceback.format_exc()}")
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, f"服务启动失败:\n{e}", "Listary 错误", 0x10)


def launch_gui():
    """启动 pywebview 原生窗口"""
    global _actual_port
    from config import find_free_port, get_port, WINDOW_WIDTH, WINDOW_HEIGHT, SERVER_READY_TIMEOUT

    from utils import log

    # 检测可用端口
    try:
        _actual_port = find_free_port(get_port())
        if _actual_port != get_port():
            log.info(f"端口 {get_port()} 被占用，使用 {_actual_port}")
    except RuntimeError:
        log.error(f"端口 {get_port()}-{get_port()+5} 全部被占用")
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, f"端口 {get_port()}-{get_port()+5} 全部被占用，无法启动服务。", "Listary 错误", 0x10)
        return

    # 启动后台服务
    server_thread = threading.Thread(target=start_server, args=(_actual_port,), daemon=True)
    server_thread.start()

    # 等待服务就绪
    import time
    import urllib.request
    url = f"http://127.0.0.1:{_actual_port}/panel"
    max_attempts = int(SERVER_READY_TIMEOUT / 0.2)
    server_ok = False
    for _ in range(max_attempts):
        try:
            urllib.request.urlopen(url, timeout=1)
            server_ok = True
            break
        except Exception:
            time.sleep(0.2)
    if not server_ok:
        log.error(f"FastAPI 服务未就绪，{SERVER_READY_TIMEOUT}s 超时")
        # 仍然打开窗口，日志里会有详细错误

    # 启动 pywebview 原生窗口 + 系统托盘
    import webview

    window = webview.create_window(
        "Listary 工具集",
        url,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=(800, 500),
    )

    def _start_tray(win):
        """系统托盘：关闭窗口时隐藏到托盘"""
        try:
            import pystray
            from PIL import Image

            # 加载图标
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico")
            if getattr(sys, "frozen", False):
                icon_path = os.path.join(sys._MEIPASS, "assets", "icon.ico")
            try:
                img = Image.open(icon_path)
            except Exception:
                from PIL import ImageDraw
                img = Image.new("RGB", (16, 16), "#0c0c0c")
                ImageDraw.Draw(img).rectangle([3, 3, 12, 12], fill="#00ff9f")

            def on_show(icon, item):
                win.show()

            def on_quit(icon, item):
                icon.stop()
                win.destroy()

            icon = pystray.Icon(
                "listary",
                img,
                "Listary 工具集",
                menu=pystray.Menu(
                    pystray.MenuItem("显示面板", on_show, default=True),
                    pystray.MenuItem("退出", on_quit),
                ),
            )

            # pywebview 5.x+ 才有 events.closing
            try:
                def on_closing():
                    win.hide()
                    return False
                win.events.closing += on_closing
            except (AttributeError, TypeError):
                pass

            icon.run()
        except Exception as ex:
            log.warning(f"托盘功能跳过: {ex}")

    tray_thread = threading.Thread(target=_start_tray, args=(window,), daemon=True)
    tray_thread.start()
    webview.start()


# ─── CLI 命令模式（保留向后兼容） ───

def cli_kill(args):
    from modules.kill_port import run
    run(args)

def cli_ssh(args):
    from modules.ssh_connect import run
    run(args)

def cli_sshcfg(args):
    from modules.ssh_manager import run
    run(args)

def cli_setup(args):
    from modules.windsurf_setup import run
    run(args)

def cli_open(args):
    from modules.windsurf_open import run
    run(args)

def cli_clean(args):
    import httpx
    from config import get_port
    try:
        resp = httpx.delete(f"http://localhost:{get_port()}/api/sessions", timeout=5)
        if resp.status_code == 200:
            print(f"已清理 {resp.json().get('cleaned', 0)} 个会话")
    except Exception:
        pass
    from utils import get_data_dir
    db_path = os.path.join(get_data_dir(), "dashboard.db")
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"已删除: {db_path}")
    print("清理完成")

CLI_COMMANDS = {
    "kill": cli_kill,
    "ssh": cli_ssh,
    "sshcfg": cli_sshcfg,
    "setup": cli_setup,
    "open": cli_open,
    "clean": cli_clean,
}


def main():
    args = sys.argv[1:]

    if args:
        cmd = args[0].lower()
        if cmd in CLI_COMMANDS:
            CLI_COMMANDS[cmd](args[1:])
            return

    # 默认：启动 GUI 面板
    launch_gui()


if __name__ == "__main__":
    main()
