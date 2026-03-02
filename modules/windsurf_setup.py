"""
IDE 项目配置 — 一键注入规则 + 上报脚本到目标项目
支持 Windsurf / Cursor 及其他可扩展 IDE。
"""

import json
import os
import shutil
import sys
import time

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from utils import get_resource_dir, get_data_dir
from modules.ide_profiles import (
    get_profile, get_config_dir_name, is_project_configured,
    IDE_CHOICES, PROFILES,
)

console = Console()

# ────────────────────────────────────────────
#  Windsurf 模板
# ────────────────────────────────────────────

_WS_RULES = """\
## 上报规则
- 每完成一个用户请求的独立任务后，自动执行 /task-done 上报看板
- 遇到需要用户决策的问题时，执行 /checkpoint 暂停等待指令
- 遇到无法自行解决的错误或阻塞时，执行 /error-report 上报
- 新对话开始时，如果 .windsurf/session_id 文件存在，先执行 /sync-context 同步上次会话上下文
- 上报时 --task 参数用一句话概括当前完成的工作
- 收到看板回复后，严格按回复内容继续执行
"""

_WS_WORKFLOWS: dict[str, str] = {
    "task-done.md": """\
---
description: 任务完成后自动上报看板并等待下一步指令
---
1. 总结当前完成的任务为一句话描述
2. 执行上报：
// turbo
   python .windsurf/report.py --task "<一句话任务描述>" --status completed
3. 等待看板回复，收到后按回复内容继续执行
""",
    "checkpoint.md": """\
---
description: 遇到需要确认的问题时暂停等待指令
---
1. 整理当前疑问点
2. 执行上报：
// turbo
   python .windsurf/report.py --task "<当前任务描述>" --status need_confirm --questions "<疑问1|疑问2>"
3. 等待看板回复，按回复内容调整方案继续
""",
    "error-report.md": """\
---
description: 遇到无法解决的错误时上报看板
---
1. 整理错误信息和已尝试的方案
2. 执行上报：
// turbo
   python .windsurf/report.py --task "<错误描述及已尝试方案>" --status blocked --questions "<需要的帮助>"
3. 等待看板回复获取解决方案
""",
    "sync-context.md": """\
---
description: 新会话开始时同步上次会话上下文
---
1. 读取上次会话上下文：
// turbo
   python .windsurf/report.py --sync
2. 将输出的上下文信息作为当前会话的背景知识
3. 告知用户已同步上次会话状态，询问下一步需求
""",
    "status.md": """\
---
description: 查看当前会话在看板上的状态
---
1. 查询状态：
// turbo
   python .windsurf/report.py --check-status
2. 向用户展示当前会话状态
""",
    "handoff.md": """\
---
description: 生成会话交接摘要供下次会话使用
---
1. 总结当前会话的所有完成工作、待办事项、关键决策
2. 执行上报：
// turbo
   python .windsurf/report.py --task "<会话总结：已完成XX，待办XX>" --status completed
3. 告知用户交接摘要已保存到看板
""",
}

# ────────────────────────────────────────────
#  Cursor 模板（.cursor/rules/*.mdc 格式）
# ────────────────────────────────────────────

_CURSOR_RULES: dict[str, str] = {
    "listary-protocol.mdc": """\
---
description: Listary 看板上报协议 — 自动汇报任务进度并等待指令
alwaysApply: true
---

## 上报规则

你的工作由 Listary 看板调度。请严格遵守以下协议：

### 任务完成时
每完成一个用户请求的独立任务后，**必须**执行上报：
```bash
python .cursor/report.py --task "<一句话任务描述>" --status completed
```
等待看板回复，收到后严格按回复内容继续执行。

### 需要用户决策时
遇到需要确认的问题，执行上报并暂停：
```bash
python .cursor/report.py --task "<当前任务描述>" --status need_confirm --questions "<疑问1|疑问2>"
```
等待看板回复，按回复内容调整方案继续。

### 遇到阻塞性错误时
遇到无法自行解决的错误，上报并等待：
```bash
python .cursor/report.py --task "<错误描述及已尝试方案>" --status blocked --questions "<需要的帮助>"
```

### 新会话开始时
如果 `.cursor/session_id` 文件存在，先同步上次会话上下文：
```bash
python .cursor/report.py --sync
```
将输出的上下文信息作为当前会话的背景知识。

### 关键要求
- `--task` 参数用一句话概括当前完成的工作
- 收到看板回复后，**严格按回复内容**继续执行
- 回复为 `[CANCEL]` 时停止当前任务
- 回复为 `[TIMEOUT]` 时自动继续下一步
""",
}


# ────────────────────────────────────────────
#  通用注入逻辑
# ────────────────────────────────────────────

