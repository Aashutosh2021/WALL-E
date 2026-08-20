# Pinout & Wiring Matrix — WALL-E AI Companion Robot

## 1. Power Distribution Network (PDN)

| Source | Target Module | Target Pin | Regulated Voltage | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **3S 11.1V LiPo Battery (+)** | Main Toggle Switch | Switch In | 11.1V - 12.6V | Master Battery Power |
| **Main Switch Output** | Buck Converter #1 (LM2596) | `IN+` | 11.1V - 12.6V | Logic Power Supply Input |
| **Main Switch Output** | Buck Converter #2 (LM2596) | `IN+` | 11.1V - 12.6V | Motor Power Supply Input |
| **3S LiPo Battery (-)** | Buck #1 & #2 Common GND | `IN-` | 0V (Common GND) | System Ground Reference |
| **Buck #1 Output (Adjust to 5.0V)** | Raspberry Pi 3B+ / 4B | Header Pin 2 / 4 (`5V`) | 5.0V DC (3A Max) | Pi Logic & Peripherals |
| **Buck #1 Output (Adjust to 5.0V)** | ESP32 Dev Board | Board Pin `VIN / 5V` | 5.0V DC | ESP32 Microcontroller Logic |
| **Buck #2 Output (Adjust to 6.0V)** | L293D Motor Shield | `EXT_PWR (+M)` Terminals | 6.0V DC (2A Max) | High-Current Motor Drive |

> ⚠️ **IMPORTANT:** All grounds (`GND`) across Battery, Buck #1, Buck #2, Raspberry Pi, ESP32, and Motor Shield **must be tied together** to establish a shared ground reference.

---

## 2. Serial Communication Link (Pi 3B+ to ESP32)

WALL-E supports two physical connection options between the Raspberry Pi and ESP32:

### Option A: USB Serial Connection (Default & Recommended)
Plug a micro-USB / Type-C cable directly from the **Raspberry Pi USB Port** into the **ESP32 USB Port**.
- **Port:** `/dev/ttyUSB0` or `/dev/serial0` (configured in `.env`)
- **Baud Rate:** `115200` or `9600` (matches `BAUD_RATE` in `.env`)

### Option B: Hardwired GPIO UART Link (`UART2`)
When utilizing direct jumper connections (as defined in `WALL_E_ESP32_UART.ino`):

| Raspberry Pi Pin | Pi Function | ESP32 Pin | ESP32 Function | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Header Pin 8** | `GPIO 14 (UART TXD0)` | **GPIO 4** | `PI_RX_PIN (UART2 RX)` | Pi TX -> ESP32 RX |
| **Header Pin 10** | `GPIO 15 (UART RXD0)` | **GPIO 27** | `PI_TX_PIN (UART2 TX)` | ESP32 TX -> Pi RX |
| **Header Pin 6** | `GND` | **GND** | `GND` | Common Ground Reference |

*(Note: ESP32 default UART2 pins GPIO 16 & 17 are reserved for the L293D shift register, so GPIO 4 & 27 are remapped for the Pi serial link).*

---

## 3. ESP32 to L293D Motor Shield Wiring Matrix

The L293D motor shield utilizes a **74HC595 8-bit shift register** for direction control and 4 dedicated PWM lines for motor speeds:

| L293D Shield Header Pin | ESP32 GPIO Pin | Function | Description |
| :--- | :--- | :--- | :--- |
| **DIR_CLK (Digital Pin 4)** | **GPIO 16** | Shift Register Clock | Clock pulse for shifting bits |
| **DIR_EN (Digital Pin 7)** | **GPIO 17** | Shift Register Output Enable | Active LOW enable |
| **DIR_SER (Digital Pin 8)** | **GPIO 5** | Shift Register Serial Data | Bitstream data input |
| **DIR_LATCH (Digital Pin 12)**| **GPIO 18** | Shift Register Latch | Latches 8 bits to motor outputs |
| **PWM_M1 (Digital Pin 11)** | **GPIO 19** | Motor 1 Speed (Left Front) | Hardware PWM (1000Hz, 8-bit) |
| **PWM_M2 (Digital Pin 3)** | **GPIO 23** | Motor 2 Speed (Left Rear) | Hardware PWM (1000Hz, 8-bit) |
| **PWM_M3 (Digital Pin 5)** | **GPIO 25** | Motor 3 Speed (Right Rear) | Hardware PWM (1000Hz, 8-bit) |
| **PWM_M4 (Digital Pin 6)** | **GPIO 26** | Motor 4 Speed (Right Front) | Hardware PWM (1000Hz, 8-bit) |
| **Shield GND** | **GND** | Logic Ground | Tied to ESP32 Ground |
| **Shield 5V** | **VIN (5V)** | Logic Supply | 5.0V from Buck Converter #1 |

---

## 4. Raspberry Pi Peripherals & Camera Setup

| Peripheral | Port / Interface | Configuration |
| :--- | :--- | :--- |
| **OV5647 5MP Camera** | MIPI-CSI Ribbon Connector | Persistent warm `picamera2` stream (320x240 RGB888) |
| **USB Microphone** | USB 2.0 Port (Pi 3B+) | 16000Hz Mono 16-bit PCM Audio Ingest |
| **USB / 3.5mm Speaker** | USB / 3.5mm Jack (Pi 3B+) | 24000Hz / 48000Hz Native Audio Output |
| **Wi-Fi Interface** | Onboard Broadcom BCM43438 | Connects to local Internet router for Cloud APIs |
