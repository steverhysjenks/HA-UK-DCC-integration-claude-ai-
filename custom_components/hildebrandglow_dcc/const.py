"""Constants for the Hildebrand Glow (DCC) integration."""

DOMAIN = "hildebrandglow_dcc"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# Stored in config entry data after initial auth
CONF_TOKEN = "token"
CONF_TOKEN_EXPIRY = "token_expiry"

# Coordinator update interval (seconds)
UPDATE_INTERVAL = 1800  # 30 minutes – matches DCC data delay

# Resource classifiers
CLASSIFIER_ELEC_CONSUMPTION = "electricity.consumption"
CLASSIFIER_ELEC_COST = "electricity.consumption.cost"
CLASSIFIER_ELEC_EXPORT = "electricity.export"
CLASSIFIER_GAS_CONSUMPTION = "gas.consumption"
CLASSIFIER_GAS_COST = "gas.consumption.cost"

CLASSIFIER_ICONS: dict[str, str] = {
    CLASSIFIER_ELEC_CONSUMPTION: "mdi:lightning-bolt",
    CLASSIFIER_ELEC_COST: "mdi:currency-gbp",
    CLASSIFIER_ELEC_EXPORT: "mdi:transmission-tower-export",
    CLASSIFIER_GAS_CONSUMPTION: "mdi:fire",
    CLASSIFIER_GAS_COST: "mdi:currency-gbp",
}

CLASSIFIER_NAMES: dict[str, str] = {
    CLASSIFIER_ELEC_CONSUMPTION: "Electricity Usage",
    CLASSIFIER_ELEC_COST: "Electricity Cost",
    CLASSIFIER_ELEC_EXPORT: "Electricity Export",
    CLASSIFIER_GAS_CONSUMPTION: "Gas Usage",
    CLASSIFIER_GAS_COST: "Gas Cost",
}

# Units returned by the API → HA device classes / units
UNIT_MAP: dict[str, str] = {
    "kWh": "kWh",
    "pence": "GBP",  # converted on the fly ÷100
}
