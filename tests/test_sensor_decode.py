"""Run with: python3 -m unittest discover -s tests -v (requires g++)."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SensorDecodeTest(unittest.TestCase):
    def test_decode_publishes_expected_raw_values(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            stub = work / "esphome/components/sensor/sensor.h"
            stub.parent.mkdir(parents=True)
            stub.write_text("""
#pragma once
#include <cmath>
namespace esphome { namespace sensor {
class Sensor {
 public:
  float state = 0;
  unsigned publications = 0;
  void publish_state(float value) { state = value; ++publications; }
};
}}
""")
            source = work / "test.cpp"
            source.write_text("""
#include "components/vitoconnect/sensor/vitoconnect_sensor.h"
#include <cassert>
#include <initializer_list>

void check(std::initializer_list<uint8_t> bytes, float expected) {
  esphome::vitoconnect::OPTOLINKSensor sensor;
  sensor.setLength(bytes.size());
  uint8_t data[4] = {};
  unsigned index = 0;
  for (auto byte : bytes) data[index++] = byte;
  sensor.decode(data, bytes.size());
  assert(sensor.publications == 1);
  assert(sensor.state == expected);
}

int main() {
  // Three-byte temperatures: raw values, before the configured multiply filter.
  check({0x79, 0x00, 0x40}, 121);
  check({0xB8, 0x01, 0x00}, 440);
  check({0x90, 0x01, 0x00}, 400);
  check({0x83, 0x01, 0x40}, 387);
  check({0x85, 0xFF, 0x00}, -123);
  check({0x85, 0xFF, 0x40}, -123);
  check({0x85, 0xFF, 0xFF}, -123);
  // Existing widths retain their unsigned/signed interpretation and byte order.
  check({0xFF}, 255);
  check({0xB8, 0x01}, 440);
  check({0x85, 0xFF}, -123);
  check({0x78, 0x56, 0x34, 0x12}, float(0x12345678u));
  check({0x00, 0x00, 0x00, 0x80}, float(0x80000000u));
}
""")
            executable = work / "test_sensor_decode"
            subprocess.run(
                [
                    "g++", "-std=c++11", "-I", str(work), "-I", str(ROOT),
                    str(source),
                    str(ROOT / "components/vitoconnect/sensor/vitoconnect_sensor.cpp"),
                    str(ROOT / "components/vitoconnect/vitoconnect_datapoint.cpp"),
                    "-o", str(executable),
                ],
                check=True, capture_output=True, text=True,
            )
            subprocess.run([str(executable)], check=True)
