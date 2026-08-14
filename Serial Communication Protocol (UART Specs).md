# Serial Communication Protocol (UART Specifications)

## 1. Physical Layer Configuration
- **Port:** `/dev/ttyUSB0` (default) or `/dev/serial0` (configurable via `ESP32_PORT`)
- **Baud Rate:** `115200 bps`
- **Data Bits:** `8`
- **Parity:** `None`
- **Stop Bits:** `1`
- **Flow Control:** `None`
- **Delimiter:** Newline character (`\n` or `0x0A`)
- **RX Buffer:** `4096 bytes` (configured in ESP32 firmware for Base64 image frames)

---

## 2. Command Reference Table

Commands sent from Raspberry Pi to ESP32 over serial:

| Command String | Category | Target Subsystem | Action Performed | ESP32 Response |
| :--- | :--- | :--- | :--- | :--- |
| `FORWARD\n` | Motion | 4x TT DC Motors | Shift Reg `0xD8` + PWM 200 (Auto-stops in 3s) | `ACK_FORWARD` |
| `BACKWARD\n` | Motion | 4x TT DC Motors | Shift Reg `0x27` + PWM 200 (Auto-stops in 3s) | `ACK_BACKWARD` |
| `LEFT\n` | Motion | 4x TT DC Motors | Shift Reg `0xC6` + PWM 200 (Auto-stops in 3s) | `ACK_LEFT` |
| `RIGHT\n` | Motion | 4x TT DC Motors | Shift Reg `0x39` + PWM 200 (Auto-stops in 3s) | `ACK_RIGHT` |
| `STOP\n` | Motion | 4x TT DC Motors | Shift Reg `0x00` + PWM 0 (Immediate Halt) | `ACK_STOP` |
| `EYES_TALKING\n` / `SPEAK\n` | Visual | Web Visor Screen | Pulsing Green animation | `ACK_EYES_TALKING` |
| `LISTEN\n` | Visual | Web Visor Screen | Glowing Cyan wide eyes | `ACK_LISTEN` |
| `EYES_THINKING\n` / `THINK\n` | Visual | Web Visor Screen | Pulsing Yellow glow | `ACK_THINK` |
| `HAPPY\n` | Visual | Web Visor Screen | Curved Magenta Arcs | `ACK_HAPPY` |
| `ANGRY\n` | Visual | Web Visor Screen | Slanted Red Eyebrows | `ACK_ANGRY` |
| `SAD\n` | Visual | Web Visor Screen | Droopy Blue Eyes | `ACK_SAD` |
| `EYES_NORMAL\n` / `IDLE\n` | Visual | Web Visor Screen | Default Blue Eyes | `ACK_IDLE` |
| `BOOT\n` | Visual | Web Visor Screen | Resets eye state to IDLE | `ACK_BOOT` |
| `IMG:<base64_jpeg>\n` | Camera | Web UI Snapshot | Displays 160x120 live image thumbnail on Web UI | None |
| `IMG_CLEAR\n` | Camera | Web UI Snapshot | Clears live image thumbnail from Web UI | `ACK_IMG_CLEAR` |

---

## 3. Shift Register Bit Mapping (L293D Shield 74HC595)

```
M1_A = Bit 2, M1_B = Bit 3 (Left Front)
M2_A = Bit 1, M2_B = Bit 4 (Left Rear)
M3_A = Bit 5, M3_B = Bit 7 (Right Rear)
M4_A = Bit 0, M4_B = Bit 6 (Right Front)

FORWARD:  M1_B, M2_B, M3_B, M4_B -> bits 3,4,6,7 -> 0b11011000 = 0xD8
BACKWARD: M1_A, M2_A, M3_A, M4_A -> bits 0,1,2,5 -> 0b00100111 = 0x27
LEFT:     M1_A, M2_A (back), M3_B, M4_B (fwd)   -> bits 1,2,6,7 -> 0b11000110 = 0xC6
RIGHT:    M1_B, M2_B (fwd), M3_A, M4_A (back)   -> bits 0,3,4,5 -> 0b00111001 = 0x39
STOP:     All bits 0                            -> 0b00000000 = 0x00
```

---

## 4. ESP32 Logging & Web API
- ESP32 maintains a circular buffer of the last 30 log lines (`MAX_LOGS = 30`).
- Web client polls `/getStatus` every 200ms receiving a delimiter-separated string: `STATE|||LOGS_HTML|||IMAGE_BASE64`.
- All commands received over UART produce timestamped serial logs and `ACK_<command>` responses.