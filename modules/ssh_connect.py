import os
import subprocess
import sys
from rich.console import Console
from rich.table import Table

from modules.ssh_manager import load_servers

console = Console()


def connect(server: dict) -> None:
    """通过 Windows Terminal 新标签连接 SSH"""
    cmd = ["wt.exe", "new-tab", "--title", server["name"], "ssh", "-t"]

    if server.get("port") and server["port"] != 22:
        cmd.extend(["-p", str(server["port"])])

    if server.get("key"):
        key_val = server["key"]
        if "PRIVATE KEY" in key_val:
            from modules.ssh_manager import save_key_content_to_file, load_servers, save_servers
            key_path = save_key_content_to_file(server.get("name", "default"), key_val)
            servers = load_servers()
            for s in servers:
                if s.get("name") == server["name"] and "PRIVATE KEY" in s.get("key", ""):
                    s["key"] = key_path
            save_servers(servers)
        else:
            key_path = os.path.expanduser(key_val)
        cmd.extend(["-i", key_path])

    remote_cmd = ""
    if server.get("path"):
        remote_cmd = f"cd {server['path']} && exec $SHELL"

    cmd.append(server["host"])
    if remote_cmd:
        cmd.append(remote_cmd)

    try:
        subprocess.Popen(cmd)
        console.print(f"[green]✓ 已在 Windows Terminal 新标签中连接: {server['name']}[/green]")
    except FileNotFoundError:
        console.print("[red]未找到 wt.exe，请确认已安装 Windows Terminal。[/red]")
        fallback_cmd = ["ssh", "-t"]
        if server.get("port") and server["port"] != 22:
            fallback_cmd.extend(["-p", str(server["port"])])
        if server.get("key"):
            fallback_cmd.extend(["-i", os.path.expanduser(server["key"])])
        fallback_cmd.append(server["host"])
        if remote_cmd:
            fallback_cmd.append(remote_cmd)
        console.print(f"[yellow]回退使用直接 SSH: {' '.join(fallback_cmd)}[/yellow]")
        subprocess.Popen(fallback_cmd)


def run(args: list[str]) -> None:
    """从 hub.py 调用的入口"""
    servers = load_servers()
    if not servers:
        return

    if args:
        try:
            idx = int(args[0]) - 1
            if 0 <= idx < len(servers):
                connect(servers[idx])
                return
            else:
                console.print(f"[red]无效的序号: {args[0]}，有效范围 1-{len(servers)}[/red]")
        except ValueError:
            console.print(f"[red]无效的序号: {args[0]}[/red]")
        return

    table = Table(title="SSH 服务器列表")
    table.add_column("序号", style="cyan", width=4)
    table.add_column("名称", style="green")
    table.add_column("主机", style="yellow")
    table.add_column("目标路径", style="dim")
    for i, srv in enumerate(servers, 1):
        table.add_row(str(i), srv["name"], srv["host"], srv.get("path", ""))
    console.print(table)

    choice = console.input("[bold cyan]请输入序号: [/bold cyan]")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(servers):
            connect(servers[idx])
        else:
            console.print("[red]无效的序号。[/red]")
    except ValueError:
        console.print("[red]无效的输入。[/red]")


if __name__ == "__main__":
    run(sys.argv[1:])
