"""DataUpdateCoordinator and Self-Learning Engine."""
import logging
from datetime import datetime, timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import Store
import homeassistant.util.dt as dt_util

from .const import DOMAIN, DEFAULT_WEIGHTS

_LOGGER = logging.getLogger(__name__)
STORAGE_KEY = f"{DOMAIN}_learned_weights"
STORAGE_VERSION = 1

class AdaptiveForecasterCoordinator(DataUpdateCoordinator):
    """Coordinator that computes forecasts and auto-calibrates coefficients daily."""

    def __init__(self, hass: HomeAssistant, config: dict):
        super().__init__(
            hass,
            _LOGGER,
            name="House Consumption Forecaster",
            update_interval=timedelta(minutes=30),
        )
        self.config = config
        self.store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.weights = dict(DEFAULT_WEIGHTS)
        self.yesterday_forecast = None

    async def async_init_store(self):
        """Load stored learned weights from HA storage."""
        stored = await self.store.async_load()
        if stored:
            self.weights.update(stored)
            _LOGGER.info("Loaded adaptive weights from storage: %s", self.weights)

    async def _async_update_data(self):
        """Fetch states, perform learning check if midnight passed, and calculate forecast."""
        now = dt_util.now()

        # 1. Автонавчання: Перевірка та коригування вчорашнього прогнозу
        await self._auto_calibrate_if_needed(now)

        # 2. Обчислення прогнозу на сьогодні та завтра з обробкою незавантажених станів
        try:
            forecast_today = await self._calculate_forecast(day_offset=0)
            forecast_tomorrow = await self._calculate_forecast(day_offset=1)
        except ValueError as err:
            raise UpdateFailed(f"Сенсори ще не готові або мають стан unavailable: {err}") from err

        # Зберігаємо сьогоднішній прогноз, щоб завтра звірити його з фактом
        if now.hour == 6 or self.yesterday_forecast is None:
            self.yesterday_forecast = forecast_today

        return {
            "forecast_today": forecast_today,
            "forecast_tomorrow": forecast_tomorrow,
            "weights": self.weights,
        }

    async def _auto_calibrate_if_needed(self, now: datetime):
        """Perform feedback loop calibration once per day at midnight."""
        actual_cons_state = self.hass.states.get(self.config["consumption_sensor"])
        if not actual_cons_state or actual_cons_state.state in ("unknown", "unavailable"):
            return

        try:
            actual_yesterday = float(actual_cons_state.state)
        except ValueError:
            return

        if self.yesterday_forecast is None or actual_yesterday <= 0:
            return

        error = actual_yesterday - self.yesterday_forecast
        relative_error = error / actual_yesterday
        self.weights["last_mape"] = round(abs(relative_error) * 100, 2)

        _LOGGER.info(
            "Auto-calibration trigger: Actual Yesterday=%.2f kWh, Forecast=%.2f kWh, Error=%.2f%%",
            actual_yesterday, self.yesterday_forecast, self.weights["last_mape"]
        )

        lr = 0.05

        self.weights["bias_correction"] += lr * relative_error
        self.weights["bias_correction"] = max(0.7, min(1.3, self.weights["bias_correction"]))

        temp_state = self.hass.states.get(self.config["temp_sensor"])
        if temp_state and temp_state.state not in ("unknown", "unavailable"):
            try:
                avg_temp = float(temp_state.state)
                if avg_temp > 24:
                    self.weights["temp_cool_coeff"] += lr * (relative_error / max(avg_temp - 24, 1))
                    self.weights["temp_cool_coeff"] = max(0.1, min(1.5, self.weights["temp_cool_coeff"]))
                elif avg_temp < 22:
                    self.weights["temp_heat_coeff"] += lr * (relative_error / max(22 - avg_temp, 1))
                    self.weights["temp_heat_coeff"] = max(0.1, min(1.5, self.weights["temp_heat_coeff"]))
            except ValueError:
                pass

        workday_state = self.hass.states.get(self.config["workday_sensor"])
        if workday_state and workday_state.state not in ("unknown", "unavailable"):
            if workday_state.state == "off":
                self.weights["weekend_boost"] += lr * relative_error * 0.1
                self.weights["weekend_boost"] = max(0.0, min(0.35, self.weights["weekend_boost"]))

        await self.store.async_save(self.weights)

    def _get_float_state(self, entity_id: str) -> float:
        """Helper to safely fetch state as float or raise ValueError."""
        state_obj = self.hass.states.get(entity_id)
        if not state_obj or state_obj.state in ("unknown", "unavailable", None):
            raise ValueError(f"Сутність {entity_id} недоступна")
        try:
            return float(state_obj.state)
        except (ValueError, TypeError) as err:
            raise ValueError(f"Сутність {entity_id} має некоректне значення '{state_obj.state}'") from err

    async def _calculate_forecast(self, day_offset: int) -> float:
        """Core mathematical model with dynamic adaptive weights."""
        cons_state = self._get_float_state(self.config["consumption_sensor"])
        solar_actual = self._get_float_state(self.config["solar_actual_sensor"])
        
        solar_fc_key = "solar_forecast_today" if day_offset == 0 else "solar_forecast_tomorrow"
        solar_forecast = self._get_float_state(self.config[solar_fc_key])
        
        temp = self._get_float_state(self.config["temp_sensor"])

        workday_obj = self.hass.states.get(self.config["workday_sensor"])
        if not workday_obj or workday_obj.state in ("unknown", "unavailable", None):
            raise ValueError(f"Сутність {self.config['workday_sensor']} недоступна")
        is_workday = workday_obj.state == "on"

        # 1. Зважена база споживання
        blended_cons = cons_state

        # 2. Базове навантаження
        base_load = max(blended_cons * 0.3, 3.0)

        # 3. Сонячний фактор з навченим мультиплікатором
        solar_7d_avg = max(solar_actual, 1.0)
        solar_factor = ((blended_cons - base_load) / solar_7d_avg) * self.weights["solar_weight"]
        solar_addition = solar_forecast * solar_factor

        # 4. Температурна корекція з адаптивними коефіцієнтами
        temp_correction = 0.0
        if temp > 24:
            temp_correction = (temp - 24) * self.weights["temp_cool_coeff"]
        elif temp < 22:
            temp_correction = (22 - temp) * self.weights["temp_heat_coeff"]

        # 5. Коригування на вихідний день
        weekend_factor = 1.0 if (is_workday or day_offset == 1) else (1.0 + self.weights["weekend_boost"])

        # Підсумковий розрахунок
        raw_forecast = (base_load + solar_addition + temp_correction) * weekend_factor
        raw_forecast *= self.weights["bias_correction"]

        # 6. Захист від аномалій (Сатурація)
        min_limit = base_load
        max_limit = blended_cons * 1.35

        return round(max(min_limit, min(raw_forecast, max_limit)), 2)