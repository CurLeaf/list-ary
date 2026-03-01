import asyncio
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, RedirectResponse

# EXE 兼容路径
if getattr(sys, "frozen", False):
    TEMPLATES_DIR = os.path.join(sys._MEIPASS, "dashboard", "templates")
else:
    TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)

from dashboard.session_manager import (
    async_init_db, async_get_all_sessions, async_get_session,
    async_check_stuck_sessions, async_clean_expired_sessions,
)

# WebSocket 连接管理
ws_clients: set[WebSocket] = set()


async def broadcast_ws(message: dict):
    """向所有 WebSocket 客户端广播消息"""
    dead = []
    for ws in list(ws_clients):
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.discard(ws)


async def send_toast_notification(project: str, task: str, status: str):
    """发送 Windows 桌面 Toast 通知"""
    try:
        from winotify import Notification
        from config import get_port
        status_emoji = {"completed": "✅", "need_confirm": "🟠", "partial": "⚠️", "blocked": "🔴"}.get(status, "📋")
        toast = Notification(
            app_id="Windsurf 调度看板",
            title=f"{status_emoji} {project}",
            msg=task[:100],
            launch=f"http://localhost:{get_port()}",
        )
        toast.show()
    except Exception:
        pass


async def stuck_checker():
    """定时检查卡死会话 + 自动清理过期会话 + SFTP 空闲连接回收"""
    while True:
        await asyncio.sleep(60)
        # SFTP 空闲连接回收
        try:
            from modules.sftp_pool import cleanup_idle
            await asyncio.to_thread(cleanup_idle)
        except Exception:
            pass
        try:
            stuck_ids = await async_check_stuck_sessions()
            for sid in stuck_ids:
                session = await async_get_session(sid)
                if session:
                    await broadcast_ws({
                        "type": "session_updated",
                        "session_id": sid,
                        "session": session,
                    })
        except Exception:
            pass
        # 自动清理过期会话
        try:
            from config import get_session_expire_days
            cleaned, deleted_ids = await async_clean_expired_sessions(get_session_expire_days())
            if cleaned > 0:
                await broadcast_ws({"type": "sessions_deleted", "session_ids": deleted_ids})
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    await async_init_db()
    task = asyncio.create_task(stuck_checker())
    yield
    task.cancel()
    try:
        from modules.sftp_pool import close_all
        close_all()
    except Exception:
        pass


app = FastAPI(title="Listary Tools", lifespan=lifespan)

# ─── 注册路由 ───
from dashboard.routers import ports, ssh, windsurf, sessions, settings
app.include_router(ports.router, prefix="/api")
app.include_router(ssh.router, prefix="/api")
app.include_router(windsurf.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(settings.router, prefix="/api")


# ─── 页面 ───

@app.get("/", response_class=HTMLResponse)
async def root_redirect():
    return RedirectResponse(url="/panel")


@app.get("/panel", response_class=HTMLResponse)
async def panel_page(request: Request):
    """主面板页面"""
    return templates.TemplateResponse("panel.html", {"request": request})


# ─── WebSocket ───

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        # 发送当前状态
        sessions_data = await async_get_all_sessions()
        await websocket.send_json({"type": "init", "sessions": sessions_data})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_clients.discard(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("dashboard.server:app", host="127.0.0.1", port=9000, reload=True)
