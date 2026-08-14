# Technical Requirement Document (TRD) - WALL-E AI Companion Robot

## 1. System Architecture Overview
The system follows a **Master-Slave Hardware Architecture**:
- **Master ("The Brain"):** Raspberry Pi 3B+ (or Pi 4B) running Raspberry Pi OS Lite (64-bit). Manages full-duplex WebSocket streaming to Gemini Live API, persistent camera frame capture (`picamera2`), asynchronous tool execution, and local audio streaming.
- **Slave ("The Muscle & Display"):** ESP32 Dev Module running C++ Arduino firmware. Controls 4 DC motors using a 74HC595 shift register with hardware PWM speed control and hosts a standalone Wi-Fi Soft-AP web server for live CSS OLED eye expressions, camera previews, and debug logging.

---

## 2. Hardware Specifications

| Subsystem | Component | Operational Voltage | Current Peak | Interface |
| :--- | :--- | :--- | :--- | :--- |
| **Master Controller** | Raspberry Pi 3B+ (1GB RAM) | 5.0V Regulated | 2.0A | USB / CSI / Wi-Fi |
| **Slave Controller** | ESP32-WROOM-32 Dev Module | 5.0V (VIN) / 3.3V Logic | 250mA | UART Serial (`115200 Baud`) |
| **Camera Sensor** | OV5647 5MP CSI Pi Camera | 3.3V (via Ribbon) | 250mA | MIPI-CSI2 / `picamera2` |
| **Motor Driver** | L293D Dual H-Bridge Motor Shield | 5.0V (Logic) / 6.0V (Motors) | 2.0A Peak | 74HC595 Shift Register + PWM |
| **Motors** | 4x Yellow TT DC Gearbox Motors | 6.0V DC | 800mA (Stall) | L293D Outputs |
| **Main Battery** | 3S LiPo Battery (11.1V 4500mAh 30C) | 11.1V - 12.6V Nominal | 45A Discharge | XT60 Connector |
| **Voltage Regulators** | 2x LM2596 Step-Down Buck Modules | In: 11.1V -> Out: 5.0V & 6.0V | 3.0A per module | Common Ground |
| **Audio Input** | USB Plug-and-Play Microphone | 5.0V (USB) | 50mA | USB Audio / ALSA (16kHz PCM) |
| **Audio Output** | USB / 3.5mm Speaker with Amplifier | 5.0V (USB) | 500mA | PortAudio / SoundDevice (24kHz) |

---

## 3. Software Dependencies & Stack

### Master (Raspberry Pi 3B+)
- **Operating System:** Raspberry Pi OS Lite (64-bit Debian Bookworm)
- **Runtime:** Python 3.10+ / 3.11+
- **Core Libraries:**
  - `websockets` (Bidirectional raw WebSocket client for Gemini Multimodal Live API)
  - `sounddevice` & `numpy` (Low-latency audio streaming & zero-copy 24kHz to 48kHz resampling)
  - `picamera2` & `opencv-python` (Persistent warm camera pipeline & thumbnail generation)
  - `aiohttp` (Asynchronous connection-pooled HTTP client for vision REST and tool APIs)
  - `pyserial` (USB/UART serial communication with ESP32)
  - `orjson` / `json` (High-performance JSON serialization on WebSocket hot-path)

### Slave (ESP32)
- **Framework:** Arduino C++ (ESP32 Board Package v3.x)
- **Core Libraries:**
  - `WiFi.h` (Soft-AP Network Configuration: `WALL-E_AP` @ `192.168.4.17`)
  - `WebServer.h` (HTTP Server on port 80 hosting HTML5/CSS3 OLED eye visor & status API)

---

## 4. Memory & Performance Budget (Raspberry Pi 3B+ 1GB RAM)

```
Total Available Physical RAM: ~920 MB
├── Linux OS Kernel, Systemd & Networking:   ~65 MB
├── Python Runtime & Gemini Live WebSocket:   ~30 MB
├── picamera2 Persistent Camera Buffer:       ~25 MB
└── Active Audio Ingest/Playback Buffers:     ~10 MB
TOTAL RUNNING RAM USAGE:                      ~130 MB
FREE / CACHED RAM:                            ~790 MB (Zero Swapping)
```

---

## 5. Latency & Timing Specifications

| Pipeline Step | Target Latency | Actual Benchmark |
| :--- | :--- | :--- |
| **Mic Ingest (64ms Chunks)** | < 70ms | 64ms buffer |
| **Gemini Live First-Byte Audio (TTFT)** | < 100ms | 40ms – 70ms |
| **Speaker Audio Output (24kHz PCM)** | < 10ms | 5ms – 8ms |
| **Total Voice Turnaround** | **< 180ms** | **~110ms – 145ms** |
| **Warm Camera Capture (`picamera2`)** | < 60ms | ~45ms |
| **Vision REST API Call** | < 1200ms | ~350ms – 900ms |
| **UART Command Dispatch** | < 5ms | ~1ms – 3ms |