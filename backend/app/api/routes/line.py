import json
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.services.line_bot_flow import flush_event
from app.services.line_messaging import (
    line_messaging_ready,
    push_text,
    verify_webhook_signature,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/line", tags=["line"])


class LineTestPushBody(BaseModel):
    to: str = Field(..., description="LINE User ID（U…）")
    text: str = "MedIntro LINE 測試訊息"


@router.post("/webhook")
async def line_webhook(request: Request):
    """
    LINE Platform Webhook。ngrok：https://…/api/line/webhook
    指令：「掛號」「查詢」等見 line_bot_flow。
    """
    body = await request.body()

    if not settings.line_channel_secret.strip():
        log.warning("LINE webhook 收到請求但未設定 LINE_CHANNEL_SECRET，已忽略")
        return {"message": "LINE not configured"}

    sig = request.headers.get("X-Line-Signature")
    if not verify_webhook_signature(body, sig):
        raise HTTPException(status_code=403, detail="Invalid LINE signature")

    if not line_messaging_ready():
        log.warning("LINE 簽章通過但未設定 CHANNEL_ACCESS_TOKEN")
        return {"message": "missing access token"}

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail="invalid json") from e

    events = payload.get("events") or []
    for ev in events:
        log.debug("LINE event type=%s", ev.get("type"))
        try:
            flush_event(ev)
        except Exception:
            log.exception("LINE flush_event 失敗")

    return {"message": "ok"}


@router.post("/test-push")
def line_test_push(body: LineTestPushBody):
    """本機測試 Push（需 LINE_TEST_ENDPOINT_ENABLED=true）。"""
    if not settings.line_test_endpoint_enabled:
        raise HTTPException(
            status_code=403,
            detail="請在 .env 設定 LINE_TEST_ENDPOINT_ENABLED=true",
        )
    try:
        push_text(to_user_id=body.to, text=body.text)
    except Exception as e:
        log.exception("LINE test-push 失敗")
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"ok": True}
