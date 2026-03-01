"""
快速启动 Windsurf 打开指定项目
"""

import os
import subprocess
import sys

from rich.console import Console
from rich.prompt import Prompt

from utils import get_data_dir
from modules.windsurf_setup import load_projects

console = Console()

# Windsurf 可执行文件的常见路径
WINDSURF_PATHS = [
    r"D:\Program Files\Windsurf Next\Windsurf - Next.exe",
    r"D:\Program Files\Windsurf\Windsurf.exe",
    r"C:\Program Files\Windsurf Next\Windsurf - Next.exe",
    r"C:\Program Files\Windsurf\Windsurf.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Windsurf\Windsurf.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Windsurf Next\Windsurf - Next.exe"),
]


def find_windsurf() -> str | None:
    """自动查找 Windsurf 可执行文件"""
    # 优先读用户配置
    config_path = os.path.join(get_data_dir(), "windsurf_path.txt")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            path = f.read().strip()
            if path and os.path.exists(path):
                return path

    # 遍历常见路径
    for path in WINDSURF_PATHS:
        if os.path.exists(path):
            return path

    return None


def save_windsurf_path(path: str):
    """保存 Windsurf 路径配置"""
    config_path = os.path.join(get_data_dir(), "windsurf_path.txt")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(path)


def open_project(project_path: str):
    """用 Windsurf 打开项目"""
    ws_path = find_windsurf()
    if not ws_path:
        console.print("[red]未找到 Windsurf，请手动指定路径。[/red]")
        ws_path = Prompt.ask("[bold cyan]Windsurf 可执行文件路径[/bold cyan]").strip().strip('"')
        if not os.path.exists(ws_path):
            console.print(f"[red]路径不存在: {ws_path}[/red]")
            return
        save_windsurf_path(ws_path)

    try:
        subprocess.Popen([ws_path, project_path])
        console.print(f"[green]✓ 已启动 Windsurf 打开: {project_path}[/green]")
    except Exception as e:
        console.print(f"[red]启动 Windsurf 失败: {e}[/red]")


def run(args: list[str]) -> None:
    """从 hub.py 调用的入口"""
    projects = load_projects()

    if args:
        # 支持序号或路径
        try:
            idx = int(args[0]) - 1
            if 0 <= idx < len(projects):
                open_project(projects[idx]["path"])
                return
        except ValueError:
            pass
        # 当作路径
        open_project(args[0])
        return

    if not projects:
        console.print("[yellow]暂无已配置项目。使用 'do setup' 先配置项目。[/yellow]")
        path = Prompt.ask("[bold cyan]或直接输入项目路径[/bold cyan]").strip().strip('"')
        if path and os.path.isdir(path):
            open_project(path)
        return

    from rich.table import Table
    table = Table(title="选择项目打开 Windsurf")
    table.add_column("序号", style="cyan", width=4)
    table.add_column("项目名", style="green")
    table.add_column("路径", style="dim")
    for i, p in enumerate(projects, 1):
        table.add_row(str(i), p["name"], p["path"])
    console.print(table)

    choice = Prompt.ask("[bold cyan]请输入序号[/bold cyan]")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(projects):
            open_project(projects[idx]["path"])
        else:
            console.print("[red]无效的序号。[/red]")
    except ValueError:
        console.print("[red]无效的输入。[/red]")


if __name__ == "__main__":
    run(sys.argv[1:])
