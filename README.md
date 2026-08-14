# 🤖 WALL-E — Autonomous AI Companion Robot

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-3B%2B%20%2F%204B-C51A4A?style=for-the-badge&logo=Raspberry-Pi&logoColor=white)](https://www.raspberrypi.com/)
[![ESP32](https://img.shields.io/badge/ESP32-Master--Slave-E7352C?style=for-the-badge&logo=espressif&logoColor=white)](https://www.espressif.com/)
[![Google Gemini](https://img.shields.io/badge/Google%20Gemini-Live%20Multimodal%20WebSocket-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white)](https://ai.google.dev/)
[![Ollama](https://img.shields.io/badge/Ollama-Cloud%20Vision-black?style=for-the-badge&logo=ollama&logoColor=white)](https://ollama.com/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

**WALL-E** is an ultra-low-latency, zero-lag, autonomous mini AI companion robot. It uses a **Raspberry Pi 3B+** as the primary master brain and an **ESP32 Dev Module** as the real-time motor controller and animated expression driver.

Driven by Google's **Gemini Multimodal Live API (`BidiGenerateContent`)** over raw WebSockets, WALL-E provides instant, human-like voice conversations (sub-100ms first-byte audio latency), real-time computer vision, animated web-based OLED eye expressions, differential motor movement, and autonomous agent tools.

---

## 🌟 Key Features

- ⚡ **Direct Gemini Multimodal Live API**: Full-duplex bidirectional streaming voice AI over WebSockets with native 16kHz PCM audio ingest and 24kHz speaker playback (`Puck` voice). Natural user barge-in/interruption supported out-of-the-box.
- 👁️ **Persistent Warm Camera Vision (`see_object`)**: `picamera2` stream kept warm in memory with stale-frame purging. Vision requests execute via asynchronous REST API calls with real-time thumbnail preview streaming to the ESP32 Web UI.
- 🤖 **4-Wheel Differential Drive (`move_robot`)**: 4-channel DC motor control via 74HC595 shift register and hardware PWM on L293D shield over 115200 Baud UART with automatic 3-second safety auto-stop.
- 📺 **Interactive ESP32 Web Dashboard & OLED Visor**: ESP32 Soft-AP (`WALL-E_AP` @ `http://xxx.xxx.xxx.xxx`) hosting real-time animated CSS OLED visor eyes (`TALKING`, `LISTEN`, `THINK`, `HAPPY`, `ANGRY`, `SAD`, `NORMAL`), live camera thumbnails, and scrolling serial console logs.
- 🌦️ **Autonomous Agent Tools**:
  - `get_weather`: Auto-detects location from public IP, caches coordinates, and fetches Open-Meteo forecasts in < 80ms.
  - `search_web`: Parallel DuckDuckGo and Wikipedia queries via `asyncio.gather`.
  - `get_time_info`: Live date, time, and weekday info.
  - `remember_fact`: Persistent JSON long-term memory (`memory.json`) auto-capped at 50 entries.
- 🪶 **Ultra-Low Memory Footprint (< 80 MB)**: Headless, optimized Python runtime tailored to run smoothly on Raspberry Pi 3B+ (1GB RAM) without overheating or freezing.

---

## 📐 System Architecture

### Master-Slave Hardware Architecture

```mermaid
graph TD
    A["3S 11.1V LiPo Battery"] --> B["Buck Converter #1 (5.0V 3A)"]
    A --> C["Buck Converter #2 (6.0V 2A)"]
    
    B --> D["Raspberry Pi 3B+ (Master Brain)"]
    B --> E["ESP32 Dev Module (Slave Controller)"]
    C --> F["L293D Motor Shield"]
    
    D -- "USB / UART Serial (/dev/ttyUSB0 @ 115200 Baud)" --> E
    D --> G["CSI Pi Camera (picamera2)"]
    D --> H["USB Microphone & Speaker (PortAudio)"]
    
    E --> I["Soft-AP Web UI (192.168.4.17)"]
    F --> J["4x TT Gearbox Motors"]
    E -- "74HC595 Shift Reg + PWM" --> F
```

---

## 🔄 Interaction Flowchart

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Pi as Raspberry Pi 3B+ (Master)
    participant Gemini as Gemini Multimodal Live (WebSocket)
    participant ESP32 as ESP32 (Slave Controller)
    
    User->>Pi: Speaks into USB Microphone (16kHz PCM Stream)
    Pi->>Gemini: realtimeInput (mediaChunks audio/pcm)
    Pi->>ESP32: Send UART "LISTEN\n"
    ESP32-->>ESP32: Visor Eyes -> LISTEN (Glowing Cyan)
    
    Gemini-->>Pi: serverContent (modelTurn audio/pcm 24kHz)
    Pi->>ESP32: Send UART "EYES_TALKING\n"
    ESP32-->>ESP32: Visor Eyes -> TALKING (Pulsing Green)
    Pi->>User: 24kHz Native Audio Output via Speaker
    
    opt Tool Call: move_robot("FORWARD")
        Gemini-->>Pi: toolCall -> move_robot(direction="FORWARD")
        Pi->>ESP32: Send UART "FORWARD\n"
        ESP32-->>ESP32: 74HC595 Shift Out (0xD8) + PWM 200 (Auto-stops in 3s)
        Pi->>Gemini: toolResponse ("WALL-E moving FORWARD.")
    end

    opt Tool Call: see_object("What do you see?")
        Gemini-->>Pi: toolCall -> see_object(prompt="...")
        Pi->>Pi: picamera2 grab fresh JPEG frame
        Pi->>ESP32: Send UART "IMG:<base64_thumbnail>\n"
        ESP32-->>ESP32: Web UI renders live camera snapshot
        Pi->>Pi: Asynchronous REST Vision API Call
        Pi->>Gemini: toolResponse (description text)
    end
    
    Gemini-->>Pi: turnComplete: true
    Pi->>ESP32: Send UART "EYES_NORMAL\n" & "IMG_CLEAR\n"
    ESP32-->>ESP32: Visor Eyes -> IDLE & Clear Web Thumbnail
```

---

## 🔌 Pinout & Wiring Matrix

### 1. Power Distribution Network (PDN)
| Source | Target Module | Target Pin | Voltage |
| :--- | :--- | :--- | :--- |
| **3S LiPo (+)** | Main Toggle Switch | In | 11.1V - 12.6V |
| **Buck #1 Output (Adjust to 5.0V)** | Raspberry Pi 3B+ | Pin 2 (`5V`) | 5.0V DC |
| **Buck #1 Output (Adjust to 5.0V)** | ESP32 Board | Pin `VIN / 5V` | 5.0V DC |
| **Buck #2 Output (Adjust to 6.0V)** | L293D Motor Shield | `EXT_PWR (+M)` | 6.0V DC |

### 2. ESP32 to L293D Motor Shield (74HC595 Shift Register & PWM)
| Signal Name | ESP32 GPIO | L293D Shield Function |
| :--- | :--- | :--- |
| **DIR_CLK** | `GPIO 16` | Shift Register Clock (Digital Pin 4) |
| **DIR_EN** | `GPIO 17` | Shift Register Enable / Active LOW (Digital Pin 7) |
| **DIR_SER** | `GPIO 5` | Shift Register Serial Data (Digital Pin 8) |
| **DIR_LATCH** | `GPIO 18` | Shift Register Latch (Digital Pin 12) |
| **PWM_M1** | `GPIO 19` | Motor 1 Speed PWM (D11) |
| **PWM_M2** | `GPIO 23` | Motor 2 Speed PWM (D3) |
| **PWM_M3** | `GPIO 25` | Motor 3 Speed PWM (D5) |
| **PWM_M4** | `GPIO 26` | Motor 4 Speed PWM (D6) |

---

## 📡 Serial Communication Protocol (UART Specs)

- **Baud Rate:** `115200 bps` | **Data Bits:** `8` | **Parity:** `None` | **Stop Bits:** `1`
- **Port:** `/dev/ttyUSB0` (or configured via `.env` as `ESP32_PORT`)
- **Delimiter:** Newline (`\n`)

| Command String | Category | Action Performed | ESP32 Response |
| :--- | :--- | :--- | :--- |
| `FORWARD\n` | Motor | 4 Motors Forward (PWM 200, 3s auto-stop) | `ACK_FORWARD` |
| `BACKWARD\n` | Motor | 4 Motors Backward (PWM 200, 3s auto-stop) | `ACK_BACKWARD` |
| `LEFT\n` | Motor | Spin Left (PWM 200, 3s auto-stop) | `ACK_LEFT` |
| `RIGHT\n` | Motor | Spin Right (PWM 200, 3s auto-stop) | `ACK_RIGHT` |
| `STOP\n` | Motor | Stop all motors immediately (PWM 0) | `ACK_STOP` |
| `EYES_TALKING\n` / `SPEAK\n` | Expression | Visor Eyes: Pulsing Green (Talking Animation) | `ACK_EYES_TALKING` |
| `LISTEN\n` | Expression | Visor Eyes: Glowing Cyan (Listening) | `ACK_LISTEN` |
| `EYES_THINKING\n` / `THINK\n` | Expression | Visor Eyes: Pulsing Yellow (Thinking) | `ACK_THINK` |
| `HAPPY\n` | Expression | Visor Eyes: Curved Magenta Arcs | `ACK_HAPPY` |
| `ANGRY\n` | Expression | Visor Eyes: Slanted Red Eyebrows | `ACK_ANGRY` |
| `SAD\n` | Expression | Visor Eyes: Droopy Blue Eyes | `ACK_SAD` |
| `EYES_NORMAL\n` / `IDLE\n` | Expression | Visor Eyes: Default Blue Visor | `ACK_IDLE` |
| `IMG:<base64>\n` | Camera | Sets live JPEG thumbnail on ESP32 Web UI | None |
| `IMG_CLEAR\n` | Camera | Clears JPEG thumbnail from ESP32 Web UI | `ACK_IMG_CLEAR` |

---

## 📁 Repository Directory Structure

```
WALL-E/
├── WALL_E_Voice_Assistant/
│   ├── main.py                   # Interactive Terminal Launcher & Diagnostics
│   ├── walle_direct_gemini.py    # Direct Gemini Multimodal Live WebSocket Client
│   ├── tools.py                  # Agent tools (move_robot, see_object, weather, search, memory)
│   ├── prompts.py                # System prompt, personality & identity rules
│   ├── memory.json               # Persistent long-term memory storage
│   └── .env                      # API keys & hardware configuration
├── WALL_E_ESP32/
│   └── WALL_E_ESP32.ino          # ESP32 C++ Firmware (74HC595 L293D + Soft-AP Web Dashboard)
├── PRD.md                        # Product Requirement Document
├── TRD.md                        # Technical Requirement Document
├── Pinout & Wiring Matrix.md     # Full Hardware Schematic & Wiring Guide
├── Serial Communication Protocol (UART Specs).md # UART Protocol Specification
├── System Architecture & Flowcharts.md # Architecture & sequence flowcharts
└── README.md                     # Main project guide
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites (Raspberry Pi OS 64-bit Lite)
Enable camera and serial hardware support:
```bash
sudo raspi-config
# Interface Options -> Camera -> Enable
# Interface Options -> Serial Port -> Enable Hardware Serial (/dev/ttyUSB0 or /dev/serial0)
```

### 2. Installation & Setup
```bash
cd ~
git clone https://github.com/Aashutosh2021/WALL-E.git
cd WALL-E/WALL_E_Voice_Assistant

# Create Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install websockets sounddevice numpy opencv-python aiohttp pyserial python-dotenv orjson picamera2
```

### 3. Configure Environment (`.env`)
Create or edit `.env` inside `WALL_E_Voice_Assistant/`:
```env
GOOGLE_API_KEY="AIzaSy..."
ROBOT_NAME="WALL-E"
USER_NAME="Aashutosh"
LAN="Hindi"
ESP32_PORT="/dev/ttyUSB0"
BAUD_RATE=115200

# Optional: Ollama Cloud Vision
OLLAMA_CLOUD_URL="https://ollama.com"
OLLAMA_API_KEY=""
OLLAMA_VISION_MODEL="gemma4:31b"
```

### 4. Flash ESP32 Firmware
Open `WALL_E_ESP32/WALL_E_ESP32.ino` in Arduino IDE, select **ESP32 Dev Module**, and upload.

### 5. Launch WALL-E Robot
```bash
cd ~/WALL-E/WALL_E_Voice_Assistant
source .venv/bin/activate
python3 main.py
```
Select **Option 1** (`⚡ Run WALL-E (Ultra-Low Latency Mode)`).

To view the live web visor and logs, connect your phone or laptop to Wi-Fi SSID `WALL-E_AP` (Password: `password123`) and open `http://192.168.4.17` in your browser.

---

## 👤 Author & Credits

- **Creator & Lead Developer:** [Aashutosh Kumar](https://github.com/Aashutosh2021)
- **Built For:** Real-Time Multimodal Robotics & Embedded AI
- **License:** MIT License
