"""端口管理 API 路由"""

import asyncio
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.models import KillPortRequest

router = APIRouter(tags=["ports"])

_ports_cache = {"ts": 0, "data": None}


@router.get("/listening-ports")
async def api_listening_ports():
    """获取当前所有监听端口列表（按端口号排序，限30条），1秒 TTL 缓存"""
    import psutil
    now = time.time()
    if _ports_cache["data"] is not None and now - _ports_cache["ts"] < 1.0:
        return _ports_cache["data"]
    try:
        connections = await asyncio.to_thread(psutil.net_connections)
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


@router.post("/kill-port")
async def api_kill_port(req: KillPortRequest):
    """杀死占用指定端口的进程"""
    import psutil
    port = req.port

    killed = []
    try:
        connections = await asyncio.to_thread(psutil.net_connections)
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
