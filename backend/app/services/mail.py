"""寄送郵件（標準函式庫 smtplib），含除錯日誌（不記錄密碼）。"""

import logging
import smtplib
import ssl
import traceback
from email.message import EmailMessage
from email.utils import formataddr

from app.config import settings

log = logging.getLogger(__name__)


def smtp_ready() -> bool:
    return bool(
        settings.smtp_enabled
        and settings.smtp_host
        and settings.mail_from_address
    )


def _smtp_config_snapshot() -> dict:
    """不含密碼，供日誌／診斷 API 使用。"""
    return {
        "smtp_enabled": settings.smtp_enabled,
        "smtp_host": settings.smtp_host or "(empty)",
        "smtp_port": settings.smtp_port,
        "smtp_use_tls": settings.smtp_use_tls,
        "smtp_use_ssl": settings.smtp_use_ssl,
        "mail_from_address": settings.mail_from_address or "(empty)",
        "mail_from_name": settings.mail_from_name,
        "smtp_user_set": bool(settings.smtp_user),
        "smtp_password_set": bool(settings.smtp_password),
        "smtp_protocol_debug": settings.mail_smtp_protocol_debug,
    }


def _apply_protocol_debug(server: smtplib.SMTP) -> None:
    """smtplib 內建除錯會寫到 stderr，與 uvicorn 同一終端機看得到。"""
    if settings.mail_smtp_protocol_debug:
        server.set_debuglevel(2)
        log.warning(
            "MAIL_SMTP_PROTOCOL_DEBUG 已啟用：SMTP 原始對話會輸出到 stderr"
        )


def send_plain_email(*, to_addr: str, subject: str, body: str) -> dict:
    """
    成功回傳不含敏感資訊的摘要 dict（方便 API 與測試）。
    失敗丟出原本例外；日誌會含原因與 SMTP 回應（若有）。
    """
    snap = _smtp_config_snapshot()
    log.info(
        "mail: 開始寄信 to=%s subject_len=%s body_len=%s snapshot=%s",
        to_addr,
        len(subject),
        len(body),
        snap,
    )

    if not smtp_ready():
        log.error(
            "mail: smtp 未就緒 enabled=%s host_set=%s from_set=%s",
            settings.smtp_enabled,
            bool(settings.smtp_host),
            bool(settings.mail_from_address),
        )
        raise RuntimeError("SMTP 未啟用或缺少 smtp_host / mail_from_address，請檢查 .env")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((settings.mail_from_name, settings.mail_from_address))
    msg["To"] = to_addr
    msg.set_content(body)

    recipients: list[str] = [to_addr]

    try:
        if settings.smtp_use_ssl:
            log.info(
                "mail: 使用 SMTP_SSL 連線 %s:%s",
                settings.smtp_host,
                settings.smtp_port,
            )
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, context=context, timeout=30
            ) as server:
                _apply_protocol_debug(server)
                log.debug("mail: SMTP_SSL ehlo / 連線建立")
                server.ehlo()
                if settings.smtp_user:
                    log.info(
                        "mail: 嘗試登入 user=%s login=%s",
                        settings.smtp_user,
                        "yes" if settings.smtp_password else "no_password",
                    )
                    if settings.smtp_password:
                        server.login(settings.smtp_user, settings.smtp_password)
                    else:
                        log.warning("mail: SMTP_USER 已設但 SMTP_PASSWORD 為空")
                else:
                    log.info("mail: 未設定 SMTP_USER，略過登入（匿名寄信，多數供應商不允許）")

                log.info(
                    "mail: send_message from=%s recipients=%s",
                    settings.mail_from_address,
                    recipients,
                )
                refused = server.send_message(
                    msg, from_addr=settings.mail_from_address, to_addrs=recipients
                )
                _log_refused(refused)
        else:
            log.info(
                "mail: 使用 SMTP (%s:%s) tls=%s",
                settings.smtp_host,
                settings.smtp_port,
                settings.smtp_use_tls,
            )
            with smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=30
            ) as server:
                _apply_protocol_debug(server)
                log.debug("mail: 建立 TCP 後 EHLO")
                code, resp = server.ehlo()
                log.debug("mail: EHLO code=%s resp=%r", code, _short_bytes(resp))
                if settings.smtp_use_tls:
                    context = ssl.create_default_context()
                    log.info("mail: STARTTLS…")
                    server.starttls(context=context)
                    code, resp = server.ehlo()
                    log.debug("mail: EHLO(post-TLS) code=%s resp=%r", code, _short_bytes(resp))

                if settings.smtp_user:
                    log.info(
                        "mail: 嘗試登入 user=%s password_set=%s",
                        settings.smtp_user,
                        bool(settings.smtp_password),
                    )
                    if settings.smtp_password:
                        server.login(settings.smtp_user, settings.smtp_password)
                    else:
                        log.warning("mail: SMTP_USER 已設但 SMTP_PASSWORD 為空")
                else:
                    log.info("mail: 未設定 SMTP_USER，略過登入")

                log.info(
                    "mail: send_message from=%s recipients=%s",
                    settings.mail_from_address,
                    recipients,
                )
                refused = server.send_message(
                    msg, from_addr=settings.mail_from_address, to_addrs=recipients
                )
                _log_refused(refused)

    except smtplib.SMTPAuthenticationError as e:
        log.error(
            "mail: SMTPAuthenticationError smtp_code=%s smtp_error=%r",
            getattr(e, "smtp_code", None),
            getattr(e, "smtp_error", b""),
        )
        log.debug("mail: traceback\n%s", traceback.format_exc())
        raise
    except smtplib.SMTPRecipientsRefused as e:
        log.error("mail: SMTPRecipientsRefused %r", e.recipients)
        log.debug("mail: traceback\n%s", traceback.format_exc())
        raise
    except smtplib.SMTPServerDisconnected as e:
        log.error(
            "mail: SMTPServerDisconnected (%s)：常見為連線被防火牆斷線、連接埠錯誤、或要先 TLS",
            e,
        )
        log.debug("mail: traceback\n%s", traceback.format_exc())
        raise
    except OSError as e:
        log.error(
            "mail: 網路／DNS 連線錯誤 errno=%s: %s",
            getattr(e, "errno", "?"),
            e,
        )
        log.debug("mail: traceback\n%s", traceback.format_exc())
        raise
    except Exception as e:
        log.exception("mail: 未預期的寄信錯誤 type=%s", type(e).__name__)
        raise

    log.info("mail: 完成寄信流程（伺服器端已收下訊息；收件與垃圾郵件資料夾由供應商決定）")
    return {"to": to_addr, "smtp_host": settings.smtp_host, "from": settings.mail_from_address}


