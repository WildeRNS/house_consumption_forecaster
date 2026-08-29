<p center>
  <b>Language / Мова:</b> 
  <a href="#-house-consumption-adaptive-forecaster-for-home-assistant">🇬🇧 English</a> | 
  <a href="#-адаптивний-прогнозист-споживання-електроенергії-для-home-assistant">🇺🇦 Українська</a>
</p>

---

# ⚡ House Consumption Adaptive Forecaster for Home Assistant

An adaptive custom integration for Home Assistant designed to accurately predict daily household energy consumption for **today** and **tomorrow**. 

It uses a dynamic self-learning model that accounts for base electrical load (calculated via Exponential Moving Average), solar production impact (Solcast / Volcast), ambient temperature offsets, and workday/weekend consumption patterns.

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

---

## 🚀 Features

- **Adaptive Self-Learning Engine:** Automatically compares yesterday's prediction against actual daily consumption at midnight and self-calibrates system coefficients using dynamic feedback loops.
- **Historical EMA Baseline:** Uses Exponential Moving Average for daily historical baseline to ensure accurate morning reports (e.g., at 07:00) without dips caused by freshly reset daily counters.
- **Solar Generation Factor:** Dynamically calculates house energy dependence on solar generation.
- **HVAC & Weather Adjustment:** Automatically adjusts forecasts based on heating (< 22°C) or cooling (> 24°C) requirements.
- **Weekend Load Boost:** Incorporates lifestyle changes on non-working days via Home Assistant's `workday` integration.
- **Anomaly Protection (Saturation Limits):** Clamps raw forecasts within realistic minimum and maximum boundaries to prevent rogue sensor readings from ruining predictions.
- **Persistent Weights Storage:** Learned weights survive system restarts using Home Assistant Storage Helpers (`Store`).
- **100% UI Configurable:** Full support for `ConfigFlow` and `OptionsFlow` — no YAML editing required.

---

## 🧠 How It Works (Mathematical & Learning Logic)

### 1. Forecast Calculation Model

The forecast for a given day is calculated using the following sequential steps:

1. **Base Load Extraction (Historical EMA):**
   Calculated as 30% of historical average daily consumption (tracked via Exponential Moving Average — EMA), ensuring early morning forecasts remain accurate and are not biased by low initial daily counter readings:
   $$\text{Base Load} = \max(\text{Historic Daily Avg (EMA)} \times 0.3, 3.0)$$

2. **Solar Factor Adjustment:**
   Calculates how much solar energy reduces grid/home energy reliance:
   $$\text{Solar Factor} = \left( \frac{\text{Historic Daily Avg} - \text{Base Load}}{\max(\text{Solar Actual}, 1.0)} \right) \times W_{\text{solar}}$$
   $$\text{Solar Addition} = \text{Solar Forecast} \times \text{Solar Factor}$$

3. **Temperature Offsets:**
   - **Cooling (> 24°C):** $\text{Offset} = (T - 24) \times W_{\text{cool}}$
   - **Heating (< 22°C):** $\text{Offset} = (22 - T) \times W_{\text{heat}}$

4. **Weekend Boost:**
   If `workday_sensor` state is `off` (weekend/holiday):
   $$\text{Weekend Factor} = 1.0 + W_{\text{weekend boost}}$$

5. **Final Assembly & Bias Correction:**
   $$\text{Raw Forecast} = (\text{Base Load} + \text{Solar Addition} + \text{Temperature Offset}) \times \text{Weekend Factor} \times W_{\text{bias correction}}$$

6. **Saturation Bounds (Min/Max Clamping):**
   To avoid extreme outliers, the output is restricted:
   $$\text{Forecast} = \max(\text{Base Load}, \min(\text{Raw Forecast}, \text{Historic Daily Avg} \times 1.35))$$

---

### 2. Auto-Calibration Feedback Loop

Every night at midnight (or upon day transition), the integration evaluates performance:

1. Updates historical average daily consumption using Exponential Moving Average (EMA):
   $$\text{EMA}_{\text{new}} = (\text{EMA}_{\text{old}} \times 0.8) + (\text{Actual Yesterday} \times 0.2)$$
2. Computes relative error:
   $$\text{Relative Error} = \frac{\text{Actual Yesterday} - \text{Forecast Yesterday}}{\text{Actual Yesterday}}$$
