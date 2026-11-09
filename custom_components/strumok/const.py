"""Константи інтеграції СтрумОК для Home Assistant.

Джерела правди (не вигадувати поля, яких там немає):
- `docs/HA-FULL-CONTRACT.md` §3 — що робить компонент 0.2.0;
- `docs/HOME-ASSISTANT-DEVICE-INTEGRATION.md` §1–§2 — поля `/api` і перелік entity;
- `docs/LOCAL-AUTONOMY-CONTRACT.md` §3.2, §4 — ключі API, `POST /api/evse/cmd`;
- прошивка: `device/firmware/src/main.cpp` (`fillStatus`), `src/evse.cpp` (`evse::panel`).
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "strumok"

# Порт локальної веб-панелі плати: `device/firmware/include/config.h`
# `#define WEBPANEL_PORT 80`. Однаковий для всіх плат, тому користувач його не вводить.
DEFAULT_PORT: Final = 80

API_PATH: Final = "/api"
# LOCAL-AUTONOMY-CONTRACT §3.2: `POST /api/evse/cmd {current_a?, enabled?, one_charge?, phase_reset?}`.
CMD_PATH: Final = "/api/evse/cmd"

# Інтервал опиту (HA-FULL-CONTRACT §3): 5–300 с, типово 15. Змінюється в
# параметрах інтеграції й застосовується одразу, без перезапуску HA.
DEFAULT_SCAN_INTERVAL_S: Final = 15
MIN_SCAN_INTERVAL_S: Final = 5
MAX_SCAN_INTERVAL_S: Final = 300

# Тайм-аут одного HTTP-запиту до плати в локальній мережі.
REQUEST_TIMEOUT: Final = 10

# Ключ API плати: `sk_` + 48 hex (`local_auth.cpp::makeKey`); плата відкидає
# будь-що без префікса `sk_` (`keyValid`).
API_KEY_PREFIX: Final = "sk_"

# Межі струму команди: `cfg_rules.h` kLocalRules `evse_cmd.current_a` 7…48 А,
# ті самі, що й у сервера (`EvCharger::MIN_CURRENT_A = 7`, моделі до 48 А).
# Коли зарядка ще не сказала свій максимум (`evse.max`), беремо найслабшу
# модель — 16 А (`EvCharger::DEFAULT_MAX_CURRENT_A`), як і сервер.
CMD_MIN_CURRENT_A: Final = 7
CMD_MAX_CURRENT_A: Final = 48
DEFAULT_MAX_CURRENT_A: Final = 16

# Скільки тримати оптимістичний стан перемикача/числа після команди: плата
# ставить команду в чергу (`cfgtext::kCmdQueued`) і застосовує за такт-два,
# тож наступне опитування може ще показати старе значення.
PENDING_COMMAND_S: Final = 20

MANUFACTURER: Final = "СтрумОК"
MODEL: Final = "Зарядна станція СтрумОК"

PLATFORMS: Final = ["binary_sensor", "button", "number", "sensor", "switch"]
