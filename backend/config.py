"""Runtime configuration for optional deployment security scanning."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SonarSettings:
    enabled: bool
    host_url: str
    token: str
    scanner_bin: str
    scan_timeout: int

    @classmethod
    def from_env(cls) -> "SonarSettings":
        try:
            timeout = int(os.getenv("SONAR_SCAN_TIMEOUT", "300"))
        except ValueError as exc:
            raise ValueError("SONAR_SCAN_TIMEOUT must be an integer") from exc
        if timeout <= 0:
            raise ValueError("SONAR_SCAN_TIMEOUT must be greater than zero")

        return cls(
            enabled=_env_bool("SONAR_ENABLED", True),
            host_url=os.getenv(
                "SONAR_HOST_URL", "http://192.168.67.252:9000"
            ).rstrip("/"),
            token=os.getenv("SONAR_TOKEN", ""),
            scanner_bin=os.getenv("SONAR_SCANNER_BIN", "sonar-scanner"),
            scan_timeout=timeout,
        )


@dataclass(frozen=True)
class GitHubAppSettings:
    app_id: str
    client_id: str
    client_secret: str
    app_slug: str
    private_key_path: str
    callback_url: str
    install_url: str
    frontend_url: str
    session_secret: str

    @classmethod
    def from_env(cls, *, require_complete: bool = False) -> "GitHubAppSettings":
        settings = cls(
            app_id=os.getenv("GITHUB_APP_ID", ""),
            client_id=os.getenv("GITHUB_APP_CLIENT_ID", ""),
            client_secret=os.getenv("GITHUB_APP_CLIENT_SECRET", ""),
            app_slug=os.getenv("GITHUB_APP_SLUG", ""),
            private_key_path=os.getenv("GITHUB_APP_PRIVATE_KEY_PATH", ""),
            callback_url=os.getenv("GITHUB_CALLBACK_URL", ""),
            install_url=os.getenv("GITHUB_INSTALL_URL", ""),
            frontend_url=os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/"),
            session_secret=os.getenv("SESSION_SECRET", ""),
        )
        if require_complete:
            missing = [
                name
                for name, value in {
                    "GITHUB_APP_ID": settings.app_id,
                    "GITHUB_APP_CLIENT_ID": settings.client_id,
                    "GITHUB_APP_CLIENT_SECRET": settings.client_secret,
                    "GITHUB_APP_SLUG": settings.app_slug,
                    "GITHUB_APP_PRIVATE_KEY_PATH": settings.private_key_path,
                    "GITHUB_CALLBACK_URL": settings.callback_url,
                    "SESSION_SECRET": settings.session_secret,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(f"Missing GitHub App configuration: {', '.join(missing)}")
            key_path = Path(settings.private_key_path).expanduser()
            if not key_path.is_file():
                raise ValueError("GITHUB_APP_PRIVATE_KEY_PATH does not reference a readable file")
        return settings
