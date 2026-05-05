from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 預設檔案在「啟動 uvicorn 時的 cwd」底下；建議於 backend 目錄啟動
    database_url: str = "sqlite:///./medintro.db"
    backend_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    log_level: str = "INFO"
    """例如 DEBUG、INFO；除錯郵件時改 DEBUG 可看完整步驟"""

    # --- SMTP（發信）---
    smtp_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False

    mail_from_address: str = ""
    mail_from_name: str = "MedIntro POC"

    mail_test_endpoint_enabled: bool = False

    mail_smtp_protocol_debug: bool = False
    """
    為 True 時，smtplib 會把 SMTP 指令／回應印到 stderr（很吵，僅短暫除錯）。
    環境變數範例：MAIL_SMTP_PROTOCOL_DEBUG=true
    """

    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    line_test_endpoint_enabled: bool = False
    """開放 POST /api/line/test-push（本機連線測試用）"""

    line_static_reminder_minutes: float = 15.0
    """LINE 掛號未提供位置時：預估等候 ≤ 此分鐘數即發預警（固定提前提醒模式）"""

    scheduler_enabled: bool = True
    warning_poll_interval_seconds: int = 60
    """背景掃描候診並判斷是否寄出預警信（秒）；POC 可改 30。"""

    warning_scan_on_startup: bool = True
    """啟動後立即跑第一次 run_warning_scan（APScheduler 區間作業預設需等滿第一個 interval）"""
    warning_travel_minutes_fallback: float = 25.0
    """
    當資料庫尚無預估交通時間（Maps 尚未串）時沿用此數值代入公式：
    「等候分鐘 − 交通分鐘 ≤ 5」則寄信。例：等候 30 分、交通 25 分 → 觸發。
    """

    google_maps_api_key: str = ""
    """GCP API Key（請限制 Routes API + Geocoding API）；僅後端環境變數"""

    clinic_address: str = ""
    """診所地址；若無 CLINIC_LATITUDE/LONGITUDE 將啟動 Geocoding 轉為座標（並快取）"""

    clinic_latitude: float | None = None
    clinic_longitude: float | None = None
    maps_region_code: str = "TW"

    maps_debug_log_bodies: bool = False
    """為 True 時，Geocoding/Routes 失敗或 DEBUG 層級可印出回應摘要（不含 API Key）"""

    ngrok_enabled: bool = False
    """本機 POC：啟動時自動開 ngrok 隧道（勿用於正式上线）"""

    ngrok_authtoken: str = ""
    ngrok_listen_port: int = 8000
    """須與 uvicorn --port 相同，否則轉發會連錯埠"""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]


settings = Settings()
