import asyncio
import os
import sys
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from dashboard.models import (
    ReportRequest, ReplyRequest, SessionPatch,
    ReportResponse, PollResponse,
    KillPortRequest, ServerConfig, ProjectSetup,
)
from dashboard import session_manager as sm

# EXE 兼容路径
if getattr(sys, "frozen", False):
    TEMPLATES_DIR = os.path.join(sys._MEIPASS, "dashboard", "templates")
else:
    TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# WebSocket 连接管理
ws_clients: list[WebSocket] = []


async def broadcast_ws(message: dict):
    """向所有 WebSocket 客户端广播消息"""
    dead = []
    for ws in ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.remove(ws)


async def send_toast_notification(project: str, task: str, status: str):
    """发送 Windows 桌面 Toast 通知"""
    try:
        from winotify import Notification
        status_emoji = {"completed": "✅", "need_confirm": "🟠", "partial": "⚠️", "blocked": "🔴"}.get(status, "📋")
        toast = Notification(
            app_id="Windsurf 调度看板",
            title=f"{status_emoji} {project}",
            msg=task[:100],
            launch="http://localhost:9000",
        )
        toast.show()
    except Exception:
        pass


async def stuck_checker():
    """定时检查卡死会话 + 自动清理过期会话"""
    while True:
        await asyncio.sleep(60)
        try:
            stuck_ids = sm.check_stuck_sessions()
            if stuck_ids:
                await broadcast_ws({
                    "type": "stuck_detected",
                    "session_ids": stuck_ids,
                    "sessions": sm.get_all_sessions(),
                })
        except Exception:
            pass
        # 自动清理过期会话
        try:
            from config import get_session_expire_days
            cleaned = sm.clean_expired_sessions(get_session_expire_days())
            if cleaned > 0:
                await broadcast_ws({"type": "auto_cleaned", "count": cleaned, "sessions": sm.get_all_sessions()})
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    sm.init_db()
    task = asyncio.create_task(stuck_checker())
    yield
    task.cancel()


app = FastAPI(title="Windsurf 调度看板", lifespan=lifespan)


# ─── 页面 ───

@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    sessions = sm.get_all_sessions()
    # 按项目分组
    projects: dict[str, list] = {}
    for s in sessions:
        projects.setdefault(s["project"], []).append(s)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "projects": projects,
        "sessions_json": json.dumps(sessions, ensure_ascii=False),
    })


# ─── WebSocket ───

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)
    try:
        # 发送当前状态
        sessions = sm.get_all_sessions()
        await websocket.send_json({"type": "init", "sessions": sessions})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in ws_clients:
            ws_clients.remove(websocket)


# ─── API ───

@app.post("/api/report", response_model=ReportResponse)
async def report(req: ReportRequest):
    """接收上报"""
    session_id, task_id = sm.create_or_update_session(
        session_id=req.session_id,
        project=req.project,
        task=req.task,
        previous_request=req.previous_request,
        status=req.status,
        questions=req.questions,
        timestamp=req.timestamp,
    )
    # 清除旧的回复事件
    sm.clear_reply_event(session_id)

    # WebSocket 广播（增量推送）
    session = sm.get_session(session_id)
    await broadcast_ws({"type": "session_updated", "session_id": session_id, "session": session})

    # 桌面通知
    await send_toast_notification(req.project, req.task, req.status)

    return ReportResponse(session_id=session_id, task_id=task_id)


@app.get("/api/poll/{session_id}", response_model=PollResponse)
async def poll(session_id: str, timeout: int = 30):
    """长轮询等待用户回复"""
    # 先检查是否已有回复
    reply = sm.get_reply(session_id)
    if reply is not None:
        return PollResponse(reply=reply, has_reply=True)

    # 等待回复事件
    event = sm.get_reply_event(session_id)
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        reply = sm.get_reply(session_id)
        if reply is not None:
            return PollResponse(reply=reply, has_reply=True)
    except asyncio.TimeoutError:
        pass

    return PollResponse(reply=None, has_reply=False)


@app.post("/api/reply/{session_id}")
async def reply(session_id: str, req: ReplyRequest):
    """用户回复/下达指令"""
    success = sm.set_reply(session_id, req.reply)
    if not success:
        return JSONResponse(status_code=404, content={"error": "会话不存在"})

    # 通知长轮询
    sm.notify_reply(session_id)

    # WebSocket 广播（增量推送）
    session = sm.get_session(session_id)
    await broadcast_ws({"type": "session_updated", "session_id": session_id, "session": session})

    return {"ok": True, "session_id": session_id}


@app.patch("/api/sessions/{session_id}")
async def patch_session(session_id: str, req: SessionPatch):
    """更新会话状态"""
    success = sm.update_session_status(session_id, req.status)
    if not success:
        return JSONResponse(status_code=404, content={"error": "会话不存在"})

    session = sm.get_session(session_id)
    await broadcast_ws({"type": "session_updated", "session_id": session_id, "session": session})

    return {"ok": True}


