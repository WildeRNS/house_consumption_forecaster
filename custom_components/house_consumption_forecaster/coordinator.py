"""DataUpdateCoordinator for House Consumption Forecaster."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_CONSUMPTION_SENSOR,
    CONF_SOLAR_ACTUAL_SENSOR,
    CONF_SOLAR_FORECAST_TODAY,
    CONF_SOLAR_FORECAST_TOMORROW,
    CONF_WEATHER_ENTITY,
    CONF_HISTORY_DAYS,
    HISTORY_STORAGE_CAP,
    DEFAULT_HISTORY_DAYS,
    MIN_HISTORY_DAYS,
    MAX_HISTORY_DAYS,
    MIN_VALID_CONSUMPTION,
    BIAS_MIN,
    BIAS_MAX,
    BIAS_MAX_DAILY_STEP,
    SOLAR_WEIGHT_MIN,
    SOLAR_WEIGHT_MAX,
    SOLAR_WEIGHT_MAX_DAILY_STEP,
    SOLAR_RATIO_MIN,
    SOLAR_RATIO_MAX,
    TEMP_COEFF_MIN,
    TEMP_COEFF_MAX,
    TEMP_COEFF_MAX_DAILY_STEP,
    MAX_TEMP_EFFECT_RATIO,
    FORECAST_FLOOR_RATIO,
    FORECAST_CEILING_RATIO,
)

_LOGGER = logging.getLogger(__name__)
# УВАГА: не піднімайте цю версію без реалізації _async_migrate_func у
# підкласі Store -- HA викликає її автоматично при зміні номера версії,
# а без реалізації це кидає NotImplementedError при завантаженні старих
# даних. Нові поля (напр. solar_history) безпечно підвантажуються через
# .get(...) з дефолтом, тож окрема міграція тут не потрібна.
STORAGE_VERSION = 1


class AdaptiveForecasterCoordinator(DataUpdateCoordinator):
    """Координатор з логікою адаптивного самонавчання та збереженням стану.

    Модель прогнозу будується так:
      1. База - середнє добове споживання будинку за останні N днів, де N --
         період усереднення, який користувач обирає в Options
         (CONF_HISTORY_DAYS, за замовчуванням DEFAULT_HISTORY_DAYS). На
         диску завжди зберігається до HISTORY_STORAGE_CAP днів історії,
         тож зміна N в налаштуваннях діє миттєво, без очікування
         накопичення нових днів.
      2. Bias-корекція - невеликий навчений мультиплікатор (+-25%), що
         компенсує систематичну похибку моделі.
      3. Сонячна корекція - ВІДНОСНА: якщо прогноз генерації СЕС на
         конкретний день вищий за свій власний середній рівень за
         розрахунковий період, прогноз споживання пропорційно піднімається
         (сонячний день -> більше активності/навантаження вдень), і
         навпаки для похмурих днів. Це навмисно НЕ сира кВт*год-сума
         сонця, а коефіцієнт відхилення від норми, помножений на частку
         від середнього споживання -- так вага має сенс незалежно від
         розміру СЕС.
      4. Температурна корекція - додаткове навантаження на
         охолодження/опалення, обмежене часткою від середнього
         споживання, щоб не могло домінувати над рештою моделі.
      5. Прогноз завжди обмежений жорсткими підлогою/стелею відносно
         середнього споживання за розрахунковий період (сан-чек), а для
         "сьогодні" додатково ніколи не може бути нижчим за вже фактично
         спожите.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=15),
        )
        self.entry = entry
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_weights")

        self._consumption_history: list[float] = [9.0]
        self._solar_history: list[float] = []
        self._last_trained_date: str = ""

        self._daily_max_consumption: float = 0.0
        self._daily_max_solar: float = 0.0
        self._daily_temp_sum: float = 0.0
        self._daily_temp_count: int = 0

        self._current_forecast_cache: float = 9.0
        self._forecast_tomorrow_cache: float = 9.0
        self._last_known_states: dict[str, float] = {}

        self._w_bias: float = 1.0
        self._w_solar: float = 0.15
        self._w_temp_cool: float = 0.4
        self._w_temp_heat: float = 0.5
        self._last_error_mape: float = 0.0

    async def async_init_store(self) -> None:
        data = await self._store.async_load()
        if data:
            self._w_bias = max(BIAS_MIN, min(BIAS_MAX, data.get("w_bias", 1.0)))
            self._w_solar = max(SOLAR_WEIGHT_MIN, min(SOLAR_WEIGHT_MAX, data.get("w_solar", 0.15)))
            self._w_temp_cool = max(TEMP_COEFF_MIN, min(TEMP_COEFF_MAX, data.get("w_temp_cool", 0.4)))
            self._w_temp_heat = max(TEMP_COEFF_MIN, min(TEMP_COEFF_MAX, data.get("w_temp_heat", 0.5)))
            self._last_error_mape = data.get("last_error_mape", 0.0)
            self._last_trained_date = data.get("last_trained_date", "")

            self._daily_max_consumption = data.get("daily_max_consumption", 0.0)
            self._daily_max_solar = data.get("daily_max_solar", 0.0)
            self._daily_temp_sum = data.get("daily_temp_sum", 0.0)
            self._daily_temp_count = data.get("daily_temp_count", 0)

            self._current_forecast_cache = data.get("current_forecast_cache", 9.0)
            self._forecast_tomorrow_cache = data.get("forecast_tomorrow_cache", 9.0)
            self._last_known_states = data.get("last_known_states", {})

            hist = data.get("consumption_history")
            if hist and isinstance(hist, list):
                self._consumption_history = [x for x in hist if x >= MIN_VALID_CONSUMPTION][-HISTORY_STORAGE_CAP:]
                if not self._consumption_history:
                    self._consumption_history = [9.0]
            else:
                self._consumption_history = [9.0]

            solar_hist = data.get("solar_history")
            if solar_hist and isinstance(solar_hist, list):
                self._solar_history = [x for x in solar_hist if x >= 0][-HISTORY_STORAGE_CAP:]
            else:
                self._solar_history = []

    async def _async_save_store(self) -> None:
        data = {
            "w_bias": self._w_bias,
            "w_solar": self._w_solar,
            "w_temp_cool": self._w_temp_cool,
            "w_temp_heat": self._w_temp_heat,
            "consumption_history": self._consumption_history,
            "solar_history": self._solar_history,
            "last_error_mape": self._last_error_mape,
            "last_trained_date": self._last_trained_date,
            "daily_max_consumption": self._daily_max_consumption,
            "daily_max_solar": self._daily_max_solar,
            "daily_temp_sum": self._daily_temp_sum,
            "daily_temp_count": self._daily_temp_count,
            "current_forecast_cache": self._current_forecast_cache,
            "forecast_tomorrow_cache": self._forecast_tomorrow_cache,
            "last_known_states": self._last_known_states,
        }
        await self._store.async_save(data)

    def _get_config_value(self, key: str) -> Any:
        return self.entry.options.get(key) or self.entry.data.get(key)

    @property
    def _history_days(self) -> int:
        """Період усереднення (днів), обраний користувачем в Options."""
        raw = self._get_config_value(CONF_HISTORY_DAYS)
        if raw is None:
            return DEFAULT_HISTORY_DAYS
        try:
            value = int(round(float(raw)))
        except (TypeError, ValueError):
            return DEFAULT_HISTORY_DAYS
        return max(MIN_HISTORY_DAYS, min(MAX_HISTORY_DAYS, value))

    @property
    def _avg_period(self) -> float:
        """Середнє добове споживання будинку за обраний користувачем період."""
        n = self._history_days
        valid_history = [x for x in self._consumption_history if x >= MIN_VALID_CONSUMPTION][-n:]
        if not valid_history:
            return 9.0
        return sum(valid_history) / len(valid_history)

    @property
    def _avg_solar_period(self) -> float:
        """Середня фактична добова генерація СЕС за обраний користувачем період."""
        n = self._history_days
        valid = [x for x in self._solar_history if x >= 0][-n:]
        if not valid:
            return 0.0
        return sum(valid) / len(valid)

    def _get_sensor_value(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state and state.state not in ("unknown", "unavailable"):
            try:
                val = float(state.state)
                self._last_known_states[entity_id] = val
                return val
            except ValueError:
                pass
        return self._last_known_states.get(entity_id)

    def _get_weather_current_temp(self, entity_id: str | None) -> float | None:
        """Отримує поточну температуру з атрибутів weather сутності."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state and state.state not in ("unknown", "unavailable"):
            temp = state.attributes.get("temperature")
            if temp is not None:
                try:
                    val = float(temp)
                    self._last_known_states[entity_id + "_temp"] = val
                    return val
                except (ValueError, TypeError):
                    pass
        return self._last_known_states.get(entity_id + "_temp")

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            now = datetime.now()
            today_str = now.date().isoformat()

            consumption_sensor = self._get_config_value(CONF_CONSUMPTION_SENSOR)
            solar_sensor = self._get_config_value(CONF_SOLAR_ACTUAL_SENSOR)
            weather_entity = self._get_config_value(CONF_WEATHER_ENTITY)

            current_consumption = self._get_sensor_value(consumption_sensor)
            current_solar = self._get_sensor_value(solar_sensor)
            current_temp = self._get_weather_current_temp(weather_entity)

            # Тренування на початку нової доби
            if self._last_trained_date != today_str:
                if self._last_trained_date != "":
                    avg_temp = (self._daily_temp_sum / self._daily_temp_count) if self._daily_temp_count > 0 else 20.0
                    await self._train_model(today_str, self._daily_max_consumption, self._daily_max_solar, avg_temp)
                else:
                    self._last_trained_date = today_str

                self._daily_max_consumption = current_consumption or 0.0
                self._daily_max_solar = current_solar or 0.0
                self._daily_temp_sum = current_temp or 20.0
                self._daily_temp_count = 1 if current_temp else 0
            else:
                if current_consumption and current_consumption > self._daily_max_consumption:
                    self._daily_max_consumption = current_consumption
                if current_solar and current_solar > self._daily_max_solar:
                    self._daily_max_solar = current_solar
                if current_temp is not None:
                    self._daily_temp_sum += current_temp
                    self._daily_temp_count += 1

            if current_consumption is None:
                _LOGGER.debug("Сенсори недоступні, повернення кешованого прогнозу.")
                return self._build_return_data()

            # --- РОБОТА З ПРОГНОЗОМ ПОГОДИ (ЩОБ УНИКНУТИ СТРИБКІВ) ---
            today_forecast_temp = current_temp
            tomorrow_forecast_temp = current_temp

            if weather_entity:
                try:
                    response = await self.hass.services.async_call(
                        "weather", "get_forecasts", {"entity_id": weather_entity, "type": "daily"},
                        blocking=True, return_response=True
                    )
                    if response and weather_entity in response:
                        forecasts = response[weather_entity].get("forecast", [])
                        if forecasts:
                            f_today = forecasts[0]
                            t_high = f_today.get("temperature")
                            t_low = f_today.get("templow")
                            if t_high is not None and t_low is not None:
                                today_forecast_temp = (t_high + t_low) / 2.0
                            elif t_high is not None:
                                today_forecast_temp = t_high

                            if len(forecasts) > 1:
                                f_tomorrow = forecasts[1]
                                t_high_tmr = f_tomorrow.get("temperature")
                                t_low_tmr = f_tomorrow.get("templow")
                                if t_high_tmr is not None and t_low_tmr is not None:
                                    tomorrow_forecast_temp = (t_high_tmr + t_low_tmr) / 2.0
                                elif t_high_tmr is not None:
                                    tomorrow_forecast_temp = t_high_tmr
                except Exception as e:
                    _LOGGER.debug("Не вдалося отримати daily прогноз погоди, використовуємо поточну температуру: %s", e)

            forecast_today = self._calculate_forecast_for_day(
                is_tomorrow=False, current_consumption=current_consumption, target_temp=today_forecast_temp
            )
            forecast_tomorrow = self._calculate_forecast_for_day(
                is_tomorrow=True, target_temp=tomorrow_forecast_temp
            )

            self._current_forecast_cache = forecast_today
            self._forecast_tomorrow_cache = forecast_tomorrow
            await self._async_save_store()

            return self._build_return_data()

        except Exception as err:
            _LOGGER.error("Помилка при розрахунку прогнозу споживання: %s", err)
            raise UpdateFailed(f"Помилка оновлення даних: {err}") from err

    def _build_return_data(self) -> dict[str, Any]:
        return {
            "forecast_today": self._current_forecast_cache,
            "forecast_tomorrow": self._forecast_tomorrow_cache,
            "avg_daily_consumption": round(self._avg_period, 2),
            "avg_daily_solar": round(self._avg_solar_period, 2),
            "history_days_used": self._history_days,
            "learned_solar_weight": round(self._w_solar, 4),
            "learned_temp_cool_coeff": round(self._w_temp_cool, 4),
            "learned_temp_heat_coeff": round(self._w_temp_heat, 4),
            "learned_bias_correction": round(self._w_bias, 3),
            "last_error_mape_pct": round(self._last_error_mape, 2),
        }

    async def _train_model(
        self,
        today_str: str,
        actual_yesterday: float,
        max_solar_yesterday: float,
        avg_temp_yesterday: float,
    ) -> None:
        if actual_yesterday >= MIN_VALID_CONSUMPTION:
            self._consumption_history.append(actual_yesterday)
            if len(self._consumption_history) > HISTORY_STORAGE_CAP:
                self._consumption_history.pop(0)

            self._solar_history.append(max(0.0, max_solar_yesterday))
            if len(self._solar_history) > HISTORY_STORAGE_CAP:
                self._solar_history.pop(0)

            predicted_yesterday = self._current_forecast_cache

            if predicted_yesterday > 0:
                error = actual_yesterday - predicted_yesterday
                self._last_error_mape = (abs(error) / actual_yesterday) * 100.0

                # Bias: невеликий щоденний крок, симетричні межі (BIAS_MIN..BIAS_MAX).
                raw_bias_delta = (error / actual_yesterday) * 0.05
                self._w_bias += max(-BIAS_MAX_DAILY_STEP, min(BIAS_MAX_DAILY_STEP, raw_bias_delta))

                # Сонячна вага коригується, лише якщо є за чим порівнювати
                # (є хоч якась історія сонячної генерації).
                if self._avg_solar_period > 0.5:
                    solar_delta = (error / actual_yesterday) * 0.03
                    self._w_solar += max(-SOLAR_WEIGHT_MAX_DAILY_STEP, min(SOLAR_WEIGHT_MAX_DAILY_STEP, solar_delta))

                if avg_temp_yesterday > 25.0:
                    delta = (error / actual_yesterday) * 0.02
                    self._w_temp_cool += max(-TEMP_COEFF_MAX_DAILY_STEP, min(TEMP_COEFF_MAX_DAILY_STEP, delta))
                elif avg_temp_yesterday < 15.0:
                    delta = (error / actual_yesterday) * 0.02
                    self._w_temp_heat += max(-TEMP_COEFF_MAX_DAILY_STEP, min(TEMP_COEFF_MAX_DAILY_STEP, delta))

            self._w_bias = max(BIAS_MIN, min(BIAS_MAX, self._w_bias))
            self._w_temp_cool = max(TEMP_COEFF_MIN, min(TEMP_COEFF_MAX, self._w_temp_cool))
            self._w_temp_heat = max(TEMP_COEFF_MIN, min(TEMP_COEFF_MAX, self._w_temp_heat))
            self._w_solar = max(SOLAR_WEIGHT_MIN, min(SOLAR_WEIGHT_MAX, self._w_solar))

            self._last_trained_date = today_str
            await self._async_save_store()
        else:
            # Показник схожий на помилку сенсора (напр. 0 або підозріло
            # малий) -- пропускаємо цей день, НЕ додаючи його в історію,
            # щоб він не зіпсував середнє.
            self._last_trained_date = today_str
            await self._async_save_store()

    def _calculate_forecast_for_day(
        self,
        is_tomorrow: bool = False,
        current_consumption: float | None = None,
        target_temp: float | None = None,
    ) -> float:
        avg = self._avg_period
        estimated_total = avg * self._w_bias

        # --- Температурна корекція, обмежена часткою від середнього ---
        temp_cap = avg * MAX_TEMP_EFFECT_RATIO
        if target_temp is not None:
            if target_temp > 25.0:
                temp_effect = (target_temp - 25.0) * self._w_temp_cool
            elif target_temp < 15.0:
                temp_effect = (15.0 - target_temp) * self._w_temp_heat
            else:
                temp_effect = 0.0
            temp_effect = max(-temp_cap, min(temp_cap, temp_effect))
            estimated_total += temp_effect

        # --- Сонячна корекція: ВІДНОСНА до власного середнього за період ---
        # Ідея: якщо прогноз генерації СЕС на цей день суттєво вищий за
        # звичний рівень -- будинок, ймовірно, споживатиме більше (більше
        # денної активності/навантаження), і навпаки для похмурого дня.
        # НЕ додається сира кВт*год сонця -- натомість береться коефіцієнт
        # відхилення від норми, помножений на частку (learned_solar_weight)
        # від середнього споживання будинку. Це працює однаково
        # передбачувано незалежно від розміру сонячної станції.
        solar_key = CONF_SOLAR_FORECAST_TOMORROW if is_tomorrow else CONF_SOLAR_FORECAST_TODAY
        solar_sensor = self._get_config_value(solar_key)

        if not solar_sensor and not is_tomorrow:
            solar_sensor = self._get_config_value(CONF_SOLAR_ACTUAL_SENSOR)

        solar_val = self._get_sensor_value(solar_sensor)
        avg_solar = self._avg_solar_period

        if solar_val is not None and avg_solar > 0.5:
            solar_ratio = solar_val / avg_solar
            solar_ratio = max(SOLAR_RATIO_MIN, min(SOLAR_RATIO_MAX, solar_ratio))
            solar_effect = (solar_ratio - 1.0) * avg * self._w_solar
            estimated_total += solar_effect

        # --- Захисні межі (сан-чек), симетричні відносно середнього ---
        floor = avg * FORECAST_FLOOR_RATIO
        ceiling = avg * FORECAST_CEILING_RATIO
        final_forecast = max(floor, min(ceiling, estimated_total))

        # Прогноз на "сьогодні" ніколи не може бути нижчим за те, що вже
        # фактично спожито на цей момент доби.
        if not is_tomorrow and current_consumption is not None:
            final_forecast = max(final_forecast, current_consumption)

        return round(final_forecast, 2)
