import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class QueueStatus(str, enum.Enum):
    waiting = "waiting"
    serving = "serving"
    done = "done"
    cancelled = "cancelled"


class TravelMode(str, enum.Enum):
    driving = "driving"
    transit = "transit"
    bicycling = "bicycling"
    walking = "walking"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    line_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    queue_entries: Mapped[list["QueueInfo"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class QueueInfo(Base):
    __tablename__ = "queue_info"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    queue_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    travel_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TravelMode.driving.value
    )

    estimated_travel_time_minutes: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    uses_dynamic_travel: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    """True：用 GPS+Maps 做「等候−交通≤5」；False：LINE 未提供位置時改「等候≤N 分鐘」提醒"""

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=QueueStatus.waiting.value, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="queue_entries")


class ClinicState(Base):
    """Singleton row：診所目前叫到的號碼（用於計算排在前面的人數）。"""

    __tablename__ = "clinic_state"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    current_serving_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
