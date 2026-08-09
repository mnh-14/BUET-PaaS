"""Runtime configuration for optional deployment security scanning."""

import os
from dataclasses import dataclass

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
