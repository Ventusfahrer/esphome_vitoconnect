#pragma once
#include "esphome/components/number/number.h"
#include "../vitoconnect.h"

namespace esphome {
namespace vitoconnect {
// Signed LE16 temperature in tenths of a degree; normal room setpoint only.
class OPTOLINKNumber : public number::Number, public Datapoint {
 public:
  void set_parent(VitoConnect *parent) { parent_ = parent; }
  void decode(uint8_t *data, uint8_t length, Datapoint *dp = nullptr) override;
 protected:
  void control(float value) override;
  VitoConnect *parent_{nullptr};
};
}  // namespace vitoconnect
}  // namespace esphome
