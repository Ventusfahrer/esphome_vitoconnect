"""Exercise production scheduling with a bounded fake Optolink transport."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PollScheduleTest(unittest.TestCase):
    def test_hub_intervals_backpressure_errors_and_rollover(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            component = work / 'component'
            component.mkdir()
            for name in ['vitoconnect.h', 'vitoconnect.cpp', 'vitoconnect_poll_schedule.h',
                         'vitoconnect_datapoint.h', 'vitoconnect_datapoint.cpp']:
                shutil.copyfile(ROOT / 'components/vitoconnect' / name, component / name)
            shutil.copytree(ROOT / 'components/vitoconnect/number', component / 'number')
            def stub(name, content):
                path = work / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            stub('esphome/core/component.h', '''
#pragma once
#include <cstdint>
#include <vector>
#include <string>
#include <cstdarg>
#include <cstdio>
extern std::vector<std::string> report_lines;
inline void test_log(const char*, const char* format, ...) {
 char buffer[1024]; va_list args; va_start(args, format);
 vsnprintf(buffer, sizeof(buffer), format, args); va_end(args);
 report_lines.emplace_back(buffer);
}
#define ESP_LOGI(...) test_log(__VA_ARGS__)
extern uint32_t test_now;
inline uint32_t millis() { return test_now; }
#define ESP_LOGD(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
namespace esphome {
class PollingComponent {
 uint32_t interval_;
 public:
 explicit PollingComponent(uint32_t interval) : interval_(interval) {}
 virtual void setup() {} virtual void loop() {} virtual void update() {}
 void set_update_interval(uint32_t value) { interval_ = value; }
 uint32_t get_update_interval() { return interval_; }
};
}
''')
            stub('esphome/components/uart/uart.h', '''
#pragma once
#include <cassert>
namespace esphome { namespace uart {
enum { UART_CONFIG_PARITY_EVEN };
class UARTDevice { public:
 int rx_count = 0;
 int rx_byte = 5;
 void check_uart_settings(int, int, int, int) {}
 void flush() {}
 int available() { return rx_count; }
 int read() { assert(rx_count > 0); --rx_count; return rx_byte; }
};
}}
''')
            stub('esphome/components/uart/uart_component.h', '#pragma once\n')
            stub('esphome/components/sensor/sensor.h', '#pragma once\n')
            stub('esphome/components/number/number.h', '''
#pragma once
namespace esphome { namespace number {
class Number {
 public:
 float state = 0;
 unsigned publications = 0;
 void publish_state(float value) { state = value; ++publications; }
 virtual void control(float) = 0;
};
}}
''')
            stub('component/vitoconnect_optolink.h', '''
#pragma once
#include <cstdint>
#include <vector>
namespace esphome { namespace vitoconnect {
enum { TIMEOUT = 0, CANCELLED = 5 };
class Optolink {
 public:
 struct Request { uint16_t address; void* arg; };
 std::vector<Request> queue;
 std::vector<uint16_t> sent;
 std::vector<uint8_t> payload;
 void (*data)(uint8_t*, uint8_t, void*) = nullptr;
 void (*error)(uint8_t, void*) = nullptr;
 static Optolink* instance;
 explicit Optolink(void*) { instance = this; }
 void onData(decltype(data) cb) { data = cb; }
 void onError(decltype(error) cb) { error = cb; }
 unsigned begins = 0, loops = 0, passive_begins = 0;
 bool timeout_next_loop = false;
 void begin() { ++begins; }
 void begin_after_enquiry() { ++passive_begins; }
 void loop() {
   ++loops;
   if (timeout_next_loop && !queue.empty()) {
     timeout_next_loop = false;
     // Match real transport: callback first, then pop the timed-out request.
     error(TIMEOUT, queue.front().arg);
     queue.erase(queue.begin());
   }
 }
 void cancel_pending() {
   while (!queue.empty()) {
     auto request = queue.front(); queue.erase(queue.begin());
     error(CANCELLED, request.arg);
   }
 }
 bool read(uint16_t address, uint8_t, void* arg) {
   if (queue.size() == 2) return false;
   queue.push_back({address, arg}); sent.push_back(address); return true;
 }
 bool write(uint16_t address, uint8_t length, uint8_t* bytes, void* arg) {
   if (queue.size() == 2) return false;
   payload.assign(bytes, bytes + length);
   queue.push_back({address, arg}); return true;
 }
 void finish(bool failed = false) {
   auto request = queue.front(); queue.erase(queue.begin());
   uint8_t value = 42;
   if (failed) error(1, request.arg); else data(&value, 1, request.arg);
 }
};
}}
''')
            for protocol in ['P300', 'KW', 'GWG']:
                stub(f'component/vitoconnect_optolink{protocol}.h', f'''
#pragma once
#include "vitoconnect_optolink.h"
namespace esphome {{ namespace vitoconnect {{
class Optolink{protocol} : public Optolink {{ public: using Optolink::Optolink; }};
}}}}
''')
            stub('test.cpp', '''
#include "component/vitoconnect.h"
#include "component/number/vitoconnect_number.h"
#include <limits>
#include <cassert>
uint32_t test_now = 0;
std::vector<std::string> report_lines;
using namespace esphome::vitoconnect;
Optolink* Optolink::instance = nullptr;
class Value : public Datapoint {
 public: unsigned count = 0;
 void decode(uint8_t*, uint8_t, Datapoint*) override { ++count; }
};
int main() {
 VitoConnect hub;
 Value fast, slow, inherited;
 fast.setAddress(1); slow.setAddress(2); inherited.setAddress(3);
 fast.setLength(1); slow.setLength(1); inherited.setLength(1);
 hub.set_protocol("P300"); hub.set_update_interval(30000);
 hub.register_datapoint(&fast, 10000, "Fast");
 hub.register_datapoint(&slow, 300000, "Slow");
 hub.register_datapoint(&inherited);
 hub.update();  // Safe before setup.
 hub.setup();
 hub.print_sensor_report();
 assert(report_lines[0].find("3 konfiguriert, 0 beantwortet, 3 ohne Antwort") != std::string::npos);
 hub.loop();
 auto* transport = Optolink::instance;
 assert(transport->sent.size() == 2);
 hub.loop(); assert(transport->sent.size() == 2); // Pending: no duplicates.
 transport->finish(); hub.loop(); // Full queue request retried, not dropped.
 assert(transport->sent.back() == 3);
 transport->finish(); transport->finish();
 assert(fast.count == 1 && slow.count == 1 && inherited.count == 1);
 test_now = 9999; hub.loop(); assert(transport->queue.empty());
 test_now = 10000; hub.loop(); assert(transport->queue.size() == 1);
 assert(transport->queue[0].address == 1);
 test_now = 30000; hub.loop(); // Fast still pending; inherited is due.
 assert(transport->queue.size() == 2 && transport->queue[1].address == 3);
 transport->finish(true);
 hub.print_sensor_report();
 assert(report_lines.back().find("Zuletzt Fehler: 1") != std::string::npos);
 transport->finish();
 hub.loop(); // Failed fast request becomes eligible on its normal cadence.
 assert(transport->queue.size() == 1 && transport->queue[0].address == 1);
 transport->finish();
 test_now = 300000; hub.loop();
 assert(transport->queue.size() == 2 && transport->queue[1].address == 2);
 transport->finish(); transport->finish(); hub.loop(); transport->finish();
 assert(slow.count == 2 && inherited.count == 3);
 PollSchedule rollover;
 rollover.interval = 10000;
 rollover.queued(UINT32_MAX - 4999); rollover.complete();
 assert(!rollover.due(4999, 30000));
 assert(rollover.due(5000, 30000));
 report_lines.clear();
 hub.print_sensor_report();
 assert(report_lines[0].find("3 konfiguriert, 3 beantwortet, 0 ohne Antwort") != std::string::npos);
 for (int i = 0; i < 4; ++i) { test_now += 150; hub.loop(); }
 assert(report_lines.size() == 6);
 assert(report_lines[2].find("0x0001 Fast: OK; OK=3 Fehler=1") != std::string::npos);
 assert(report_lines[3].find("0x0002 Slow: OK; OK=2 Fehler=0") != std::string::npos);
 assert(report_lines[4].find("0x0003") != std::string::npos);
 assert(report_lines[5] == "Sensorpruefung beendet");
 PollSchedule stats;
 assert(std::string(stats.status(0, 10000)) == "KEINE_ANTWORT");
 stats.queued(0); stats.received(0);
 assert(stats.successes == 1 && !stats.pending);
 assert(std::string(stats.status(20000, 10000)) == "OK");
 assert(std::string(stats.status(20001, 10000)) == "VERALTET");
 stats.failed(7);
 assert(stats.errors == 1 && stats.last_error == 7);
 assert(std::string(stats.status(20002, 10000)) == "FEHLER");
 stats.received(20003);
 assert(stats.errors == 1 && stats.successes == 2 && !stats.last_failed);
 stats.successes = UINT32_MAX; stats.received(20004); assert(stats.successes == UINT32_MAX);
 stats.errors = UINT32_MAX; stats.failed(8); assert(stats.errors == UINT32_MAX);
 // Real number encoder and hub callbacks: no optimistic state publication.
 class TestNumber : public OPTOLINKNumber { public: using OPTOLINKNumber::control; };
 VitoConnect writer;
 TestNumber room;
 room.set_parent(&writer); room.setAddress(0x2000); room.setLength(2);
 writer.set_protocol("P300"); writer.set_update_interval(60000);
 writer.register_datapoint(&room, 60000, "Room");
 room.control(21); // Before setup: safe and no publication.
 assert(room.publications == 0);
 writer.setup();
 transport = Optolink::instance;
 for (float value : {9.0f, 31.0f, 21.5f, std::numeric_limits<float>::quiet_NaN()})
   room.control(value);
 assert(transport->queue.empty());
 room.control(21);
 assert(transport->queue.size() == 1 && transport->queue[0].address == 0x2000);
 assert(transport->payload == std::vector<uint8_t>({0xD2, 0x00}));
 transport->finish(); // Write ACK must not decode the echoed value.
 assert(room.publications == 0);
 writer.loop();
 assert(transport->queue.size() == 1); // Immediate readback, before interval expires.
 auto request = transport->queue.front(); transport->queue.erase(transport->queue.begin());
 uint8_t confirmed[] = {0xDC, 0x00};
 transport->data(confirmed, 2, request.arg);
 assert(room.publications == 1 && room.state == 22); // Actual read wins.
 room.control(10); room.control(30);
 assert(transport->payload == std::vector<uint8_t>({0x2C, 0x01}));
 room.control(21); // Queue full: no optimistic publication or leaked callback.
 assert(transport->queue.size() == 2 && room.publications == 1);
 transport->finish(true); transport->finish(true);
 writer.loop(); assert(transport->queue.size() == 1);
 transport->finish(true); // Failed readback: retain last confirmed value.
 assert(room.publications == 1 && room.state == 22);
 // Pausing cancels both reads and writes, rejects new work, and keeps RX/logs alive.
 test_now += 60000;
 room.control(21); writer.loop();
 assert(transport->queue.size() == 2);
 auto loops_before = transport->loops;
 writer.set_communication_paused(true);
 assert(writer.is_communication_paused() && transport->queue.empty());
 writer.rx_count = 3;
 writer.loop(); writer.update(); room.control(22);
 assert(writer.rx_count == 0 && transport->queue.empty());
 assert(transport->loops == loops_before);
 writer.print_sensor_report();
 assert(report_lines.back().find("Zuletzt Fehler: 1") != std::string::npos);
 writer.rx_count = 2;
 writer.set_communication_paused(false);
 assert(writer.rx_count == 0 && transport->begins == 2);
 writer.set_communication_paused(false); assert(transport->begins == 2);
 writer.loop(); assert(transport->queue.size() == 1);
 transport->finish(true);
 // Boot silence and timeout latch: cancellation must wait for callback unwind.
 VitoConnect guarded;
 Value first, second;
 first.setAddress(10); first.setLength(1);
 second.setAddress(11); second.setLength(1);
 guarded.set_protocol("P300"); guarded.set_update_interval(10000);
 guarded.set_start_paused(true); guarded.set_pause_on_timeout(true);
 guarded.register_datapoint(&first); guarded.register_datapoint(&second);
 guarded.setup(); transport = Optolink::instance;
 guarded.loop(); guarded.update();
 assert(guarded.is_communication_paused());
 assert(transport->loops == 0 && transport->queue.empty());
 assert(!guarded.write_datapoint(&first, confirmed));
 guarded.set_communication_paused(false); guarded.loop();
 assert(transport->queue.size() == 2);
 transport->timeout_next_loop = true; guarded.loop();
 assert(guarded.is_communication_paused() && transport->queue.empty());
 loops_before = transport->loops;
 test_now += 1000000;
 guarded.loop(); guarded.update();
 assert(transport->loops == loops_before && transport->queue.empty());
 guarded.set_communication_paused(false); guarded.loop();
 assert(transport->queue.size() == 2);
 transport->finish(); transport->finish();
 assert(first.count == 1 && second.count == 1);
 // Automatic recovery needs a full stream of unsolicited enquiries, not time alone.
 VitoConnect automatic;
 Value automatic_value; automatic_value.setAddress(12); automatic_value.setLength(1);
 automatic.set_protocol("P300"); automatic.set_update_interval(10000);
 automatic.set_start_paused(true); automatic.set_pause_on_timeout(true);
 automatic.set_recovery_delay(120000);
 automatic.register_datapoint(&automatic_value);
 automatic.setup(); transport = Optolink::instance;
 test_now = UINT32_MAX - 99999; // Exercise timer rollover during safety wait.
 automatic.loop();
 assert(automatic.is_communication_paused() && transport->loops == 0);
 for (int i=0; i<60; ++i) {
   automatic.rx_count = 1; automatic.loop(); test_now += 2000;
   assert(automatic.is_communication_paused());
 }
 automatic.loop(); // Delay expired, but no new 05: still silent.
 assert(automatic.is_communication_paused());
 automatic.rx_count = 1; automatic.loop();
 assert(!automatic.is_communication_paused() && transport->passive_begins == 1);
 assert(transport->loops == 0 && transport->queue.empty());
 automatic.loop(); assert(transport->queue.size() == 1);
 transport->timeout_next_loop = true; automatic.loop();
 assert(automatic.is_communication_paused() && transport->queue.empty());
 automatic.rx_count = 1; automatic.loop();
 test_now += 6000; automatic.rx_count = 1; automatic.loop(); // gap restarts timer
 for (int i=0; i<59; ++i) {
   test_now += 2000; automatic.rx_count = 1; automatic.loop();
 }
 assert(automatic.is_communication_paused());
 automatic.rx_byte = 6; automatic.rx_count = 1; automatic.loop(); // unexpected byte restarts
 automatic.rx_byte = 5;
 for (int i=0; i<60; ++i) {
   test_now += 2000; automatic.rx_count = 1; automatic.loop();
   assert(automatic.is_communication_paused());
 }
 test_now += 2000; automatic.rx_count = 1; automatic.loop();
 assert(!automatic.is_communication_paused() && transport->passive_begins == 2);
 automatic.loop(); transport->finish();
 automatic.set_communication_paused(true); // Explicit manual pause must not auto-release.
 for (int i=0; i<65; ++i) {
   test_now += 2000; automatic.rx_count = 1; automatic.loop();
 }
 assert(automatic.is_communication_paused() && transport->passive_begins == 2);
 VitoConnect invalid; invalid.set_protocol("invalid"); invalid.setup(); invalid.loop();
}
''')
            executable = work / 'test'
            result = subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra',
                '-I', str(work), str(work / 'test.cpp'),
                str(component / 'vitoconnect.cpp'),
                str(component / 'number/vitoconnect_number.cpp'),
                str(component / 'vitoconnect_datapoint.cpp'),
                '-o', str(executable)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(executable)], check=True)
