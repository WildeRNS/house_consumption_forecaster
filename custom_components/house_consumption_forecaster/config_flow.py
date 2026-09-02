"""Config flow and Options flow for House Consumption Forecaster."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import (
    DOMAIN,
    CONF_CONSUMPTION_SENSOR,
    CONF_SOLAR_ACTUAL_SENSOR,
    CONF_SOLAR_FORECAST_TODAY,
    CONF_SOLAR_FORECAST_TOMORROW,
    CONF_WEATHER_ENTITY,
    CONF_WORKDAY_SENSOR,
)

class ForecasterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for initial setup."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ForecasterOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Прогнозування споживання", data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_CONSUMPTION_SENSOR): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(CONF_SOLAR_ACTUAL_SENSOR): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(CONF_SOLAR_FORECAST_TODAY): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(CONF_SOLAR_FORECAST_TOMORROW): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(CONF_WEATHER_ENTITY): EntitySelector(EntitySelectorConfig(domain="weather")), # Тепер тільки weather
            vol.Required(CONF_WORKDAY_SENSOR): EntitySelector(EntitySelectorConfig(domain="binary_sensor")),
        })

        return self.async_show_form(step_id="user", data_schema=schema)


class ForecasterOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for changing configured sensors."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self._config_entry.data, **self._config_entry.options}

        schema = vol.Schema({
            vol.Required(
                CONF_CONSUMPTION_SENSOR,
                default=current.get(CONF_CONSUMPTION_SENSOR),
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_SOLAR_ACTUAL_SENSOR,
                default=current.get(CONF_SOLAR_ACTUAL_SENSOR),
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_SOLAR_FORECAST_TODAY,
                default=current.get(CONF_SOLAR_FORECAST_TODAY),
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_SOLAR_FORECAST_TOMORROW,
                default=current.get(CONF_SOLAR_FORECAST_TOMORROW),
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_WEATHER_ENTITY,
                default=current.get(CONF_WEATHER_ENTITY),
            ): EntitySelector(EntitySelectorConfig(domain="weather")),
            vol.Required(
                CONF_WORKDAY_SENSOR,
                default=current.get(CONF_WORKDAY_SENSOR),
            ): EntitySelector(EntitySelectorConfig(domain="binary_sensor")),
        })

        return self.async_show_form(step_id="init", data_schema=schema)