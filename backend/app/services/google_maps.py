"""
Google Maps Platform：Geocoding API（診所地址）+ Routes API computeRoutes（交通時間）。
僅後端呼叫，請勿把 API Key 放前端。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx

from app.config import settings

log = logging.getLogger(__name__)

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

ClinicCoords = tuple[float, float]

# 程式啟動後快取 Geocoding 結果，避免每次都打 Geocoding
_clinic_cached: ClinicCoords | None = None


def maps_configured_for_routing() -> bool:
    if not settings.google_maps_api_key.strip():
        return False
    if settings.clinic_latitude is not None and settings.clinic_longitude is not None:
        return True
    if settings.clinic_address.strip():
        return True
    return False


def reset_clinic_cache() -> None:
    """測試用：強制下次重新解析診所座標"""
    global _clinic_cached
    _clinic_cached = None


def _json_preview(obj: object, limit: int = 1200) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    if len(s) > limit:
        return s[:limit] + f"...(+{len(s) - limit} chars)"
    return s


def _maps_should_log_http_body(level: int) -> bool:
    return settings.maps_debug_log_bodies or log.isEnabledFor(level)


def _hint_geocode_status(status: str) -> str:
    hints = {
        "REQUEST_DENIED": "金鑰未啟用 Geocoding API、帳單未開啟或金鑰被 IP/HTTP referrer 檔住了",
        "OVER_QUERY_LIMIT": "配額或頻率已滿／帳務問題",
        "ZERO_RESULTS": "地址無法解析—請確認 CLINIC_ADDRESS 或改用座標",
        "INVALID_REQUEST": "address 參數格式或編碼有誤",
    }
    return hints.get(status, "請對照 Geocoding API 官方 status 說明")


def _hint_routes_http(status_code: int, err: dict | None) -> str:
    msg = ""
    if isinstance(err, dict):
        msg = err.get("message") or ""
    if status_code == 403:
        return "403—常見為金鑰未啟用 Routes API、billing、credentials 類型不符"
    if status_code == 400:
        return f"400—請求 JSON 不符規格或不支援的組合 FieldMask/Message：{msg[:200]}"
    if status_code == 429:
        return "429—配額過高或 rate limit"
    return msg[:300] if msg else f"HTTP {status_code}"


def geocode_address(address: str) -> ClinicCoords:
    """將地址轉為 (lat, lng)。失敗丟 RuntimeError。"""
    key = settings.google_maps_api_key.strip()
    if not key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY 未設定")

    stripped = address.strip()
    if not stripped:
        raise RuntimeError("clinic_address 為空")

    region = settings.maps_region_code.strip() or "TW"
    log.debug(
        "maps geocode→ %s （address≈%.80s / region=%s）",
        _GEOCODE_URL,
        stripped,
        region,
    )

    with httpx.Client(timeout=20.0) as client:
        r = client.get(
            _GEOCODE_URL,
            params={"address": stripped, "region": region, "key": key},
        )
        txt = r.text
        try:
            data = r.json()
        except Exception as e:
            log.error(
                "geocode 回應非 JSON status_code=%s preview=%r",
                r.status_code,
                txt[:500],
            )
            raise RuntimeError("Geocoding 回應不是 JSON") from e

    if _maps_should_log_http_body(logging.DEBUG):
        log.debug("geocode raw preview=%s", _json_preview(data, 800))

    st = data.get("status")
    if st != "OK" or not data.get("results"):
        err_m = data.get("error_message", "")
        hint = _hint_geocode_status(st or "")
        log.error(
            "geocode 失敗 status=%s hint=%s error_message=%s preview=%s",
            st,
            hint,
            err_m,
            _json_preview(data, 600),
        )
        raise RuntimeError(
            f"Geocoding 失敗 status={st} — {hint}. error_message={err_m}"
        )

    loc = data["results"][0]["geometry"]["location"]
    lat, lng = float(loc["lat"]), float(loc["lng"])
    log.info("geocode: ok → (%.5f, %.5f)", lat, lng)
    return lat, lng


def get_clinic_destination() -> ClinicCoords | None:
    """
    診所終點座標：優先 .env 的 CLINIC_LATITUDE/LONGITUDE；否則用 CLINIC_ADDRESS Geocoding（快取）。
    """
    global _clinic_cached

    if _clinic_cached is not None:
        return _clinic_cached

    lat, lng = settings.clinic_latitude, settings.clinic_longitude
    if lat is not None and lng is not None:
        _clinic_cached = (float(lat), float(lng))
        log.info(
            "clinic 座標來自環境變數: (%.5f, %.5f)",
            _clinic_cached[0],
            _clinic_cached[1],
        )
        return _clinic_cached

    addr = settings.clinic_address.strip()
    if not addr:
        return None

    if not settings.google_maps_api_key.strip():
        log.warning("有 CLINIC_ADDRESS 但未設定 GOOGLE_MAPS_API_KEY，無法 Geocoding")
        return None

    _clinic_cached = geocode_address(addr)
    return _clinic_cached


def warm_clinic_coordinates() -> None:
    """啟動時預熱 Geocoding，失敗僅紀錄 log。"""
    try:
        c = get_clinic_destination()
        if c:
            log.info(
                "maps: 診所終點已就緒 (%.5f, %.5f)",
                c[0],
                c[1],
            )
        elif settings.google_maps_api_key.strip():
            log.warning(
                "maps: 請設定 CLINIC_ADDRESS 或 CLINIC_LATITUDE+CLINIC_LONGITUDE "
                "才能計算 Routes"
            )
    except Exception:
        log.exception("maps: Geocoding 診所失敗（將於首次掃描時重試或使用 fallback）")


def _duration_to_minutes(protobuf_duration: str) -> float:
    raw = protobuf_duration.strip()
    if raw.endswith("s"):
        raw = raw[:-1]
    return float(raw) / 60.0


def _travel_mode_to_route_enum(mode: str) -> tuple[str, dict]:
    """
    回傳 (RouteTravelMode, extra_request_body_fields)。
    extra 會 merge 進 computeRoutes JSON body。
    """
    m = mode.lower().strip()
    extras: dict = {}

    if m == "driving":
        return "DRIVE", {
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        }
    if m == "walking":
        return "WALK", {}
    if m == "bicycling":
        return "BICYCLE", {}
    if m == "transit":
        now_z = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        extras["departureTime"] = now_z
        return "TRANSIT", extras

    log.warning("未知 travel_mode=%s，改用 DRIVE", mode)
    return "DRIVE", {"routingPreference": "TRAFFIC_AWARE_OPTIMAL"}


def compute_route_travel_minutes(
    *,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    travel_mode: str,
) -> float:
    """
    Routes API computeRoutes：回傳 route.duration（考量交通／大眾運輸）。
    """
    key = settings.google_maps_api_key.strip()
    if not key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY 未設定")

    travel_enum, extras = _travel_mode_to_route_enum(travel_mode)

    def waypoint(la: float, ln: float) -> dict:
        return {"location": {"latLng": {"latitude": la, "longitude": ln}}}

    body: dict = {
        "origin": waypoint(origin_lat, origin_lng),
        "destination": waypoint(dest_lat, dest_lng),
        "travelMode": travel_enum,
        "languageCode": "zh-TW",
        "regionCode": settings.maps_region_code.strip() or "TW",
    }
    body.update(extras)

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.staticDuration",
    }

    log.debug(
        "routes computeRoutes travelMode=%s origin=(%.4f,%.4f) dest=(%.4f,%.4f) extras=%s",
        travel_enum,
        origin_lat,
        origin_lng,
        dest_lat,
        dest_lng,
        list(extras.keys()),
    )

    with httpx.Client(timeout=25.0) as client:
        r = client.post(_ROUTES_URL, json=body, headers=headers)
        txt = r.text
        try:
            data = r.json()
        except Exception as e:
            log.error(
                "Routes 回應非 JSON status=%s preview=%r",
                r.status_code,
                txt[:600],
            )
            raise RuntimeError(f"Routes API 無法解析 JSON HTTP {r.status_code}") from e

    if not r.is_success:
        err_obj = data.get("error") if isinstance(data, dict) else None
        hint = _hint_routes_http(r.status_code, err_obj if isinstance(err_obj, dict) else None)
        log.error(
            "routes 失敗 HTTP=%s hint=%s error=%s body_preview=%s",
            r.status_code,
            hint,
            err_obj,
            _json_preview(data, 1000),
        )
        raise RuntimeError(
            f"Routes HTTP {r.status_code}: {hint} detail={err_obj or txt[:400]}"
        )

    if _maps_should_log_http_body(logging.DEBUG):
        log.debug("routes success preview=%s", _json_preview(data, 1000))

    routes = data.get("routes") or []
    if not routes:
        log.error(
            "routes 無路線 travelMode=%s origin=(%.4f,%.4f) dest=(%.4f,%.4f) preview=%s",
            travel_enum,
            origin_lat,
            origin_lng,
            dest_lat,
            dest_lng,
            _json_preview(data, 800),
        )
        raise RuntimeError(
            "Routes API 無路線（routes 為空）— 常見：transit 無班次、起訖過遠、或座標在海上"
        )

    dur = routes[0].get("duration")
    if not dur:
        sd = routes[0].get("staticDuration")
        if not sd:
            log.error("routes[0] 無 duration/staticDuration: %s", _json_preview(routes[0]))
            raise RuntimeError(f"Routes 回應無 duration：{routes[0]}")
        dur = sd
        log.debug("routes 使用 staticDuration 代替 duration（可能無即時路況）")

    minutes = _duration_to_minutes(str(dur))
    dist = routes[0].get("distanceMeters")
    log.info(
        "routes: ok duration=%s distanceMeters=%s travel_mode=%s → %.2f min",
        dur,
        dist,
        travel_mode,
        minutes,
    )
    return round(minutes, 2)


def try_refresh_queue_travel_minutes(
    *,
    patient_lat: float,
    patient_lng: float,
    travel_mode: str,
    queue_id: int | None = None,
) -> float | None:
    """若 Maps 未完成設定或呼叫失敗，回傳 None。"""
    label = f"queue_id={queue_id}" if queue_id is not None else "queue=—"

    if not maps_configured_for_routing():
        log.debug("%s maps refresh 略過：Maps 未完成設定（金鑰或診所座標／地址）", label)
        return None

    dest = get_clinic_destination()
    if dest is None:
        log.warning(
            "%s maps refresh 略過：診所終點座標不可用（請檢查 CLINIC_* 與 Geocoding）",
            label,
        )
        return None

    log.debug(
        "%s maps refresh→ patient≈(%.5f,%.5f) dest≈(%.5f,%.5f) mode=%s",
        label,
        patient_lat,
        patient_lng,
        dest[0],
        dest[1],
        travel_mode,
    )

    try:
        return compute_route_travel_minutes(
            origin_lat=patient_lat,
            origin_lng=patient_lng,
            dest_lat=dest[0],
            dest_lng=dest[1],
            travel_mode=travel_mode,
        )
    except Exception as e:
        log.error(
            "%s Routes 計算失敗：%s（若需完整回應：LOG_LEVEL=DEBUG 並設 MAPS_DEBUG_LOG_BODIES=true）",
            label,
            e,
            exc_info=log.isEnabledFor(logging.DEBUG),
        )
        return None
