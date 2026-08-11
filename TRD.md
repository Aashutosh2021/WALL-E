# Technical Requirement Document (TRD) - WALL-E AI Companion Robot

## 1. System Architecture Overview
The system follows a **Master-Slave Hardware Architecture**:
- **Master ("The Brain"):** Raspberry Pi 3B+ running Raspberry Pi OS Lite (64-bit). Handles audio input/output, camera vision, network communication, and LLM reasoning.
- **Slave ("The Muscle"):** ESP32 Dev Board running C++ Arduino firmware. Handles real-time motor PWM output, L293D shift register control, and OLED screen rendering.

---

## 2. Hardware Specifications

| Subsystem | Component | Operational Voltage | Current Peak |
| :--- | :--- | :--- | :--- |
| **Master Board** | Raspberry Pi 3B+ (1GB RAM) | 5.0V Regulated | 2.0A |
| **Slave Board** | ESP32 Dev Module | 5.0V / 3.3V | 250mA |
| **Vision Input** | OV5647 5MP CSI Pi Camera | 3.3V (via Pi) | 250mA |
| **Motor Driver** | DK Electronics L293D Shield | 5.0V (Logic) / 6.0V (Motors) | 1.5A Peak |
| **Motors** | 2x - 4x Yellow TT Gearbox Motors | 6.0V DC | 800mA (Stall) |
| **Display** | 0.96" I2C SSD1306 OLED Screen | 3.3V DC | 20mA |
| **Main Power** | ZOP Power 3S LiPo (11.1V 4500mAh 30C) | 11.1V - 12.6V Nominal | 45A Max Discharge |
| **Voltage Regulators** | 2x LM2596 Buck Converters | Input: 11.1V -> Output: 5V & 6V | 3.0A per module |

---

## 3. Software Dependencies & Stack

### Master (Raspberry Pi 3B+)
- **OS:** Raspberry Pi OS Lite (64-bit Debian 12 Bookworm)
- **Runtime:** Python 3.11+
- **Key Libraries:**
  - `pyserial` (Hardware UART Communication)
  - `google-genai` (Gemini 2.5 Flash API)
  - `edge-tts` & `pygame` (Text-To-Speech Synthesis & Audio Playback)
  - `SpeechRecognition` & `PyAudio` (USB Mic Capture)
  - `opencv-python` & `picamera2` (Video capture & processing)
  - `flask` (Remote Web Stream & Controller)

### Slave (ESP32)
- **Framework:** Arduino C++ (ESP32 Board Package v2.0+)
- **Key Libraries:**
  - `Wire.h` (I2C Protocol for OLED)
  - `Adafruit_GFX.h` & `Adafruit_SSD1306.h` (Eye Animation Graphics)

---

## 4. Memory Budget (Raspberry Pi 3B+ 1GB RAM)

  Total Physical RAM: 920 MB (Available)
  ├── OS Kernel & NetworkManager: ~70 MB
  ├── Python Runtime & PySerial:  ~25 MB
  ├── OpenCV Camera Buffer:      ~35 MB
  └── Active LiveKit / LLM Thread: ~40 MB
  TOTAL IDLE RAM USED:            ~170 MB (Free RAM: ~750 MB)