"""DataUpdateCoordinator for House Consumption Forecaster."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class HouseConsumptionCoordinator(DataUpdateCoordinator):
    """Клас координатора для розрахунку прогнозу споживання будинку."""

    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        """Ініціалізація координатора."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=15),
        )
        self.entry = entry

        # Налаштування адаптації та історичної пам'яті
        self._w_bias: float = 1.0
        self._avg_daily_consumption: float = 9.0  # Стартове середньодобове споживання (кВт·год)
        self._last_day: int = datetime.now().day

    async def _async_update_data(self) -> dict[str, Any]:
        """Оновлення даних та розрахунок прогнозів."""
        try:
            now = datetime.now()

            # Перевірка зміни доби о півночі для оновлення історичного середнього (EMA)
            if now.day != self._last_day:
                await self._update_historical_average()
                self._last_day = now.day

            # Розрахунок прогнозів
            forecast_today = self._calculate_forecast_for_day(is_tomorrow=False)
            forecast_tomorrow = self._calculate_forecast_for_day(is_tomorrow=True)

            return {
                "forecast_today": forecast_today,
                "forecast_tomorrow": forecast_tomorrow,
                "avg_daily_consumption": round(self._avg_daily_consumption, 2),
            }

        except Exception as err:
            _LOGGER.error("Помилка при розрахунку прогнозу споживання: %s", err)
            raise UpdateFailed(f"Помилка оновлення даних: {err}") from err

    async def _update_historical_average(self) -> None:
        """Оновлює середньодобове споживання на основі підсумків минулого дня (EMA)."""
        consumption_sensor = self.entry.options.get("consumption_sensor") or self.entry.data.get(
            "consumption_sensor"
        )

        if consumption_sensor:
            state = self.hass.states.get(consumption_sensor)
            if state and state.state not in ("unknown", "unavailable"):
                try:
                    yesterday_val = float(state.state)
                    if yesterday_val > 1.0:
                        # 80% ваги на накопичену історію + 20% на останній фактичний день
                        self._avg_daily_consumption = (
                            self._avg_daily_consumption * 0.8
                        ) + (yesterday_val * 0.2)
                        _LOGGER.info(
                            "Історичне середньодобове споживання оновлено: %.2f кВт·год",
                            self._avg_daily_consumption,
                        )
                except ValueError:
                    pass

    def _calculate_base_load(self) -> float:
        """
        Розраховує базове навантаження на основі історичного середнього (EMA),
        щоб о 07:00 ранку прогноз не просідав до мінімальних 3.0 кВт·год.
        """
        # 30% від історичного середнього значення з мінімальним порогом 3.0 кВт·год
        base_load = max(self._avg_daily_consumption * 0.3, 3.0)
        return base_load

    def _calculate_forecast_for_day(self, is_tomorrow: bool = False) -> float:
        """Підсумковий розрахунок прогнозу споживання на день."""
        base_load = self._calculate_base_load()

        # Базовий орієнтир на день на основі історії
        estimated_total = self._avg_daily_consumption

        # Коригування для вихідних днів (субота / неділя +15%)
        target_date = datetime.now() + timedelta(days=1 if is_tomorrow else 0)
        if target_date.weekday() >= 5:
            estimated_total *= 1.15

        # Застосування навченого коефіцієнта зміщення W_bias
        final_forecast = max(estimated_total * self._w_bias, base_load)

        return round(final_forecast, 2)