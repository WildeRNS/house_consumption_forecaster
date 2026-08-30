<p align="center">
  <b>Language / Мова:</b> 
  <a href="#-house-consumption-adaptive-forecaster-for-home-assistant">🇬🇧 English</a> | 
  <a href="#-адаптивний-прогнозист-споживання-електроенергії-для-home-assistant">🇺🇦 Українська</a>
</p>

---

# ⚡ House Consumption Adaptive Forecaster for Home Assistant

An adaptive custom integration for Home Assistant designed to accurately predict daily household energy consumption for **today** and **tomorrow**. 

It uses a dynamic self-learning model that accounts for base electrical load (calculated via a 7-day rolling average), solar production impact (positive correlation with Solcast / Volcast / Forecast.Solar), ambient temperature offsets, and workday/weekend consumption patterns.

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
- **7-Day Historical Baseline:** Uses a strict 7-day rolling average to closely track your most recent baseline consumption, discarding outdated habits.
- **Positive Solar Correlation:** Understands that excess solar generation acts as a *stimulus* for consumption (e.g., turning on boilers, washing machines). Higher solar forecasts dynamically increase the expected house consumption.
- **Floor Clamping Protection:** The forecast for "Today" mathematically cannot drop below the energy your house has already consumed up to the current minute.
- **HVAC & Weather Adjustment:** Automatically adjusts forecasts based on cooling (> 25°C) or heating (< 15°C) requirements.
- **Weekend Load Boost:** Incorporates lifestyle changes on non-working days via Home Assistant's `workday` integration or standard calendar logic (+15% weekend boost).
- **Anomaly Protection & Rate Limiting:** Clamps weight adaptations to a maximum step of $\pm 0.05$ per day alongside absolute boundaries to prevent single-day consumption anomalies from distorting the model.
- **Persistent Weights Storage:** Learned weights and baseline statistics survive system restarts using Home Assistant's native Storage Helper (`Store`).
- **Unified Device Architecture:** Groups entities under a single virtual device with clean entity naming.
- **100% UI Configurable:** Full support for `ConfigFlow` and `OptionsFlow` — no YAML editing required.

---

## 🧠 How It Works (Mathematical & Learning Logic)

### 1. Forecast Calculation Model

The forecast for a given day is calculated using the following sequential steps:

1. **Base Load Extraction (7-Day Average):**
   Calculated as 30% of the historical average daily consumption over the last 7 days:
   $$\text{Base Load} = \max(\text{7-Day Avg} \times 0.3, 3.0)$$

2. **Solar Factor Addition:**
   Calculates the extra consumption stimulated by expected solar energy:
   $$\text{Solar Addition} = \text{Solar Forecast} \times W_{\text{solar}}$$

3. **Temperature Offsets:**
   - **Cooling (> 25°C):** $\text{Offset} = (T - 25.0) \times W_{\text{cool}}$
   - **Heating (< 15°C):** $\text{Offset} = (15.0 - T) \times W_{\text{heat}}$

4. **Weekend Boost:**
   If `workday_sensor` state is `off` (or Saturday/Sunday):
   $$\text{Estimated Total} = \text{Estimated Total} \times 1.15$$

5. **Final Assembly & Bias Correction:**
   $$\text{Raw Forecast} = (\text{7-Day Avg} \times W_{\text{bias correction}}) + \text{Temperature Offset} + \text{Solar Addition}$$

