# Product Requirement Document (PRD) - WALL-E AI Companion Robot

## 1. Project Vision & Objective
To build an interactive, autonomous, ultra-low-latency mini AI companion robot named **WALL-E**. The robot combines native multimodal streaming voice interaction, real-time camera vision, animated web-based OLED eye expressions, and 4-wheel differential motor movement into a compact desktop-friendly chassis, powered by Cloud LLM APIs (Google Gemini Multimodal Live API / Ollama Vision) and edge computing (Raspberry Pi 3B+ & ESP32).

---

## 2. Target Audience & Use Cases
- **Educational / Developer Demo:** Demonstrating dual-microcontroller (Master-Slave) robotics architecture with real-time bidirectional WebSocket streaming.
- **Personal AI Desktop Companion:** Autonomous conversational voice assistant that can answer questions, recognize objects via camera, remember user details, and drive on voice commands.
- **STEM & Robotics Enthusiasts:** Low-cost substitute for commercial companion robots using standard off-the-shelf components.

---

## 3. Key Functional Features

| Feature ID | Feature Name | Description |
| :--- | :--- | :--- |
| **FR-01** | **Direct Gemini Live Voice AI** | Full-duplex bidirectional streaming voice interaction using Google Gemini Multimodal Live API (`BidiGenerateContent`) over WebSockets with native 16kHz audio input and 24kHz audio output (`Puck` voice). Native barge-in/interrupt support. |
| **FR-02** | **Zero-Lag Camera Vision (`see_object`)** | Persistent warm `picamera2` capture with stale-frame purging. Multimodal analysis via dedicated REST API (Ollama Cloud / Gemini Flash) and live 160x120 thumbnail preview on ESP32 Web UI. |
| **FR-03** | **Dynamic OLED Visor & Web Dashboard** | ESP32 Soft-AP (`WALL-E_AP` @ `192.168.4.17`) hosting real-time animated CSS OLED visor eyes (`TALKING`, `LISTEN`, `THINK`, `HAPPY`, `ANGRY`, `SAD`, `NORMAL`), live camera thumbnails, and scrolling terminal serial console. |
| **FR-04** | **4-Wheel Differential Movement (`move_robot`)** | 4-channel DC motor drive via 74HC595 shift register and hardware PWM on L293D shield with safety auto-stop after 3 seconds (`MOTOR_RUN_MS 3000`). |
| **FR-05** | **Master-Slave Serial Protocol** | Thread-safe USB/Hardware UART communication (`/dev/ttyUSB0` @ 115200 Baud) with command dispatch (`FORWARD`, `BACKWARD`, `LEFT`, `RIGHT`, `STOP`, `EYES_*`, `IMG:*`, `IMG_CLEAR`). |
| **FR-06** | **Fast Autonomous Agent Tools** | Built-in tool calling: IP-cached live weather (Open-Meteo), parallel web search (DuckDuckGo + Wikipedia), live time/date, and persistent JSON long-term memory (`remember_fact`). |
| **FR-07** | **Ultra-Low RAM Footprint** | Headless architecture running in < 80 MB RAM on Raspberry Pi 3B+ (1GB RAM) with sub-100ms first-byte voice latency. |

---

## 4. Non-Functional Requirements
- **Latency:** End-to-end voice first-byte latency < 150ms (Mic PCM chunk -> Gemini Live WebSocket -> Speaker PCM stream).
- **Vision Speed:** Image capture to spoken scene description in < 1.5s via warm camera sensor and asynchronous REST call.
- **Power Autonomy:** Continuous runtime of 4 to 6 hours using 3S LiPo battery (11.1V 4500mAh) with dual buck conversion (5V logic, 6V motors).
- **Safety:** Automatic motor timeout (3s) on movement commands to prevent runaway robot.
- **Thermal & Resource Efficiency:** CPU usage kept under 25% on Raspberry Pi 3B+ during live listening.