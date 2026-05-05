from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class QueueRegister(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr | None = None
    line_id: str | None = Field(None, max_length=128)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    travel_mode: str = Field(
        ...,
        description="driving | transit | bicycling | walking（汽車/機車皆用 driving）",
    )


class UserOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    email: str | None
    line_id: str | None
    created_at: datetime


class QueueInfoOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    queue_number: int
    latitude: float
    longitude: float
    travel_mode: str
    estimated_travel_time_minutes: float | None
    notification_sent: bool
    uses_dynamic_travel: bool
    status: str
    created_at: datetime
    updated_at: datetime


class RegisterResponse(BaseModel):
    user: UserOut
    queue: QueueInfoOut
    clinic_current_number: int
    people_before_you: int


class QueueHallStatus(BaseModel):
    current_serving_number: int
    your_queue_number: int
    people_before_you: int
    estimated_wait_minutes: float


class AdvanceNextResponse(BaseModel):
    ok: bool
    current_serving_number: int


class WarningScanResult(BaseModel):
    scanned: int
    notified: int
    skipped_condition: int
    skipped_no_contact: int
    """使用者既無 email 也無 line_user_id（理論上不應發生）"""

    skipped_notifier_off: int
    """有聯絡方式但 SMTP／LINE 後端未就緒，或兩路皆送失敗前的分類（見 lines）"""

    errors: int
    lines: list[str]


class MapClinicStatus(BaseModel):
    api_key_configured: bool
    routing_ready: bool
    clinic_latitude: float | None = None
    clinic_longitude: float | None = None
    """僅約略座標方便除錯；完整精度僅伺服器內部使用"""

    clinic_source: str = ""
    """env_coords | geocoded_address | unresolved"""

    message: str = ""
