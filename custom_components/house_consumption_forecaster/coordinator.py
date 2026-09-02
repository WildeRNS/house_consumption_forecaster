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
    CONF_WORKDAY_SENSOR,
)

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1

class AdaptiveForecasterCoordinator(DataUpdateCoordinator):
    """Клас координатора з логікою машинного навчання та постійним збереженням стану."""

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
        self._w_temp_cool: float = 0.5
        self._w_temp_heat: float = 0.8
        self._last_error_mape: float = 0.0

    async def async_init_store(self) -> None:
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
                is_weekend = self._is_weekend_or_holiday(now)
                return self._build_return_data(is_weekend)

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
                            # Прогноз на сьогодні (усереднюємо між мін і макс, або беремо макс)
                            f_today = forecasts[0]
                            t_high = f_today.get("temperature")
                            t_low = f_today.get("templow")
                            if t_high is not None and t_low is not None:
                                today_forecast_temp = (t_high + t_low) / 2.0
                            elif t_high is not None:
                                today_forecast_temp = t_high

                            # Прогноз на завтра
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

            is_weekend = self._is_weekend_or_holiday(now)
            return self._build_return_data(is_weekend)

        except Exception as err:
            _LOGGER.error("Помилка при розрахунку прогнозу споживання: %s", err)
            raise UpdateFailed(f"Помилка оновлення даних: {err}") from err

    def _build_return_data(self, is_weekend: bool) -> dict[str, Any]:
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

    async def _train_model(self, today_str: str, actual_yesterday: float, max_solar_yesterday: float, avg_temp_yesterday: float) -> None:
        if actual_yesterday > 4.0:
            self._consumption_history.append(actual_yesterday)
            if len(self._consumption_history) > 7:
                self._consumption_history.pop(0)

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

    def _calculate_forecast_for_day(self, is_tomorrow: bool = False, current_consumption: float | None = None, target_temp: float | None = None) -> float:
        base_limit = self._avg_7d * 0.85 
        target_date = datetime.now() + timedelta(days=1 if is_tomorrow else 0)
        estimated_total = self._avg_7d * self._w_bias

        if self._is_weekend_or_holiday(target_date):
            estimated_total *= 1.15

        # Температурна корекція на базі ОЧІКУВАНОЇ СЕРЕДНЬОЇ за добу (Вирішує баг з вранішніми стрибками)
        if target_temp is not None:
            if target_temp > 25.0:
                estimated_total += (target_temp - 25.0) * self._w_temp_cool
            elif target_temp < 15.0:
                estimated_total += (15.0 - target_temp) * self._w_temp_heat

        # Сонячна корекція (Solcast / Volcast ВЖЕ враховує сонячно чи хмарно у кВт·год)
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