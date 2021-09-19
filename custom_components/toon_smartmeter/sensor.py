"""Sensor for Toon Smart Meter integration."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from functools import reduce
import logging
from typing import Final

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    STATE_CLASS_TOTAL_INCREASING,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_RESOURCES,
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_GAS,
    DEVICE_CLASS_POWER,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
    VOLUME_CUBIC_METERS,

)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle, dt

BASE_URL = "http://{0}:{1}/hdrv_zwave?action=getDevices.json"
_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=10)

SENSOR_PREFIX = "Toon "
ATTR_MEASUREMENT = "measurement"
ATTR_SECTION = "section"

SENSOR_LIST = {
    "gasused",
    "gasusedcnt",
    "elecusageflowpulse",
    "elecusagecntpulse",
    "elecusageflowlow",
    "elecusageflowhigh",
    "elecprodflowlow",
    "elecprodflowhigh",
    "elecusagecntlow",
    "elecusagecnthigh",
    "elecprodcntlow",
    "elecprodcnthigh",
    "elecsolar",
    "elecsolarcnt",
    "heat",
    "waterflow",
    "waterusedcnt",
}

SENSOR_TYPES: Final[tuple[SensorEntityDescription, ...]] = (
    SensorEntityDescription(
        key="gasused",
        name="Gas Used Last Hour",
        icon="mdi:gas-cylinder",
        device_class=DEVICE_CLASS_GAS,
        native_unit_of_measurement=VOLUME_CUBIC_METERS,
        state_class=STATE_CLASS_TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="gasusedcnt",
        name="Gas Used Cnt",
        icon="mdi:gas-cylinder",
        device_class=DEVICE_CLASS_GAS,
        native_unit_of_measurement=VOLUME_CUBIC_METERS,
        state_class=STATE_CLASS_TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecusageflowpulse",
        name="Power Use",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=DEVICE_CLASS_POWER,
    ),
    SensorEntityDescription(
        key="elecusageflowlow",
        name="P1 Power Use Low",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=DEVICE_CLASS_POWER,
    ),
    SensorEntityDescription(
        key="elecusageflowhigh",
        name="P1 Power Use High",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=DEVICE_CLASS_POWER,
    ),
    SensorEntityDescription(
        key="elecprodflowlow",
        name="P1 Power Prod Low",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=DEVICE_CLASS_POWER,
    ),
    SensorEntityDescription(
        key="elecprodflowhigh",
        name="P1 Power Prod High",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=DEVICE_CLASS_POWER,
    ),
    SensorEntityDescription(
        key="elecusagecntpulse",
        name="P1 Power Use Cnt",
        icon="mdi:flash",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecusagecntlow",
        name="P1 Power Use Cnt Low",
        icon="mdi:flash",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecusagecnthigh",
        name="P1 Power Use Cnt High",
        icon="mdi:flash",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecprodcntlow",
        name="P1 Power Prod Cnt Low",
        icon="mdi:flash",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecprodcnthigh",
        name="P1 Power Prod Cnt High",
        icon="mdi:flash",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecsolar",
        name="P1 Power Solar",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=DEVICE_CLASS_POWER,
    ),
    SensorEntityDescription(
        key="elecsolarcnt",
        name="P1 Power Solar Cnt",
        icon="mdi:flash",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="heat",
        name="P1 Heat",
        icon="mdi:fire",
    ),
    SensorEntityDescription(
        key="waterflow",
        name="Actual water usage",
        icon="mdi:water-pump",
        native_unit_of_measurement="L/min",
    ),
    SensorEntityDescription(
        key="waterusedcnt",
        name="Water used",
        icon="mdi:water",
        native_unit_of_measurement=VOLUME_CUBIC_METERS,
        state_class=STATE_CLASS_TOTAL_INCREASING,
    ),
)


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=80): cv.positive_int,
        vol.Required(CONF_RESOURCES, default=list(SENSOR_LIST)): vol.All(
            cv.ensure_list, [vol.In(SENSOR_LIST)]
        ),
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Setup the Toon Smart Meter sensors."""

    session = async_get_clientsession(hass)
    data = ToonSmartMeterData(session, config.get(CONF_HOST), config.get(CONF_PORT))
    await data.async_update()

    # Create a new sensor for each sensor type.
    entities = []
    for description in SENSOR_TYPES:
        if description.key in config[CONF_RESOURCES]:
            sensor = ToonSmartMeterSensor(description, data)
            entities.append(sensor)
    async_add_entities(entities, True)
    return True


# pylint: disable=abstract-method
class ToonSmartMeterData(object):
    """Handle Toon object and limit updates."""

    def __init__(self, session, host, port):
        """Initialize the data object."""

        self._session = session
        self._url = BASE_URL.format(host, port)
        self._data = None

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        """Download and update data from Toon."""

        try:
            with async_timeout.timeout(5):
                response = await self._session.get(
                    self._url, headers={"Accept-Encoding": "identity"}
                )
        except aiohttp.ClientError:
            _LOGGER.error("Cannot poll Toon using url: %s", self._url)
            return
        except asyncio.TimeoutError:
            _LOGGER.error(
                "Timeout error occurred while polling Toon using url: %s", self._url
            )
            return
        except Exception as err:
            _LOGGER.error("Unknown error occurred while polling Toon: %s", err)
            self._data = None
            return

        try:
            self._data = await response.json(content_type="text/javascript")
            _LOGGER.debug("Data received from Toon: %s", self._data)
        except Exception as err:
            _LOGGER.error("Cannot parse data received from Toon: %s", err)
            self._data = None

    @property
    def latest_data(self):
        """Return the latest data object."""
        if self._data:
            return self._data
        return None


