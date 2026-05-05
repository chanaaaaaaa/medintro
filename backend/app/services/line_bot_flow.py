"""LINE OA 對話：掛號（姓名→位置／不提供）、查詢候診。"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass

from app.config import settings
from app.crud import (
    create_registration_from_line,
    get_clinic_state,
    get_latest_waiting_queue_by_line_uid,
    people_before,
)
from app.database import SessionLocal
from app.services.line_messaging import (
    quick_reply_registration_location,
    reply_text,
)

log = logging.getLogger(__name__)

LINE_TEXT_NO_GPS = "【掛號】不提供位置"


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").strip()


def _is_register_cmd(t: str) -> bool:
    x = _nfc(t).lower().replace(" ", "")
    return x in {"掛號", "挂号", "我要掛號", "我要挂号", "開始掛號", "開始挂号", "📋掛號"}


def _is_query_cmd(t: str) -> bool:
    x = _nfc(t).lower().replace(" ", "")
    return x in {"查詢", "查询", "進度", "进度", "候診", "候诊", "叫號", "叫号", "狀態", "状态", "📋查詢"}


@dataclass
class LineRegDraft:
    step: str = "idle"  # idle | wait_name | wait_location
    name: str | None = None


_draft_map: dict[str, LineRegDraft] = {}


def _get_draft(uid: str) -> LineRegDraft:
    if uid not in _draft_map:
        _draft_map[uid] = LineRegDraft()
    return _draft_map[uid]


def _clear_draft(uid: str) -> None:
    _draft_map.pop(uid, None)


def welcome_message() -> str:
    mins = settings.line_static_reminder_minutes
    return (
        "歡迎使用 MedIntro 候診助手（POC）。\n\n"
        "📌 「掛號」—線上掛號，可選擇是否分享位置以利動態預估抵達。\n"
        f"📌 若不分享位置：將在預估等候約 **{mins:.0f} 分鐘內**發提醒（固定提前模式）。\n"
        "📌 「查詢」—查目前叫號與您的預估等候。\n\n"
        "請直接傳上述關鍵字開始。"
    )


def _reply_progress(uid: str, reply_token: str) -> None:
    db = SessionLocal()
    try:
        clinic = get_clinic_state(db)
        current = clinic.current_serving_number

        pair = get_latest_waiting_queue_by_line_uid(db, uid)
        if not pair:
            reply_text(
                reply_token=reply_token,
                text="查無等候中的掛號紀錄。傳「掛號」可重新掛號。",
            )
            return

        queue, user = pair
        pb = people_before(queue.queue_number, current)
        wait_min = pb * 5.0
        mode = (
            "動態預警（GPS+路程）"
            if queue.uses_dynamic_travel
            else f"固定提前（預估等候 ≤ {settings.line_static_reminder_minutes:.0f} 分時提醒）"
        )

        txt = (
            f"您好 {user.name}，\n"
            f"目前診間叫號：**{current}**\n"
            f"您的號碼：**{queue.queue_number}**\n"
            f"在您之前估計：**{pb}** 位（約 **{wait_min:.0f}** 分）\n"
            f"候診 id：`{queue.id}`\n"
            f"預警模式：{mode}\n"
            "祝候診順利。"
        )
        reply_text(reply_token=reply_token, text=txt)
    finally:
        db.close()


def _finalize_register(
    uid: str,
    reply_token: str,
    *,
    lat: float,
    lng: float,
    uses_dynamic_travel: bool,
) -> None:
    draft = _get_draft(uid)
    name = draft.name or "未填姓名"

    db = SessionLocal()
    try:
        user, queue, cur = create_registration_from_line(
            db,
            name=name,
            line_user_id=uid,
            latitude=lat,
            longitude=lng,
            uses_dynamic_travel=uses_dynamic_travel,
        )
        pb = people_before(queue.queue_number, cur)
        wait_hint = pb * 5

        gps_line = (
            "已收到位置，將以動態路程估算配合候診預警。"
            if uses_dynamic_travel
            else (
                f"未使用位置；當預估等候約 **{settings.line_static_reminder_minutes:.0f} 分鐘內**"
                "時會提醒您（固定提前模式）。"
            )
        )

        txt = (
            f"✅ {user.name} 掛號成功！\n"
            f"您的號碼：**{queue.queue_number}**\n"
            f"候診 id：`{queue.id}`\n"
            f"在您之前約 **{pb}** 人（估 **{wait_hint:.0f}** 分）\n"
            f"{gps_line}\n\n"
            "隨時可傳「查詢」看最新進度。"
        )
        reply_text(reply_token=reply_token, text=txt)
    except Exception:
        log.exception("LINE finalize register")
        reply_text(
            reply_token=reply_token,
            text="掛號暫時失敗，請稍後再試或洽櫃台。",
        )
    finally:
        db.close()

    _clear_draft(uid)


def handle_follow(reply_token: str) -> None:
    reply_text(reply_token=reply_token, text=welcome_message())


def handle_line_event(ev: dict) -> None:
    """處理 type=message（replyToken 僅可使用一次）。"""
    reply_token = ev.get("replyToken")
    src = ev.get("source") or {}
    uid = src.get("userId")
    if not reply_token or not uid:
        return

    msg = ev.get("message") or {}
    mtype = msg.get("type")
    draft = _get_draft(uid)

    if mtype == "location":
        if draft.step != "wait_location":
            reply_text(
                reply_token=reply_token,
                text="請先傳「掛號」並輸入姓名後，再傳定位。",
            )
            return

        lat = float(msg["latitude"])
        lng = float(msg["longitude"])
        _finalize_register(
            uid,
            reply_token,
            lat=lat,
            lng=lng,
            uses_dynamic_travel=True,
        )
        return

    if mtype != "text":
        return

    text_raw = msg.get("text") or ""

    if _is_query_cmd(text_raw):
        _reply_progress(uid, reply_token)
        return

    if _nfc(text_raw) == _nfc(LINE_TEXT_NO_GPS) or LINE_TEXT_NO_GPS in text_raw:
        if draft.step != "wait_location":
            reply_text(
                reply_token=reply_token,
                text=(
                    "請先輸入「掛號」後依序完成。「不提供」請在詢問位置的步驟使用"
                    f"（Quick Reply 或完整複製：{LINE_TEXT_NO_GPS}）。"
                ),
            )
            return

        _finalize_register(
            uid,
            reply_token,
            lat=0.0,
            lng=0.0,
            uses_dynamic_travel=False,
        )
        return

    if _is_register_cmd(text_raw):
        draft.step = "wait_name"
        draft.name = None
        reply_text(
            reply_token=reply_token,
            text=(
                "好的，開始掛號。\n請**直接傳一行文字**：您的「姓名」（1～30 個字為佳）。"
            ),
        )
        return

    if draft.step == "wait_name":
        name = text_raw.strip()
        if len(name) < 1 or len(name) > 120:
            reply_text(
                reply_token=reply_token,
                text="請輸入合理的姓名長度後再試。",
            )
            return
        draft.name = name[:120]
        draft.step = "wait_location"

        body = (
            f"{name} 您好。\n下一步請擇一：\n\n"
            "1️⃣ **分享 GPS**：輸入欄「＋」→「位置資訊」傳您目前所在——"
            "用於路程預估與「等候 − 路程 ≤ 5 分鐘」動態預警。\n\n"
            f"2️⃣ **不提供**：點下方 Quick Reply；系統將在**預估等候約 "
            f"{settings.line_static_reminder_minutes:.0f} 分鐘內**提醒您（固定提前）。"
        )
        reply_text(
            reply_token=reply_token,
            text=body,
            quick_reply=quick_reply_registration_location(),
        )
        return

    if draft.step == "wait_location":
        reply_text(
            reply_token=reply_token,
            text=(
                "請傳「位置訊息」，或發送 Quick Reply／以下整段文字：\n"
                f"{LINE_TEXT_NO_GPS}"
            ),
        )
        return

    reply_text(
        reply_token=reply_token,
        text=welcome_message() + "\n\n（可先傳「掛號」或「查詢」）",
    )


def flush_event(ev: dict) -> None:
    et = ev.get("type")
    if et == "follow":
        rt = ev.get("replyToken")
        if rt:
            handle_follow(rt)
        return
    if et == "message":
        handle_line_event(ev)
        return
    log.debug("LINE 忽略事件 type=%s", et)