def _inject_windsurf(config_dir: str, dashboard_url: str, project_name: str):
    """Windsurf: 写入 rules + workflows/"""
    workflows_dir = os.path.join(config_dir, "workflows")
    os.makedirs(workflows_dir, exist_ok=True)

    rules_path = os.path.join(config_dir, "rules")
    with open(rules_path, "w", encoding="utf-8") as f:
        f.write(_WS_RULES)
    console.print(f"  [green]✓[/green] {rules_path}")

    for filename, content in _WS_WORKFLOWS.items():
        path = os.path.join(workflows_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        console.print(f"  [green]✓[/green] {path}")


def _inject_cursor(config_dir: str, dashboard_url: str, project_name: str):
    """Cursor: 写入 .cursor/rules/*.mdc"""
    rules_dir = os.path.join(config_dir, "rules")
    os.makedirs(rules_dir, exist_ok=True)

    for filename, content in _CURSOR_RULES.items():
        path = os.path.join(rules_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        console.print(f"  [green]✓[/green] {path}")


_IDE_INJECTORS = {
    "windsurf": _inject_windsurf,
    "cursor": _inject_cursor,
}


def inject_to_project(
    project_path: str,
    project_name: str,
    dashboard_url: str = None,
    ide: str = "windsurf",
):
    """向目标项目注入 IDE 配置（规则 + 上报脚本）"""
    if dashboard_url is None:
        from config import get_port
        dashboard_url = f"http://localhost:{get_port()}"

    profile = get_profile(ide)
    config_dir = os.path.join(project_path, profile["config_dir"])
    reports_dir = os.path.join(config_dir, "reports")

    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)

    # 1. IDE 专属规则/workflow
    injector = _IDE_INJECTORS.get(ide)
    if injector:
        injector(config_dir, dashboard_url, project_name)

    # 2. 拷贝上报脚本（通用）
    report_src = os.path.join(get_resource_dir(), "report", "report.py")
    report_dst = os.path.join(config_dir, "report.py")
    if os.path.exists(report_src):
        shutil.copy2(report_src, report_dst)
    else:
        console.print(f"  [yellow]⚠ 上报脚本模板不存在: {report_src}，跳过拷贝[/yellow]")
    console.print(f"  [green]✓[/green] {report_dst}")

    # 3. 生成配置文件（通用）
    config_path = os.path.join(config_dir, "report_config.json")
    config = {
        "project_name": project_name,
        "dashboard_url": dashboard_url,
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    console.print(f"  [green]✓[/green] {config_path}")

    # 4. 记录到项目列表
    projects = load_projects()
    existing = [p for p in projects if p["path"] == project_path and p.get("ide", "windsurf") == ide]
    if existing:
        existing[0]["name"] = project_name
    else:
        projects.append({"name": project_name, "path": project_path, "ide": ide})
    save_projects(projects)


# ────────────────────────────────────────────
#  项目列表管理
# ────────────────────────────────────────────

def get_projects_config_path() -> str:
    return os.path.join(get_data_dir(), "projects.json")


_projects_cache: dict = {"data": None, "ts": 0.0, "ttl": 10.0}


def load_projects() -> list[dict]:
    now = time.time()
    if _projects_cache["data"] is not None and now - _projects_cache["ts"] < _projects_cache["ttl"]:
        return _projects_cache["data"]
    path = get_projects_config_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            result = json.load(f)
            for p in result:
                p.setdefault("ide", "windsurf")
            _projects_cache["data"] = result
            _projects_cache["ts"] = now
            return result
    return []


def save_projects(projects: list[dict]):
    path = get_projects_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)
    _projects_cache["data"] = projects
    _projects_cache["ts"] = time.time()


# ────────────────────────────────────────────
#  CLI 入口
# ────────────────────────────────────────────

def setup_project(project_path: str | None = None, project_name: str | None = None):
    if not project_path:
        project_path = Prompt.ask("[bold cyan]项目路径[/bold cyan]").strip().strip('"')
    if not os.path.isdir(project_path):
        console.print(f"[red]目录不存在: {project_path}[/red]")
        return

    project_path = os.path.abspath(project_path)
    if not project_name:
        default_name = os.path.basename(project_path)
        project_name = Prompt.ask("[bold cyan]项目名称[/bold cyan]", default=default_name)

    ide_choice = Prompt.ask(
        f"[bold cyan]IDE[/bold cyan] ({'/'.join(IDE_CHOICES)})",
        default="windsurf",
    )
    if ide_choice not in IDE_CHOICES:
        console.print(f"[red]不支持的 IDE: {ide_choice}[/red]")
        return

    dashboard_url = Prompt.ask("[bold cyan]看板地址[/bold cyan]", default="http://localhost:9000")

    ide_name = PROFILES[ide_choice]["name"]
    console.print(f"\n[bold]注入 {ide_name} 配置到: {project_path}[/bold]")
    inject_to_project(project_path, project_name, dashboard_url, ide=ide_choice)
    console.print(f"\n[green]✓ 项目 [{project_name}] ({ide_name}) 配置完成！[/green]")


def list_projects():
    projects = load_projects()
    if not projects:
        console.print("[yellow]暂无已配置项目。使用 'do setup' 添加项目。[/yellow]")
        return projects

    table = Table(title="已配置项目")
    table.add_column("序号", style="cyan", width=4)
    table.add_column("项目名", style="green")
    table.add_column("IDE", style="magenta", width=10)
    table.add_column("路径", style="dim")
    table.add_column("状态", width=6)
    for i, p in enumerate(projects, 1):
        ide = p.get("ide", "windsurf")
        configured = is_project_configured(p["path"], ide)
        status = "[green]✓[/green]" if configured else "[red]✗[/red]"
        ide_name = PROFILES.get(ide, {}).get("name", ide)
        table.add_row(str(i), p["name"], ide_name, p["path"], status)
    console.print(table)
    return projects


def run(args: list[str]) -> None:
    if args:
        setup_project(project_path=args[0], project_name=args[1] if len(args) > 1 else None)
    else:
        setup_project()


if __name__ == "__main__":
    run(sys.argv[1:])
