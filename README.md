<p align="center">
  <b>Language / Мова:</b> 
  <a href="#-house-consumption-adaptive-forecaster-for-home-assistant">🇬🇧 English</a> | 
  <a href="#-адаптивний-прогнозист-споживання-електроенергії-для-home-assistant">🇺🇦 Українська</a>
</p>

---

# ⚡ House Consumption Adaptive Forecaster for Home Assistant

An adaptive custom integration for Home Assistant designed to accurately predict daily household energy consumption for **today** and **tomorrow**. 

It uses a dynamic self-learning model that accounts for base electrical load (calculated via Exponential Moving Average), solar production impact (Solcast / Volcast / Forecast.Solar), ambient temperature offsets, and workday/weekend consumption patterns.

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
- **Historical EMA Baseline:** Uses Exponential Moving Average (80% history, 20% recent day) for daily baseline tracking, ensuring early morning forecasts remain reliable without dips caused by freshly reset daily counters.
- **Solar Generation Factor:** Dynamically calculates house energy dependence on solar generation and factors in expected PV production.
- **HVAC & Weather Adjustment:** Automatically adjusts forecasts based on cooling (> 25°C) or heating (< 15°C) requirements.
- **Weekend Load Boost:** Incorporates lifestyle changes on non-working days via Home Assistant's `workday` integration or standard calendar logic (+15% weekend boost).
- **Anomaly Protection & Rate Limiting:** Clamps weight adaptations to a maximum step of $\pm 0.05$ per day alongside absolute boundaries ($W_{\text{bias}} \in [0.5, 1.5]$) to prevent single-day consumption anomalies from distorting the model.
- **Persistent Weights Storage:** Learned weights and baseline statistics survive system restarts using Home Assistant's native Storage Helper (`Store`).
- **Unified Device Architecture:** Groups entities under a single virtual device with clean entity naming (`sensor.house_energy_forecast_today` and `sensor.house_energy_forecast_tomorrow`).
- **100% UI Configurable:** Full support for `ConfigFlow` and `OptionsFlow` — no YAML editing required.

---

## 🧠 How It Works (Mathematical & Learning Logic)

### 1. Forecast Calculation Model

The forecast for a given day is calculated using the following sequential steps:

1. **Base Load Extraction (Historical EMA):**
   Calculated as 30% of historical average daily consumption (tracked via Exponential Moving Average — EMA), ensuring early morning forecasts remain stable:
   $$\text{Base Load} = \max(\text{Historic Daily Avg (EMA)} \times 0.3, 3.0)$$

2. **Solar Factor Adjustment:**
   Calculates how much solar energy reduces grid reliance:
   $$\text{Solar Addition} = \text{Solar Forecast} \times W_{\text{solar}}$$

3. **Temperature Offsets:**
   - **Cooling (> 25°C):** $\text{Offset} = (T - 25.0) \times W_{\text{cool}}$
   - **Heating (< 15°C):** $\text{Offset} = (15.0 - T) \times W_{\text{heat}}$

4. **Weekend Boost:**
   If `workday_sensor` state is `off` (or Saturday/Sunday):
   $$\text{Estimated Total} = \text{Estimated Total} \times 1.15$$

5. **Final Assembly & Bias Correction:**
   $$\text{Raw Forecast} = \text{Historic Daily Avg} \times W_{\text{bias correction}} + \text{Temperature Offset} + \text{Solar Addition}$$

6. **Saturation Bounds (Min Clamping):**
   To avoid invalid predictions, output is restricted against the minimum base load:
   $$\text{Forecast} = \max(\text{Raw Forecast}, \text{Base Load})$$

---

### 2. Auto-Calibration Feedback Loop

Every night at midnight (or upon date transition checked via ISO date tracking), the integration evaluates performance:

1. Updates historical average daily consumption using Exponential Moving Average (EMA):
   $$\text{EMA}_{\text{new}} = (\text{EMA}_{\text{old}} \times 0.8) + (\text{Actual Yesterday} \times 0.2)$$
2. Computes relative error and MAPE (Mean Absolute Percentage Error):
   $$\text{Relative Error} = \frac{\text{Actual Yesterday} - \text{Forecast Yesterday}}{\text{Actual Yesterday}}$$
   $$\text{MAPE} = \left| \frac{\text{Actual Yesterday} - \text{Forecast Yesterday}}{\text{Actual Yesterday}} \right| \times 100\%$$
