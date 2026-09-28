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
    webhook_secret: str
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
            webhook_secret=os.getenv("GITHUB_WEBHOOK_SECRET", ""),
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
                    "GITHUB_WEBHOOK_SECRET": settings.webhook_secret,
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


@dataclass(frozen=True)
class DatabaseProvisionSettings:
    """Configuration for per-user databases provisioned on the deployer cluster."""

    enabled: bool
    deployer_url: str
    runtime: str
    default_size_gb: int
    allowed_engines: tuple
    allowed_sizes: tuple
    max_per_user: int
    max_per_project: int
    storage_class: str
    external_host: str
    cost_credits: int

    @classmethod
    def from_env(cls) -> "DatabaseProvisionSettings":
        engines = tuple(
            item.strip()
            for item in os.getenv(
                "DATABASE_ALLOWED_ENGINES", "postgres,mongodb,redis"
            ).split(",")
            if item.strip()
        )
        sizes = tuple(
            int(item.strip())
            for item in os.getenv(
                "DATABASE_ALLOWED_SIZES_GB", "1,5"
            ).split(",")
            if item.strip()
        )
        max_per_user = _env_int_or("DATABASE_MAX_PER_USER", 2)
        max_per_project = _env_int_or("DATABASE_MAX_PER_PROJECT", 1)
        default_size = _env_int_or("DATABASE_DEFAULT_SIZE_GB", 1)
        cost_credits = _env_int_or("DATABASE_COST_CREDITS", 0)

        return cls(
            enabled=_env_bool("DATABASE_PROVISIONING_ENABLED", True),
            deployer_url=os.getenv("DEPLOYER_URL", "http://192.168.68.121:5000").rstrip("/"),
            runtime=os.getenv("APP_RUNTIME", "docker").strip().lower(),
            default_size_gb=default_size,
            allowed_engines=engines,
            allowed_sizes=sizes,
            max_per_user=max_per_user,
            max_per_project=max_per_project,
            storage_class=os.getenv("DATABASE_STORAGE_CLASS", "local-path").strip() or "local-path",
            external_host=os.getenv("DATABASE_EXTERNAL_HOST", "192.168.68.121").strip(),
            cost_credits=cost_credits,
        )


def _env_int_or(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
