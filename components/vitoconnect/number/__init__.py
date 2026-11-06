import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import number
from esphome.const import CONF_ADDRESS, CONF_NAME, CONF_UPDATE_INTERVAL, UNIT_CELSIUS, DEVICE_CLASS_TEMPERATURE
from .. import CONF_VITOCONNECT_ID, VitoConnect, vitoconnect_ns

DEPENDENCIES = ["vitoconnect"]
OPTOLINKNumber = vitoconnect_ns.class_("OPTOLINKNumber", number.Number)
CONFIG_SCHEMA = number.number_schema(OPTOLINKNumber, unit_of_measurement=UNIT_CELSIUS, device_class=DEVICE_CLASS_TEMPERATURE).extend({
    cv.GenerateID(CONF_VITOCONNECT_ID): cv.use_id(VitoConnect),
    cv.Required(CONF_ADDRESS): cv.All(cv.uint16_t, cv.one_of(0x2000)),
    cv.Optional(CONF_UPDATE_INTERVAL, default="60s"): cv.positive_time_period_milliseconds,
})

async def to_code(config):
    var = await number.new_number(config, min_value=10, max_value=30, step=1)
    hub = await cg.get_variable(config[CONF_VITOCONNECT_ID])
    cg.add(var.set_parent(hub))
    cg.add(var.setAddress(config[CONF_ADDRESS]))
    cg.add(var.setLength(2))
    cg.add(hub.register_datapoint(var, config[CONF_UPDATE_INTERVAL], config.get(CONF_NAME, "")))