def get_smtp_diagnostic() -> dict:
    """供 GET /api/mail/smtp-diagnostic 使用，不含密碼。"""
    snap = _smtp_config_snapshot()
    ready = smtp_ready()
    hints: list[str] = [
        "GET /smtp-diagnostic 不會連線 SMTP，也不會寄信，只讀取目前 .env 設定。",
    ]
    if not settings.smtp_enabled:
        hints.append("SMTP_ENABLED=false，寄信程式會拒絕執行。")
    if not settings.smtp_host.strip():
        hints.append("SMTP_HOST 為空，請確認 .env 與 uvicorn 啟動目錄。")
    if not settings.mail_from_address.strip():
        hints.append("MAIL_FROM_ADDRESS 為空。")
    if settings.smtp_user and not settings.smtp_password:
        hints.append("已設定 SMTP_USER 但 SMTP_PASSWORD 為空，多數信箱無法認證。")
    elif not settings.smtp_user and settings.smtp_password:
        hints.append("有密碼但無 SMTP_USER，無法 login。")

    host_l = settings.smtp_host.lower()
    if "gmail" in host_l:
        hints.append("Gmail：須開兩步驟驗證，SMTP 密碼請用「應用程式密碼」。")
    if settings.smtp_use_ssl and settings.smtp_use_tls:
        hints.append("同時 smtp_use_ssl 與 smtp_use_tls 為 true 時請再確認（465 多用 SSL_only）。")
    if ready:
        hints.append("設定足以上線；若仍未收到信，可先查垃圾信件匣與供應商寄件紀錄。")

    return {
        "smtp_ready": ready,
        "log_level": settings.log_level,
        "settings": snap,
        "hints": hints,
    }


def _short_bytes(b) -> bytes | str:
    if isinstance(b, bytes):
        head = b[:200]
        return head.decode("utf-8", errors="replace")
    return b


def _log_refused(refused) -> None:
    if refused:
        log.error("mail: send_message 回傳拒收對象 refused=%s", refused)
        raise RuntimeError(f"SMTP 拒絕收件: {refused}")
    log.debug("mail: send_message 無拒收回傳字典（表示此階段未回報部分失敗）")
