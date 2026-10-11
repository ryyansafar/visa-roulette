#include <WiFi.h>
#include <WebSocketsClient.h>
#include <Wire.h>

// Wiring: ESP32(3V3->GY-521 VCC, GND->GND, 21->SDA, 22->SCL); click switch between GPIO 13 and GND

#ifndef LED_BUILTIN
#define LED_BUILTIN 2
#endif

#ifndef M_PI
#define M_PI 3.141592653589793
#endif

// Copy secrets.example.h to secrets.h (git-ignored) and fill in the Wi-Fi and booth laptop address.
#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Missing secrets.h: copy secrets.example.h to secrets.h and fill it in."
#endif

const char* SERVER_HOST = SERVER_HOST_IP;
const int SERVER_PORT = 8766;
const char* WS_PATH = "/ws/imu";

const uint8_t MPU_ADDR = 0x68;
const uint8_t PWR_MGMT_1 = 0x6B;
const uint8_t ACCEL_CONFIG = 0x1C;
const uint8_t GYRO_CONFIG = 0x1B;
const uint8_t CONFIG = 0x1A;
const uint8_t SMPLRT_DIV = 0x19;
const uint8_t ACCEL_XOUT_H = 0x3B;

float gyro_bias_x, gyro_bias_y, gyro_bias_z;
const int CALIB_SAMPLES = 500;
const int BATCH_SIZE = 25;
const unsigned long SAMPLE_INTERVAL_US = 2000;

const uint8_t CLICK_PIN = 0;         // BOOT button on most ESP32 dev boards, active low
const uint8_t CLICK_PIN_EXT = 13;     // external push button between GPIO 13 and GND
const unsigned long CLICK_DEBOUNCE_MS = 40;
bool click_was_down = false;
unsigned long click_changed_ms = 0;

unsigned long boot_time_us, last_sample_us;
char json_buffer[2048];
int sample_count = 0;

struct Sample {
  float t, ax, ay, az, gx, gy, gz;
} samples[BATCH_SIZE];

WebSocketsClient webSocket;

void send_batch();
void poll_click();
void read_imu(int16_t& ax, int16_t& ay, int16_t& az, int16_t& gx, int16_t& gy, int16_t& gz);
void read_gyro(int16_t& gx, int16_t& gy, int16_t& gz);
void read_bytes(uint8_t reg, uint8_t* buf, int len);
void write_reg(uint8_t reg, uint8_t val);
void webSocketEvent(WStype_t type, uint8_t* payload, size_t length);

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\nVisa Roulette IMU Streamer");

  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(CLICK_PIN, INPUT_PULLUP);
  pinMode(CLICK_PIN_EXT, INPUT_PULLUP);
  Wire.begin(21, 22, 400000);
  delay(100);

  write_reg(PWR_MGMT_1, 0x01);
  write_reg(ACCEL_CONFIG, 0x18);
  write_reg(GYRO_CONFIG, 0x18);
  write_reg(CONFIG, 0x01);
  write_reg(SMPLRT_DIV, 0x01);
  delay(100);

  Serial.println("Calibrating gyro...");
  digitalWrite(LED_BUILTIN, HIGH);

  float sum_gx = 0, sum_gy = 0, sum_gz = 0;
  for (int i = 0; i < CALIB_SAMPLES; i++) {
    int16_t gx, gy, gz;
    read_gyro(gx, gy, gz);
    sum_gx += gx; sum_gy += gy; sum_gz += gz;
    delay(2);
  }

  gyro_bias_x = sum_gx / CALIB_SAMPLES / 16.4;
  gyro_bias_y = sum_gy / CALIB_SAMPLES / 16.4;
  gyro_bias_z = sum_gz / CALIB_SAMPLES / 16.4;
  digitalWrite(LED_BUILTIN, LOW);
  Serial.printf("Bias: %.3f, %.3f, %.3f DPS\n", gyro_bias_x, gyro_bias_y, gyro_bias_z);

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 20) {
    delay(500); Serial.print(".");
    retries++;
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? "\nWiFi OK" : "\nWiFi fail");

  webSocket.begin(SERVER_HOST, SERVER_PORT, WS_PATH);
  webSocket.onEvent(webSocketEvent);

  boot_time_us = micros();
  last_sample_us = boot_time_us;
}

