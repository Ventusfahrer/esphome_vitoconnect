#include "vitoconnect_number.h"
#include <cmath>

namespace esphome {
namespace vitoconnect {
void OPTOLINKNumber::decode(uint8_t *data, uint8_t length, Datapoint *) {
  if (length != 2) return;
  const int16_t raw = static_cast<int16_t>(uint16_t(data[0]) | (uint16_t(data[1]) << 8));
  publish_state(raw / 10.0f);
}
void OPTOLINKNumber::control(float value) {
  if (!std::isfinite(value) || value < 10 || value > 30 || value != std::round(value)) {
    ESP_LOGW("vitoconnect.number", "Invalid room setpoint");
    return;
  }
  const uint16_t raw = static_cast<uint16_t>(std::lround(value * 10));
  uint8_t data[2] = {static_cast<uint8_t>(raw), static_cast<uint8_t>(raw >> 8)};
  if (!parent_ || !parent_->write_datapoint(this, data))
    ESP_LOGW("vitoconnect.number", "Could not queue room setpoint write");
}
}  // namespace vitoconnect
}  // namespace esphome