class ToonSmartMeterSensor(SensorEntity):
    """Representation of a Smart Meter connected to Toon."""

    def __init__(self, description: SensorEntityDescription, data):
        """Initialize the sensor."""
        self.entity_description = description
        self._data = data

        self._state = None

        self._type = self.entity_description.key
        self._attr_icon = self.entity_description.icon
        self._attr_name = SENSOR_PREFIX + self.entity_description.name
        self._attr_state_class = self.entity_description.state_class
        self._attr_native_unit_of_measurement = self.entity_description.native_unit_of_measurement
        self._attr_device_class = self.entity_description.device_class
        self._attr_unique_id = f"{SENSOR_PREFIX}_{self._type}"

        self._discovery = False
        self._dev_id = {}

    def _validateOutput(self, value):
        """Return 0 if the output from the Toon is NaN (happens after a reboot)"""
        try:
            if value.lower() == "nan":
                value = 0    @property
        except:
            return value

        return value

    @property
    def state(self):
        """Return the state of the sensor. (total/current power consumption/production or total gas used)"""
        return self._state

    async def async_update(self):
        """Get the latest data and use it to update our sensor state."""

        await self._data.async_update()
        energy = self._data.latest_data

        if not energy:
            return
        
        p1_device = "dev_15"
        water_device = "dev_27"
        solar_device = "dev_20.export"
        
        """gas verbruik laatste uur"""
        if self._type == "gasused":
            self._state = float(energy[p1_device + ".1"]["CurrentGasFlow"]) / 1000

            """gas verbruik teller laatste uur"""
        elif self._type == "gasusedcnt":
            self._state = float(energy[p1_device + ".1"]["CurrentGasQuantity"]) / 1000
            
            """elec verbruik puls"""
        elif self._type == "elecusageflowpulse":
            self._state = energy[p1_device + ".2"]["CurrentElectricityFlow"]

            """elec verbruik teller puls"""
        elif self._type == "elecusagecntpulse":
            self._state = float(energy[p1_device + ".2"]["CurrentElectricityQuantity"]) / 1000
            
            """elec verbruik laag"""
        elif self._type == "elecusageflowlow":
            self._state = energy[p1_device + ".6"]["CurrentElectricityFlow"]
            
            """elec verbruik teller laag"""
        elif self._type == "elecusagecntlow":
            self._state = float(energy[p1_device + ".6"]["CurrentElectricityQuantity"] ) / 1000

            """elec verbruik hoog/normaal"""
        elif self._type == "elecusageflowhigh":
            self._state = energy[p1_device + ".4"]["CurrentElectricityFlow"]

            """elec verbruik teller hoog/normaal"""
        elif self._type == "elecusagecnthigh":
            self._state = float(energy[p1_device + ".4"]["CurrentElectricityQuantity"]) / 1000

            """elec teruglever laag"""
        elif self._type == "elecprodflowlow":
            self._state = energy[p1_device + ".7"]["CurrentElectricityFlow"]

            """elec teruglever teller laag"""
        elif self._type == "elecprodcntlow":
            self._state = float(energy[p1_device + ".7"]["CurrentElectricityQuantity"]) / 1000

            """elec teruglever hoog/normaal"""
        elif self._type == "elecprodflowhigh":
            self._state = energy[p1_device + ".5"]["CurrentElectricityFlow"]
 
            """elec teruglever teller hoog/normaal"""
        elif self._type == "elecprodcnthigh":
            self._state = float(energy[p1_device + ".5"]["CurrentElectricityQuantity"]) / 1000

            """zon op toon"""
        elif self._type == "elecsolar":
            self._state = energy[solar_device]["CurrentElectricityFlow"]

            """zon op toon teller"""
        elif self._type == "elecsolarcnt":
            self._state = float(energy[solar_device]["CurrentElectricityQuantity"]) / 1000

            """heat"""
        elif self._type == "heat":
            self._state = float(energy[p1_device + ".8"]["CurrentHeatQuantity"]) / 1000

            """water op toon"""
        elif self._type == 'waterflow':
            self._state = round((float(energy[water_device + ".9"]["CurrentWaterFlow"])/60), 1)

            """water op toon teller"""
        elif self._type == 'waterusedcnt':
            self._state = float(energy[water_device + ".9"]["CurrentWaterQuantity"])/1000
        
            
        _LOGGER.debug("Device: {} State: {}".format(self._type, self._state))

def safe_get(_dict, keys, default=None):
    def _reducer(d, key):
        if isinstance(d, dict):
            return d.get(key, default)
        return default

    return reduce(_reducer, keys, _dict)
