import sys
import psutil
from rich.console import Console
from rich.table import Table

console = Console()


def kill_port(port: int) -> None:
    """查找并杀死占用指定端口的进程"""
    try:
        connections = psutil.net_connections()
    except psutil.AccessDenied:
        console.print("[red]需要管理员权限才能查看网络连接，请以管理员身份运行。[/red]")
        return

    found = []
    for conn in connections:
        if conn.laddr and conn.laddr.port == port and conn.status == "LISTEN":
            if conn.pid and conn.pid not in [item["pid"] for item in found]:
                try:
                    proc = psutil.Process(conn.pid)
                    found.append({
                        "pid": conn.pid,
                        "name": proc.name(),
                        "exe": proc.exe() if proc.exe() else "N/A",
                        "process": proc,
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    found.append({
                        "pid": conn.pid,
                        "name": "unknown",
                        "exe": "N/A",
                        "process": None,
                    })

    if not found:
        console.print(f"[yellow]端口 {port} 没有进程在监听。[/yellow]")
        return

    table = Table(title=f"端口 {port} 监听进程")
    table.add_column("PID", style="cyan")
    table.add_column("进程名", style="green")
    table.add_column("路径", style="dim")
    for item in found:
        table.add_row(str(item["pid"]), item["name"], item["exe"])
    console.print(table)

    for item in found:
        pid = item["pid"]
        proc = item["process"]
        if proc is None:
            try:
                proc = psutil.Process(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                console.print(f"[red]PID {pid} 无法访问，跳过。[/red]")
                continue
        try:
            proc.terminate()
            proc.wait(timeout=3)
            console.print(f"[green]✓ 已终止 PID {pid} ({item['name']})[/green]")
        except psutil.TimeoutExpired:
            try:
                proc.kill()
                console.print(f"[green]✓ 已强制杀死 PID {pid} ({item['name']})[/green]")
            except Exception as e:
                console.print(f"[red]✗ 强制杀死 PID {pid} 失败: {e}[/red]")
        except psutil.AccessDenied:
            console.print(f"[red]✗ PID {pid} 权限不足，请以管理员身份运行。[/red]")
        except Exception as e:
            console.print(f"[red]✗ 终止 PID {pid} 失败: {e}[/red]")


def run(args: list[str]) -> None:
    """从 hub.py 调用的入口"""
    if not args:
        port_str = console.input("[bold cyan]请输入端口号: [/bold cyan]")
    else:
        port_str = args[0]

    try:
        port = int(port_str)
    except ValueError:
        console.print(f"[red]无效的端口号: {port_str}[/red]")
        return

    kill_port(port)


if __name__ == "__main__":
    run(sys.argv[1:])
