#pragma once

#include <cstdint>

namespace esphome {
namespace vitoconnect {

// One outstanding request per datapoint. Unsigned subtraction handles millis rollover.
struct PollSchedule {
  uint32_t interval{0};  // Zero inherits the hub interval.
  uint32_t last_queued{0};
  bool started{false};
  bool pending{false};

  bool due(uint32_t now, uint32_t fallback) const {
    return !pending && (!started || uint32_t(now - last_queued) >=
                                    (interval == 0 ? fallback : interval));
  }
  void queued(uint32_t now) {
    last_queued = now;
    started = true;
    pending = true;
  }
  void complete() { pending = false; }
};

}  // namespace vitoconnect
}  // namespace esphome
