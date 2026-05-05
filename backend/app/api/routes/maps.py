import logging

from fastapi import APIRouter

from app.config import settings
from app.schemas import MapClinicStatus
from app.services import google_maps as gm

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/maps", tags=["maps"])


@router.get("/clinic-status", response_model=MapClinicStatus)
def clinic_status():
    """不含 API Key；確認診所終點是否已解析。"""
    has_key = bool(settings.google_maps_api_key.strip())
    msg = ""
    lat = lng = None
    src = "unresolved"

    if not has_key:
        return MapClinicStatus(
            api_key_configured=False,
            routing_ready=False,
            message="未設定 GOOGLE_MAPS_API_KEY",
            clinic_source=src,
        )

    env_lat = settings.clinic_latitude
    env_lng = settings.clinic_longitude
    if env_lat is not None and env_lng is not None:
        lat, lng = float(env_lat), float(env_lng)
        src = "env_coords"
        msg = "診所座標來自環境變數"
    elif settings.clinic_address.strip():
        try:
            c = gm.get_clinic_destination()
            if c:
                lat, lng = c[0], c[1]
                src = "geocoded_address"
                msg = "診所座標來自 Geocoding（已快取）"
        except Exception as e:
            log.exception("clinic-status geocode error")
            return MapClinicStatus(
                api_key_configured=True,
                routing_ready=False,
                message=str(e),
                clinic_source="unresolved",
            )
    else:
        msg = "請設定 CLINIC_ADDRESS 或 CLINIC_LATITUDE+CLINIC_LONGITUDE"

    ready = lat is not None and lng is not None
    if ready:
        lat = round(lat, 4)
        lng = round(lng, 4)

    return MapClinicStatus(
        api_key_configured=True,
        routing_ready=ready,
        clinic_latitude=lat,
        clinic_longitude=lng,
        clinic_source=src,
        message=msg,
    )
