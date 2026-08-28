"""Sensor platform for House Consumption Forecaster."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up forecaster sensors from config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        ConsumptionForecastSensor(coordinator, "today"),
        ConsumptionForecastSensor(coordinator, "tomorrow"),
    ]
    async_add_entities(entities)

class ConsumptionForecastSensor(CoordinatorEntity, SensorEntity):
    """Representation of a consumption forecast sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:home-lightning-bolt"

    def __init__(self, coordinator, day_key):
        super().__init__(coordinator)
        self.day_key = day_key
        self._attr_translation_key = f"forecast_{day_key}"
        self._attr_unique_id = f"house_energy_forecast_{day_key}"

    @property
    def native_value(self):
        """Return forecast value."""
        return self.coordinator.data.get(f"forecast_{self.day_key}")

    @property
    def extra_state_attributes(self):
        """Expose dynamic learned weights into state attributes for monitoring."""
        weights = self.coordinator.data.get("weights", {})
        return {
            "learned_solar_weight": weights.get("solar_weight"),
            "learned_temp_cool_coeff": weights.get("temp_cool_coeff"),
            "learned_temp_heat_coeff": weights.get("temp_heat_coeff"),
            "learned_weekend_boost_pct": round(weights.get("weekend_boost", 0) * 100, 1),
            "learned_bias_correction": weights.get("bias_correction"),
            "last_error_mape_pct": weights.get("last_mape"),
        }