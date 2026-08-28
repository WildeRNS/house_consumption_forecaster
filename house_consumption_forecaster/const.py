"""Constants for House Consumption Forecaster."""
DOMAIN = "house_consumption_forecaster"

# Default learned parameters
DEFAULT_WEIGHTS = {
    "solar_weight": 1.0,        # Мультиплікатор сонячного фактора
    "temp_cool_coeff": 0.4,     # кВт·год/°C для спеки (>24°C)
    "temp_heat_coeff": 0.5,     # кВт·год/°C для холоду (<22°C)
    "weekend_boost": 0.12,      # 12% приріст на вихідні
    "bias_correction": 1.0,     # Загальний мультиплікатор точного підгону
    "last_mape": 0.0,           # Останній відсоток похибки (Mean Absolute Percentage Error)
}

# Config Flow keys
CONF_CONSUMPTION_SENSOR = "consumption_sensor"
CONF_SOLAR_ACTUAL_SENSOR = "solar_actual_sensor"
CONF_SOLAR_FORECAST_TODAY = "solar_forecast_today"
CONF_SOLAR_FORECAST_TOMORROW = "solar_forecast_tomorrow"
CONF_TEMP_SENSOR = "temp_sensor"
CONF_WORKDAY_SENSOR = "workday_sensor"