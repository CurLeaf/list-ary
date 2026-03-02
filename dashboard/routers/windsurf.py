"""项目管理 API 路由 — 支持 Windsurf / Cursor / 可扩展 IDE"""

import asyncio
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.models import ProjectSetup
from modules.ide_profiles import (
    IDE_CHOICES, PROFILES,
    find_executable, is_project_configured,
)

router = APIRouter(tags=["projects"])


@router.get("/ide-profiles")
async def list_ide_profiles():
    """返回可用 IDE 列表"""
    return [{"id": k, "name": v["name"]} for k, v in PROFILES.items()]


@router.get("/browse-folder")
async def browse_folder():
    """打开原生文件夹选择对话框"""
    import sys

    def _pick() -> str:
        if sys.platform == "win32":
            import subprocess
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                "$d.Description = '选择项目文件夹'; "
                "$d.ShowNewFolderButton = $true; "
                "if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath } else { '' }"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True, timeout=120,
            )
            return result.stdout.strip()
        else:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            folder = filedialog.askdirectory(title="选择项目文件夹")
            root.destroy()
            return folder or ""

    path = await asyncio.to_thread(_pick)

    if not path:
        return {"ok": False, "path": ""}
    return {"ok": True, "path": path}


@router.get("/projects")
async def list_projects():
    """获取项目列表（含 IDE 类型和配置状态）"""
    from modules.windsurf_setup import load_projects
    projects = load_projects()
    for p in projects:
        ide = p.get("ide", "windsurf")
        p["configured"] = is_project_configured(p["path"], ide)
        p["ide_name"] = PROFILES.get(ide, {}).get("name", ide)
    return projects


@router.post("/projects/setup")
async def setup_project(req: ProjectSetup):
    """配置项目（注入 IDE 规则 + 上报脚本）"""
    from modules.windsurf_setup import inject_to_project, load_projects
    from config import get_port
    project_path = req.path.strip().strip('"')
    project_name = req.name.strip()
    ide = req.ide if req.ide in IDE_CHOICES else "windsurf"
    dashboard_url = f"http://localhost:{get_port()}"

    if not project_path or not os.path.isdir(project_path):
        return JSONResponse(status_code=400, content={"error": f"目录不存在: {project_path}"})
    if not project_name:
        project_name = os.path.basename(os.path.abspath(project_path))

    try:
        inject_to_project(project_path, project_name, dashboard_url, ide=ide)
        projects = load_projects()
        for p in projects:
            p["configured"] = is_project_configured(p["path"], p.get("ide", "windsurf"))
            p["ide_name"] = PROFILES.get(p.get("ide", "windsurf"), {}).get("name", p.get("ide", "windsurf"))
        return {"ok": True, "project": project_name, "path": project_path, "projects": projects}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/projects/{index}/open")
async def open_project(index: int):
    """用对应 IDE 打开项目"""
    from modules.windsurf_setup import load_projects
    projects = load_projects()
    if not (0 <= index < len(projects)):
        return JSONResponse(status_code=404, content={"error": "项目不存在"})
    project = projects[index]
    ide = project.get("ide", "windsurf")
    ide_name = PROFILES.get(ide, {}).get("name", ide)

    exe_path = find_executable(ide)
    if not exe_path:
        return JSONResponse(status_code=404, content={"error": f"未找到 {ide_name}，请在设置中指定路径"})

    import subprocess
    try:
        subprocess.Popen([exe_path, project["path"]])
        return {"ok": True, "project": project["name"]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/projects/{index}/reinject")
async def reinject_project(index: int):
    """重新注入 IDE 配置到已有项目"""
    from modules.windsurf_setup import load_projects, inject_to_project
    projects = load_projects()
    if not (0 <= index < len(projects)):
        return JSONResponse(status_code=404, content={"error": "项目不存在"})
    project = projects[index]
    if not os.path.isdir(project["path"]):
        return JSONResponse(status_code=404, content={"error": f"项目目录不存在: {project['path']}"})
    ide = project.get("ide", "windsurf")
    try:
        inject_to_project(project["path"], project["name"], ide=ide)
        return {"ok": True, "project": project["name"]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/projects/{index}")
async def remove_project(index: int):
    """从项目列表移除（不删除文件）"""
    from modules.windsurf_setup import load_projects, save_projects
    projects = load_projects()
    if not (0 <= index < len(projects)):
        return JSONResponse(status_code=404, content={"error": "项目不存在"})
    removed = projects.pop(index)
    save_projects(projects)
    return {"ok": True, "removed": removed["name"], "projects": projects}