6. **Floor Clamping & Saturation Bounds:**
   To avoid invalid predictions, output is restricted against the minimum base load and the actual current consumption (for today's forecast):
   $$\text{Forecast} = \max(\text{Raw Forecast}, \text{Base Load}, \text{Actual Current Consumption})$$

---

### 2. Auto-Calibration Feedback Loop

Every night at midnight (or upon date transition checked via ISO date tracking), the integration evaluates performance:

1. Appends yesterday's actual consumption to the 7-day rolling history array (dropping the oldest day).
2. Computes relative error and MAPE (Mean Absolute Percentage Error):
   $$\text{Relative Error} = \frac{\text{Actual Yesterday} - \text{Forecast Yesterday}}{\text{Actual Yesterday}}$$
3. Updates weights using learning rate $\eta = 0.05$ with strict step limits ($\Delta \le \pm 0.05$):
   - **Bias Correction:** $W_{\text{bias}} \leftarrow W_{\text{bias}} + \text{clamp}(\eta \times \text{Relative Error}, -0.05, 0.05)$
   - **Cooling Coeff ($W_{\text{cool}}$):** Adjusted if average temperature exceeded 25°C.
   - **Heating Coeff ($W_{\text{heat}}$):** Adjusted if average temperature dropped below 15°C.
   - **Solar Weight ($W_{\text{solar}}$):** Adjusted positively based on the ratio of forecast error to actual solar yield.
4. **Global Boundary Enforcement:**
   $$W_{\text{bias}} \in [0.5, 1.5], \quad W_{\text{cool}} \in [0.0, 2.0], \quad W_{\text{heat}} \in [0.0, 3.0], \quad W_{\text{solar}} \in [0.0, 1.5]$$
5. Automatically saves updated weights to `.storage/house_consumption_forecaster_<entry_id>_weights`.

---

## ⏱ Sensor Calibration Timeline

The integration relies on a daily feedback loop at midnight to continuously calibrate its internal weights:

* **Day 1 (First Midnight):** Performs its first actual vs. forecast comparison, initiates the 7-day history array, and applies the initial bias correction ($W_{\text{bias}}$).
* **Days 3–5 (Core Learning Phase):** Main adaptation period. The $W_{\text{bias}}$ multiplier and temperature weights converge toward your home's realistic average.
* **1–2 Weeks (Full Stabilization):** Complete self-learning cycle. The model fills its 7-day history array and captures enough weekday/weekend transitions to fine-tune the `weekend_boost` and solar positive correlation.

---
*(Installation, Configuration, and Entities sections remain unchanged)*
---

<p align="center">
  <a href="#-house-consumption-adaptive-forecaster-for-home-assistant">⬆ Нагору до англійської версії / Back to English</a>
</p>

# ⚡ Адаптивний прогнозист споживання електроенергії для Home Assistant

Адаптивна кастомна інтеграція для Home Assistant, розроблена для точного прогнозування добового споживання електроенергії будинком на **сьогодні** та **завтра**.

Інтеграція використовує динамічну модель з автонавчанням, яка враховує базове електричне навантаження (на основі 7-денної історії), стимулюючий вплив сонячної генерації (додатна кореляція з Solcast / Volcast / Forecast.Solar), температурну корекцію (опалення/охолодження) та різницю в профілі споживання між робочими та вихідними днями.

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

- **Адаптивний модуль самонавчання:** Щоночі о півночі порівнює вчорашній прогноз із фактичним добовим споживанням та самостійно коригує коефіцієнти.
- **7-денна історична база:** Замість безкінечного усереднення використовується масив за останні 7 днів для максимальної відповідності вашим поточним звичкам.
- **Додатна кореляція з СЕС:** Розуміє, що наявність сонця стимулює використання додаткових приладів (бойлери, пралки). Чим вищий прогноз генерації, тим вищим буде прогноз споживання будинку.
- **Захист від провалів (Floor Clamping):** Прогноз на "Сьогодні" математично не може впасти нижче того обсягу енергії, який ваш будинок *вже* спожив на поточну хвилину.
- **Температурна компенсація:** Автоматично коригує прогноз залежно від потреби в охолодженні (> 25°C) або опаленні (< 15°C).
- **Коригування на вихідні дні:** Враховує зміну побутового навантаження у неробочі дні (+15% до бази).
- **Захист від аномалій:** Обмежує добову зміну кожного коефіцієнта вектором $\pm 0.05$, що запобігає спотворенню моделі через випадкові сплески споживання.
- **Збереження коефіцієнтів:** Навчені коефіцієнти зберігаються у внутрішній базі даних Home Assistant (`Store`).

---

## 🧠 Принцип роботи (Математична модель та автонавчання)

### 1. Математична модель розрахунку прогнозу

Розрахунок прогнозу здійснюється за такими послідовними кроками:

1. **Розрахунок базового навантаження (Середнє за 7 днів):**
   Розраховується як 30% від середньодобового споживання за останній тиждень:
   $$\text{Базове навантаження} = \max(\text{Середнє за 7 днів} \times 0.3, 3.0)$$

2. **Врахування стимулюючого сонячного фактора:**
   Оцінюється додаткове споживання, викликане надлишком сонячної енергії:
   $$\text{Прирощення СЕС} = \text{Прогноз СЕС} \times W_{\text{solar}}$$

3. **Температурна корекція:**
   - **Охолодження (> 25°C):** $\text{Корекція} = (T - 25.0) \times W_{\text{cool}}$
   - **Опалення (< 15°C):** $\text{Корекція} = (15.0 - T) \times W_{\text{heat}}$

4. **Коригування на вихідний день:**
   Якщо стан `workday_sensor` дорівнює `off` (або субота/неділя):
   $$\text{Розрахункове споживання} = \text{Розрахункове споживання} \times 1.15$$

5. **Підсумкова збірка та Bias-корекція:**
   $$\text{Сирий прогноз} = (\text{Середнє за 7 днів} \times W_{\text{bias correction}}) + \text{Темп. корекція} + \text{Прирощення СЕС}$$

6. **Сатурація та Floor Clamping (Межі безпеки):**
   Для виключення занижених значень результат порівнюється з поточними показами лічильника:
   $$\text{Фінальний прогноз} = \max(\text{Сирий прогноз}, \text{Базове навантаження}, \text{Поточне споживання})$$

---

### 2. Цикл автоматичного самонавчання

Щодня о півночі координатор здійснює перевірку та калібрування:

1. Додає фактичне споживання за вчорашній день до 7-денного масиву історії (видаляючи найстаріший запис).
2. Обчислюється відносна помилка та середня відсоткова помилка (MAPE):
   $$\text{Відносна помилка} = \frac{\text{Факт вчора} - \text{Прогноз вчора}}{\text{Факт вчора}}$$
3. Оновлюються ваги з коефіцієнтом навчання $\eta = 0.05$ та обмеженням максимального кроку ($\Delta \le \pm 0.05$):
   - **Bias Correction:** $W_{\text{bias}} \leftarrow W_{\text{bias}} + \text{clamp}(\eta \times \text{Відносна помилка}, -0.05, 0.05)$
   - **Сонячна вага ($W_{\text{solar}}$):** коригується *у плюс* залежно від похибки відносно обсягу генерації СЕС.
4. **Контроль допустимих меж:**
   $$W_{\text{bias}} \in [0.5, 1.5], \quad W_{\text{cool}} \in [0.0, 2.0], \quad W_{\text{heat}} \in [0.0, 3.0], \quad W_{\text{solar}} \in [0.0, 1.5]$$
5. Оновлені коефіцієнти автоматично перезаписуються у файл `.storage`.