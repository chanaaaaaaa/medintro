"""開發用：用 pyngrok 自動對外公開本機連接埠（與 LINE Webhook / 測試用）。"""

from __future__ import annotations

import logging

from app.config import settings

log = logging.getLogger(__name__)


def start_ngrok() -> str:
    """
    建立 HTTP tunnel 至本機 NGROK_LISTEN_PORT。
    取得 Authtoken：https://dashboard.ngrok.com/get-started/your-authtoken
    """
    port = settings.ngrok_listen_port
    token = settings.ngrok_authtoken.strip()
    if not token:
        raise RuntimeError("已啟用 NGROK_ENABLED 但未設定 NGROK_AUTHTOKEN")

    from pyngrok import conf, ngrok

    conf.get_default().auth_token = token

    try:
        ngrok.kill()
    except Exception:
        pass

    tunnel = ngrok.connect(port, "http")
    url = getattr(tunnel, "public_url", "") or ""
    url = url.strip()
    if not url:
        raise RuntimeError("pyngrok 未傳回 public_url")
    log.info(
        "ngrok 隧道已建立 → %s （轉發至本機連接埠 %s）",
        url,
        port,
    )
    log.info("請將 LINE Webhook 設為：%s/api/line/webhook", url.rstrip("/"))
    return url.rstrip("/")


def stop_ngrok() -> None:
    if not settings.ngrok_enabled:
        return
    try:
        from pyngrok import ngrok

        ngrok.kill()
        log.info("ngrok 已關閉")
    except Exception:
        log.exception("ngrok 關閉時發生例外（可忽略）")
