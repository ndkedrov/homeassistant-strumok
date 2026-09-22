"""Константи інтеграції СтрумОК для Home Assistant.

Джерело правди для полів `/api` та переліку entity — спільний контракт
`docs/HOME-ASSISTANT-DEVICE-INTEGRATION.md` (§1, §2) у репозиторії
`strumok` (тікети STR-459/STR-460/STR-461). Не додавати сюди поле, якого
немає в цьому контракті, і не вигадувати нових — джерело для самих полів
`/api` це `lang/uk/device_api.php` (група ``status``, ендпоінт ``/api``) і
`device/firmware/src/main.cpp` (`fillStatus`) та `device/firmware/src/evse.cpp`
(`evse::panel`).
"""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "strumok"

# Порт локальної веб-панелі плати — підтверджено в прошивці, а не вгадано
# (правило "ніяких здогадів"): `device/firmware/include/config.h:1114`
# `#define WEBPANEL_PORT 80`. Локальний `/api` НЕ вимагає автентифікації
# (docs/HOME-ASSISTANT-DEVICE-INTEGRATION.md §1) — конфіг-флоу просить лише
# хост, портом користувач керувати не може (стандартний для всіх плат).
DEFAULT_PORT = 80

API_PATH = "/api"

# 15 секунд — компроміс, зафіксований у контракті (§4): показники плати
# (потужності, SoC, стан заряду) не змінюються щосекунди, а зайвий трафік
# на плату без PSRAM і так уже обмежений ресурс (проєктна памʼять
# strumok-no-psram-ble-tls-budget). Частіше за 15 с сенс мав би лише для
# графіків у реальному часі, які ця інтеграція не будує.
DEFAULT_SCAN_INTERVAL = timedelta(seconds=15)

# Тайм-аут одного HTTP-запиту до плати. Плата в локальній мережі, тому
# запит має відповідати за долі секунди; 10 с — запас на завантажену
# Wi-Fi мережу, не привід чекати довше.
REQUEST_TIMEOUT = 10

CONF_HOST = "host"

MANUFACTURER = "СтрумОК"
MODEL = "Зарядна станція СтрумОК"

PLATFORMS = ["sensor", "binary_sensor"]
