"""Session/Dashboard API 路由"""

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.models import (
    ReportRequest, ReplyRequest, SessionPatch,
    ReportResponse, PollResponse,
)
from dashboard import session_manager as sm
from dashboard.session_manager import (
    async_create_or_update_session, async_set_reply,
    async_get_reply, async_get_session, async_get_all_sessions,
    async_update_session_status, async_delete_session, async_clean_all_sessions,
    async_get_session_context,
)

router = APIRouter(tags=["sessions"])


@router.post("/report", response_model=ReportResponse)
async def report(req: ReportRequest):
    """接收上报"""
    from dashboard.server import broadcast_ws, send_toast_notification
    session_id, task_id = await async_create_or_update_session(
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
    session = await async_get_session(session_id)
    await broadcast_ws({"type": "session_updated", "session_id": session_id, "session": session})

    # 桌面通知
    await send_toast_notification(req.project, req.task, req.status)

    return ReportResponse(session_id=session_id, task_id=task_id)


@router.get("/poll/{session_id}", response_model=PollResponse)
async def poll(session_id: str, timeout: int = 30):
    """长轮询等待用户回复"""
    # 先检查是否已有回复
    reply = await async_get_reply(session_id)
    if reply is not None:
        return PollResponse(reply=reply, has_reply=True)

    # 等待回复事件
    event = sm.get_reply_event(session_id)
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        reply = await async_get_reply(session_id)
        if reply is not None:
            return PollResponse(reply=reply, has_reply=True)
    except asyncio.TimeoutError:
        pass

    return PollResponse(reply=None, has_reply=False)


@router.post("/reply/{session_id}")
async def reply(session_id: str, req: ReplyRequest):
    """用户回复/下达指令"""
    from dashboard.server import broadcast_ws
    success = await async_set_reply(session_id, req.reply)
    if not success:
        return JSONResponse(status_code=404, content={"error": "会话不存在"})

    # 通知长轮询
    sm.notify_reply(session_id)

    # WebSocket 广播（增量推送）
    session = await async_get_session(session_id)
    await broadcast_ws({"type": "session_updated", "session_id": session_id, "session": session})

    return {"ok": True, "session_id": session_id}


@router.patch("/sessions/{session_id}")
async def patch_session(session_id: str, req: SessionPatch):
    """更新会话状态"""
    from dashboard.server import broadcast_ws
    success = await async_update_session_status(session_id, req.status)
    if not success:
        return JSONResponse(status_code=404, content={"error": "会话不存在"})

    session = await async_get_session(session_id)
    await broadcast_ws({"type": "session_updated", "session_id": session_id, "session": session})

    return {"ok": True}


@router.get("/sessions")
async def list_sessions():
    """获取所有活跃会话"""
    return await async_get_all_sessions()


@router.get("/sessions/{session_id}/context")
async def get_context(session_id: str):
    """获取会话历史摘要"""
    context = await async_get_session_context(session_id)
    if not context:
        return JSONResponse(status_code=404, content={"error": "会话不存在"})
    return {"context": context}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    from dashboard.server import broadcast_ws
    success = await async_delete_session(session_id)
    sm.remove_reply_event(session_id)
    if not success:
        return JSONResponse(status_code=404, content={"error": "会话不存在"})

    await broadcast_ws({"type": "session_deleted", "session_id": session_id})

    return {"ok": True}


@router.delete("/sessions")
async def clean_sessions():
    """清理所有会话"""
    from dashboard.server import broadcast_ws
    count = await async_clean_all_sessions()
    await broadcast_ws({"type": "all_cleaned", "sessions": []})
    return {"ok": True, "cleaned": count}
