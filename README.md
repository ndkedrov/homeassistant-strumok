# СтрумОК для Home Assistant

Custom component для [Home Assistant](https://www.home-assistant.io/), який
працює з вашою зарядною станцією СтрумОК напряму по локальній мережі — через
той самий HTTP API (`GET /api`), на якому відкривається веб-панель плати.
MQTT-брокер не потрібен.

Версія **0.2.0**:

- **сама знаходить станцію** в мережі (DHCP, а на платах, що оголошують службу,
  ще й mDNS `_strumok._tcp`) і сама оновлює її IP, якщо роутер видав нову адресу;
- **сенсори** станції й дому: стан, струм, потужність і енергія сесії заряду,
  генерація, батарея, мережа, споживання, Wi-Fi, шина інвертора;
- **керування зарядкою** (увімкнути/призупинити, струм, перевизначити фазу) —
  якщо задано ключ API і прошивка станції вміє локальні команди;
- **інтервал опитування** 5–300 с (типово 15), змінюється без перезапуску;
- **повторна автентифікація**, коли станція перестала приймати ключ;
- **діагностика** для підтримки (секрети вирізано);
- інтерфейс **українською та англійською**.

> Оберіть **один** спосіб: цю інтеграцію або MQTT-місток станції. Якщо ввімкнути
> обидва, Home Assistant покаже два однакові пристрої, а автоматизації керуватимуть
> зарядкою двічі.

Докладна інструкція з картинками: <https://strumok.app/device/home-assistant/hacs>.

## Встановлення через HACS

Пакета немає в офіційному каталозі HACS — додайте репозиторій вручну:

1. Home Assistant → **HACS** → три крапки вгорі праворуч → **Custom repositories**.
2. Repository: `https://github.com/ndkedrov/homeassistant-strumok`, Type: **Integration** → **Add**.
3. Знайдіть **СтрумОК** у HACS → **Download**.
4. Перезапустіть Home Assistant (**Settings → System → Restart**).

Мінімальна версія Home Assistant — **2025.2** (`hacs.json`).

### Без HACS

Скопіюйте `custom_components/strumok/` у `<конфіг Home Assistant>/custom_components/strumok/`
і перезапустіть Home Assistant.

## Налаштування

**Автоматично.** Після перезапуску станція з'явиться в **Settings → Devices &
services → Discovered** як «СтрумОК SK-…». Натисніть **Add**; ключ API можна
вставити одразу або пізніше.

**Вручну.** **Add integration → СтрумОК** → IP-адреса станції (та сама, що
відкриває веб-панель). Порт не потрібен: завжди 80.

Home Assistant у Docker без `network_mode: host` не бачить DHCP-пакетів, тож
автовиявлення там не спрацює. Додайте станцію вручну.

### Ключ API

Ключ потрібен, щоб керувати зарядкою, а також щоб читати дані, якщо на станції
закрито читання без входу.

1. Веб-панель станції → **Захист станції → Ключі API**.
2. «Для чого»: **Home Assistant**, дайте назву → **Створити ключ**.
3. Скопіюйте ключ (`sk_…`): панель показує його лише один раз.
4. Вставте при додаванні станції або пізніше: інтеграція → ⋮ → **Reconfigure**.

Інтеграція перевіряє ключ порожньою командою, яку станція відхиляє ще до
виконання (`422 empty`), тож під час перевірки зарядка нічого не робить.
Якщо ключ відкликали, станція відповість 401, і Home Assistant сам попросить
повторну автентифікацію (**Reauthenticate**).

### Параметри

Інтеграція → **Configure** → інтервал опитування 5–300 с. Новий інтервал діє
одразу, без перезавантаження інтеграції.

## Сутності

Один пристрій «СтрумОК» (`SK-…`) з посиланням **Visit** на веб-панель станції.

| Сутність | Тип | Джерело в `/api` | Примітки |
|---|---|---|---|
| `charging_state` | sensor (enum) | `evse.status` | 24 стани зі словника прошивки, перекладені |
| `charging_current` | sensor, A | `evse.cur` | уставка, яку прийняла зарядка |
| `charging_power` | sensor, **W** | `evse.kw` | попри назву — вати (у 0.1.0 помилково показувались кВт) |
| `charging_session_energy` | sensor, kWh, `total_increasing` | `evse.session_kwh` | лише якщо прошивка віддає поле |
| `home_battery_soc` | sensor, % | `live.m.batt_soc_pct` | батарея дому, не авто |
| `pv_power` / `battery_power` / `grid_power` / `load_power` | sensor, W | `live.m.*_power_w` | є, коли плата впізнала інвертор |
| `charging_allowed` | binary_sensor | `evse.on` | |
| `car_connected` | binary_sensor | `evse.units[0].car` | на одноблочних платах часто недоступний |
| `grid_present` | binary_sensor, `power` | `live.grid_state`, інакше `live.m.grid_present` + напруги | мережа є, коли стан не `absent`; на старішій прошивці — реле замкнене АБО хоч одна фаза (L1–L3, а де їх немає — `grid_voltage_v`) понад 50 В. Реле Deye розмикається й при живій мережі, тому сирий прапорець не годиться |
| `grid_state` | sensor (enum) | `live.grid_state.state` | `absent` — напруги немає, `unstable` — напруга є, але поза 207–253 В, зникла фаза або інвертор від'єднався від мережі, `normal` — у нормі. Лише з прошивкою, що віддає цей блок |
| `grid_state_reason` | sensor (enum) | `live.grid_state.reason` | `none`, `voltage_low`, `voltage_high`, `phase_missing`, `reconnecting` (мережа щойно повернулась, інвертор її перевіряє), `inverter_off` (інвертор від'єднався, захищаючись) |
| `wifi_online`, `inverter_bus_connected` | binary_sensor, diagnostic | `wifi.on`, `bus.connected` | |
| `wifi_rssi` | sensor, dBm, diagnostic | `wifi.rssi` | вимкнений за замовчуванням |
| `uptime`, `firmware_version` | sensor, diagnostic | `up`, `fw` | |
| `charging_enabled` | **switch** | `evse.on` | `POST /api/evse/cmd {"enabled": …}` |
| `charging_current` | **number**, A | `evse.cur` | `{"current_a": N}`; межі від max(7, `evse.min_a`) до `evse.max` (16, поки зарядка не сказала) |
| `phase_reset` | **button** | — | `{"phase_reset": true}` |

Керувальні сутності з'являються, лише коли в `/api` є блок `auth` (прошивка з
локальними командами) і в інтеграції задано ключ API. Якщо прошивку оновили,
вони, як і енергія сесії, з'являться без перезапуску Home Assistant. Поле, якого
станція зараз не віддає, стає `unavailable`, а не нулем.

Відповіді станції на команди: `409` (зарядку ще не знайдено тощо) і `422`
(значення поза межами) Home Assistant показує з поясненням самої станції.
`401` запускає повторну автентифікацію.

## Розробка й тести

Тести ганяють справжній Home Assistant через `pytest-homeassistant-custom-component`
(потрібен Python ≥ 3.14.2 для HA 2026.9):

```bash
cd integrations/homeassistant-strumok
uv venv --python 3.14 .venv && source .venv/bin/activate
uv pip install -r requirements_test.txt
pytest -q
```

- `tests/test_parser.py` — розбір `/api`: відсутнє поле ніколи не кидає виняток;
- `tests/test_config_flow.py` — user, DHCP, zeroconf, підтвердження, ключ, reauth,
  reconfigure, параметри;
- `tests/test_init.py` — завантаження, 401 → reauth, мережеві помилки → `unavailable`,
  поява нових сутностей після OTA, діагностика;
- `tests/test_control.py` — тіла `POST /api/evse/cmd`, Bearer, 401/409/422/404.