3. Updates weights using learning rate $\eta = 0.05$ with strict step limits ($\Delta \le \pm 0.05$):
   - **Bias Correction:** $W_{\text{bias}} \leftarrow W_{\text{bias}} + \text{clamp}(\eta \times \text{Relative Error}, -0.05, 0.05)$
   - **Cooling Coeff ($W_{\text{cool}}$):** Adjusted if average temperature exceeded 25°C.
   - **Heating Coeff ($W_{\text{heat}}$):** Adjusted if average temperature dropped below 15°C.
   - **Solar Weight ($W_{\text{solar}}$):** Adjusted based on actual solar yield ratio.
4. **Global Boundary Enforcement:**
   $$W_{\text{bias}} \in [0.5, 1.5], \quad W_{\text{cool}} \in [0.0, 2.0], \quad W_{\text{heat}} \in [0.0, 3.0], \quad W_{\text{solar}} \in [-1.0, 0.0]$$
5. Automatically saves updated weights to `.storage/house_consumption_forecaster_<entry_id>_weights`.

---

## ⏱ Sensor Calibration Timeline

The integration relies on a daily feedback loop at midnight to continuously calibrate its internal weights:

* **Day 1 (First Midnight):** The integration performs its first actual vs. forecast comparison, updates the daily historical base average (EMA), and applies the initial bias correction ($W_{\text{bias}}$).
* **Days 3–5 (Core Learning Phase):** Main adaptation period. The $W_{\text{bias}}$ multiplier and temperature weights converge toward your home's realistic average daily baseline.
* **1–2 Weeks (Full Stabilization):** Complete self-learning cycle. The model captures enough weekday/weekend transitions to fine-tune the `weekend_boost` behavior and seasonal HVAC coefficients.

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

1. Download the latest release archive.
2. Copy the `custom_components/house_consumption_forecaster` directory into your Home Assistant's `/config/custom_components/` directory.
3. Path structure: `/config/custom_components/house_consumption_forecaster/manifest.json`
4. Restart Home Assistant.

---

## ⚙️ Configuration

1. Go to **Settings** $\rightarrow$ **Devices & Services**.
2. Click **Add Integration** and search for **House Consumption Forecaster**.
3. Select your input entities:
   - **Daily Consumption Sensor:** Cumulative house consumption sensor in kWh (`sensor.daily_consumption`).
   - **Actual Solar Generation Sensor:** Cumulative daily PV generation sensor in kWh.
   - **Solar Forecast (Today):** Solcast / Volcast / Forecast.Solar expected daily generation sensor for today.
   - **Solar Forecast (Tomorrow):** Solcast / Volcast / Forecast.Solar expected daily generation sensor for tomorrow.
   - **Temperature Sensor:** Outdoor ambient temperature or weather forecast entity.
   - **Workday Binary Sensor:** Binary sensor determining workdays vs weekends (`binary_sensor.workday_sensor`).

> 💡 **Need to change sensors later?** Click **Configure** on the integration card to open the **Options Flow** modal and update mappings anytime.

---

## 📊 Entities & Attributes

The integration creates a unified device named **House Energy Forecast** containing two entities:

1. `sensor.house_energy_forecast_today` — Predicted consumption for today (in kWh).
2. `sensor.house_energy_forecast_tomorrow` — Predicted consumption for tomorrow (in kWh).

### State Attributes:
Each entity exposes learned model parameters in its state attributes:
- `Learned solar weight`: Learned multiplicative factor for solar production impact.
- `Learned temp cool coeff`: Cooling load adaptation coefficient (kWh/°C above 25°C).
- `Learned temp heat coeff`: Heating load adaptation coefficient (kWh/°C below 15°C).
- `Learned weekend boost pct`: Percentage boost applied on weekends (15.0% or 0.0%).
- `Learned bias correction`: Current multiplicative bias scale factor.
- `Last error mape pct`: Last calculated Mean Absolute Percentage Error (%).

---
---

<p align="center">
  <a href="#-house-consumption-adaptive-forecaster-for-home-assistant">⬆ Нагору до англійської версії / Back to English</a>
</p>

# ⚡ Адаптивний прогнозист споживання електроенергії для Home Assistant

Адаптивна кастомна інтеграція для Home Assistant, розроблена для точного прогнозування добового споживання електроенергії будинком на **сьогодні** та **завтра**.

