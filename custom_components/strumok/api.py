"""HTTP-клієнт локального API плати СтрумОК.

Навмисно без залежності від `homeassistant` — лише `aiohttp`, щоб і config
flow, і координатор ходили в плату одним шляхом, а розбір відповідей можна
було тестувати окремо.

Поведінка плати (LOCAL-AUTONOMY-CONTRACT §3.2, §4; `webpanel.cpp`):
- `GET /api` — стан; при закритому читанні (`ropen=0`) без ключа → 401 `{error:"auth"}`;
- `POST /api/evse/cmd` — команда зарядці: 200 / 409 (`no_charger`) / 422
  (`invalid` з `fields` або `empty`) / 401 (`auth`); старі прошивки → 404;
- ключ API — `Authorization: Bearer sk_…`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .auth import auth_headers
from .const import API_PATH, CMD_PATH, DEFAULT_PORT, REQUEST_TIMEOUT


class StrumokError(Exception):
    """Базова помилка звернення до плати."""


class StrumokConnectionError(StrumokError):
    """Плата не відповіла, відповіла не JSON-ом або неочікуваним кодом."""


class StrumokAuthError(StrumokError):
    """Плата відповіла 401: ключа немає або він хибний."""


class StrumokCommandError(StrumokError):
    """Плата відхилила команду (409 / 422 / інший не-200)."""

    def __init__(self, status: int, code: str, message: str, fields: dict[str, Any]) -> None:
        super().__init__(message or code or f"HTTP {status}")
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields


class StrumokClient:
    """Звернення до однієї плати за хостом."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        api_key: str | None = None,
        port: int = DEFAULT_PORT,
        timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        self._session = session
        self.host = host
        self.port = port
        self.api_key = api_key or None
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        if self.port == DEFAULT_PORT:
            return f"http://{self.host}"
        return f"http://{self.host}:{self.port}"

    @property
    def panel_url(self) -> str:
        """Адреса веб-панелі плати (`configuration_url` пристрою)."""
        return f"{self.base_url}/"

    def _headers(self) -> dict[str, str]:
        # Одна реалізація заголовка на весь компонент (auth.py, LOCAL-AUTONOMY §4).
        return auth_headers(self.api_key)

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with asyncio.timeout(self._timeout):
                async with self._session.request(
                    method, url, json=payload, headers=self._headers()
                ) as resp:
                    status = resp.status
                    try:
                        # Плата не завжди ставить Content-Type: application/json.
                        body = await resp.json(content_type=None)
                    except (ValueError, aiohttp.ContentTypeError):
                        body = None
        except TimeoutError as err:
            raise StrumokConnectionError(f"{url}: тайм-аут") from err
        except aiohttp.ClientError as err:
            raise StrumokConnectionError(f"{url}: {err}") from err
        return status, body

    async def async_get_status(self) -> dict[str, Any]:
        """`GET /api` — повний стан плати одним JSON-обʼєктом."""
        status, body = await self._request("GET", API_PATH)
        if status == 401:
            raise StrumokAuthError("/api: 401")
        if status != 200:
            raise StrumokConnectionError(f"/api: HTTP {status}")
        if not isinstance(body, dict):
            raise StrumokConnectionError("/api: відповідь не JSON-обʼєкт")
        return body

    async def async_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        """`POST /api/evse/cmd` із тілом `payload` (`{enabled}`, `{current_a}`, `{phase_reset}`)."""
        status, body = await self._request("POST", CMD_PATH, payload)
        data = body if isinstance(body, dict) else {}
        if status == 200:
            return data
        if status == 401:
            raise StrumokAuthError(f"{CMD_PATH}: 401")
        fields = data.get("fields")
        raise StrumokCommandError(
            status,
            str(data.get("error") or ""),
            str(data.get("msg") or ""),
            fields if isinstance(fields, dict) else {},
        )

    async def async_check_key(self) -> bool:
        """Перевірити ключ, нічого не змінюючи на платі.

        Порожня команда `{}` проходить ту саму перевірку входу, що й справжня
        (middleware панелі, `localauth::requestAllowed`), а обробник відповідає
        422 `empty` ще до будь-якої дії (`main.cpp::webEvseCmd`). Тож:
        401 → ключ хибний (`StrumokAuthError`); 422/200 → ключ прийнято → True;
        404/405/501 → прошивка без локальних команд → False.
        """
        try:
            await self.async_command({})
        except StrumokCommandError as err:
            if err.status == 422:
                return True
            if err.status in (404, 405, 501):
                return False
            raise
        return True
