from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.crud import (
    advance_serving,
    create_registration,
    get_clinic_state,
    get_queue_by_id,
    people_before,
)
from app.database import get_db
from app.schemas import (
    AdvanceNextResponse,
    QueueHallStatus,
    QueueInfoOut,
    QueueRegister,
    RegisterResponse,
    UserOut,
    WarningScanResult,
)

router = APIRouter(prefix="/api/queue", tags=["queue"])


@router.post("/register", response_model=RegisterResponse)
def register(payload: QueueRegister, db: Session = Depends(get_db)):
    try:
        user, queue, current = create_registration(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    pb = people_before(queue.queue_number, current)
    return RegisterResponse(
        user=UserOut.model_validate(user),
        queue=QueueInfoOut.model_validate(queue),
        clinic_current_number=current,
        people_before_you=pb,
    )


@router.get("/hall/{queue_id}", response_model=QueueHallStatus)
def hall_status(queue_id: int, db: Session = Depends(get_db)):
    q = get_queue_by_id(db, queue_id)
    if q is None:
        raise HTTPException(status_code=404, detail="找不到此掛號紀錄")

    clinic = get_clinic_state(db)
    current = clinic.current_serving_number
    pb = people_before(q.queue_number, current)
    wait_min = pb * 5.0

    return QueueHallStatus(
        current_serving_number=current,
        your_queue_number=q.queue_number,
        people_before_you=pb,
        estimated_wait_minutes=wait_min,
    )


@router.post("/advance-next", response_model=AdvanceNextResponse)
def advance_next(db: Session = Depends(get_db)):
    n = advance_serving(db)
    return AdvanceNextResponse(ok=True, current_serving_number=n)


@router.post("/warning-scan-now", response_model=WarningScanResult)
def warning_scan_now():
    """立即執行一次「時間預警」掃描（與排程共用邏輯），方便本機除錯。"""
    from app.services.warning_job import run_warning_scan

    raw = run_warning_scan()
    return WarningScanResult(**raw)
