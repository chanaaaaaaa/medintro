from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_config import configure_logging
from app.database import SessionLocal, engine
from app.database_schema import ensure_sqlite_columns
from app.api.routes.mail import router as mail_router
from app.api.routes.maps import router as maps_router
from app.api.routes.queue import router as queue_router
from app.api.routes.line import router as line_router
from app.models import Base

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log = logging.getLogger(__name__)
    app.state.ngrok_public_url = None

    Base.metadata.create_all(bind=engine)
    ensure_sqlite_columns()
    db = SessionLocal()
    try:
        from app.crud import get_clinic_state

        get_clinic_state(db)
    finally:
        db.close()

    from app.services.google_maps import warm_clinic_coordinates

    warm_clinic_coordinates()

    if settings.ngrok_enabled:
        try:
            from app.services.ngrok_tunnel import start_ngrok

            app.state.ngrok_public_url = start_ngrok()
        except Exception:
            log.exception(
                "ngrok 自動啟動失敗（請確認 NGROK_AUTHTOKEN、埠 NGROK_LISTEN_PORT 與 uvicorn --port 一致）"
            )

    sched = None
    if settings.scheduler_enabled:
        from apscheduler.schedulers.background import BackgroundScheduler

        from app.services.warning_job import run_warning_scan

        sched = BackgroundScheduler(daemon=True)
        sched.add_job(
            run_warning_scan,
            "interval",
            seconds=settings.warning_poll_interval_seconds,
            id="queue_warning_scan",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        sched.start()
        log.info(
            "warning 排程：每 %ss 觸發一次（另可在啟動時先跑一輪，見 WARNING_SCAN_ON_STARTUP）",
            settings.warning_poll_interval_seconds,
        )

        if settings.warning_scan_on_startup:
            try:
                log.info("warning 啟動後立即執行第一次 run_warning_scan …")
                run_warning_scan()
                log.info("warning 啟動後首次掃描已結束（後續交由排程間隔觸發）")
            except Exception:
                log.exception("warning 啟動後首次掃描失敗（不影響服務與後續排程）")

    yield

    if sched is not None and sched.running:
        sched.shutdown(wait=False)

    try:
        from app.services.ngrok_tunnel import stop_ngrok

        stop_ngrok()
    except Exception:
        log.exception("ngrok 關閉時例外")


app = FastAPI(title="MedIntro POC", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(queue_router)
app.include_router(maps_router)
app.include_router(mail_router)
app.include_router(line_router)


@app.get("/")
def root():
    """瀏覽器直接開 http://127.0.0.1:8000/ 時有路徑可讀；API 請用 /api/..."""
    return {
        "service": "MedIntro POC",
        "message": "後端運作中",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/health",
        "api": {
            "register": "POST /api/queue/register",
            "hall": "GET /api/queue/hall/{queue_id}",
            "advance_next": "POST /api/queue/advance-next",
            "warning_scan": "POST /api/queue/warning-scan-now（預警掃描，與排程同源）",
            "maps_clinic": "GET /api/maps/clinic-status",
            "mail_test": "POST /api/mail/test-send（需 MAIL_TEST_ENDPOINT_ENABLED=true）",
            "mail_diagnostic": "GET /api/mail/smtp-diagnostic（同上）",
            "line_webhook": "POST /api/line/webhook（或用 GET /api/ngrok/status 取完整網址）",
            "line_test_push": "POST /api/line/test-push（需 LINE_TEST_ENDPOINT_ENABLED=true）",
            "ngrok_status": "GET /api/ngrok/status（自動隧道開啟時）",
        },
    }


@app.get("/api/ngrok/status")
def ngrok_tunnel_status(req: Request):
    """自動 pyngrok 隧道對外網址與 LINE Webhook 絕對路径。"""
    base = getattr(req.app.state, "ngrok_public_url", None)
    if not base:
        return {
            "ngrok_autostart": settings.ngrok_enabled,
            "public_base_url": None,
            "line_webhook_url": None,
            "forward_to_port": settings.ngrok_listen_port,
            "hint": "未建立隧道：設 NGROK_ENABLED=true 與 NGROK_AUTHTOKEN，且埠與 uvicorn 一致",
        }
    b = str(base).rstrip("/")
    return {
        "ngrok_autostart": True,
        "public_base_url": b,
        "line_webhook_url": f"{b}/api/line/webhook",
        "forward_to_port": settings.ngrok_listen_port,
    }


@app.get("/health")
def health():
    return {"status": "ok"}
