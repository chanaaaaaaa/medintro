import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from app.config import settings
from app.services.mail import get_smtp_diagnostic, send_plain_email

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mail", tags=["mail"])


class TestSendBody(BaseModel):
    to: EmailStr
    subject: str = "MedIntro POC 郵件測試"
    body: str = "這是一封測試郵件。若收到表示 SMTP 設定正確。"


@router.get("/smtp-diagnostic")
def smtp_diagnostic():
    if not settings.mail_test_endpoint_enabled:
        raise HTTPException(
            status_code=403,
            detail="未開放：請在 .env 設定 MAIL_TEST_ENDPOINT_ENABLED=true",
        )
    log.info(
        "GET smtp-diagnostic：只檢查 .env 是否解析成功，尚未連線 SMTP；"
        "要看寄信用 POST /api/mail/test-send"
    )
    return get_smtp_diagnostic()


@router.post("/test-send")
def test_send(payload: TestSendBody):
    if not settings.mail_test_endpoint_enabled:
        raise HTTPException(
            status_code=403,
            detail="未開放：請在 .env 設定 MAIL_TEST_ENDPOINT_ENABLED=true",
        )
    if not settings.smtp_enabled:
        raise HTTPException(status_code=400, detail="請先設定 SMTP_ENABLED=true")
    log.info("mail test-send: 收到請求 to=%s", payload.to)
    try:
        summary = send_plain_email(
            to_addr=payload.to,
            subject=payload.subject,
            body=payload.body,
        )
    except Exception as e:
        log.exception("test-send failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    log.info("mail test-send: 成功 to=%s", payload.to)
    return {"ok": True, "summary": summary, "note": "請同時查看終端機 mail: 開頭的日誌"}
