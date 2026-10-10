# MPU-6050 IMU Hardware Guide

## Wiring

| ESP32 Pin | GY-521 Pin | Signal |
|-----------|-----------|--------|
| 3V3       | VCC       | Power  |
| GND       | GND       | Ground |
| GPIO 21   | SDA       | I2C Data |
| GPIO 22   | SCL       | I2C Clock |

## Mounting Orientation

Mount the GY-521 board on the paper plane prop with the chip top face up and the printed X arrow pointing toward the plane's nose:

```
    Nose of plane
         ↑
         |
    +----+----+
    | X →    |  MPU-6050
    | Y ↙    |  (top face up)
    | Z ⊙    |
    +--------+
         |
       Wing
```

- **+X**: Forward (toward nose)
- **+Y**: Left
- **+Z**: Up

## Configuration & Rationale

- **Accelerometer**: ±16 g range (AFS_SEL=3, 2048 LSB/g)
  - Hand throws peak above 10 g; default ±2 g range clips
- **Gyro**: ±2000 °/s range (FS_SEL=3, 16.4 LSB/°/s)
  - Wrist flick produces fast rotation; ±500 °/s insufficient
- **Sample Rate**: 500 Hz (SMPLRT_DIV=1, DLPF_CFG=1)
  - Captures fast transients; 184 Hz bandwidth adequate for paper plane dynamics
- **I2C Speed**: 400 kHz (standard fast mode)

## Data Format

Each WebSocket message contains one batch of 25 samples (50 ms) as JSON:

```json
{
  "samples": [
    [t, ax, ay, az, gx, gy, gz],
    [t, ax, ay, az, gx, gy, gz],
    ...
  ]
}
```

- `t`: Seconds since board boot (float, 4 decimals)
- `ax, ay, az`: Acceleration in m/s² (float, 3 decimals)
  - At rest: +9.81 on the up axis (gravity is a specific force)
  - Raw value / 2048 * 9.80665 = m/s²
- `gx, gy, gz`: Angular velocity in rad/s (float, 3 decimals)
  - Bias-corrected (gyro bias averaged at boot for 1 second)
  - Raw value / 16.4 - bias_dps converted to rad/s

**Note**: Rows of 4 values are also accepted by the backend (t, ax, ay, az) without gyro.

## Flashing

### Arduino IDE

1. Install board support: Board Manager → "ESP32 by Espressif Systems"
2. Install libraries:
   - Sketch → Include Library → Manage Libraries
   - Search "WebSocketsClient" → Install "WebSockets by Links2004"
3. Select board: Tools → Board → ESP32 → "ESP32 Dev Module"
4. Set port: Tools → Port → "/dev/tty..."
5. Edit config: Set WIFI_SSID, WIFI_PASS, SERVER_HOST to your laptop's LAN IP
6. Upload: Sketch → Upload or Ctrl+U

### Arduino CLI

```bash
arduino-cli board install esp32:esp32
arduino-cli lib install "WebSockets"
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/mpu6050_streamer
arduino-cli upload -p /dev/ttyUSB0 --fqbn esp32:esp32:esp32 firmware/mpu6050_streamer
```

## Bench Test (5 Steps)

1. **At Rest (1 second)**: Board on table, no motion
   - LED blinks during calibration; Serial prints gyro bias
   - Backend should show zero acceleration except +9.81 on Z axis

2. **Gentle Throw**: Toss plane gently onto cushion
   - Monitor console for accelerometer peaks
   - Should see ~5–15 g depending on force

3. **Viewer Status**: Open `ws://HOST:8766/ws/throw` in a browser
   - Displays `throw` or `rejected` message with code
   - Codes: `no_rest` (board moved during calibration), `too_weak` (throw below threshold), `mount_angle` (wrong orientation), `straight_up` (vertical throw)

4. **Rotation Check**: Spin plane in hand while held still
   - Gyro axes should show reasonable rotation rates (~200–500 °/s)
   - No gyro output = I2C failure

5. **Recovery Check**: Let board settle 2–3 seconds after throw
   - Accelerometer should return to ~9.81 Z, zero X/Y
   - No recovery = calibration failed or board mounted upside down

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| **No samples received** | SDA/SCL swapped | Check wiring; verify LED blinks during setup |
| **Accelerometer clips at ±16 g** | Throw too hard | Reduce force or mounting angle |
| **Left/right reversed** | Board mounted upside down or rotated 90° | Rotate board so X arrow points to nose and top face up |
| **Mirrored values on one axis** | Single-axis flipped mounting | Re-orient board |
| **I2C timeout during calibration** | Address mismatch (MPU is at 0x69 when AD0=HIGH) | Check AD0 pin; soldering might pull it high |
| **WiFi fails** | Wrong SSID/password or out of range | Edit placeholders; check RSSI on Serial output |
| **WebSocket "connection refused"** | SERVER_HOST or SERVER_PORT wrong | Verify laptop LAN IP and backend port 8766 |

---

## Support

For issues, feedback, or contributions:
- Portfolio: https://ryyansafar.site
- Code: https://github.com/ryyansafar
- Support: https://buymeacoffee.com/ryyansafar
- PayPal: https://www.paypal.com/paypalme/ryyansafar
- Razorpay: https://razorpay.me/@ryyansafar