Інтеграція використовує динамічну модель з автонавчанням, яка враховує базове електричне навантаження (на основі історичного EMA), вплив сонячної генерації (Solcast / Volcast / Forecast.Solar), температурну корекцію (опалення/охолодження) та різницю в профілі споживання між робочими та вихідними днями.

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
- **Історичний базовий рівень (EMA):** Використовує експоненціально зважене середнє значення (80% історія, 20% факт останньої доби), що гарантує точність ранкових прогнозах без просідання через оновлений лічильник.
- **Сонячний фактор:** Динамічно розраховує залежність споживання будинку від рівня сонячної генерації та враховує добові прогнози СЕС.
- **Температурна компенсація:** Автоматично коригує прогноз залежно від потреби в охолодженні (> 25°C) або опаленні (< 15°C).
- **Коригування на вихідні дні:** Враховує зміну побутового навантаження у неробочі дні за допомогою системного сенсора `workday` або календаря (+15% до бази).
- **Захист від аномалій та лімітування кроку:** Обмежує добову зміну кожного коефіцієнта вектором $\pm 0.05$ та жорсткими межами ($W_{\text{bias}} \in [0.5, 1.5]$), що запобігає спотворенню моделі через випадкові аномальні сплески споживання.
- **Збереження коефіцієнтів:** Навчені коефіцієнти та статистика зберігаються у внутрішній базі даних Home Assistant (`Store`) і не скидаються при перезапуску системи.
- **Єдина пристроєва архітектура:** Сенсори об'єднані у віртуальний пристрій «Прогноз споживання електроенергії» з короткими іменами (`sensor.house_energy_forecast_today` та `sensor.house_energy_forecast_tomorrow`).
- **100% GUI налаштування:** Повна підтримка `ConfigFlow` та `OptionsFlow` — жодного редагування YAML файлів.

---

## 🧠 Принцип роботи (Математична модель та автонавчання)

### 1. Математична модель розрахунку прогнозу

Розрахунок прогнозу здійснюється за такими послідовними кроками:

1. **Розрахунок базового навантаження (Історичний EMA):**
   Розраховується як 30% від історичного середньодобового споживання (з використанням експоненціально зваженого середнього — EMA):
   $$\text{Базове навантаження} = \max(\text{Історичне середнє (EMA)} \times 0.3, 3.0)$$

2. **Врахування сонячного фактора:**
   Оцінюється рівень заміщення мережевого споживання власною генерацією СЕС:
   $$\text{Прирощення СЕС} = \text{Прогноз СЕС} \times W_{\text{solar}}$$

3. **Температурна корекція:**
   - **Охолодження (> 25°C):** $\text{Корекція} = (T - 25.0) \times W_{\text{cool}}$
   - **Опалення (< 15°C):** $\text{Корекція} = (15.0 - T) \times W_{\text{heat}}$

4. **Коригування на вихідний день:**
   Якщо стан `workday_sensor` дорівнює `off` (або субота/неділя):
   $$\text{Розрахункове споживання} = \text{Розрахункове споживання} \times 1.15$$

5. **Підсумкова збірка та Bias-корекція:**
   $$\text{Сирий прогноз} = \text{Історичне середнє} \times W_{\text{bias correction}} + \text{Темп. корекція} + \text{Прирощення СЕС}$$

6. **Сатурація (Межі безпеки):**
   Для виключення занижених або від'ємних значень результат обмежується базовим рівнем:
   $$\text{Фінальний прогноз} = \max(\text{Сирий прогноз}, \text{Базове навантаження})$$

---

### 2. Цикл автоматичного самонавчання

Щодня о півночі (з контролем дати за ISO-форматом) координатор здійснює перевірку та калібрування:

1. Оновлює історичне середньодобове споживання за формулою експоненціального усереднення (EMA):
   $$\text{EMA}_{\text{нов}} = (\text{EMA}_{\text{стар}} \times 0.8) + (\text{Факт вчора} \times 0.2)$$
2. Обчислюється відносна помилка та середня відсоткова помилка (MAPE):
   $$\text{Відносна помилка} = \frac{\text{Факт вчора} - \text{Прогноз вчора}}{\text{Факт вчора}}$$
   $$\text{MAPE} = \left| \frac{\text{Факт вчора} - \text{Прогноз вчора}}{\text{Факт вчора}} \right| \times 100\%$$
