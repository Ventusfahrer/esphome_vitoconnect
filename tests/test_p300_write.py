"""Exercise real queue ownership and P300 parsing, including the captured error frame."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class P300WriteTest(unittest.TestCase):
    def test_real_queue_and_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            uart = work / 'esphome/components/uart/uart.h'
            uart.parent.mkdir(parents=True)
            uart.write_text('''
#pragma once
#include <cstdint>
#include <cstddef>
#include <deque>
#include <vector>
extern uint32_t test_now;
inline uint32_t millis() { return test_now; }
namespace esphome { namespace uart {
class UARTDevice {
 public:
 std::deque<uint8_t> rx;
 std::vector<uint8_t> tx;
 int available() { return rx.size(); }
 int read() { if (rx.empty()) return -1; auto b=rx.front(); rx.pop_front(); return b; }
 void flush() {}
 void write_array(const uint8_t *data, size_t length) { tx.assign(data, data+length); }
};
}}
''')
            log = work / 'esphome/core/log.h'
            log.parent.mkdir(parents=True)
            log.write_text('#pragma once\n#define ESP_LOGW(...) ((void)0)\n')
            source = work / 'test.cpp'
            source.write_text('''
#include <cassert>
#include <vector>
#include <cstdint>
#define private public
#include "components/vitoconnect/vitoconnect_optolinkP300.h"
#undef private
using namespace esphome::vitoconnect;
uint32_t test_now = 0;
unsigned successes = 0, failures = 0;
uint8_t last_error = 255;
std::vector<uint8_t> result;
void success(uint8_t* data, uint8_t length, void* arg) {
 assert(arg == reinterpret_cast<void*>(123));
 ++successes; result.assign(data, data+length);
}
void failure(uint8_t error, void*) { ++failures; last_error=error; }
void deliver(OptolinkP300 &link, esphome::uart::UARTDevice &uart, std::vector<uint8_t> frame) {
 uart.rx.push_back(6); link._sentAck();
 // Exercise fragmentation: each byte may arrive in its own UART poll.
 for (auto byte : frame) { uart.rx.push_back(byte); link._receive(); }
 assert(link._state == OptolinkP300::RECEIVE_ACK);
 link._receiveAck();
}
int main() {
 esphome::uart::UARTDevice uart;
 OptolinkP300 link(&uart);
 link.onData(success); link.onError(failure);
 for (int i=0; i<100; ++i) {
   { uint8_t value[] = {0xDC, 0}; assert(link.write(0x2000, 2, value, reinterpret_cast<void*>(123))); }
   // Allocations after the temporary queue copies are destroyed must not change payload.
   std::vector<std::vector<uint8_t>> churn(30, std::vector<uint8_t>(2, 0x55));
   link._send();
   assert(uart.tx == std::vector<uint8_t>({0x41,7,0,2,0x20,0,2,0xDC,0,7}));
   deliver(link, uart, {0x41,5,1,2,0x20,0,2,0x2A});
   assert(successes == unsigned(2*i+1) && failures == 0);
   assert(result == std::vector<uint8_t>({0xDC,0}));
   assert(link.read(0x2000,2,reinterpret_cast<void*>(123)));
   link._send();
   deliver(link, uart, {0x41,7,1,1,0x20,0,2,0xD2,0,0xFD});
   assert(successes == unsigned(2*i+2)); // Reuse the ring buffer across wraparound.
 }
 unsigned before = successes;
 uint8_t value[] = {0xDC,0};
 assert(link.write(0x2000,2,value)); link._send();
 // Exact device error from the user's log: 9 bytes, not 8.
 deliver(link, uart, {0x41,6,3,2,0x20,0,1,0x21,0x4D});
 assert(failures == 1 && last_error == VITO_ERROR && successes == before);
 assert(link.read(0x2000,2,reinterpret_cast<void*>(123))); link._send();
 deliver(link, uart, {0x41,7,1,1,0x20,0,2,0xD2,0,0xFD});
 assert(successes == before+1 && result == std::vector<uint8_t>({0xD2,0}));
 // Bad checksum and excessive header length are rejected without buffer overflow.
 assert(link.write(0x2000,2,value)); link._send();
 deliver(link, uart, {0x41,5,1,2,0x20,0,2,0});
 assert(failures == 2 && last_error == CRC);
 assert(link.write(0x2000,2,value)); link._send();
 deliver(link, uart, {0x41,255});
 assert(failures == 3 && last_error == LENGTH);
}
''')
            component = ROOT / 'components/vitoconnect'
            executable = work / 'test'
            built = subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra',
                '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                '-I', str(work), '-I', str(ROOT), str(source),
                *[str(component / name) for name in ['vitoconnect_optolink.cpp',
                    'vitoconnect_optolinkDP.cpp', 'vitoconnect_optolinkP300.cpp']],
                '-o', str(executable)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            subprocess.run([str(executable)], check=True)
