"""设置 + 自启管理 API 路由"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["settings"])


@router.get("/autostart")
async def get_autostart():
    """获取开机自启状态"""
    from modules.autostart import is_autostart_enabled
    return {"enabled": is_autostart_enabled()}


@router.post("/autostart")
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


@router.get("/settings")
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


@router.post("/settings")
async def save_settings_api(req: dict):
    """保存用户设置"""
    from config import load_settings, save_settings
    current = load_settings()
    for k in ("port", "stuck_timeout", "session_expire_days", "windsurf_path", "lang"):
        if k in req:
            current[k] = req[k]
    # 类型校验：数值字段必须为正整数
    for k in ("port", "stuck_timeout", "session_expire_days"):
        if k in current:
            try:
                current[k] = int(current[k])
                if current[k] <= 0:
                    return JSONResponse(status_code=400, content={"error": f"{k} 必须为正整数"})
            except (ValueError, TypeError):
                return JSONResponse(status_code=400, content={"error": f"{k} 必须为正整数"})
    save_settings(current)
    return {"ok": True}