3. Calculates MAPE (Mean Absolute Percentage Error) and updates weights using a learning rate ($\eta = 0.05$):
   - **Bias Correction:** $W_{\text{bias}} \leftarrow W_{\text{bias}} + \eta \times \text{Relative Error}$
   - **Cooling Coeff:** Adjusted if temperature exceeded 24°C.
   - **Heating Coeff:** Adjusted if temperature dropped below 22°C.
   - **Weekend Boost:** Adjusted if yesterday was a non-working day.
4. Automatically saves the updated weights to `/config/.storage/house_consumption_forecaster_learned_weights`.

---

## ⏱ Sensor Calibration Timeline

The integration relies on a daily feedback loop at midnight to continuously calibrate its internal weights:

* **Day 1 (First Midnight):** The integration performs its first actual vs. forecast comparison, updates the daily historical base average (EMA), and applies the initial bias correction ($W_{\text{bias}}$).
* **Days 3–5 (Core Learning Phase):** Main adaptation period. The $W_{\text{bias}}$ multiplier and temperature weights converge toward your home's realistic average daily baseline (e.g., 8–10 kWh/day).
* **1–2 Weeks (Full Stabilization):** Complete self-learning cycle. The model captures enough weekday/weekend transitions to fine-tune the `weekend_boost` multiplier and seasonal HVAC coefficients.

---

## 📦 Installation

### Method 1: HACS (Recommended)

1. Open **HACS** in Home Assistant.
2. Click the top-right menu (three dots) and select **Custom repositories**.
3. Add the repository URL: `https://github.com/WildeRNS/house_consumption_forecaster`
4. Category: **Integration**.
5. Click **Add**, find `House Consumption Forecaster` in the list, and click **Download**.
6. Restart Home Assistant.

### Method 2: Manual Installation

1. Download the latest release from the Releases page.
2. Copy the `custom_components/house_consumption_forecaster` directory from the archive into your Home Assistant's `/config/custom_components/` directory.
3. Your path should look like: `/config/custom_components/house_consumption_forecaster/manifest.json`
4. Restart Home Assistant.

---

## ⚙️ Configuration

1. Go to **Settings** $\rightarrow$ **Devices & Services**.
2. Click **Add Integration** and search for **House Consumption Forecaster**.
3. Select your input entities:
   - **Daily Consumption Sensor:** Cumulative house consumption sensor in kWh (`sensor.daily_consumption`).
   - **Actual Solar Generation Sensor:** Cumulative daily PV generation sensor in kWh.
   - **Solar Forecast (Today):** Solcast / Volcast expected daily generation sensor for today.
   - **Solar Forecast (Tomorrow):** Solcast / Volcast expected daily generation sensor for tomorrow.
   - **Temperature Sensor:** Outdoor ambient temperature or weather forecast entity.
   - **Workday Binary Sensor:** Binary sensor determining workdays vs weekends (`binary_sensor.workday_sensor`).

> 💡 **Need to change sensors later?** Click **Configure** on the integration card to open the **Options Flow** modal and update mappings anytime.

---

## 📊 Entities & Attributes

The integration creates two primary sensor entities:

1. `sensor.house_energy_forecast_today` — Predicted consumption for today (in kWh).
2. `sensor.house_energy_forecast_tomorrow` — Predicted consumption for tomorrow (in kWh).

### State Attributes:
Each entity exposes learned model parameters in its state attributes:
- `avg_daily_consumption`: Learned historic daily consumption baseline (in kWh).
- `bias_correction`: Current multiplicative bias scale factor.
- `temp_cool_coeff`: Cooling load adaptation multiplier.
- `temp_heat_coeff`: Heating load adaptation multiplier.
- `weekend_boost`: Extra load multiplier applied on weekends.
- `last_mape`: Last calculated forecast percentage error (%).

---
---

<p center>
  <a href="#-house-consumption-adaptive-forecaster-for-home-assistant">⬆ Нагору до англійської версії / Back to English</a>
</p>

# ⚡ Адаптивний прогнозист споживання електроенергії для Home Assistant

Адаптивна кастомна інтеграція для Home Assistant, розроблена для точного прогнозування добового споживання електроенергії будинком на **сьогодні** та **завтра**.

Інтеграція використовує динамічну модель з автонавчанням, яка враховує базове електричне навантаження (на основі історичного EMA), вплив сонячної генерації (Solcast / Volcast), температурну корекцію (опалення/охолодження) та різницю в профілі споживання між робочими та вихідними днями.

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

