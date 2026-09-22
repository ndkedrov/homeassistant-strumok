"""Config flow: користувач вводить лише IP/хост плати СтрумОК.

Порт (80) фіксований і не питається — це `WEBPANEL_PORT`, однаковий для
всіх плат (`device/firmware/include/config.h:1114`). Автентифікації немає
(контракт §1), тому поля пароля тут навмисно нема: `/api` його не приймає
й не перевіряє.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import parser
from .const import API_PATH, DEFAULT_PORT, DOMAIN, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})


class CannotConnect(Exception):
    """Не вдалось достукатись до `/api` за цим хостом."""


async def _validate_host(hass, host: str) -> dict[str, Any]:
    """Постукати в `GET http://<host>:80/api` і повернути мінімальну інформацію.

    Піднімає `CannotConnect`, якщо плата не відповіла або відповідь — не
    JSON-обʼєкт. Успішна відповідь без поля `dev` теж вважається
    підключенням (не всі відповіді контракту гарантують це поле в
    кожному билді прошивки), просто unique_id тоді будується з хоста.
    """
    session = async_get_clientsession(hass)
    url = f"http://{host}:{DEFAULT_PORT}{API_PATH}"
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise CannotConnect(f"HTTP {resp.status}")
                data = await resp.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError) as err:
        raise CannotConnect(str(err)) from err
    except ValueError as err:  # invalid JSON
        raise CannotConnect(f"Некоректна JSON-відповідь: {err}") from err

    if not isinstance(data, dict):
        raise CannotConnect(f"Очікував JSON-обʼєкт, отримав {type(data)}")

    return {
        "dev": parser.device_id(data),
        "fw": parser.firmware_version(data),
    }


class StrumokConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow для інтеграції СтрумОК."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                info = await _validate_host(self.hass, host)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                unique_id = info["dev"] or host
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})

                title = info["dev"] or host
                return self.async_create_entry(
                    title=title,
                    data={CONF_HOST: host, CONF_PORT: DEFAULT_PORT},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
