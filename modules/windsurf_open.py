"""
快速启动 IDE 打开指定项目 — 支持 Windsurf / Cursor / 可扩展
"""

import os
import subprocess
import sys

from rich.console import Console
from rich.prompt import Prompt

from modules.ide_profiles import (
    find_executable, save_executable_path, get_profile, PROFILES,
)
from modules.windsurf_setup import load_projects

console = Console()


def find_windsurf() -> str | None:
    """向后兼容：查找 Windsurf 可执行文件"""
    return find_executable("windsurf")


def save_windsurf_path(path: str):
    """向后兼容：保存 Windsurf 路径"""
    save_executable_path("windsurf", path)


def open_project(project_path: str, ide: str = "windsurf"):
    """用指定 IDE 打开项目"""
    profile = get_profile(ide)
    ide_name = profile["name"]
    exe_path = find_executable(ide)

    if not exe_path:
        console.print(f"[red]未找到 {ide_name}，请手动指定路径。[/red]")
        exe_path = Prompt.ask(f"[bold cyan]{ide_name} 可执行文件路径[/bold cyan]").strip().strip('"')
        if not os.path.exists(exe_path):
            console.print(f"[red]路径不存在: {exe_path}[/red]")
            return
        save_executable_path(ide, exe_path)

    try:
        subprocess.Popen([exe_path, project_path])
        console.print(f"[green]✓ 已启动 {ide_name} 打开: {project_path}[/green]")
    except Exception as e:
        console.print(f"[red]启动 {ide_name} 失败: {e}[/red]")


def run(args: list[str]) -> None:
    projects = load_projects()

    if args:
        try:
            idx = int(args[0]) - 1
            if 0 <= idx < len(projects):
                ide = projects[idx].get("ide", "windsurf")
                open_project(projects[idx]["path"], ide=ide)
                return
        except ValueError:
            pass
        open_project(args[0])
        return

    if not projects:
        console.print("[yellow]暂无已配置项目。使用 'do setup' 先配置项目。[/yellow]")
        path = Prompt.ask("[bold cyan]或直接输入项目路径[/bold cyan]").strip().strip('"')
        if path and os.path.isdir(path):
            open_project(path)
        return

    from rich.table import Table
    table = Table(title="选择项目打开")
    table.add_column("序号", style="cyan", width=4)
    table.add_column("项目名", style="green")
    table.add_column("IDE", style="magenta", width=10)
    table.add_column("路径", style="dim")
    for i, p in enumerate(projects, 1):
        ide = p.get("ide", "windsurf")
        ide_name = PROFILES.get(ide, {}).get("name", ide)
        table.add_row(str(i), p["name"], ide_name, p["path"])
    console.print(table)

    choice = Prompt.ask("[bold cyan]请输入序号[/bold cyan]")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(projects):
            ide = projects[idx].get("ide", "windsurf")
            open_project(projects[idx]["path"], ide=ide)
        else:
            console.print("[red]无效的序号。[/red]")
    except ValueError:
        console.print("[red]无效的输入。[/red]")


if __name__ == "__main__":
    run(sys.argv[1:])
