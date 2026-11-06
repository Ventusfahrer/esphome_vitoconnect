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

void VitoConnect::register_datapoint(Datapoint *datapoint, uint32_t update_interval) {
    ESP_LOGD(TAG, "Adding datapoint with address %x and length %d", datapoint->getAddress(), datapoint->getLength());
    ScheduledDatapoint entry;
    entry.dp = datapoint;
    entry.schedule.interval = update_interval;
    this->_datapoints.push_back(entry);
}

void VitoConnect::loop() {
    if (!_optolink) return;
    _optolink->loop();
    schedule_due_();
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

void VitoConnect::_onData(uint8_t* data, uint8_t len, void* arg) {
  CbArg* cbArg = reinterpret_cast<CbArg*>(arg);
  cbArg->scheduled->schedule.complete();
  cbArg->dp->decode(data, len, cbArg->dp);
  delete cbArg;
}

void VitoConnect::_onError(uint8_t error, void* arg) {
  ESP_LOGD(TAG, "Error received: %d", error);
  CbArg* cbArg = reinterpret_cast<CbArg*>(arg);
  cbArg->scheduled->schedule.complete();
  if (cbArg->v->_onErrorCb) cbArg->v->_onErrorCb(error, cbArg->dp);
  delete cbArg;
}

}  // namespace vitoconnect
}  // namespace esphome
