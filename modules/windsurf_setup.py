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

RULES_TEMPLATE = """\
## 上报规则
- 每完成一个用户请求的独立任务后，自动执行 /task-done 上报看板
- 遇到需要用户决策的问题时，执行 /checkpoint 暂停等待指令
- 遇到无法自行解决的错误或阻塞时，执行 /error-report 上报
- 新对话开始时，如果 .windsurf/session_id 文件存在，先执行 /sync-context 同步上次会话上下文
- 上报时 --task 参数用一句话概括当前完成的工作
- 收到看板回复后，严格按回复内容继续执行
"""

TASK_DONE_WORKFLOW = """\
---
description: 任务完成后自动上报看板并等待下一步指令
---
1. 总结当前完成的任务为一句话描述
2. 执行上报：
// turbo
   python .windsurf/report.py --task "<一句话任务描述>" --status completed
3. 等待看板回复，收到后按回复内容继续执行
"""

CHECKPOINT_WORKFLOW = """\
---
description: 遇到需要确认的问题时暂停等待指令
---
1. 整理当前疑问点
2. 执行上报：
// turbo
   python .windsurf/report.py --task "<当前任务描述>" --status need_confirm --questions "<疑问1|疑问2>"
3. 等待看板回复，按回复内容调整方案继续
"""

ERROR_REPORT_WORKFLOW = """\
---
description: 遇到无法解决的错误时上报看板
---
1. 整理错误信息和已尝试的方案
2. 执行上报：
// turbo
   python .windsurf/report.py --task "<错误描述及已尝试方案>" --status blocked --questions "<需要的帮助>"
3. 等待看板回复获取解决方案
"""

SYNC_CONTEXT_WORKFLOW = """\
---
description: 新会话开始时同步上次会话上下文
---
1. 读取上次会话上下文：
// turbo
   python .windsurf/report.py --sync
2. 将输出的上下文信息作为当前会话的背景知识
3. 告知用户已同步上次会话状态，询问下一步需求
"""

STATUS_WORKFLOW = """\
---
description: 查看当前会话在看板上的状态
---
1. 查询状态：
// turbo
   python .windsurf/report.py --check-status
2. 向用户展示当前会话状态
"""

HANDOFF_WORKFLOW = """\
---
description: 生成会话交接摘要供下次会话使用
---
1. 总结当前会话的所有完成工作、待办事项、关键决策
2. 执行上报：
// turbo
   python .windsurf/report.py --task "<会话总结：已完成XX，待办XX>" --status completed
3. 告知用户交接摘要已保存到看板
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

    # 1. 写入 rules 全局规则（自动 Hook）
    rules_path = os.path.join(windsurf_dir, "rules")
    with open(rules_path, "w", encoding="utf-8") as f:
        f.write(RULES_TEMPLATE)
    console.print(f"  [green]✓[/green] {rules_path}")

    # 2. 写入 workflow 模板
    workflows = {
        "task-done.md": TASK_DONE_WORKFLOW,
        "checkpoint.md": CHECKPOINT_WORKFLOW,
        "error-report.md": ERROR_REPORT_WORKFLOW,
        "sync-context.md": SYNC_CONTEXT_WORKFLOW,
        "status.md": STATUS_WORKFLOW,
        "handoff.md": HANDOFF_WORKFLOW,
    }
    for filename, content in workflows.items():
        path = os.path.join(workflows_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        console.print(f"  [green]✓[/green] {path}")

    # 3. 拷贝上报脚本
    report_src = os.path.join(get_resource_dir(), "report", "report.py")
    report_dst = os.path.join(windsurf_dir, "report.py")
    if os.path.exists(report_src):
        shutil.copy2(report_src, report_dst)
    else:
        console.print(f"  [yellow]⚠ 上报脚本模板不存在: {report_src}，跳过拷贝[/yellow]")
    console.print(f"  [green]✓[/green] {report_dst}")

    # 4. 生成配置文件
    config_path = os.path.join(windsurf_dir, "report_config.json")
    config = {
        "project_name": project_name,
        "dashboard_url": dashboard_url,
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    console.print(f"  [green]✓[/green] {config_path}")

    # 5. 记录到项目列表
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
