"""
Webhook 通知模块 — 会话状态变化时推送到外部服务。
自动识别 URL 格式，适配常见平台：
  - Telegram Bot API
  - 企业微信 (WeCom)
  - 钉钉 (DingTalk)
  - Bark (iOS)
  - 通用 JSON Webhook (POST { text, title })
"""

import json
import logging

import httpx

log = logging.getLogger("webhook")

_TIMEOUT = 10


def _detect_platform(url: str) -> str:
    u = url.lower()
    if "api.telegram.org" in u:
        return "telegram"
    if "qyapi.weixin.qq.com" in u:
        return "wecom"
    if "oapi.dingtalk.com" in u:
        return "dingtalk"
    if "api.day.app" in u or "/push" in u and "bark" in u:
        return "bark"
    return "generic"


def _build_payload(platform: str, title: str, body: str, url: str) -> tuple[str, dict]:
    """返回 (post_url, json_body)"""
    if platform == "telegram":
        text = f"*{title}*\n{body}"
        chat_id = None
        if "chat_id=" in url:
            import re
            m = re.search(r"chat_id=(-?\d+)", url)
            if m:
                chat_id = m.group(1)
                url = re.sub(r"[?&]chat_id=-?\d+", "", url).rstrip("?&")
        payload = {"text": text, "parse_mode": "Markdown"}
        if chat_id:
            payload["chat_id"] = chat_id
        return url, payload

    if platform == "wecom":
        return url, {
            "msgtype": "text",
            "text": {"content": f"{title}\n{body}"},
        }

    if platform == "dingtalk":
        return url, {
            "msgtype": "text",
            "text": {"content": f"{title}\n{body}"},
        }

    if platform == "bark":
        return url, {
            "title": title,
            "body": body,
            "group": "Listary",
        }

    return url, {
        "title": title,
        "text": f"{title}\n{body}",
        "body": body,
        "msg": f"{title}\n{body}",
    }


def send(webhook_url: str, title: str, body: str) -> tuple[bool, str]:
    """发送 Webhook 通知，返回 (success, error_message)"""
    if not webhook_url:
        return False, "无 webhook URL"
    try:
        platform = _detect_platform(webhook_url)
        post_url, payload = _build_payload(platform, title, body, webhook_url)
        resp = httpx.post(post_url, json=payload, timeout=_TIMEOUT)
        if resp.status_code < 300:
            return True, ""
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        log.warning(f"Webhook 发送失败: {e}")
        return False, str(e)


def notify_session(webhook_url: str, project: str, task: str, status: str):
    """会话状态变更通知"""
    if not webhook_url:
        return
    status_map = {
        "waiting": "Waiting",
        "completed": "Completed",
        "need_confirm": "Need Confirm",
        "blocked": "Blocked",
        "stuck": "Stuck",
    }
    label = status_map.get(status, status)
    title = f"[{label}] {project}"
    send(webhook_url, title, task[:200])
