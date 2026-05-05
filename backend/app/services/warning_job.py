"""
動態時間預警：掃描候診，符合條件則 Email／LINE 通知。

- uses_dynamic_travel=True：等候分鐘 − 交通分鐘 ≤ 5（交通來自 Maps／fallback）
- uses_dynamic_travel=False（LINE 未提供位置）：預估等候 ≤ LINE_STATIC_REMINDER_MINUTES 即通知
"""

from __future__ import annotations

import logging
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.crud import get_clinic_state, people_before
from app.database import SessionLocal
from app.models import QueueInfo, QueueStatus
from app.services.google_maps import (
    maps_configured_for_routing,
    try_refresh_queue_travel_minutes,
)
from app.services.line_messaging import line_messaging_ready, push_text
from app.services.mail import send_plain_email, smtp_ready

log = logging.getLogger(__name__)


def run_warning_scan() -> dict:
    stats = {
        "scanned": 0,
        "notified": 0,
        "skipped_condition": 0,
        "skipped_no_contact": 0,
        "skipped_notifier_off": 0,
        "errors": 0,
        "lines": [],
    }

    if not settings.scheduler_enabled:
        stats["lines"].append("SCHEDULER_ENABLED=false，跳過本次掃描")
        log.info("warning_scan: scheduler 停用，略過")
        return stats

    smtp_on = smtp_ready()
    line_on = line_messaging_ready()
    if not smtp_on and not line_on:
        stats["lines"].append(
            "通知通道：SMTP 與 LINE 皆未就緒（至少需啟用其一）"
        )
        log.warning(
            "warning_scan: SMTP 與 LINE Messaging 皆未設定，僅更新交通／門檻判斷，不會發送"
        )

    db: Session = SessionLocal()
    try:
        clinic = get_clinic_state(db)
        current = clinic.current_serving_number

        stmt = (
            select(QueueInfo)
            .where(
                QueueInfo.status == QueueStatus.waiting.value,
                QueueInfo.notification_sent.is_(False),
            )
            .options(joinedload(QueueInfo.user))
        )
        rows = list(db.scalars(stmt).unique().all())
        stats["scanned"] = len(rows)

        static_threshold = float(settings.line_static_reminder_minutes)

        for q in rows:
            u = q.user
            pb = people_before(q.queue_number, current)
            wait_min = float(pb * 5)

            dynamic = getattr(q, "uses_dynamic_travel", True)
            used_routes_api = False

            travel: float | None = None
            gap: float | None = None

            if dynamic and maps_configured_for_routing():
                refreshed = try_refresh_queue_travel_minutes(
                    patient_lat=q.latitude,
                    patient_lng=q.longitude,
                    travel_mode=q.travel_mode,
                    queue_id=q.id,
                )
                if refreshed is not None:
                    q.estimated_travel_time_minutes = refreshed
                    used_routes_api = True
                elif maps_configured_for_routing():
                    log.info(
                        "warning_scan queue_id=%s Maps 未取得交通（見 google_maps log）",
                        q.id,
                    )

            if dynamic:
                if q.estimated_travel_time_minutes is None:
                    q.estimated_travel_time_minutes = float(
                        settings.warning_travel_minutes_fallback
                    )

                travel = float(q.estimated_travel_time_minutes)
                gap = wait_min - travel
                should_notify = gap <= 5
            else:
                travel = None
                gap = None
                should_notify = wait_min <= static_threshold

            db.commit()

            if not should_notify:
                stats["skipped_condition"] += 1
                if dynamic:
                    log.info(
                        "warning_scan 略過 queue_id=%s wait=%s travel=%s gap=%s（動態門檻未達）",
                        q.id,
                        wait_min,
                        travel,
                        gap,
                    )
                else:
                    log.info(
                        "warning_scan 略過 queue_id=%s wait=%s（固定模式，候診>%s 分）",
                        q.id,
                        wait_min,
                        static_threshold,
                    )
                continue

            has_email = bool(u and u.email and str(u.email).strip())
            has_line_uid = bool(u and u.line_id and str(u.line_id).strip())

            if not has_email and not has_line_uid:
                stats["skipped_no_contact"] += 1
                stats["lines"].append(f"queue_id={q.id} 無聯絡方式")
                continue

            can_mail = has_email and smtp_on
            can_line = has_line_uid and line_on

            if not can_mail and not can_line:
                stats["skipped_notifier_off"] += 1
                stats["lines"].append(
                    f"queue_id={q.id} 通道未就緒；dynamic={dynamic}"
                )
                continue

            if dynamic and travel is not None:
                travel_note = (
                    "預估交通時間來源：Google Routes。\n"
                    if used_routes_api
                    else "預估交通時間來源：資料庫／系統代入。\n"
                )
                notify_ctx = (
                    f"動態門檻：等候 {wait_min:.0f} 分、交通約 {travel:.0f} 分（gap={gap:.1f}）。\n"
                    f"{travel_note}"
                )
            else:
                notify_ctx = (
                    "固定預警：您先前未分享位置——"
                    f"當預估等候約 **{static_threshold:.0f} 分鐘內**即通知。\n"
                )

            short_body = (
                f"{u.name} 您好，\n"
                f"目前叫號 **{current}**，您的號碼 **{q.queue_number}**。\n"
                f"{notify_ctx}"
                "**建議儘速前往診所或依現場安排。**"
            )
            subject = (
                f"[MedIntro] 看診號碼 {q.queue_number} 即將輪到，建議準備／出發"
            )
            long_body = (
                f"{u.name} 您好，\n\n"
                f"診間叫號：{current}，您的號碼：{q.queue_number}。\n"
                f"預估尚須等候約 {wait_min:.0f} 分鐘。\n\n"
                f"{notify_ctx}\n"
                "祝順利。\n"
            )

            sent_any = False
            last_err: Exception | None = None

            if can_mail:
                log.info(
                    "warning_scan: Email queue_id=%s dynamic=%s",
                    q.id,
                    dynamic,
                )
                try:
                    send_plain_email(
                        to_addr=u.email.strip(),
                        subject=subject,
                        body=long_body,
                    )
                    sent_any = True
                except Exception as e:
                    last_err = e
                    stats["errors"] += 1
                    log.exception("warning_scan: Email queue_id=%s 失敗", q.id)

            if can_line:
                log.info("warning_scan: LINE queue_id=%s", q.id)
                try:
                    push_text(to_user_id=u.line_id.strip(), text=short_body)
                    sent_any = True
                except Exception as e:
                    last_err = e
                    stats["errors"] += 1
                    log.exception("warning_scan: LINE queue_id=%s 失敗", q.id)

            if sent_any:
                q.notification_sent = True
                db.commit()
                stats["notified"] += 1
                stats["lines"].append(
                    f"已通知 queue_id={q.id}（Email={'Y' if can_mail else 'N'} LINE={'Y' if can_line else 'N'}）"
                )
            else:
                if last_err:
                    db.rollback()
                stats["skipped_notifier_off"] += 1
                stats["lines"].append(
                    f"queue_id={q.id} 通知全失敗"
                )

        log.info(
            "warning_scan done scanned=%s notified=%s …",
            stats["scanned"],
            stats["notified"],
        )

    finally:
        db.close()

    return stats
