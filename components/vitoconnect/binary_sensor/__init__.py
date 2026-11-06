import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import binary_sensor
from esphome.const import CONF_NAME, CONF_UPDATE_INTERVAL, CONF_ADDRESS

from .. import CONF_VITOCONNECT_ID, VitoConnect, vitoconnect_ns

DEPENDENCIES = ["vitoconnect"]
OPTOLINKBinarySensor = vitoconnect_ns.class_(
    "OPTOLINKBinarySensor", binary_sensor.BinarySensor
)

CONFIG_SCHEMA = binary_sensor.binary_sensor_schema(OPTOLINKBinarySensor).extend(
    {
        cv.GenerateID(): cv.declare_id(OPTOLINKBinarySensor),
        cv.GenerateID(CONF_VITOCONNECT_ID): cv.use_id(VitoConnect),
        cv.Required(CONF_ADDRESS): cv.uint16_t,
        cv.Optional(CONF_UPDATE_INTERVAL): cv.positive_time_period_milliseconds,
    }
)


async def to_code(config):
    var = await binary_sensor.new_binary_sensor(config)

    # Add configuration to datapoint
    cg.add(var.setAddress(config[CONF_ADDRESS]))
    cg.add(var.setLength(1))

    # Add sensor to component hub (VitoConnect)
    hub = await cg.get_variable(config[CONF_VITOCONNECT_ID])
    if CONF_UPDATE_INTERVAL in config:
        cg.add(hub.register_datapoint(var, config[CONF_UPDATE_INTERVAL], config.get(CONF_NAME, "")))
    else:
        cg.add(hub.register_datapoint(var, 0, config.get(CONF_NAME, "")))
