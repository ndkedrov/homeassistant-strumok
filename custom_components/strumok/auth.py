"""Ключ API плати (docs/LOCAL-AUTONOMY-CONTRACT.md §4).

Чистий модуль без залежності від Home Assistant — його перевіряють юніт-тести
так само, як `parser.py`.

За замовчуванням плата читання `/api` не закриває (``ropen=1``) — тоді ключ
не потрібен і заголовка немає зовсім, тобто поведінка інтеграції рівно та
сама, що й до появи входу. Якщо власник увімкнув вхід і закрив читання, він
створює в панелі плати ключ ``ha:<назва>`` і вписує його в поле «Ключ API»;
тоді кожен запит несе ``Authorization: Bearer <ключ>``.
"""

from __future__ import annotations

# Те саме значення, що homeassistant.const.CONF_API_KEY (його бере config flow).
CONF_API_KEY = "api_key"

# Код відповіді плати на запит без сеансу/ключа, коли вхід увімкнено.
HTTP_UNAUTHORIZED = 401


def auth_headers(api_key: str | None) -> dict[str, str]:
    """Заголовки запиту до плати: порожньо без ключа, Bearer — з ключем."""
    key = (api_key or "").strip()
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}
