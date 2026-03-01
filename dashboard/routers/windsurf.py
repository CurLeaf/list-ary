"""Windsurf 项目管理 API 路由"""

import asyncio
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.models import ProjectSetup

router = APIRouter(tags=["windsurf"])


@router.get("/browse-folder")
async def browse_folder():
    """打开原生文件夹选择对话框"""

    def _pick() -> str:
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
    """获取 Windsurf 项目列表"""
    from modules.windsurf_setup import load_projects
    projects = load_projects()
    for p in projects:
        ws_dir = os.path.join(p["path"], ".windsurf")
        p["configured"] = os.path.isdir(ws_dir)
    return projects


@router.post("/projects/setup")
async def setup_project(req: ProjectSetup):
    """配置 Windsurf 项目"""
    from modules.windsurf_setup import inject_to_project, load_projects
    from config import get_port
    project_path = req.path.strip().strip('"')
    project_name = req.name.strip()
    dashboard_url = f"http://localhost:{get_port()}"

    if not project_path or not os.path.isdir(project_path):
        return JSONResponse(status_code=400, content={"error": f"目录不存在: {project_path}"})
    if not project_name:
        project_name = os.path.basename(os.path.abspath(project_path))

    try:
        inject_to_project(project_path, project_name, dashboard_url)
        return {"ok": True, "project": project_name, "path": project_path, "projects": load_projects()}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/projects/{index}/open")
async def open_project(index: int):
    """用 Windsurf 打开项目"""
    from modules.windsurf_setup import load_projects
    from modules.windsurf_open import find_windsurf
    projects = load_projects()
    if not (0 <= index < len(projects)):
        return JSONResponse(status_code=404, content={"error": "项目不存在"})
    project = projects[index]

    ws_path = find_windsurf()
    if not ws_path:
        return JSONResponse(status_code=404, content={"error": "未找到 Windsurf，请在设置中指定路径"})

    import subprocess
    try:
        subprocess.Popen([ws_path, project["path"]])
        return {"ok": True, "project": project["name"]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/projects/{index}/reinject")
async def reinject_project(index: int):
    """重新注入 .windsurf/ 配置到已有项目（更新 workflows + rules）"""
    from modules.windsurf_setup import load_projects, inject_to_project
    projects = load_projects()
    if not (0 <= index < len(projects)):
        return JSONResponse(status_code=404, content={"error": "项目不存在"})
    project = projects[index]
    if not os.path.isdir(project["path"]):
        return JSONResponse(status_code=404, content={"error": f"项目目录不存在: {project['path']}"})
    try:
        inject_to_project(project["path"], project["name"])
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
