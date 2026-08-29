"""Sensor platform for House Consumption Forecaster."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AdaptiveForecasterCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Налаштування сенсорів інтеграції."""
    coordinator: AdaptiveForecasterCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = [
        HouseConsumptionForecasterSensor(coordinator, entry, "today", "Сьогодні"),
        HouseConsumptionForecasterSensor(coordinator, entry, "tomorrow", "Завтра"),
    ]

    async_add_entities(sensors)


class HouseConsumptionForecasterSensor(CoordinatorEntity, SensorEntity):
    """Клас сенсора для відображення прогнозу та атрибутів."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:home-lightning-bolt"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AdaptiveForecasterCoordinator,
        entry: ConfigEntry,
        forecast_type: str,
        name: str,
    ) -> None:
        """Ініціалізація сенсора."""
        super().__init__(coordinator)
        self._entry = entry
        self._forecast_type = forecast_type

        # Фіксований entity_id для збереження історії та сумісності
        self.entity_id = f"sensor.house_energy_forecast_{forecast_type}"
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{forecast_type}"

    @property
    def device_info(self) -> DeviceInfo:
        """Прив'язка сенсорів до єдиного пристрою в Home Assistant."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Прогноз споживання електроенергії",
            manufacturer="Custom Integration",
            model="Adaptive Forecaster ML",
        )

    @property
    def native_value(self) -> float | None:
        """Повертає значення прогнозу."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(f"forecast_{self._forecast_type}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Повертає атрибути з вагами та коефіцієнтами."""
        if not self.coordinator.data:
            return {}

        return {
            "Learned solar weight": self.coordinator.data.get("learned_solar_weight", 0.0),
            "Learned temp cool coeff": self.coordinator.data.get("learned_temp_cool_coeff", 0.0),
            "Learned temp heat coeff": self.coordinator.data.get("learned_temp_heat_coeff", 0.0),
            "Learned weekend boost pct": self.coordinator.data.get("learned_weekend_boost_pct", 0.0),
            "Learned bias correction": self.coordinator.data.get("learned_bias_correction", 1.0),
            "Last error mape pct": self.coordinator.data.get("last_error_mape_pct", 0.0),
        }