3. Оновлюються ваги з коефіцієнтом навчання $\eta = 0.05$ та обмеженням максимального добового кроку ($\Delta \le \pm 0.05$):
   - **Bias Correction (Основне зміщення):** $W_{\text{bias}} \leftarrow W_{\text{bias}} + \text{clamp}(\eta \times \text{Відносна помилка}, -0.05, 0.05)$
   - **Коефіцієнт охолодження ($W_{\text{cool}}$):** коригується, якщо середньодобова температура перевищувала 25°C.
   - **Коефіцієнт опалення ($W_{\text{heat}}$):** коригується, якщо середньодобова температура була нижчою за 15°C.
   - **Сонячна вага ($W_{\text{solar}}$):** коригується залежно від відношення генерації до споживання.
4. **Контроль допустимих меж:**
   $$W_{\text{bias}} \in [0.5, 1.5], \quad W_{\text{cool}} \in [0.0, 2.0], \quad W_{\text{heat}} \in [0.0, 3.0], \quad W_{\text{solar}} \in [-1.0, 0.0]$$
5. Оновлені коефіцієнти автоматично перезаписуються у файл `.storage/house_consumption_forecaster_<entry_id>_weights`.

---

## ⏱ Терміни калібрування сенсорів

Система працює на основі добового циклу зворотного зв'язку (Feedback Loop) о півночі, тому адаптація проходить у кілька етапів:

* **1-ша доба (Перша північ):** Інтеграція вперше порівнює реальне споживання з прогнозом, оновлює експоненціальне середнє (EMA) та вносить першу правку в коефіцієнт зміщення ($W_{\text{bias}}$).
* **3–5 днів (Основна фаза навчання):** Головний період адаптації. Коефіцієнт $W_{\text{bias}}$ та температурні ваги вирівнюються під реальний середній рівень споживання вашого будинку.
* **1–2 тижні (Повна стабілізація):** Повний цикл автонавчання. Алгоритм захоплює декілька вихідних днів для точного калібрування логіки `weekend_boost` та сезонних температурних коефіцієнтів.

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
2. Скопіюйте папку `house_consumption_forecaster` з архіву у папку `/config/custom_components/` вашого Home Assistant.
3. Шлях до файлів повинен мати вигляд: `/config/custom_components/house_consumption_forecaster/manifest.json`
4. Перезапустіть Home Assistant.

---

## ⚙️ Налаштування

1. Перейдіть у **Налаштування** $\rightarrow$ **Пристрої та служби** (Devices & Services).
2. Натисніть **Додати інтеграцію** та знайдіть **House Consumption Forecaster**.
3. Оберіть ваші вхідні сутності:
   - **Сенсор споживання будинку:** Накопичувальний сенсор споживання будинку за день у кВт·год (`sensor.daily_consumption`).
   - **Сенсор фактичної генерації СЕС:** Накопичувальний сенсор добової генерації СЕС у кВт·год.
   - **Прогноз СЕС (Сьогодні):** Сенсор очікуваної генерації на сьогодні від Solcast / Volcast / Forecast.Solar.
   - **Прогноз СЕС (Завтра):** Сенсор очікуваної генерації на завтра від Solcast / Volcast / Forecast.Solar.
   - **Сенсор температури:** Сенсор зовнішньої температури або сутність прогнозу погоди.
   - **Binary Sensor робочих днів:** Сенсор визначення робочих/вихідних днів (`binary_sensor.workday_sensor`).

> 💡 **Змінилися сенсори?** Натисніть кнопку **Налаштувати** (Options) на картці інтеграції, щоб змінити прив'язку сутностей у будь-який момент.

---

## 📊 Сутності та атрибути

Інтеграція створює пристрій **Прогноз споживання електроенергії** з двома сутностями:

1. `sensor.house_energy_forecast_today` — Прогнозоване споживання на сьогодні (у кВт·год).
2. `sensor.house_energy_forecast_tomorrow` — Прогнозоване споживання на завтра (у кВт·год).

### Атрибути стану:
Кожен сенсор містить у своїх атрибутах поточні навчені параметри моделі:
- `Learned solar weight`: Навчений коефіцієнт впливу сонячної генерації.
- `Learned temp cool coeff`: Коефіцієнт адаптації до навантаження охолодження (кВт·год/°C понад 25°C).
- `Learned temp heat coeff`: Коефіціент адаптації до навантаження опалення (кВт·год/°C нижче 15°C).
- `Learned weekend boost pct`: Додатковий відсоток навантаження для вихідних днів (15.0% або 0.0%).
- `Learned bias correction`: Поточний мультиплікатор загального зміщення.
- `Last error mape pct`: Останній розрахований відсоток помилки прогнозу (%).