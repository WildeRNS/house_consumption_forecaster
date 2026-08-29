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

        # Базові показники за замовчуванням
        self._avg_daily_consumption: float = 9.0
        self._last_trained_date: str = ""
        self._yesterday_forecast: float = 9.0

        # Навчені коефіцієнти (Weights)
        self._w_bias: float = 1.0
        self._w_solar: float = -0.1
        self._w_temp_cool: float = 0.5
        self._w_temp_heat: float = 0.8
        self._last_error_mape: float = 0.0

    async def async_init_store(self) -> None:
        """Зчитування збережених коефіцієнтів з JSON-сховища при запуску."""
        data = await self._store.async_load()
        if data:
            self._w_bias = data.get("w_bias", 1.0)
            self._w_solar = data.get("w_solar", -0.1)
            self._w_temp_cool = data.get("w_temp_cool", 0.5)
            self._w_temp_heat = data.get("w_temp_heat", 0.8)
            self._avg_daily_consumption = data.get("avg_daily_consumption", 9.0)
            self._last_error_mape = data.get("last_error_mape", 0.0)
            self._last_trained_date = data.get("last_trained_date", "")
            self._yesterday_forecast = data.get("yesterday_forecast", 9.0)
            _LOGGER.info("Відновлено збережені ваги моделі прогнозування з пам'яті")

    async def _async_save_store(self) -> None:
        """Збереження поточного стану ваг у JSON-сховище."""
        data = {
            "w_bias": self._w_bias,
            "w_solar": self._w_solar,
            "w_temp_cool": self._w_temp_cool,
            "w_temp_heat": self._w_temp_heat,
            "avg_daily_consumption": self._avg_daily_consumption,
            "last_error_mape": self._last_error_mape,
            "last_trained_date": self._last_trained_date,
            "yesterday_forecast": self._yesterday_forecast,
        }
        await self._store.async_save(data)

    def _get_config_value(self, key: str) -> str | None:
        """Отримання значення з налаштувань інтеграції."""
        return self.entry.options.get(key) or self.entry.data.get(key)

    async def _async_update_data(self) -> dict[str, Any]:
        """Оновлення даних (кожні 15 хвилин)."""
        try:
            now = datetime.now()
            today_str = now.date().isoformat()

            # Навчаємо модель, якщо настала нова доба і ми ще не навчалися сьогодні
            if self._last_trained_date != today_str:
                await self._train_model(today_str)

            # Розрахунок прогнозів
            forecast_today = self._calculate_forecast_for_day(is_tomorrow=False)
            forecast_tomorrow = self._calculate_forecast_for_day(is_tomorrow=True)

            # Перевірка на вихідний день за сенсором або календарем
            is_weekend = self._is_weekend_or_holiday(now)

            return {
                "forecast_today": forecast_today,
                "forecast_tomorrow": forecast_tomorrow,
                "avg_daily_consumption": round(self._avg_daily_consumption, 2),
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

    async def _train_model(self, today_str: str) -> None:
        """Логіка адаптивного навчання з безпечними межами змін."""
        consumption_sensor = self._get_config_value(CONF_CONSUMPTION_SENSOR)
        temp_sensor = self._get_config_value(CONF_TEMP_SENSOR)
        solar_sensor = self._get_config_value(CONF_SOLAR_ACTUAL_SENSOR)

        actual_consumption = self._get_sensor_value(consumption_sensor)

        if actual_consumption and actual_consumption > 1.0:
            # 1. Оновлення скоригованого середнього (EMA)
            self._avg_daily_consumption = (self._avg_daily_consumption * 0.8) + (actual_consumption * 0.2)

            # 2. Розрахунок похибки MAPE та безпечне коригування Bias
            if self._yesterday_forecast > 0:
                error = actual_consumption - self._yesterday_forecast
                self._last_error_mape = (abs(error) / actual_consumption) * 100.0

                raw_bias_delta = (error / actual_consumption) * 0.05
                bias_delta = max(-0.05, min(0.05, raw_bias_delta))
                self._w_bias += bias_delta

            # 3. Вплив температури з захистним обмеженням кроку
            avg_temp = self._get_sensor_value(temp_sensor)
            if avg_temp is not None:
                if avg_temp > 25.0:
                    delta = (actual_consumption - self._avg_daily_consumption) * 0.005
                    self._w_temp_cool += max(-0.05, min(0.05, delta))
                elif avg_temp < 15.0:
                    delta = (actual_consumption - self._avg_daily_consumption) * 0.005
                    self._w_temp_heat += max(-0.05, min(0.05, delta))

            # 4. Вплив сонячної генерації
            solar_prod = self._get_sensor_value(solar_sensor)
            if solar_prod is not None and solar_prod > 0:
                solar_delta = 0.001 * (solar_prod / actual_consumption)
                self._w_solar -= max(0.0, min(0.05, solar_delta))

            # 5. Глобальні запобіжники для коефіцієнтів
            self._w_bias = max(0.5, min(1.5, self._w_bias))
            self._w_temp_cool = max(0.0, min(2.0, self._w_temp_cool))
            self._w_temp_heat = max(0.0, min(3.0, self._w_temp_heat))
            self._w_solar = max(-1.0, min(0.0, self._w_solar))

            # Оновлюємо дату та зберігаємо прогноз на сьогодні для завтрашнього навчання
            self._last_trained_date = today_str
            self._yesterday_forecast = self._calculate_forecast_for_day(is_tomorrow=False)
            
            await self._async_save_store()
            _LOGGER.info(
                "Модель успішно навчено за %s. Новий MAPE: %.2f%%, Bias: %.3f",
                today_str, self._last_error_mape, self._w_bias
            )

    def _get_sensor_value(self, entity_id: str | None) -> float | None:
        """Безпечне зчитування числових значень із Home Assistant."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state and state.state not in ("unknown", "unavailable"):
            try:
                return float(state.state)
            except ValueError:
                return None
        return None

    def _is_weekend_or_holiday(self, target_date: datetime) -> bool:
        """Перевірка чи є день вихідним за сенсором Workday або за датою."""
        workday_sensor = self._get_config_value(CONF_WORKDAY_SENSOR)
        if workday_sensor:
            state = self.hass.states.get(workday_sensor)
            if state and state.state not in ("unknown", "unavailable"):
                return state.state == "off"
        return target_date.weekday() >= 5

    def _calculate_forecast_for_day(self, is_tomorrow: bool = False) -> float:
        """Генерація прогнозу споживання."""
        base_load = max(self._avg_daily_consumption * 0.3, 3.0)
        target_date = datetime.now() + timedelta(days=1 if is_tomorrow else 0)

        estimated_total = self._avg_daily_consumption * self._w_bias

        if self._is_weekend_or_holiday(target_date):
            estimated_total *= 1.15

        temp_sensor = self._get_config_value(CONF_TEMP_SENSOR)
        current_temp = self._get_sensor_value(temp_sensor)
        if current_temp is not None:
            if current_temp > 25.0:
                estimated_total += (current_temp - 25.0) * self._w_temp_cool
            elif current_temp < 15.0:
                estimated_total += (15.0 - current_temp) * self._w_temp_heat

        # Вибір відповідного прогнозу сонця
        solar_key = CONF_SOLAR_FORECAST_TOMORROW if is_tomorrow else CONF_SOLAR_FORECAST_TODAY
        solar_sensor = self._get_config_value(solar_key) or self._get_config_value(CONF_SOLAR_ACTUAL_SENSOR)
        solar_val = self._get_sensor_value(solar_sensor)

        if solar_val is not None:
            estimated_total += solar_val * self._w_solar

        return round(max(estimated_total, base_load), 2)