---

## 🚀 Можливості

- **Адаптивний модуль самонавчання:** Щоночі о півночі порівнює вчорашній прогноз із фактичним добовим споживанням та самостійно коригує коефіцієнти системи за принципом зворотного зв'язку (Feedback Loop).
- **Історичний базовий рівень (EMA):** Використовує експоненціально зважене середнє значення історичного споживання, що гарантує точність ранкових звітів (наприклад, о 07:00) без просідання через оновлений о півночі лічильник.
- **Сонячний фактор:** Динамічно розраховує залежність споживання будинку від рівня сонячної генерації.
- **Температурна компенсація:** Автоматично коригує прогноз залежно від потреби в охолодженні (> 24°C) або опаленні (< 22°C).
- **Коригування на вихідні дні:** Враховує зміну побутового навантаження у неробочі дні за допомогою системного сенсора `workday`.
- **Захист від аномалій (Сатурація):** Обмежує вихідні значення прогнозу розумними мінімальними та максимальними межами, запобігаючи збоям через некоректні дані сенсорів.
- **Збереження коефіцієнтів:** Навчені коефіцієнти зберігаються у внутрішній базі даних Home Assistant (`Store`) і не скидаються при перезапуску системи.
- **100% GUI налаштування:** Повна підтримка `ConfigFlow` та `OptionsFlow` — жодного редагування YAML файлів.

---

## 🧠 Принцип роботи (Математична модель та автонавчання)

### 1. Математична модель розрахунку прогнозу

Розрахунок прогнозу здійснюється за такими послідовними кроками:

1. **Розрахунок базового навантаження (Історичний EMA):**
   Розраховується як 30% від історичного середньодобового споживання (з використанням експоненціально зваженого середнього — EMA). Це гарантує точні ранкові прогнози (наприклад, о 07:00) без просідання через оновлений о півночі лічильник:
   $$\text{Базове навантаження} = \max(\text{Історичне середнє (EMA)} \times 0.3, 3.0)$$

2. **Врахування сонячного фактора:**
   Оцінюється рівень заміщення мережевого споживання власною генерацією СЕС:
   $$\text{Сонячний фактор} = \left( \frac{\text{Історичне середнє} - \text{Базове навантаження}}{\max(\text{Факт СЕС}, 1.0)} \right) \times W_{\text{solar}}$$
   $$\text{Прирощення СЕС} = \text{Прогноз СЕС} \times \text{Сонячний фактор}$$

3. **Температурна корекція:**
   - **Охолодження (> 24°C):** $\text{Корекція} = (T - 24) \times W_{\text{cool}}$
   - **Опалення (< 22°C):** $\text{Корекція} = (22 - T) \times W_{\text{heat}}$

4. **Коригування на вихідний день:**
   Якщо стан `workday_sensor` дорівнює `off` (вихідний/свято):
   $$\text{Множник вихідного дня} = 1.0 + W_{\text{weekend boost}}$$

5. **Підсумкова збірка та Bias-корекція:**
   $$\text{Сирий прогноз} = (\text{Базове навантаження} + \text{Прирощення СЕС} + \text{Темп. корекція}) \times \text{Множник вихідного дня} \times W_{\text{bias correction}}$$

6. **Сатурація (Межі безпеки):**
   Для виключення аномальних стрибків значення обмежується діапазоном:
   $$\text{Фінальний прогноз} = \max(\text{Базове навантаження}, \min(\text{Сирий прогноз}, \text{Історичне середнє} \times 1.35))$$

---

### 2. Цикл автоматичного самонавчання

Щодня о півночі координатор здійснює перевірку та калібрування:

1. Оновлює історичне середньодобове споживання за формулою експоненціального усереднення (EMA):
   $$\text{EMA}_{\text{нов}} = (\text{EMA}_{\text{стар}} \times 0.8) + (\text{Факт вчора} \times 0.2)$$
2. Обчислюється відносна помилка вчорашнього прогнозу:
   $$\text{Відносна помилка} = \frac{\text{Факт вчора} - \text{Прогноз вчора}}{\text{Факт вчора}}$$
3. Розраховується середня помилка (MAPE) та оновлюються ваги з коефіцієнтом навчання ($\eta = 0.05$):
   - **Bias Correction (Основне зміщення):** $W_{\text{bias}} \leftarrow W_{\text{bias}} + \eta \times \text{Відносна помилка}$
   - **Коефіцієнт охолодження:** коригується, якщо температура перевищувала 24°C.
   - **Коефіцієнт опалення:** коригується, якщо температура була нижчою за 22°C.
   - **Буст вихідного дня:** коригується, якщо вчора був вихідний день.
