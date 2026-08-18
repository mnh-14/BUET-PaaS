"""GitHub App authentication and API operations. Tokens are never persisted."""

import time
from pathlib import Path
from typing import Any

import jwt
import requests

from config import GitHubAppSettings


API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"


class GitHubAppError(RuntimeError):
    pass


class GitHubAccessError(GitHubAppError):
    pass


class GitHubAppService:
    def __init__(
        self,
        settings: GitHubAppSettings,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings
        self.session = session or requests.Session()

    def generate_app_jwt(self) -> str:
        try:
            private_key = Path(self.settings.private_key_path).expanduser().read_text()
        except OSError as exc:
            raise GitHubAppError("GitHub App private key is unavailable") from exc
        now = int(time.time())
        return jwt.encode(
            {"iat": now - 60, "exp": now + 9 * 60, "iss": self.settings.app_id},
            private_key,
            algorithm="RS256",
        )

    def create_installation_token(
        self, installation_id: int, repository_id: int | None = None
    ) -> str:
        payload = {"repository_ids": [repository_id]} if repository_id else None
        response = self._request(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            token=self.generate_app_jwt(),
            json=payload,
        )
        token = response.get("token")
        if not token:
            raise GitHubAppError("GitHub did not return an installation token")
        return str(token)

    def get_installation(self, installation_id: int) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/app/installations/{installation_id}",
            token=self.generate_app_jwt(),
        )

    def list_installation_repositories(self, installation_id: int) -> list[dict[str, Any]]:
        token = self.create_installation_token(installation_id)
        payload = self._request(
            "GET", "/installation/repositories", token=token, params={"per_page": 100}
        )
        return list(payload.get("repositories", []))

    def get_repository(
        self, installation_id: int, full_name: str, repository_id: int | None = None
    ) -> dict[str, Any]:
        token = self.create_installation_token(installation_id, repository_id)
        return self._request("GET", f"/repos/{full_name}", token=token)

    def list_branches(
        self, installation_id: int, full_name: str, repository_id: int
    ) -> list[dict[str, Any]]:
        token = self.create_installation_token(installation_id, repository_id)
        return self._request(
            "GET", f"/repos/{full_name}/branches", token=token, params={"per_page": 100}
        )

    def resolve_branch_head(
        self, installation_id: int, full_name: str, repository_id: int, branch: str
    ) -> str:
        token = self.create_installation_token(installation_id, repository_id)
        payload = self._request(
            "GET", f"/repos/{full_name}/branches/{branch}", token=token
        )
        try:
            return str(payload["commit"]["sha"])
        except (KeyError, TypeError) as exc:
            raise GitHubAppError("GitHub branch response did not include a commit SHA") from exc

    def verify_repository_access(
        self, installation_id: int, repository_id: int
    ) -> dict[str, Any]:
        repositories = self.list_installation_repositories(installation_id)
        for repository in repositories:
            if int(repository.get("id", -1)) == repository_id:
                return repository
        raise GitHubAccessError("Repository is not accessible to this GitHub installation")

    def exchange_oauth_code(self, code: str) -> str:
        try:
            response = self.session.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                json={
                    "client_id": self.settings.client_id,
                    "client_secret": self.settings.client_secret,
                    "code": code,
                    "redirect_uri": self.settings.callback_url,
                },
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GitHubAppError("GitHub OAuth exchange failed") from exc
        token = payload.get("access_token")
        if not token:
            raise GitHubAppError("GitHub OAuth authorization was not granted")
        return str(token)

    def get_user(self, user_token: str) -> dict[str, Any]:
        return self._request("GET", "/user", token=user_token)

    def list_user_installations(self, user_token: str) -> list[dict[str, Any]]:
        payload = self._request(
            "GET", "/user/installations", token=user_token, params={"per_page": 100}
        )
        return list(payload.get("installations", []))

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = self.session.request(
                method,
                f"{API_ROOT}{path}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": API_VERSION,
                },
                params=params,
                json=json,
                timeout=20,
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status in {401, 403, 404}:
                raise GitHubAccessError("GitHub App access was denied or revoked") from exc
            raise GitHubAppError("GitHub API request failed") from exc
        except (requests.RequestException, ValueError) as exc:
            raise GitHubAppError("GitHub API is unavailable") from exc
