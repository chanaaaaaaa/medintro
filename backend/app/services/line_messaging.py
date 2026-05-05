"""
LINE Messaging API：簽章驗證、Push / Reply（僅後端持 CHANNEL_ACCESS_TOKEN）。
掛號表的 line_id 請填「官方帳的好友 User ID」（多為 U 開頭），可向聊天室傳任意訊取得。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger(__name__)

_LINE_REPLY = "https://api.line.me/v2/bot/message/reply"
_LINE_PUSH = "https://api.line.me/v2/bot/message/push"


def line_messaging_ready() -> bool:
    return bool(
        settings.line_channel_secret.strip()
        and settings.line_channel_access_token.strip()
    )


def verify_webhook_signature(body: bytes, signature: str | None) -> bool:
    """X-Line-Signature：HMAC-SHA256(channel_secret, body) Base64"""
    secret = settings.line_channel_secret.strip()
    if not secret or not signature:
        return False
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode()
    return hmac.compare_digest(expected, signature)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.line_channel_access_token.strip()}",
        "Content-Type": "application/json",
    }


def reply_text(*, reply_token: str, text: str, quick_reply: dict | None = None) -> None:
    msg: dict[str, Any] = {"type": "text", "text": text}
    if quick_reply:
        msg["quickReply"] = quick_reply

    payload: dict[str, Any] = {
        "replyToken": reply_token,
        "messages": [msg],
    }
    with httpx.Client(timeout=15.0) as client:
        r = client.post(_LINE_REPLY, headers=_headers(), json=payload)
        if not r.is_success:
            log.error(
                "LINE reply HTTP %s: %s",
                r.status_code,
                r.text[:500],
            )
            r.raise_for_status()


def quick_reply_registration_location() -> dict:
    """掛號第二階段：請傳位置或按『不提供』。"""
    no_loc = "【掛號】不提供位置"
    return {
        "items": [
            {
                "type": "action",
                "action": {
                    "type": "message",
                    "label": "不提供位置（固定提前提醒）",
                    "text": no_loc,
                },
            }
        ]
    }

def push_text(*, to_user_id: str, text: str) -> None:
    """Push 訊息給已加官方帳為好友的使用者。"""
    if not line_messaging_ready():
        raise RuntimeError("LINE Messaging 未設定（LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN）")

    uid = to_user_id.strip()
    payload: dict[str, Any] = {
        "to": uid,
        "messages": [{"type": "text", "text": text[:5000]}],
    }
    log.info("LINE push → user_id 前綴=%s…", uid[:8])
    with httpx.Client(timeout=15.0) as client:
        r = client.post(_LINE_PUSH, headers=_headers(), json=payload)
        if not r.is_success:
            log.error("LINE push HTTP %s: %s", r.status_code, r.text[:800])
            r.raise_for_status()


def build_user_id_help_message(sender_user_id: str) -> str:
    return (
        "【MedIntro POC】\n"
        f"您的 Messaging API User ID（請完整複製填在掛號表「LINE」欄位）：\n\n"
        f"`{sender_user_id}`\n\n"
        "此 ID 與好友設定的「使用者名稱／@ID」不同。"
    )
