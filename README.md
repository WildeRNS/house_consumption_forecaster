<p align="center">
  <b>Language / Мова:</b> 
  <a href="#-house-consumption-adaptive-forecaster-for-home-assistant">🇬🇧 English</a> | 
  <a href="#-адаптивний-прогнозист-споживання-електроенергії-для-home-assistant">🇺🇦 Українська</a>
</p>

---

# ⚡ House Consumption Adaptive Forecaster for Home Assistant

An adaptive custom integration for Home Assistant designed to accurately predict daily household energy consumption for **today** and **tomorrow**.

It uses a dynamic self-learning model that accounts for base electrical load (a rolling multi-day average), a **relative** solar production correlation (positive correlation against Solcast / Volcast / Forecast.Solar, scaled to your own installation's average — not a raw kWh add-on), and ambient temperature offsets.

---

## 📋 Table of Contents
- [Features](#-features)
- [How It Works (Mathematical & Learning Logic)](#-how-it-works-mathematical--learning-logic)
- [Sensor Calibration Timeline](#-sensor-calibration-timeline)
- [Installation](#-installation)
  - [Method 1: HACS (Recommended)](#method-1-hacs-recommended)
  - [Method 2: Manual Installation](#method-2-manual-installation)
- [Configuration](#-configuration)
- [Entities & Attributes](#-entities--attributes)
- [Changelog](#-changelog)

---

## 🚀 Features

- **State Caching & Restart Protection:** Eliminates forecast drops during Home Assistant reboots by instantly recalling the last known valid states of unavailable sensors.
- **Adaptive Self-Learning Engine:** Automatically compares yesterday's prediction against actual daily consumption at midnight and self-calibrates system coefficients using dynamic feedback loops.
- **10-Day Historical Baseline:** Uses a rolling 10-day average (for both consumption and solar generation) to closely track your most recent baseline, discarding outdated habits while staying resistant to single-day noise.
- **Relative Solar Correlation:** Compares the solar forecast for a given day against its *own* rolling average, not an absolute kWh figure. A day forecast to be sunnier-than-usual proportionally raises expected consumption; a duller-than-usual day proportionally lowers it. This scales correctly regardless of your PV system's size and can self-learn down to zero influence if no real correlation exists.
- **Symmetric Bias Correction:** The self-learned bias multiplier is bounded equally in both directions (±15%), so the model can correct itself downward just as strongly as upward — it can no longer get permanently "stuck" biased toward overestimation.
- **Forecast Ceiling & Floor:** The forecast is always clamped within `[0.5×, 1.6×]` of the rolling average — it can no longer run away unbounded the way an uncapped forecast could.
- **Floor Clamping Protection:** The forecast for "Today" mathematically cannot drop below the energy your house has already consumed up to the current minute.
- **HVAC & Weather Adjustment:** Automatically adjusts forecasts based on cooling (> 25°C) or heating (< 15°C) requirements using daily weather forecast data, capped at a fraction of the baseline so it can't dominate the model in extreme weather.
- **Anomaly Protection & Rate Limiting:** Clamps weight adaptations to small daily steps alongside absolute boundaries to prevent single-day consumption anomalies from distorting the model. Days with suspiciously low consumption (a likely sensor glitch) are excluded from the history instead of dragging the average down.
- **Persistent Weights Storage:** Learned weights and baseline statistics survive system restarts using Home Assistant's native Storage Helper (`Store`).
- **Unified Device Architecture:** Groups entities under a single virtual device with clean entity naming.
- **100% UI Configurable:** Full support for `ConfigFlow` and `OptionsFlow` — no YAML editing required. No workday/weekend sensor to configure — that dependency has been removed.

---

## 🧠 How It Works (Mathematical & Learning Logic)

### 1. Forecast Calculation Model

The forecast for a given day is calculated using the following sequential steps:

1. **Base Load (N-Day Average):**
   The rolling average daily consumption over the last `HISTORY_DAYS` days (10 by default):
   $$\text{Base} = \text{avg}_{N\text{-day}}$$

2. **Bias Correction:**
   A self-learned multiplier, symmetrically bounded to ±15%:
   $$\text{Base}_{\text{corrected}} = \text{Base} \times W_{\text{bias}}, \quad W_{\text{bias}} \in [0.85,\ 1.15]$$

3. **Temperature Offset (capped):**
   - **Cooling (> 25°C):** $\text{Offset} = (T - 25.0) \times W_{\text{cool}}$
   - **Heating (< 15°C):** $\text{Offset} = (15.0 - T) \times W_{\text{heat}}$
   - Clamped to $\pm 35\%$ of `Base`, so extreme temperatures can't dominate the forecast.

4. **Relative Solar Correction:**
   Solar influence is expressed as a *deviation from the PV system's own average*, not a raw kWh addition:
   $$\text{Solar Ratio} = \text{clamp}\left(\frac{\text{Solar Forecast}}{\text{Avg Solar}_{N\text{-day}}},\ 0.3,\ 2.0\right)$$
   $$\text{Solar Effect} = (\text{Solar Ratio} - 1.0) \times \text{Base} \times W_{\text{solar}}, \quad W_{\text{solar}} \in [0.0,\ 0.30]$$
   A sunnier-than-average day raises the forecast proportionally; a duller day lowers it. If the sensor reports no meaningful solar history yet, the term is skipped entirely (no false signal).

5. **Final Assembly:**
   $$\text{Estimated Total} = \text{Base}_{\text{corrected}} + \text{Temperature Offset} + \text{Solar Effect}$$

6. **Safety Clamping (Floor & Ceiling):**
   Unlike an unbounded model, the result is always clamped symmetrically against the baseline:
   $$\text{Forecast} = \text{clamp}(\text{Estimated Total},\ 0.5 \times \text{Base},\ 1.6 \times \text{Base})$$
   For **today's** forecast only, the result additionally can never fall below what has already been consumed:
   $$\text{Forecast}_{\text{today}} = \max(\text{Forecast},\ \text{Actual Current Consumption})$$

---

### 2. Auto-Calibration Feedback Loop

Once per day, on date transition, the integration evaluates yesterday's performance:

1. Appends yesterday's actual consumption (and actual solar yield) to the rolling `HISTORY_DAYS`-day arrays, dropping the oldest entry. Days below `MIN_VALID_CONSUMPTION` (1.0 kWh — a likely sensor glitch rather than a real "quiet" day) are skipped instead of polluting the average.
2. Computes the forecast error and MAPE (Mean Absolute Percentage Error):
   $$\text{Error} = \text{Actual Yesterday} - \text{Predicted Yesterday}$$
3. Nudges the weights with small, clamped daily steps proportional to the relative error:
   - **Bias Correction:** $W_{\text{bias}} \leftarrow W_{\text{bias}} + \text{clamp}\left(\dfrac{\text{Error}}{\text{Actual}} \times 0.04,\ -0.03,\ 0.03\right)$
   - **Solar Weight:** adjusted the same way, but only once a meaningful solar history exists — and can shrink all the way to `0.0` if the correlation isn't real.
   - **Cooling / Heating Coefficients:** adjusted only when yesterday's *true daily average* temperature crossed the relevant threshold (> 25°C / < 15°C).
4. **Global Boundary Enforcement (symmetric, tightened from earlier versions):**
   $$W_{\text{bias}} \in [0.85,\ 1.15], \quad W_{\text{solar}} \in [0.0,\ 0.30], \quad W_{\text{cool}},\ W_{\text{heat}} \in [0.0,\ 1.2]$$
5. Saves the updated weights and rolling history to `.storage/house_consumption_forecaster_<entry_id>_weights`.

---

## ⏱ Sensor Calibration Timeline

The integration relies on a daily feedback loop at midnight to continuously calibrate its internal weights:

* **Day 1 (First Midnight):** Performs its first actual vs. forecast comparison, initiates the consumption/solar history arrays, and applies the initial bias correction ($W_{\text{bias}}$).
* **Days 3–5 (Core Learning Phase):** Main adaptation period. The $W_{\text{bias}}$ multiplier and temperature weights converge toward your home's realistic average.
* **~10 Days (Full Stabilization):** The rolling `HISTORY_DAYS`-day window fills up, giving both the consumption baseline and the solar correlation a full, stable sample to learn from.

---

## 📦 Installation

### Method 1: HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=WildeRNS&repository=house_consumption_forecaster&category=integration)

1. Click the badge above (it opens HACS with this repository pre-filled as a custom repository), or add it manually: open **HACS** → menu (⋮) → **Custom repositories** → paste `https://github.com/WildeRNS/house_consumption_forecaster`, category **Integration**.
2. Find `House Consumption Forecaster` in HACS and click **Download**.
3. Restart Home Assistant.

### Method 2: Manual Installation

1. Download the latest release archive.
2. Copy the `custom_components/house_consumption_forecaster` directory into your Home Assistant's `/config/custom_components/` directory.
3. Path structure: `/config/custom_components/house_consumption_forecaster/manifest.json`
4. Restart Home Assistant.

---

## ⚙️ Configuration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=house_consumption_forecaster)

1. Click the badge above, or go to **Settings** $\rightarrow$ **Devices & Services** $\rightarrow$ **Add Integration** and search for **House Consumption Forecaster**.
2. Select your input entities:
   - **Daily Consumption Sensor:** Cumulative house consumption sensor in kWh (`sensor.daily_consumption`).
   - **Actual Solar Generation Sensor:** Cumulative daily PV generation sensor in kWh.
   - **Solar Forecast (Today):** Solcast / Volcast / Forecast.Solar expected daily generation sensor for today.
   - **Solar Forecast (Tomorrow):** Solcast / Volcast / Forecast.Solar expected daily generation sensor for tomorrow.
   - **Weather Entity:** Weather integration entity providing daily temperature forecasts for heating/cooling offsets (e.g., `weather.home`).

> ℹ️ **No more workday sensor.** Earlier versions required a `binary_sensor.workday_sensor` for a weekend load boost. It has been removed — if you're upgrading, simply reopen **Options** on the integration card; the field is gone and nothing further is needed.

> 💡 **Need to change sensors later?** Click **Configure** on the integration card to open the **Options Flow** modal and update mappings anytime.

---

## 📊 Entities & Attributes

The integration creates a unified device named **Прогноз споживання електроенергії** containing two entities:

1. `sensor.house_energy_forecast_today` — Predicted consumption for today (in kWh).
2. `sensor.house_energy_forecast_tomorrow` — Predicted consumption for tomorrow (in kWh).

### State Attributes:
Each entity exposes learned model parameters in its state attributes:
- `Internal {N}-day avg`: Current rolling baseline average over `HISTORY_DAYS` days (label updates automatically if that constant changes).
- `Internal avg daily solar`: Current rolling average actual solar yield over the same window.
- `Learned solar weight`: Learned relative-influence factor for solar production (`0.0`–`0.30`).
- `Learned temp cool coeff`: Cooling load adaptation coefficient (kWh/°C above 25°C).
- `Learned temp heat coeff`: Heating load adaptation coefficient (kWh/°C below 15°C).
- `Learned bias correction`: Current symmetric bias multiplier (`0.85`–`1.15`).
- `Last error mape pct`: Last calculated Mean Absolute Percentage Error (%).

---

## 🔄 Changelog

### 1.3.0 — Configurable averaging window & faster catch-up
- **Added a UI setting** ("Averaging Period (days)") to configure how many days of history feed the rolling consumption/solar average — no more editing code to change this. Default `10`, adjustable `3`–`30`, editable anytime via **Configure** on the integration card.
- Up to `30` days of history are now stored internally regardless of the configured window, so changing the setting takes effect **instantly** instead of waiting to re-accumulate data.
- **Widened the bias correction bounds** to a symmetric `±25%` (was `±15%`) — the previous range couldn't fully correct for a real, sustained drop in consumption faster than the averaging window itself could catch up, leaving a persistent gap between forecast and actual. Bounds remain symmetric in both directions.

### 1.2.0 — Overestimation fix
- **Removed** the workday/weekend sensor and the entire weekend-boost logic.
- **Bias correction is now symmetric** (`0.85–1.15`, was asymmetric `0.85–1.25`) — the model can no longer correct itself upward more easily than downward.
- **Solar correction rewritten as a relative ratio** against its own rolling average, instead of adding a raw kWh figure. The weight can now shrink all the way to `0.0` (was floored at `0.05`).
- **Added a forecast ceiling** (`1.6×` baseline) — previously there was only a floor, so the forecast could inflate with no upper limit.
- **Lowered the minimum valid consumption threshold** from `4.0` to `1.0` kWh, so legitimate low-usage days are no longer discarded from the average.
- **Extended the history window** from 7 to 10 days (`HISTORY_DAYS`) for both consumption and (new) solar generation.
- **Capped the temperature offset** to a fraction of the baseline so extreme weather can't dominate the forecast.
- Kept `STORAGE_VERSION = 1` — bumping it requires a migration function in Home Assistant's `Store`, or it raises `NotImplementedError` on load; new fields load safely via `.get()` defaults instead.
- Attribute labels (e.g. `Internal N-day avg`) are now built from `HISTORY_DAYS` instead of being hardcoded, so they can't drift out of sync again.

---
---

<p align="center">
  <a href="#-house-consumption-adaptive-forecaster-for-home-assistant">⬆ Нагору до англійської версії / Back to English</a>
</p>

# ⚡ Адаптивний прогнозист споживання електроенергії для Home Assistant

Адаптивна кастомна інтеграція для Home Assistant, розроблена для точного прогнозування добового споживання електроенергії будинком на **сьогодні** та **завтра**.

Інтеграція використовує динамічну модель з автонавчанням, яка враховує базове електричне навантаження (ковзне середнє за декілька днів), **відносний** вплив сонячної генерації (додатна кореляція з Solcast / Volcast / Forecast.Solar, масштабована відносно власного середнього вашої станції — а не додавання сирої кВт·год-суми) та температурну компенсацію (опалення/охолодження).

---

## 📋 Зміст
- [Можливості](#-можливості-1)
- [Принцип роботи (Математична модель та автонавчання)](#-принцип-роботи-математична-модель-та-автонавчання-1)
- [Терміни калібрування сенсорів](#-терміни-калібрування-сенсорів-1)
- [Встановлення](#-встановлення-1)
  - [Спосіб 1: Через HACS (Рекомендовано)](#спосіб-1-через-hacs-рекомендовано-1)
  - [Спосіб 2: Ручне встановлення](#спосіб-2-ручне-встановлення-1)
- [Налаштування](#-налаштування-1)
- [Сутності та атрибути](#-сутності-та-атрибути-1)
- [Історія змін](#-історія-змін-1)

---

## 🚀 Можливості

- **Кешування станів та захист від рестартів:** Усуває провали на графіках під час перезавантаження Home Assistant завдяки миттєвому підключенню останніх відомих станів для тимчасово недоступних сенсорів.
- **Адаптивний модуль самонавчання:** Щоночі порівнює вчорашній прогноз із фактичним добовим споживанням та самостійно коригує коефіцієнти.
- **10-денна історична база:** Ковзне середнє за останні 10 днів (і для споживання, і для сонячної генерації) — точніше відповідає вашим поточним звичкам, ніж коротше вікно, і водночас стійкіше до випадкового шуму одного дня.
- **Відносна кореляція з СЕС:** Прогноз генерації СЕС на конкретний день порівнюється з **власним** ковзним середнім, а не береться як абсолютне число кВт·год. Сонячніший за звичайне день пропорційно піднімає прогноз споживання, похмуріший — пропорційно знижує. Це коректно масштабується незалежно від розміру вашої станції, і вага може самостійно "зануритись" до нуля, якщо реальної кореляції немає.
- **Симетрична bias-корекція:** Навчений коефіцієнт зміщення обмежений однаково в обидва боки (±15%) — модель більше не може "застрягти" у стані, коли їй легше завищувати прогноз, ніж занижувати.
- **Стеля та підлога прогнозу:** Результат завжди затиснутий у межах `[0.5×, 1.6×]` від середнього — прогноз більше не може необмежено зростати, як це було можливо раніше (коли існувала лише підлога).
- **Захист від провалів (Floor Clamping):** Прогноз на "Сьогодні" математично не може впасти нижче того обсягу енергії, який ваш будинок *вже* спожив на поточну хвилину.
- **Температурна компенсація:** Автоматично коригує прогноз на основі прогнозу добових температур (охолодження > 25°C або опалення < 15°C), обмежена часткою від бази, щоб екстремальна погода не могла домінувати над рештою моделі.
- **Захист від аномалій:** Обмежує добову зміну кожного коефіцієнта невеликим кроком, що запобігає спотворенню моделі через випадкові сплески споживання. Дні з підозріло малим споживанням (ймовірна помилка сенсора) виключаються з історії, а не тягнуть середнє вниз.
- **Збереження коефіцієнтів:** Навчені коефіцієнти зберігаються у внутрішній базі даних Home Assistant (`Store`).
- **Єдина архітектура пристрою:** Групує сутності під одним віртуальним пристроєм з чистими іменами.
- **100% налаштування через UI:** Повна підтримка `ConfigFlow` та `OptionsFlow` — без редагування YAML. Сенсор вихідного/робочого дня більше не потрібен — цю залежність прибрано повністю.

---

## 🧠 Принцип роботи (Математична модель та автонавчання)

### 1. Математична модель розрахунку прогнозу

Розрахунок прогнозу здійснюється за такими послідовними кроками:

1. **Базове навантаження (середнє за N днів):**
   Ковзне середнє добове споживання за останні `HISTORY_DAYS` днів (за замовчуванням 10):
   $$\text{База} = \text{avg}_{N\text{-денне}}$$

2. **Bias-корекція:**
   Навчений мультиплікатор, симетрично обмежений ±15%:
   $$\text{База}_{\text{скоригована}} = \text{База} \times W_{\text{bias}}, \quad W_{\text{bias}} \in [0.85,\ 1.15]$$

3. **Температурна корекція (з обмеженням):**
   - **Охолодження (> 25°C):** $\text{Корекція} = (T - 25.0) \times W_{\text{cool}}$
   - **Опалення (< 15°C):** $\text{Корекція} = (15.0 - T) \times W_{\text{heat}}$
   - Обмежена ±35% від `Бази`, щоб екстремальна погода не могла домінувати над прогнозом.

4. **Відносна сонячна корекція:**
   Вплив сонця виражається як **відхилення від власного середнього** сонячної станції, а не додавання сирої кВт·год-суми:
   $$\text{Сонячний коефіцієнт} = \text{clamp}\left(\frac{\text{Прогноз СЕС}}{\text{Середня генерація}_{N\text{-денна}}},\ 0.3,\ 2.0\right)$$
   $$\text{Сонячний ефект} = (\text{Сонячний коефіцієнт} - 1.0) \times \text{База} \times W_{\text{solar}}, \quad W_{\text{solar}} \in [0.0,\ 0.30]$$
   Сонячніший за звичайне день пропорційно піднімає прогноз, похмуріший — пропорційно знижує. Якщо історії сонячної генерації ще недостатньо, цей доданок просто пропускається (без хибного сигналу).

5. **Підсумкова збірка:**
   $$\text{Розрахункове споживання} = \text{База}_{\text{скоригована}} + \text{Темп. корекція} + \text{Сонячний ефект}$$

6. **Захисні межі (підлога та стеля):**
   На відміну від необмеженої моделі, результат завжди симетрично затиснутий відносно бази:
   $$\text{Прогноз} = \text{clamp}(\text{Розрахункове споживання},\ 0.5 \times \text{База},\ 1.6 \times \text{База})$$
   Лише для прогнозу на **сьогодні** результат додатково ніколи не може опуститись нижче вже фактично спожитого:
   $$\text{Прогноз}_{\text{сьогодні}} = \max(\text{Прогноз},\ \text{Поточне фактичне споживання})$$

---

### 2. Цикл автоматичного самонавчання

Раз на добу, при переході на нову дату, координатор оцінює вчорашню точність:

1. Додає фактичне вчорашнє споживання (і фактичну генерацію СЕС) до ковзних масивів історії за `HISTORY_DAYS` днів, видаляючи найстаріший запис. Дні з показником нижче `MIN_VALID_CONSUMPTION` (1.0 кВт·год — ймовірна помилка сенсора, а не реально "тихий" день) пропускаються, а не псують середнє.
2. Обчислюється похибка прогнозу та MAPE (середня абсолютна відсоткова помилка):
   $$\text{Похибка} = \text{Факт вчора} - \text{Прогноз вчора}$$
3. Ваги коригуються невеликими, обмеженими добовими кроками, пропорційними відносній похибці:
   - **Bias Correction:** $W_{\text{bias}} \leftarrow W_{\text{bias}} + \text{clamp}\left(\dfrac{\text{Похибка}}{\text{Факт}} \times 0.04,\ -0.03,\ 0.03\right)$
   - **Сонячна вага:** коригується так само, але лише коли вже накопичена значуща історія сонячної генерації — і може зменшитись аж до `0.0`, якщо реальної кореляції немає.
   - **Температурні коефіцієнти ($W_{\text{cool}}$ / $W_{\text{heat}}$):** коригуються, лише якщо *справжня середньодобова* температура вчора перетнула відповідний поріг (> 25°C / < 15°C).
4. **Контроль допустимих меж (симетричні, звужені порівняно з попередньою версією):**
   $$W_{\text{bias}} \in [0.85,\ 1.15], \quad W_{\text{solar}} \in [0.0,\ 0.30], \quad W_{\text{cool}},\ W_{\text{heat}} \in [0.0,\ 1.2]$$
5. Оновлені коефіцієнти та історія автоматично зберігаються у `.storage/house_consumption_forecaster_<entry_id>_weights`.

---

## ⏱ Терміни калібрування сенсорів

Система працює на основі добового циклу зворотного зв'язку (Feedback Loop), тому адаптація проходить у кілька етапів:

* **1-ша доба (Перша північ):** Інтеграція вперше порівнює реальне споживання з прогнозом, ініціює масиви історії споживання/сонця та вносить першу правку в коефіцієнт зміщення ($W_{\text{bias}}$).
* **3–5 днів (Основна фаза навчання):** Головний період адаптації. Коефіцієнт $W_{\text{bias}}$ та температурні ваги вирівнюються під реальний середній рівень споживання вашого будинку.
* **~10 днів (Повна стабілізація):** Ковзне вікно за `HISTORY_DAYS` днів повністю заповнюється — і базове споживання, і сонячна кореляція отримують повну, стабільну вибірку для навчання.

---

## 📦 Встановлення

### Спосіб 1: Через HACS (Рекомендовано)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=WildeRNS&repository=house_consumption_forecaster&category=integration)

1. Натисніть кнопку вище (вона відкриє HACS одразу з цим репозиторієм, готовим до додавання як користувацький), або додайте вручну: відкрийте **HACS** → меню (⋮) → **Custom repositories** → вставте `https://github.com/WildeRNS/house_consumption_forecaster`, категорія **Integration**.
2. Знайдіть `House Consumption Forecaster` у HACS і натисніть **Download**.
3. Перезапустіть Home Assistant.

### Спосіб 2: Ручне встановлення

1. Завантажте останній реліз зі сторінки Releases.
2. Скопіюйте папку `house_consumption_forecaster` з архіву у папку `/config/custom_components/` вашого Home Assistant.
3. Шлях до файлів повинен мати вигляд: `/config/custom_components/house_consumption_forecaster/manifest.json`
4. Перезапустіть Home Assistant.

---

## ⚙️ Налаштування

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=house_consumption_forecaster)

1. Натисніть кнопку вище, або перейдіть у **Налаштування** $\rightarrow$ **Пристрої та служби** $\rightarrow$ **Додати інтеграцію** та знайдіть **House Consumption Forecaster**.
2. Оберіть вхідні сутності:
   - **Сенсор споживання будинку:** Накопичувальний сенсор споживання будинку за день у кВт·год (`sensor.daily_consumption`).
   - **Сенсор фактичної генерації СЕС:** Накопичувальний сенсор добової генерації СЕС у кВт·год.
   - **Прогноз СЕС (Сьогодні):** Сенсор очікуваної генерації на сьогодні від Solcast / Volcast / Forecast.Solar.
   - **Прогноз СЕС (Завтра):** Сенсор очікуваної генерації на завтра від Solcast / Volcast / Forecast.Solar.
   - **Сутність погоди:** Сутність інтеграції погоди, що надає прогноз добових температур для розрахунку кліматичних оффсетів (наприклад, `weather.home`).

> ℹ️ **Сенсора вихідного дня більше немає.** У попередніх версіях був потрібен `binary_sensor.workday_sensor` для вихідного приросту навантаження. Його прибрано повністю — якщо оновлюєтесь зі старої версії, просто відкрийте **Options** на картці інтеграції: поле зникло само, додаткових дій не потрібно.

> 💡 **Змінилися сенсори?** Натисніть кнопку **Налаштувати** (Options) на картці інтеграції, щоб змінити прив'язку сутностей у будь-який момент.

---

## 📊 Сутності та атрибути

Інтеграція створює пристрій **Прогноз споживання електроенергії** з двома сутностями:

1. `sensor.house_energy_forecast_today` — Прогнозоване споживання на сьогодні (у кВт·год).
2. `sensor.house_energy_forecast_tomorrow` — Прогнозоване споживання на завтра (у кВт·год).

### Атрибути стану:
Кожен сенсор містить у своїх атрибутах актуальні параметри моделі:
- `Internal {N}-day avg`: Поточне ковзне середнє за `HISTORY_DAYS` днів (напис оновлюється автоматично, якщо ця константа зміниться).
- `Internal avg daily solar`: Поточне ковзне середнє фактичної генерації СЕС за той самий період.
- `Learned solar weight`: Навчений коефіцієнт відносного впливу сонячної генерації (`0.0`–`0.30`).
- `Learned temp cool coeff`: Коефіцієнт адаптації до навантаження охолодження (кВт·год/°C понад 25°C).
- `Learned temp heat coeff`: Коефіцієнт адаптації до навантаження опалення (кВт·год/°C нижче 15°C).
- `Learned bias correction`: Поточний симетричний мультиплікатор зміщення (`0.85`–`1.15`).
- `Last error mape pct`: Останній розрахований відсоток помилки прогнозу (%).

---

## 🔄 Історія змін

### 1.3.0 — Налаштовуваний період усереднення та швидше "наздоганяння"
- **Додано налаштування в UI** ("Період усереднення (днів)") — тепер кількість днів історії, за якими рахується ковзне середнє споживання/сонця, змінюється без редагування коду. За замовчуванням `10`, діапазон `3`–`30`, можна змінити будь-коли через **Налаштувати** на картці інтеграції.
- Внутрішньо тепер завжди зберігається до `30` днів історії незалежно від обраного періоду усереднення, тож зміна налаштування діє **миттєво**, без очікування накопичення нових днів.
- **Розширено межі bias-корекції** до симетричних `±25%` (було `±15%`) — попередній діапазон не встигав повністю компенсувати реальне стійке падіння споживання швидше, ніж встигало зміститись саме ковзне середнє, через що зберігався помітний розрив між прогнозом і фактом. Межі лишаються симетричними в обидва боки.

### 1.2.0 — Виправлення завищення прогнозу
- **Прибрано** сенсор вихідного/робочого дня та всю логіку вихідного приросту навантаження.
- **Bias-корекція тепер симетрична** (`0.85–1.15`, було асиметрично `0.85–1.25`) — модель більше не може коригуватись вгору легше, ніж вниз.
- **Сонячна корекція переписана як відносний коефіцієнт** до власного ковзного середнього, замість додавання сирої кВт·год-суми. Вага тепер може зменшитись аж до `0.0` (раніше була підлога `0.05`).
- **Додано стелю прогнозу** (`1.6×` від бази) — раніше існувала лише підлога, і прогноз міг зростати без жодної верхньої межі.
- **Знижено поріг мінімального валідного споживання** з `4.0` до `1.0` кВт·год, щоб легітимні дні з малим споживанням більше не відкидались із середнього.
- **Розширено вікно історії** з 7 до 10 днів (`HISTORY_DAYS`) — і для споживання, і (нове) для сонячної генерації.
- **Обмежено температурну корекцію** часткою від бази, щоб екстремальна погода не могла домінувати над прогнозом.
- Залишено `STORAGE_VERSION = 1` — підняття цього номера вимагає функції міграції в `Store` Home Assistant, інакше при завантаженні виникає `NotImplementedError`; нові поля безпечно підвантажуються через `.get()` з дефолтами.
- Написи атрибутів (напр. `Internal N-day avg`) тепер будуються з `HISTORY_DAYS`, а не хардкодяться — більше не можуть розійтися з реальним значенням.
