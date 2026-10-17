import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    frontend_origin: str
    cookie_secure: bool
    session_seconds: int
    cookie_name: str = "grading_session"
    cookie_path: str = "/api"
    storage_root: Path = Path(os.getenv('STORAGE_ROOT', str(Path(__file__).resolve().parents[2] / '.storage')))
    max_file_bytes: int = int(os.getenv('MAX_FILE_MB','50')) * 1024 * 1024
    max_upload_files: int = int(os.getenv('MAX_UPLOAD_FILES','20'))
    max_archive_entries: int = int(os.getenv('MAX_ARCHIVE_ENTRIES','1000'))
    max_extracted_bytes: int = int(os.getenv('MAX_EXTRACTED_MB','200')) * 1024 * 1024
    login_ip_limit: int = int(os.getenv('LOGIN_IP_LIMIT','60'))
    login_account_limit: int = int(os.getenv('LOGIN_ACCOUNT_LIMIT','10'))
    login_window_seconds: int = int(os.getenv('LOGIN_WINDOW_SECONDS','300'))


settings = Settings(
    database_url=os.getenv("DATABASE_URL", "postgresql://grading:grading_dev_only@localhost:5432/grading"),
    frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
    cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    session_seconds=int(os.getenv("SESSION_HOURS", "8")) * 3600,
)
