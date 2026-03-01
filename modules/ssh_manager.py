"""
SSH 服务器配置管理 — 增删改查
"""

import json
import os
import sys
import time

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from utils import get_config_path, get_data_dir

console = Console()


def _get_servers_read_path() -> str:
    """读取路径：优先 data_dir，回退 _MEIPASS"""
    return get_config_path("servers.json")


def _get_servers_write_path() -> str:
    """写入路径：始终写入 data_dir（EXE 模式下 _MEIPASS 只读）"""
    return os.path.join(get_data_dir(), "servers.json")


# ─── 服务器列表缓存（10秒 TTL） ───
_servers_cache: dict = {"data": None, "ts": 0.0, "ttl": 10.0}


def load_servers() -> list[dict]:
    now = time.time()
    if _servers_cache["data"] is not None and now - _servers_cache["ts"] < _servers_cache["ttl"]:
        return _servers_cache["data"]
    path = _get_servers_read_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            result = json.load(f)
            _servers_cache["data"] = result
            _servers_cache["ts"] = now
            return result
    return []


def save_servers(servers: list[dict]):
    path = _get_servers_write_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(servers, f, ensure_ascii=False, indent=2)
    _servers_cache["data"] = servers
    _servers_cache["ts"] = time.time()


def save_key_content_to_file(server_name: str, key_content: str) -> str:
    """将 SSH 密钥内容保存为文件，返回文件路径（统一入口，消除重复代码）"""
    import re
    safe_name = re.sub(r'[^\w\-]', '_', server_name).strip('_') or 'default'
    keys_dir = os.path.join(get_data_dir(), "ssh_keys")
    os.makedirs(keys_dir, exist_ok=True)
    key_path = os.path.join(keys_dir, f"{safe_name}_key")
    content = key_content if key_content.endswith('\n') else key_content + '\n'
    with open(key_path, "w", encoding="utf-8", newline='\n') as f:
        f.write(content)
    try:
        os.chmod(key_path, 0o600)
    except Exception:
        pass
    return key_path


def show_servers(servers: list[dict]):
    if not servers:
        console.print("[yellow]暂无服务器配置。[/yellow]")
        return
    table = Table(title="SSH 服务器配置")
    table.add_column("序号", style="cyan", width=4)
    table.add_column("名称", style="green")
    table.add_column("主机", style="yellow")
    table.add_column("端口", width=6)
    table.add_column("路径", style="dim")
    table.add_column("密钥", style="dim")
    for i, s in enumerate(servers, 1):
        table.add_row(
            str(i), s["name"], s["host"],
            str(s.get("port", 22)),
            s.get("path", ""),
            s.get("key", "") or "无",
        )
    console.print(table)


def add_server():
    console.print("\n[bold]添加新服务器[/bold]")
    name = Prompt.ask("[cyan]名称[/cyan]（如：生产服务器 - 项目A）")
    host = Prompt.ask("[cyan]主机[/cyan]（如：user@192.168.1.100）")
    port = Prompt.ask("[cyan]端口[/cyan]", default="22")
    path = Prompt.ask("[cyan]远程路径[/cyan]（如：/var/www/project）", default="")
    key = Prompt.ask("[cyan]SSH 密钥路径[/cyan]（如：~/.ssh/id_rsa，留空则用默认）", default="")

    server = {
        "name": name,
        "host": host,
        "port": int(port),
        "path": path,
        "key": key,
    }

    servers = load_servers()
    servers.append(server)
    save_servers(servers)
    console.print(f"[green]✓ 已添加服务器: {name}[/green]")


def edit_server():
    servers = load_servers()
    show_servers(servers)
    if not servers:
        return

    choice = Prompt.ask("[cyan]输入要编辑的序号[/cyan]")
    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(servers)):
            console.print("[red]无效序号。[/red]")
            return
    except ValueError:
        console.print("[red]无效输入。[/red]")
        return

    s = servers[idx]
    console.print(f"\n[bold]编辑: {s['name']}[/bold]（直接回车保持原值）")
    s["name"] = Prompt.ask("[cyan]名称[/cyan]", default=s["name"])
    s["host"] = Prompt.ask("[cyan]主机[/cyan]", default=s["host"])
    s["port"] = int(Prompt.ask("[cyan]端口[/cyan]", default=str(s.get("port", 22))))
    s["path"] = Prompt.ask("[cyan]远程路径[/cyan]", default=s.get("path", ""))
    s["key"] = Prompt.ask("[cyan]SSH 密钥[/cyan]", default=s.get("key", ""))

    save_servers(servers)
    console.print(f"[green]✓ 已更新服务器: {s['name']}[/green]")


def delete_server():
    servers = load_servers()
    show_servers(servers)
    if not servers:
        return

    choice = Prompt.ask("[cyan]输入要删除的序号[/cyan]")
    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(servers)):
            console.print("[red]无效序号。[/red]")
            return
    except ValueError:
        console.print("[red]无效输入。[/red]")
        return

    removed = servers.pop(idx)
    save_servers(servers)
    console.print(f"[green]✓ 已删除服务器: {removed['name']}[/green]")


def run(args: list[str]) -> None:
    """从 hub.py 调用的入口"""
    if args:
        sub = args[0].lower()
        if sub == "add":
            add_server()
            return
        elif sub == "edit":
            edit_server()
            return
        elif sub == "del":
            delete_server()
            return

    # 交互菜单
    servers = load_servers()
    show_servers(servers)

    console.print("\n[bold cyan]操作:[/bold cyan]")
    console.print("  [1] 添加服务器")
    console.print("  [2] 编辑服务器")
    console.print("  [3] 删除服务器")
    console.print("  [q] 返回")

    choice = Prompt.ask("[bold cyan]选择[/bold cyan]")
    match choice.strip():
        case "1":
            add_server()
        case "2":
            edit_server()
        case "3":
            delete_server()
        case _:
            return


if __name__ == "__main__":
    run(sys.argv[1:])
