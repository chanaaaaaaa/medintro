from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ClinicState, QueueInfo, QueueStatus, TravelMode, User
from app.schemas import QueueRegister

ALLOWED_TRAVEL_MODES = {m.value for m in TravelMode}


def get_clinic_state(db: Session) -> ClinicState:
    row = db.scalar(select(ClinicState).where(ClinicState.id == 1))
    if row is None:
        row = ClinicState(id=1, current_serving_number=0)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def people_before(queue_number: int, current_serving: int) -> int:
    if queue_number > current_serving:
        return max(0, queue_number - current_serving - 1)
    return 0


def next_queue_number(db: Session) -> int:
    m = db.scalar(select(func.max(QueueInfo.queue_number)))
    return (m or 0) + 1


def create_registration(db: Session, payload: QueueRegister) -> tuple[User, QueueInfo, int]:
    if payload.travel_mode not in ALLOWED_TRAVEL_MODES:
        raise ValueError(
            f"travel_mode 必須為: {', '.join(sorted(ALLOWED_TRAVEL_MODES))}"
        )
    if not payload.email and not payload.line_id:
        raise ValueError("email 與 line_id 至少填寫一項")

    user = User(
        name=payload.name,
        email=payload.email,
        line_id=payload.line_id,
    )
    db.add(user)
    db.flush()

    qn = next_queue_number(db)
    queue = QueueInfo(
        user_id=user.id,
        queue_number=qn,
        latitude=payload.latitude,
        longitude=payload.longitude,
        travel_mode=payload.travel_mode,
        uses_dynamic_travel=True,
        status=QueueStatus.waiting.value,
    )
    db.add(queue)
    db.commit()
    db.refresh(user)
    db.refresh(queue)

    clinic = get_clinic_state(db)
    return user, queue, clinic.current_serving_number


def create_registration_from_line(
    db: Session,
    *,
    name: str,
    line_user_id: str,
    latitude: float,
    longitude: float,
    uses_dynamic_travel: bool,
    travel_mode: str = TravelMode.driving.value,
) -> tuple[User, QueueInfo, int]:
    """
    LINE 專用掛號（無 Email）。若不提供 GPS，請傳 latitude=longitude=0 並設 uses_dynamic_travel=False。
    """
    if travel_mode not in ALLOWED_TRAVEL_MODES:
        travel_mode = TravelMode.driving.value

    user = User(name=name.strip()[:120], email=None, line_id=line_user_id.strip())
    db.add(user)
    db.flush()

    qn = next_queue_number(db)
    queue = QueueInfo(
        user_id=user.id,
        queue_number=qn,
        latitude=latitude,
        longitude=longitude,
        travel_mode=travel_mode,
        uses_dynamic_travel=uses_dynamic_travel,
        status=QueueStatus.waiting.value,
    )
    db.add(queue)
    db.commit()
    db.refresh(user)
    db.refresh(queue)

    clinic = get_clinic_state(db)
    return user, queue, clinic.current_serving_number


def get_latest_waiting_queue_by_line_uid(
    db: Session, line_uid: str
) -> tuple[QueueInfo, User] | None:
    stmt = (
        select(QueueInfo, User)
        .join(User, QueueInfo.user_id == User.id)
        .where(
            User.line_id == line_uid.strip(),
            QueueInfo.status == QueueStatus.waiting.value,
        )
        .order_by(QueueInfo.id.desc())
        .limit(1)
    )
    row = db.execute(stmt).first()
    return (row[0], row[1]) if row else None


def get_queue_by_id(db: Session, queue_id: int) -> QueueInfo | None:
    return db.get(QueueInfo, queue_id)


def advance_serving(db: Session) -> int:
    """模擬叫下一位：將 current_serving_number +1（不超過最大已掛號號碼可選，此 POC 僅遞增）。"""
    clinic = get_clinic_state(db)
    clinic.current_serving_number += 1
    db.commit()
    db.refresh(clinic)
    return clinic.current_serving_number