void loop() {
  webSocket.loop();
  poll_click();

  unsigned long now_us = micros();
  if (now_us - last_sample_us >= SAMPLE_INTERVAL_US) {
    last_sample_us = now_us;

    int16_t ax_raw, ay_raw, az_raw, gx_raw, gy_raw, gz_raw;
    read_imu(ax_raw, ay_raw, az_raw, gx_raw, gy_raw, gz_raw);

    float t = (now_us - boot_time_us) / 1e6;
    samples[sample_count].t = t;
    samples[sample_count].ax = ax_raw / 2048.0 * 9.80665;
    samples[sample_count].ay = ay_raw / 2048.0 * 9.80665;
    samples[sample_count].az = az_raw / 2048.0 * 9.80665;
    samples[sample_count].gx = (gx_raw / 16.4 - gyro_bias_x) * M_PI / 180.0;
    samples[sample_count].gy = (gy_raw / 16.4 - gyro_bias_y) * M_PI / 180.0;
    samples[sample_count].gz = (gz_raw / 16.4 - gyro_bias_z) * M_PI / 180.0;

    if (++sample_count >= BATCH_SIZE) {
      send_batch();
      sample_count = 0;
    }
  }
}

void send_batch() {
  if (!webSocket.isConnected()) return;

  int offset = snprintf(json_buffer, sizeof(json_buffer), "{\"samples\":[");
  for (int i = 0; i < BATCH_SIZE; i++) {
    Sample& s = samples[i];
    offset += snprintf(json_buffer + offset, sizeof(json_buffer) - offset,
      "[%.4f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f]%s",
      s.t, s.ax, s.ay, s.az, s.gx, s.gy, s.gz,
      i < BATCH_SIZE - 1 ? "," : "");
  }
  snprintf(json_buffer + offset, sizeof(json_buffer) - offset, "]}");
  webSocket.sendTXT((uint8_t*)json_buffer, strlen(json_buffer));
}

void poll_click() {
  bool down = digitalRead(CLICK_PIN) == LOW || digitalRead(CLICK_PIN_EXT) == LOW;
  unsigned long now_ms = millis();
  if (down == click_was_down || now_ms - click_changed_ms < CLICK_DEBOUNCE_MS) return;
  click_was_down = down;
  click_changed_ms = now_ms;
  if (webSocket.isConnected()) webSocket.sendTXT(down ? "{\"button\":1}" : "{\"button\":0}");
}

void read_imu(int16_t& ax, int16_t& ay, int16_t& az, int16_t& gx, int16_t& gy, int16_t& gz) {
  uint8_t buf[14];
  read_bytes(ACCEL_XOUT_H, buf, 14);
  ax = (int16_t)((buf[0] << 8) | buf[1]);
  ay = (int16_t)((buf[2] << 8) | buf[3]);
  az = (int16_t)((buf[4] << 8) | buf[5]);
  gx = (int16_t)((buf[8] << 8) | buf[9]);
  gy = (int16_t)((buf[10] << 8) | buf[11]);
  gz = (int16_t)((buf[12] << 8) | buf[13]);
}

void read_gyro(int16_t& gx, int16_t& gy, int16_t& gz) {
  uint8_t buf[6];
  read_bytes(0x43, buf, 6);
  gx = (int16_t)((buf[0] << 8) | buf[1]);
  gy = (int16_t)((buf[2] << 8) | buf[3]);
  gz = (int16_t)((buf[4] << 8) | buf[5]);
}

void read_bytes(uint8_t reg, uint8_t* buf, int len) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.endTransmission(false);
  Wire.requestFrom(MPU_ADDR, (uint8_t)len);
  for (int i = 0; i < len; i++) buf[i] = Wire.read();
}

void write_reg(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission();
}

void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  if (type == WStype_CONNECTED) Serial.println("WS connected");
  else if (type == WStype_DISCONNECTED) Serial.println("WS disconnected");
}
