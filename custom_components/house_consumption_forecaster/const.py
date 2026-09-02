"""Constants for House Consumption Forecaster."""
DOMAIN = "house_consumption_forecaster"

# Default learned parameters
DEFAULT_WEIGHTS = {
    "solar_weight": 0.15,
    "temp_cool_coeff": 0.4,
    "temp_heat_coeff": 0.5,
    "weekend_boost": 0.12,
    "bias_correction": 1.0,
    "last_mape": 0.0,
}

# Config Flow keys
CONF_CONSUMPTION_SENSOR = "consumption_sensor"
CONF_SOLAR_ACTUAL_SENSOR = "solar_actual_sensor"
CONF_SOLAR_FORECAST_TODAY = "solar_forecast_today"
CONF_SOLAR_FORECAST_TOMORROW = "solar_forecast_tomorrow"
CONF_WEATHER_ENTITY = "weather_entity" # Змінено з temp_sensor на weather_entity
CONF_WORKDAY_SENSOR = "workday_sensor"