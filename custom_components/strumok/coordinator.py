"""DataUpdateCoordinator: опитує локальний `/api` плати СтрумОК.

Один HTTP GET-запит на цикл віддає весь стан плати одним JSON-документом
(`fillStatus`, `device/firmware/src/main.cpp:7808`) — координатор лише
скачує його як є, а розбір конкретних полів роблять чисті функції з
`parser.py`. Помилка мережі одного циклу опитування не має валити всю
інтеграцію — `UpdateFailed` дає entity стандартний стан `unavailable` до
наступного успішного опитування, а не виняток, що зупиняє координатор
назавжди.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import API_PATH, DEFAULT_SCAN_INTERVAL, DOMAIN, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class StrumokApiError(Exception):
    """Плата не відповіла або відповіла не JSON-ом."""


class StrumokDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Опитує `GET http://<host>:<port>/api` кожні `DEFAULT_SCAN_INTERVAL`."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        update_interval: timedelta = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{host}",
            update_interval=update_interval,
        )
        self._host = host
        self._port = port
        self._session = async_get_clientsession(hass)

    @property
    def api_url(self) -> str:
        return f"http://{self._host}:{self._port}{API_PATH}"

    @property
    def host(self) -> str:
        """Хост плати — запасний ідентифікатор, поки координатор ще не отримав перший `/api`."""
        return self._host

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self._fetch()
        except StrumokApiError as err:
            raise UpdateFailed(str(err)) from err

    async def _fetch(self) -> dict[str, Any]:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.get(self.api_url) as resp:
                    if resp.status != 200:
                        raise StrumokApiError(
                            f"{self.api_url} повернув HTTP {resp.status}"
                        )
                    # /api не вимагає автентифікації (контракт §1), але й не
                    # завжди виставляє Content-Type: application/json — тому
                    # content_type=None, щоб не впасти на цьому.
                    data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise StrumokApiError(f"Не вдалось з'єднатись із {self.api_url}: {err}") from err
        except TimeoutError as err:
            raise StrumokApiError(f"Тайм-аут запиту до {self.api_url}") from err
        except ValueError as err:  # invalid JSON
            raise StrumokApiError(f"Некоректна JSON-відповідь від {self.api_url}: {err}") from err

        if not isinstance(data, dict):
            raise StrumokApiError(f"Очікував JSON-обʼєкт від {self.api_url}, отримав {type(data)}")
        return data
