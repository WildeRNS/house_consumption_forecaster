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
    CONF_TEMP_SENSOR,
    CONF_WORKDAY_SENSOR,
)

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1

class AdaptiveForecasterCoordinator(DataUpdateCoordinator):
    """Клас координатора з логікою машинного навчання та постійним збереженням стану."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Ініціалізація координатора."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=15),
        )
        self.entry = entry
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_weights")

        # Базові показники
        self._consumption_history: list[float] = [9.0]
        self._last_trained_date: str = ""

        # Кешування для захисту від перезавантажень та опівнічного скидання
        self._daily_max_consumption: float = 0.0
        self._daily_max_solar: float = 0.0
        self._daily_temp_sum: float = 0.0
        self._daily_temp_count: int = 0
        
        self._current_forecast_cache: float = 9.0
        self._forecast_tomorrow_cache: float = 9.0
        self._last_known_states: dict[str, float] = {}

        # Навчені коефіцієнти (Weights)
        self._w_bias: float = 1.0
        self._w_solar: float = 0.15
        self._w_temp_cool: float = 0.5
        self._w_temp_heat: float = 0.8
        self._last_error_mape: float = 0.0

    async def async_init_store(self) -> None:
        """Зчитування збережених даних."""
        data = await self._store.async_load()
        if data:
            self._w_bias = max(0.85, min(1.25, data.get("w_bias", 1.0)))
            self._w_solar = max(0.05, min(0.35, data.get("w_solar", 0.15)))
            self._w_temp_cool = data.get("w_temp_cool", 0.5)
            self._w_temp_heat = data.get("w_temp_heat", 0.8)
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
                self._consumption_history = [x for x in hist if x > 4.0]
                if not self._consumption_history:
                    self._consumption_history = [9.0]
            else:
                self._consumption_history = [9.0]

    async def _async_save_store(self) -> None:
        """Збереження поточного стану."""
        data = {
            "w_bias": self._w_bias,
            "w_solar": self._w_solar,
            "w_temp_cool": self._w_temp_cool,
            "w_temp_heat": self._w_temp_heat,
            "consumption_history": self._consumption_history,
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

    def _get_config_value(self, key: str) -> str | None:
        return self.entry.options.get(key) or self.entry.data.get(key)
        
    @property
    def _avg_7d(self) -> float:
        valid_history = [x for x in self._consumption_history if x > 4.0]
        if not valid_history:
            return 9.0
        return sum(valid_history) / len(valid_history)

    def _get_sensor_value(self, entity_id: str | None) -> float | None:
        """Отримання значення з фолбеком на останнє відоме."""
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
        
        # Якщо сенсор недоступний (наприклад, під час рестарту), беремо з кешу
        return self._last_known_states.get(entity_id)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            now = datetime.now()
            today_str = now.date().isoformat()

            consumption_sensor = self._get_config_value(CONF_CONSUMPTION_SENSOR)
            solar_sensor = self._get_config_value(CONF_SOLAR_ACTUAL_SENSOR)
            temp_sensor = self._get_config_value(CONF_TEMP_SENSOR)

            current_consumption = self._get_sensor_value(consumption_sensor)
            current_solar = self._get_sensor_value(solar_sensor)
            current_temp = self._get_sensor_value(temp_sensor)

            # Тренування на початку нової доби
            if self._last_trained_date != today_str:
                if self._last_trained_date != "":
                    # Передаємо накопичені за минулу добу дані
                    avg_temp = (self._daily_temp_sum / self._daily_temp_count) if self._daily_temp_count > 0 else 20.0
                    await self._train_model(
                        today_str, 
                        self._daily_max_consumption, 
                        self._daily_max_solar,
                        avg_temp
                    )
                else:
                    self._last_trained_date = today_str
                
                # Скидання добових лічильників
                self._daily_max_consumption = current_consumption or 0.0
                self._daily_max_solar = current_solar or 0.0
                self._daily_temp_sum = current_temp or 20.0
                self._daily_temp_count = 1 if current_temp else 0
            else:
                # Оновлення максимумів протягом дня
                if current_consumption and current_consumption > self._daily_max_consumption:
                    self._daily_max_consumption = current_consumption
                if current_solar and current_solar > self._daily_max_solar:
                    self._daily_max_solar = current_solar
                if current_temp is not None:
                    self._daily_temp_sum += current_temp
                    self._daily_temp_count += 1

            # Якщо дані критичного сенсора недоступні (рестарт HA), повертаємо кеш
            if current_consumption is None:
                _LOGGER.debug("Сенсори недоступні, повернення кешованого прогнозу.")
                is_weekend = self._is_weekend_or_holiday(now)
                return {
                    "forecast_today": self._current_forecast_cache,
                    "forecast_tomorrow": self._forecast_tomorrow_cache,
                    "avg_daily_consumption": round(self._avg_7d, 2),
                    "learned_solar_weight": round(self._w_solar, 4),
                    "learned_temp_cool_coeff": round(self._w_temp_cool, 4),
                    "learned_temp_heat_coeff": round(self._w_temp_heat, 4),
                    "learned_weekend_boost_pct": 15.0 if is_weekend else 0.0,
                    "learned_bias_correction": round(self._w_bias, 3),
                    "last_error_mape_pct": round(self._last_error_mape, 2),
                }

            forecast_today = self._calculate_forecast_for_day(
                is_tomorrow=False, current_consumption=current_consumption
            )
            forecast_tomorrow = self._calculate_forecast_for_day(
                is_tomorrow=True
            )

            self._current_forecast_cache = forecast_today
            self._forecast_tomorrow_cache = forecast_tomorrow
            
            # Зберігаємо стан кожні 15 хвилин, щоб уникнути втрат при перезавантаженні
            await self._async_save_store()

            is_weekend = self._is_weekend_or_holiday(now)
            return {
                "forecast_today": forecast_today,
                "forecast_tomorrow": forecast_tomorrow,
                "avg_daily_consumption": round(self._avg_7d, 2),
                "learned_solar_weight": round(self._w_solar, 4),
                "learned_temp_cool_coeff": round(self._w_temp_cool, 4),
                "learned_temp_heat_coeff": round(self._w_temp_heat, 4),
                "learned_weekend_boost_pct": 15.0 if is_weekend else 0.0,
                "learned_bias_correction": round(self._w_bias, 3),
                "last_error_mape_pct": round(self._last_error_mape, 2),
            }

        except Exception as err:
            _LOGGER.error("Помилка при розрахунку прогнозу споживання: %s", err)
            raise UpdateFailed(f"Помилка оновлення даних: {err}") from err

    async def _train_model(self, today_str: str, actual_yesterday: float, max_solar_yesterday: float, avg_temp_yesterday: float) -> None:
        """Логіка адаптивного навчання з виправленими зміщеннями."""
        if actual_yesterday > 4.0:
            self._consumption_history.append(actual_yesterday)
            if len(self._consumption_history) > 7:
                self._consumption_history.pop(0)

            # На момент виклику цієї функції (00:01) в кеші лежить фінальний прогноз з 23:45 вчорашнього дня
            predicted_yesterday = self._current_forecast_cache
            
            if predicted_yesterday > 0:
                error = actual_yesterday - predicted_yesterday
                self._last_error_mape = (abs(error) / actual_yesterday) * 100.0

                raw_bias_delta = (error / actual_yesterday) * 0.05
                self._w_bias += max(-0.05, min(0.05, raw_bias_delta))

                if max_solar_yesterday > 0:
                    solar_delta = (error / max_solar_yesterday) * 0.02
                    self._w_solar += max(-0.02, min(0.02, solar_delta))

                if avg_temp_yesterday > 25.0:
                    delta = error * 0.005
                    self._w_temp_cool += max(-0.05, min(0.05, delta))
                elif avg_temp_yesterday < 15.0:
                    delta = error * 0.005
                    self._w_temp_heat += max(-0.05, min(0.05, delta))

            self._w_bias = max(0.85, min(1.25, self._w_bias))
            self._w_temp_cool = max(0.0, min(2.0, self._w_temp_cool))
            self._w_temp_heat = max(0.0, min(3.0, self._w_temp_heat))
            self._w_solar = max(0.05, min(0.35, self._w_solar))

            self._last_trained_date = today_str
            await self._async_save_store()
        else:
            self._last_trained_date = today_str
            await self._async_save_store()

    def _is_weekend_or_holiday(self, target_date: datetime) -> bool:
        workday_sensor = self._get_config_value(CONF_WORKDAY_SENSOR)
        if workday_sensor:
            state = self.hass.states.get(workday_sensor)
            if state and state.state not in ("unknown", "unavailable"):
                return state.state == "off"
        return target_date.weekday() >= 5

    def _calculate_forecast_for_day(self, is_tomorrow: bool = False, current_consumption: float | None = None) -> float:
        base_limit = self._avg_7d * 0.85 
        target_date = datetime.now() + timedelta(days=1 if is_tomorrow else 0)

        estimated_total = self._avg_7d * self._w_bias

        if self._is_weekend_or_holiday(target_date):
            estimated_total *= 1.15

        temp_sensor = self._get_config_value(CONF_TEMP_SENSOR)
        current_temp = self._get_sensor_value(temp_sensor)
        if current_temp is not None:
            if current_temp > 25.0:
                estimated_total += (current_temp - 25.0) * self._w_temp_cool
            elif current_temp < 15.0:
                estimated_total += (15.0 - current_temp) * self._w_temp_heat

        solar_key = CONF_SOLAR_FORECAST_TOMORROW if is_tomorrow else CONF_SOLAR_FORECAST_TODAY
        solar_sensor = self._get_config_value(solar_key)
        
        if not solar_sensor and not is_tomorrow:
            solar_sensor = self._get_config_value(CONF_SOLAR_ACTUAL_SENSOR)
            
        solar_val = self._get_sensor_value(solar_sensor)

        if solar_val is not None and solar_val > 0:
            estimated_total += solar_val * self._w_solar

        final_forecast = max(estimated_total, base_limit)

        if not is_tomorrow and current_consumption is not None:
            final_forecast = max(final_forecast, current_consumption)

        return round(final_forecast, 2)