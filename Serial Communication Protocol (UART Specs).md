# Serial Communication Protocol (UART Specifications)

## 1. Physical Layer Configuration
- **Port:** `/dev/serial0` (default hardware serial) or `/dev/ttyUSB0` (configured via `SERIAL_PORT` in `.env`)
- **Baud Rate:** `115200 bps` or `9600 bps` (configured via `BAUD_RATE` in `.env`)
- **Data Bits:** `8` | **Parity:** `None` | **Stop Bits:** `1`
- **Flow Control:** `None`
- **Delimiter:** Newline character (`\n` or `0x0A`)
- **RX Buffer:** `4096 bytes` on ESP32 firmware for image frames
- **Architecture:** Persistent non-blocking connection in Python with background asynchronous reader thread (`_serial_reader`) to prevent command stalling and drain incoming `ACK_` / debug logs.

---

## 2. Master Command Reference Table

Commands transmitted from Raspberry Pi to ESP32 over serial:

| Command String | Category | Target Subsystem | Action Performed | Duration / Auto-stop | ESP32 Response |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `FORWARD\n` | Motion | 4x TT DC Motors | Shift Reg `0xD8` + PWM 200 | Auto-stops in **3.0s** (`MOTOR_RUN_MS 3000`) | `ACK_FORWARD` |
| `BACKWARD\n` | Motion | 4x TT DC Motors | Shift Reg `0x27` + PWM 200 | Auto-stops in **3.0s** (`MOTOR_RUN_MS 3000`) | `ACK_BACKWARD` |
| `LEFT\n` | Motion | 4x TT DC Motors | Shift Reg `0xC6` + PWM 200 | Auto-stops in **0.7s** (`TURN_RUN_MS 700`) | `ACK_LEFT` |
| `RIGHT\n` | Motion | 4x TT DC Motors | Shift Reg `0x39` + PWM 200 | Auto-stops in **0.7s** (`TURN_RUN_MS 700`) | `ACK_RIGHT` |
| `STOP\n` | Motion | 4x TT DC Motors | Shift Reg `0x00` + PWM 0 | Immediate Halt | `ACK_STOP` |
| `EYES_TALKING\n` / `SPEAK\n` | Visual | Web Visor Screen | Pulsing Green animation (Talking) | Continuous while AI speaks | `ACK_EYES_TALKING` |
| `LISTEN\n` | Visual | Web Visor Screen | Glowing Cyan wide eyes (Listening) | Set while user speaks | `ACK_LISTEN` |
| `EYES_THINKING\n` / `THINK\n` | Visual | Web Visor Screen | Pulsing Yellow glow (Tool executing) | Set during tool execution | `ACK_THINK` |
| `HAPPY\n` | Visual | Web Visor Screen | Curved Magenta Arcs | State switch | `ACK_HAPPY` |
| `ANGRY\n` | Visual | Web Visor Screen | Slanted Red Eyebrows | State switch | `ACK_ANGRY` |
| `SAD\n` | Visual | Web Visor Screen | Droopy Blue Eyes | State switch | `ACK_SAD` |
| `EYES_NORMAL\n` / `IDLE\n` | Visual | Web Visor Screen | Default Blue Visor | Idle state | `ACK_IDLE` |
| `BOOT\n` | Visual | Web Visor Screen | Resets state machine to IDLE | Startup | `ACK_BOOT` |
| `IMG:<base64_jpeg>\n` | Camera | Web UI Snapshot | Displays 160x120 live image thumbnail | Gated by `ENABLE_ESP32_IMAGE` | None |
| `IMG_CLEAR\n` | Camera | Web UI Snapshot | Clears live image thumbnail from Web UI | Sent upon turn completion | `ACK_IMG_CLEAR` |

---

## 3. Shift Register Bit Mapping (L293D Shield 74HC595)

The L293D motor shield directs 4 DC motors through an 8-bit shift register:

```
Bit 0: M4_A (Right Front Reverse)
Bit 1: M2_A (Left Rear Reverse)
Bit 2: M1_A (Left Front Reverse)
Bit 3: M1_B (Left Front Forward)
Bit 4: M2_B (Left Rear Forward)
Bit 5: M3_A (Right Rear Reverse)
Bit 6: M4_B (Right Front Forward)
Bit 7: M3_B (Right Rear Forward)
```

### Motor Direction Truth Table
- **FORWARD:** `M1_B | M2_B | M4_B | M3_B` -> Bits `3, 4, 6, 7` -> `0b11011000` = `0xD8`
- **BACKWARD:** `M1_A | M2_A | M3_A | M4_A` -> Bits `0, 1, 2, 5` -> `0b00100111` = `0x27`
- **LEFT SPIN:** `M1_A | M2_A | M3_B | M4_B` -> Bits `1, 2, 6, 7` -> `0b11000110` = `0xC6`
- **RIGHT SPIN:** `M1_B | M2_B | M3_A | M4_A` -> Bits `0, 3, 4, 5` -> `0b00111001` = `0x39`
- **STOP:** All bits 0 -> `0b00000000` = `0x00`

---

## 4. ESP32 Logging & Web API
- ESP32 maintains an in-memory circular buffer of the last 30 log lines (`MAX_LOGS = 30`).
- Web client polls `/getStatus` every 200ms receiving a delimiter-separated string: `STATE|||LOGS_HTML|||IMAGE_BASE64`.
- All commands received over UART produce timestamped serial logs and `ACK_<command>` responses.