@app.get("/api/sessions")
async def list_sessions():
    """获取所有活跃会话"""
    return sm.get_all_sessions()


@app.get("/api/sessions/{session_id}/context")
async def get_context(session_id: str):
    """获取会话历史摘要"""
    context = sm.get_session_context(session_id)
    if not context:
        return JSONResponse(status_code=404, content={"error": "会话不存在"})
    return {"context": context}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    success = sm.delete_session(session_id)
    sm.remove_reply_event(session_id)
    if not success:
        return JSONResponse(status_code=404, content={"error": "会话不存在"})

    await broadcast_ws({"type": "session_deleted", "session_id": session_id})

    return {"ok": True}


@app.delete("/api/sessions")
async def clean_sessions():
    """清理所有会话"""
    count = sm.clean_all_sessions()
    await broadcast_ws({"type": "all_cleaned", "sessions": []})
    return {"ok": True, "cleaned": count}


# ─── Hub 功能 API ───

@app.get("/panel", response_class=HTMLResponse)
async def panel_page(request: Request):
    """主面板页面"""
    return templates.TemplateResponse("panel.html", {"request": request})


_ports_cache = {"ts": 0, "data": None}

@app.get("/api/listening-ports")
async def api_listening_ports():
    """获取当前所有监听端口列表（按端口号排序，限30条），1秒 TTL 缓存"""
    import time, psutil
    now = time.time()
    if _ports_cache["data"] is not None and now - _ports_cache["ts"] < 1.0:
        return _ports_cache["data"]
    try:
        connections = psutil.net_connections()
    except psutil.AccessDenied:
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})

    ports = {}
    for conn in connections:
        if conn.laddr and conn.status == "LISTEN" and conn.pid:
            port = conn.laddr.port
            if port in ports:
                continue
            try:
                proc = psutil.Process(conn.pid)
                ports[port] = {
                    "port": port,
                    "pid": conn.pid,
                    "name": proc.name(),
                    "exe": proc.exe() or "",
                }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                ports[port] = {"port": port, "pid": conn.pid, "name": "unknown", "exe": ""}

    result = sorted(ports.values(), key=lambda x: x["port"])[:30]
    response = {"ports": result, "total": len(ports)}
    _ports_cache["ts"] = now
    _ports_cache["data"] = response
    return response


@app.post("/api/kill-port")
async def api_kill_port(req: KillPortRequest):
    """杀死占用指定端口的进程"""
    import psutil
    port = req.port

    killed = []
    try:
        connections = psutil.net_connections()
    except psutil.AccessDenied:
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})

    seen_pids = set()
    for conn in connections:
        if conn.laddr and conn.laddr.port == port and conn.status == "LISTEN":
            if conn.pid and conn.pid not in seen_pids:
                seen_pids.add(conn.pid)
                try:
                    proc = psutil.Process(conn.pid)
                    info = {"pid": conn.pid, "name": proc.name(), "exe": proc.exe() or "N/A"}
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        proc.kill()
                    info["status"] = "killed"
                    killed.append(info)
                except psutil.AccessDenied:
                    killed.append({"pid": conn.pid, "name": "unknown", "status": "access_denied"})
                except psutil.NoSuchProcess:
                    pass
                except Exception as e:
                    killed.append({"pid": conn.pid, "name": "unknown", "status": f"error: {e}"})

    return {"port": port, "killed": killed, "count": len(killed)}


@app.get("/api/servers")
async def list_servers():
    """获取 SSH 服务器列表"""
    from modules.ssh_manager import load_servers
    return load_servers()


@app.post("/api/servers")
async def add_server(req: ServerConfig):
    """添加 SSH 服务器"""
    from modules.ssh_manager import load_servers, save_servers
    servers = load_servers()
    servers.append(req.model_dump())
    save_servers(servers)
    return {"ok": True, "servers": servers}


@app.put("/api/servers/{index}")
async def update_server(index: int, req: ServerConfig):
    """更新 SSH 服务器"""
    from modules.ssh_manager import load_servers, save_servers
    servers = load_servers()
    if not (0 <= index < len(servers)):
        return JSONResponse(status_code=404, content={"error": "服务器不存在"})
    servers[index] = req.model_dump()
    save_servers(servers)
    return {"ok": True, "servers": servers}


@app.delete("/api/servers/{index}")
async def remove_server(index: int):
    """删除 SSH 服务器"""
    from modules.ssh_manager import load_servers, save_servers
    servers = load_servers()
    if not (0 <= index < len(servers)):
        return JSONResponse(status_code=404, content={"error": "服务器不存在"})
    removed = servers.pop(index)
    save_servers(servers)
    return {"ok": True, "removed": removed["name"], "servers": servers}


