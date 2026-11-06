/*
  optolink.cpp - Connect Viessmann heating devices via Optolink to ESPhome

  Copyright (C) 2023  Philipp Danner

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

#include "vitoconnect.h"

namespace esphome {
namespace vitoconnect {

static const char *TAG = "vitoconnect";

void VitoConnect::setup() {

    this->check_uart_settings(4800, 2, uart::UART_CONFIG_PARITY_EVEN, 8);

    ESP_LOGD(TAG, "Starting optolink with protocol: %s", this->protocol.c_str());
    if (this->protocol.compare("P300") == 0) {
        _optolink = new OptolinkP300(this);
    } else if (this->protocol.compare("KW") == 0) {
        _optolink = new OptolinkKW(this);
    } else if (this->protocol.compare("GWG") == 0) {
        _optolink = new OptolinkGWG(this);
    } else {
      ESP_LOGW(TAG, "Unknown protocol.");
    }

    // optimize datapoint list
    _datapoints.shrink_to_fit();

    if (_optolink) {

      // add onData and onError callbacks
      _optolink->onData(&VitoConnect::_onData);
      _optolink->onError(&VitoConnect::_onError);
      
      // set initial state
      _optolink->begin();

    } else {
      ESP_LOGW(TAG, "Not able to initialize VitoConnect");
    }
}

void VitoConnect::register_datapoint(Datapoint *datapoint, uint32_t update_interval, const std::string &name) {
    ESP_LOGD(TAG, "Adding datapoint with address %x and length %d", datapoint->getAddress(), datapoint->getLength());
    ScheduledDatapoint entry;
    entry.dp = datapoint;
    entry.name = name;
    entry.schedule.interval = update_interval;
    this->_datapoints.push_back(entry);
}

bool VitoConnect::write_datapoint(Datapoint *datapoint, uint8_t *data) {
    if (!_optolink || protocol != "P300") return false;
    for (auto &entry : _datapoints) {
      if (entry.dp != datapoint) continue;
      CbArg *arg = new CbArg(this, &entry);
      arg->writing = true;
      if (!_optolink->write(datapoint->getAddress(), datapoint->getLength(), data, arg)) {
        delete arg;
        return false;
      }
      return true;
    }
    return false;
}

void VitoConnect::loop() {
    if (!_optolink) return;
    _optolink->loop();
    schedule_due_();
    report_next_();
}

void VitoConnect::update() {
    schedule_due_();
}

void VitoConnect::schedule_due_() {
    if (!_optolink) return;
    const uint32_t now = millis();
    for (auto &entry : _datapoints) {
      if (!entry.schedule.due(now, this->get_update_interval())) continue;
      CbArg* arg = new CbArg(this, &entry);
      if (!_optolink->read(entry.dp->getAddress(), entry.dp->getLength(),
                           reinterpret_cast<void*>(arg))) {
        delete arg;
        // Queue full: leave this request due and retry after the protocol drains it.
        break;
      }
      entry.schedule.queued(now);
    }
}

// Keep this report independent of the log history. Pace lines to avoid an API log burst.
void VitoConnect::print_sensor_report() {
  const uint32_t now = millis();
  size_t answered = 0, failed = 0, stale = 0, pending = 0;
  for (const auto &entry : _datapoints) {
    const auto &s = entry.schedule;
    if (s.successes != 0) ++answered;
    if (s.last_failed) ++failed;
    if (strcmp(s.status(now, get_update_interval()), "VERALTET") == 0) ++stale;
    if (s.pending) ++pending;
  }
  ESP_LOGI(TAG, "Sensorpruefung: %u konfiguriert, %u beantwortet, %u ohne Antwort",
           unsigned(_datapoints.size()), unsigned(answered), unsigned(_datapoints.size() - answered));
  ESP_LOGI(TAG, "Zuletzt Fehler: %u, veraltet (>2 Intervalle): %u, ausstehend: %u; Zaehler seit Neustart",
           unsigned(failed), unsigned(stale), unsigned(pending));
  report_index_ = 0;
  report_last_line_ = now;
  report_active_ = true;
}

void VitoConnect::report_next_() {
  const uint32_t now = millis();
  if (!report_active_ || uint32_t(now - report_last_line_) < 150) return;
  report_last_line_ = now;
  if (report_index_ >= _datapoints.size()) {
    ESP_LOGI(TAG, "Sensorpruefung beendet");
    report_active_ = false;
    return;
  }
  const auto &entry = _datapoints[report_index_++];
  const auto &s = entry.schedule;
  // '-' distinguishes never answered from an answer received at boot time zero.
  const std::string age = s.successes == 0 ? "-" : std::to_string(uint32_t(now - s.last_success) / 1000);
  ESP_LOGI(TAG, "%u/%u 0x%04X %s: %s; OK=%lu Fehler=%lu Alter_s=%s Intervall_s=%lu Offen=%s Fehlercode=%u",
           unsigned(report_index_), unsigned(_datapoints.size()), entry.dp->getAddress(),
           entry.name.c_str(), s.status(now, get_update_interval()),
           static_cast<unsigned long>(s.successes), static_cast<unsigned long>(s.errors), age.c_str(),
           static_cast<unsigned long>((s.interval == 0 ? get_update_interval() : s.interval) / 1000),
           s.pending ? "ja" : "nein", unsigned(s.last_error));
}

void VitoConnect::_onData(uint8_t* data, uint8_t len, void* arg) {
  CbArg* cbArg = reinterpret_cast<CbArg*>(arg);
  if (cbArg->writing) {
    // A write acknowledgement echoes the payload; only a real read confirms state.
    cbArg->scheduled->schedule.started = false;
    delete cbArg;
    return;
  }
  cbArg->scheduled->schedule.received(millis());
  cbArg->dp->decode(data, len, cbArg->dp);
  delete cbArg;
}

void VitoConnect::_onError(uint8_t error, void* arg) {
  ESP_LOGD(TAG, "Error received: %d", error);
  CbArg* cbArg = reinterpret_cast<CbArg*>(arg);
  if (cbArg->writing) {
    ESP_LOGW(TAG, "Write failed at 0x%04X: %u", cbArg->dp->getAddress(), error);
    cbArg->scheduled->schedule.started = false;
  } else {
    cbArg->scheduled->schedule.failed(error);
  }
  if (cbArg->v->_onErrorCb) cbArg->v->_onErrorCb(error, cbArg->dp);
  delete cbArg;
}

}  // namespace vitoconnect
}  // namespace esphome
