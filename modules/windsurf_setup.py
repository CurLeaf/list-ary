"""
Windsurf 项目配置 — 一键注入 workflow 规则 + 上报脚本到目标项目
"""

import json
import os
import shutil
import sys

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from utils import get_resource_dir, get_data_dir

console = Console()

TASK_DONE_WORKFLOW = """\
---
description: 任务完成后上报看板并等待指令
---
1. 执行上报脚本（previous_request 自动从本地历史读取，无需传入）：
// turbo
   python .windsurf/report.py --task "{task}" --status "{status}" --questions "{questions}"
2. 脚本先保存本地 JSON，再提交到看板，然后阻塞等待用户回复
3. 收到回复后，回复写入本地 JSON，输出到 stdout，按回复内容继续执行
"""

CHECKPOINT_WORKFLOW = """\
---
description: 执行中遇到需要确认的问题时调用
---
1. 执行上报脚本：
// turbo
   python .windsurf/report.py --task "{当前任务描述}" --status need_confirm --questions "{需要确认的问题}"
2. 阻塞等待用户在看板回复
3. 收到回复后按回复内容继续当前任务
"""


def get_projects_config_path() -> str:
    """获取已配置项目列表的路径"""
    return os.path.join(get_data_dir(), "projects.json")


def load_projects() -> list[dict]:
    """加载已配置的项目列表"""
    path = get_projects_config_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_projects(projects: list[dict]):
    """保存项目列表"""
    path = get_projects_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)


def inject_to_project(project_path: str, project_name: str, dashboard_url: str = "http://localhost:9000"):
    """向目标项目注入 .windsurf/ 配置"""
    windsurf_dir = os.path.join(project_path, ".windsurf")
    workflows_dir = os.path.join(windsurf_dir, "workflows")
    reports_dir = os.path.join(windsurf_dir, "reports")

    os.makedirs(workflows_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)

    # 1. 写入 workflow 规则
    task_done_path = os.path.join(workflows_dir, "task-done.md")
    with open(task_done_path, "w", encoding="utf-8") as f:
        f.write(TASK_DONE_WORKFLOW)
    console.print(f"  [green]✓[/green] {task_done_path}")

    checkpoint_path = os.path.join(workflows_dir, "checkpoint.md")
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        f.write(CHECKPOINT_WORKFLOW)
    console.print(f"  [green]✓[/green] {checkpoint_path}")

    # 2. 拷贝上报脚本
    report_src = os.path.join(get_resource_dir(), "report", "report.py")
    report_dst = os.path.join(windsurf_dir, "report.py")
    if os.path.exists(report_src):
        shutil.copy2(report_src, report_dst)
    else:
        console.print(f"  [yellow]⚠ 上报脚本模板不存在: {report_src}，跳过拷贝[/yellow]")
    console.print(f"  [green]✓[/green] {report_dst}")

    # 3. 生成配置文件
    config_path = os.path.join(windsurf_dir, "report_config.json")
    config = {
        "project_name": project_name,
        "dashboard_url": dashboard_url,
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    console.print(f"  [green]✓[/green] {config_path}")

    # 4. 记录到项目列表
    projects = load_projects()
    existing = [p for p in projects if p["path"] == project_path]
    if existing:
        existing[0]["name"] = project_name
    else:
        projects.append({"name": project_name, "path": project_path})
    save_projects(projects)


def setup_project(project_path: str | None = None, project_name: str | None = None):
    """交互式配置项目"""
    if not project_path:
        project_path = Prompt.ask("[bold cyan]项目路径[/bold cyan]").strip().strip('"')

    if not os.path.isdir(project_path):
        console.print(f"[red]目录不存在: {project_path}[/red]")
        return

    project_path = os.path.abspath(project_path)

    if not project_name:
        default_name = os.path.basename(project_path)
        project_name = Prompt.ask("[bold cyan]项目名称[/bold cyan]", default=default_name)

    dashboard_url = Prompt.ask("[bold cyan]看板地址[/bold cyan]", default="http://localhost:9000")

    console.print(f"\n[bold]注入 Windsurf 配置到: {project_path}[/bold]")
    inject_to_project(project_path, project_name, dashboard_url)
    console.print(f"\n[green]✓ 项目 [{project_name}] 配置完成！[/green]")
    console.print(f"[dim]Windsurf 中可使用 /task-done 和 /checkpoint 触发上报[/dim]")


def list_projects():
    """列出已配置的项目"""
    projects = load_projects()
    if not projects:
        console.print("[yellow]暂无已配置项目。使用 'do setup' 添加项目。[/yellow]")
        return projects

    table = Table(title="已配置 Windsurf 项目")
    table.add_column("序号", style="cyan", width=4)
    table.add_column("项目名", style="green")
    table.add_column("路径", style="dim")
    table.add_column("状态", width=6)
    for i, p in enumerate(projects, 1):
        ws_dir = os.path.join(p["path"], ".windsurf")
        status = "[green]✓[/green]" if os.path.isdir(ws_dir) else "[red]✗[/red]"
        table.add_row(str(i), p["name"], p["path"], status)
    console.print(table)
    return projects


def run(args: list[str]) -> None:
    """从 hub.py 调用的入口"""
    if args:
        setup_project(project_path=args[0], project_name=args[1] if len(args) > 1 else None)
    else:
        setup_project()


if __name__ == "__main__":
    run(sys.argv[1:])