@app.get("/api/servers/ping")
async def ping_servers():
    """探测所有 SSH 服务器在线状态"""
    import socket
    from modules.ssh_manager import load_servers
    from config import SSH_PING_TIMEOUT
    servers = load_servers()
    results = []
    for s in servers:
        host = s.get("host", "").split("@")[-1]  # user@host -> host
        port = s.get("port", 22)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(SSH_PING_TIMEOUT)
            sock.connect((host, port))
            sock.close()
            results.append(True)
        except Exception:
            results.append(False)
    return {"status": results}


@app.post("/api/ssh-connect/{index}")
async def ssh_connect(index: int):
    """连接到 SSH 服务器"""
    import subprocess, shutil
    from modules.ssh_manager import load_servers
    servers = load_servers()
    if not (0 <= index < len(servers)):
        return JSONResponse(status_code=404, content={"error": "服务器不存在"})
    server = servers[index]

    ssh_cmd = ["ssh", "-t"]
    if server.get("port") and server["port"] != 22:
        ssh_cmd += ["-p", str(server["port"])]
    if server.get("key"):
        key_path = os.path.expanduser(server["key"])
        ssh_cmd += ["-i", key_path]
    ssh_cmd.append(server["host"])
    if server.get("path"):
        ssh_cmd.append(f"cd {server['path']} && exec $SHELL")

    wt = shutil.which("wt") or shutil.which("wt.exe")
    try:
        if wt:
            subprocess.Popen([wt, "new-tab", "--title", server["name"]] + ssh_cmd)
        else:
            subprocess.Popen(["cmd", "/c", "start"] + ssh_cmd)
        return {"ok": True, "server": server["name"]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/projects")
async def list_projects():
    """获取 Windsurf 项目列表"""
    from modules.windsurf_setup import load_projects
    projects = load_projects()
    for p in projects:
        ws_dir = os.path.join(p["path"], ".windsurf")
        p["configured"] = os.path.isdir(ws_dir)
    return projects


@app.post("/api/projects/setup")
async def setup_project(req: ProjectSetup):
    """配置 Windsurf 项目"""
    from modules.windsurf_setup import inject_to_project, load_projects
    project_path = req.path.strip().strip('"')
    project_name = req.name.strip()
    dashboard_url = "http://localhost:9000"

    if not project_path or not os.path.isdir(project_path):
        return JSONResponse(status_code=400, content={"error": f"目录不存在: {project_path}"})
    if not project_name:
        project_name = os.path.basename(os.path.abspath(project_path))

    try:
        inject_to_project(project_path, project_name, dashboard_url)
        return {"ok": True, "project": project_name, "path": project_path, "projects": load_projects()}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/projects/{index}/open")
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


@app.post("/api/projects/{index}/reinject")
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


@app.delete("/api/projects/{index}")
async def remove_project(index: int):
    """从项目列表移除（不删除文件）"""
    from modules.windsurf_setup import load_projects, save_projects
    projects = load_projects()
    if not (0 <= index < len(projects)):
        return JSONResponse(status_code=404, content={"error": "项目不存在"})
    removed = projects.pop(index)
    save_projects(projects)
    return {"ok": True, "removed": removed["name"], "projects": projects}


@app.get("/api/autostart")
async def get_autostart():
    """获取开机自启状态"""
    from modules.autostart import is_autostart_enabled
    return {"enabled": is_autostart_enabled()}


@app.post("/api/autostart")
async def set_autostart(req: dict):
    """设置开机自启"""
    from modules.autostart import enable_autostart, disable_autostart
    enabled = req.get("enabled", False)
    if enabled:
        ok = enable_autostart()
    else:
        ok = disable_autostart()
    if not ok:
        return JSONResponse(status_code=500, content={"error": "操作注册表失败，请检查权限"})
    return {"ok": True, "enabled": enabled}


@app.get("/api/settings")
async def get_settings():
    """获取用户设置"""
    from config import load_settings, PORT, STUCK_TIMEOUT_MINUTES, SESSION_EXPIRE_DAYS
    s = load_settings()
    return {
        "port": s.get("port", PORT),
        "stuck_timeout": s.get("stuck_timeout", STUCK_TIMEOUT_MINUTES),
        "session_expire_days": s.get("session_expire_days", SESSION_EXPIRE_DAYS),
        "windsurf_path": s.get("windsurf_path", ""),
        "lang": s.get("lang", "zh"),
    }


@app.post("/api/settings")
async def save_settings_api(req: dict):
    """保存用户设置"""
    from config import load_settings, save_settings
    current = load_settings()
    for k in ("port", "stuck_timeout", "session_expire_days", "windsurf_path", "lang"):
        if k in req:
            current[k] = req[k]
    save_settings(current)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("dashboard.server:app", host="0.0.0.0", port=9000, reload=True)
