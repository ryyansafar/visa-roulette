#!/bin/sh
# Flash the MPU-6050 streamer to a plugged-in ESP32, then watch its serial output.
# Needs firmware/mpu6050_streamer/secrets.h (copy secrets.example.h and fill it in).
set -e
cd "$(dirname "$0")/../firmware/mpu6050_streamer"
[ -f secrets.h ] || { echo "Missing secrets.h - run: cp secrets.example.h secrets.h  and fill in Wi-Fi + this laptop's IP"; exit 1; }
PORT="${1:-$(ls /dev/cu.usbserial-* /dev/cu.SLAB_USBtoUART* /dev/cu.wchusbserial* 2>/dev/null | head -1)}"
[ -n "$PORT" ] || { echo "No ESP32 serial port found. Plug it in with a data USB cable."; exit 1; }
echo "Flashing to $PORT"
arduino-cli compile --fqbn esp32:esp32:esp32 .
arduino-cli upload -p "$PORT" --fqbn esp32:esp32:esp32 .
echo "Serial monitor (Ctrl-C to stop). Expect: Bias..., WiFi OK, WS connected"
arduino-cli monitor -p "$PORT" -c baudrate=115200