4. Оновлені коефіцієнти автоматично перезаписуються у файл `/config/.storage/house_consumption_forecaster_learned_weights`.

---

## ⏱ Терміни калібрування сенсорів

Система працює на основі добового циклу зворотного зв'язку (Feedback Loop) о півночі, тому адаптація проходить у кілька етапів:

* **1-ша доба (Перша північ):** Інтеграція вперше порівнює реальне споживання з прогнозом, оновлює експоненціальне середнє (EMA) та вносить першу правку в коефіцієнт зміщення ($W_{\text{bias}}$).
* **3–5 днів (Основна фаза навчання):** Головний період адаптації. Коефіцієнт $W_{\text{bias}}$ та температурні ваги вирівнюються під реальний середній рівень споживання вашого будинку (наприклад, 8–10 кВт·год/день).
* **1–2 тижні (Повна стабілізація):** Повний цикл автонавчання. Алгоритм захоплює декілька вихідних днів для точного калібрування множника `weekend_boost` та сезонних температурних коефіцієнтів.

---

## 📦 Встановлення

### Спосіб 1: Через HACS (Рекомендовано)

1. Відкрийте **HACS** у вашому Home Assistant.
2. Натисніть на три крапки у правому верхньому кутку та виберіть **Custom repositories** (Користувацькі репозиторії).
3. Додайте URL репозиторію: `https://github.com/WildeRNS/house_consumption_forecaster`
4. Категорія: **Integration**.
5. Натисніть **Add**, знайдіть `House Consumption Forecaster` у списку та натисніть **Download**.
6. Перезапустіть Home Assistant.

### Спосіб 2: Ручне встановлення

1. Завантажте останній реліз зі сторінки Releases.
2. Скопіюйте папку `house_consumption_forecaster` з директорії `custom_components` архіву у папку `/config/custom_components/` вашого Home Assistant.
3. Шлях до файлів повинен мати вигляд: `/config/custom_components/house_consumption_forecaster/manifest.json`
4. Перезапустіть Home Assistant.

---

## ⚙️ Налаштування

1. Перейдіть у **Налаштування** $\rightarrow$ **Пристрої та служби** (Devices & Services).
2. Натисніть **Додати інтеграцію** та знайдіть **House Consumption Forecaster**.
3. Оберіть ваші вхідні сутності:
   - **Сенсор споживання будинку:** Накопичувальний сенсор споживання будинку за день у кВт·год (`sensor.daily_consumption`).
   - **Сенсор фактичної генерації СЕС:** Накопичувальний сенсор добової генерації СЕС у кВт·год.
   - **Прогноз СЕС (Сьогодні):** Сенсор очікуваної генерації на сьогодні від Solcast / Volcast.
   - **Прогноз СЕС (Завтра):** Сенсор очікуваної генерації на завтра від Solcast / Volcast.
   - **Сенсор температури:** Сенсор зовнішньої температури або сутність прогнозу погоди.
   - **Binary Sensor робочих днів:** Сенсор визначення робочих/вихідних днів (`binary_sensor.workday_sensor`).

> 💡 **Змінилися сенсори?** Натисніть кнопку **Налаштувати** (Options) на картці інтеграції, щоб змінити прив'язку сутностей у будь-який момент.

---

## 📊 Сутності та атрибути

Інтеграція створює дві основні сутності:

1. `sensor.house_energy_forecast_today` — Прогнозоване споживання на сьогодні (у кВт·год).
2. `sensor.house_energy_forecast_tomorrow` — Прогнозоване споживання на завтра (у кВт·год).

### Атрибути стану:
Кожен сенсор містить у своїх атрибутах поточні навчені параметри моделі:
- `avg_daily_consumption`: Навчене історичне середньодобове споживання будинку (у кВт·год).
- `bias_correction`: Поточний мультиплікатор загального зміщення.
- `temp_cool_coeff`: Коефіцієнт адаптації до навантаження охолодження.
- `temp_heat_coeff`: Коефіцієнт адаптації до навантаження опалення.
- `weekend_boost`: Додатковий коефіцієнт навантаження для вихідних днів.
- `last_mape`: Останній розрахований відсоток помилки прогнозу (%).