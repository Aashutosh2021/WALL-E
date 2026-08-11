# Serial Communication Protocol (UART Specifications)

## 1. Physical Layer Configuration
- **Baud Rate:** `115200 bps`
- **Data Bits:** `8`
- **Parity:** `None`
- **Stop Bits:** `1`
- **Flow Control:** `None`
- **Delimiter:** Newline character (`\n` or `0x0A`)

---

## 2. Master Command Reference Table

Commands sent from Raspberry Pi to ESP32 over `/dev/serial0`:

| Command String | Target Subsystem | Action Performed | ESP32 OLED Response |
| :--- | :--- | :--- | :--- |
| `FORWARD\n` | Motors | Both motors rotate Forward at PWM 220 | Eyes: Normal |
| `BACKWARD\n` | Motors | Both motors rotate Backward at PWM 220 | Eyes: Normal |
| `LEFT\n` | Motors | Left motor Reverse, Right motor Forward | Eyes: Normal |
| `RIGHT\n` | Motors | Left motor Forward, Right motor Reverse | Eyes: Normal |
| `STOP\n` | Motors | All motor channels disabled (0 PWM) | Eyes: Normal |
| `EYES_LISTEN\n` | OLED Screen | None (Motors maintain state) | Eyes: Wide Awake / Listening |
| `EYES_THINKING\n`| OLED Screen | None (Motors maintain state) | Eyes: Narrowed / Thinking animation |
| `EYES_TALKING\n` | OLED Screen | None (Motors maintain state) | Eyes: Animated Blink / Speaking |
| `EYES_NORMAL\n`  | OLED Screen | None (Motors maintain state) | Eyes: Default WALL-E static eyes |