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

  uint32_t successes{0};
  uint32_t errors{0};
  uint32_t last_success{0};
  uint8_t last_error{0};
  bool last_failed{false};

  void received(uint32_t now) {
    complete();
    if (successes != UINT32_MAX) ++successes;
    last_success = now;
    last_failed = false;
  }
  void failed(uint8_t error) {
    complete();
    if (errors != UINT32_MAX) ++errors;
    last_error = error;
    last_failed = true;
  }
  const char* status(uint32_t now, uint32_t fallback) const {
    if (last_failed) return "FEHLER";
    if (successes == 0) return "KEINE_ANTWORT";
    const uint32_t period = interval == 0 ? fallback : interval;
    if (uint64_t(uint32_t(now - last_success)) > uint64_t(period) * 2)
      return "VERALTET";
    return "OK";
  }

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
