# Product Requirement Document (PRD) - WALL-E AI Companion Robot

## 1. Project Vision & Objective
To build an interactive, autonomous, ultra-low-latency mini AI companion robot named **WALL-E**. The robot combines full-duplex multimodal streaming voice interaction, persistent warm camera vision, real-time animated web-based OLED eye expressions, differential 4-wheel motor drive, and persistent conversation memory into a compact desktop-friendly chassis, powered by Cloud LLM APIs (Google Gemini Multimodal Live API & Ollama Cloud Vision) and edge computing (Raspberry Pi 3B+ & ESP32).

---

## 2. Target Audience & Use Cases
- **Educational / Robotics Demo:** Demonstrates a dual-microcontroller (Master-Slave) edge robotics architecture with low-latency WebSockets and hardware UART links.
- **Personal AI Desktop Companion:** Autonomous conversational assistant that answers questions in Hindi/English/Hinglish, inspects and describes scenes via camera, auto-saves long-term user facts, and drives on voice commands.
- **STEM & DIY Robotics Enthusiasts:** Accessible, open-source reference design utilizing affordable standard hobbyist components (Raspberry Pi, ESP32, L293D shield, TT motors, CSI camera).

---

## 3. Key Functional Features

| Feature ID | Feature Name | Description |
| :--- | :--- | :--- |
| **FR-01** | **Direct Gemini Live Voice AI** | Full-duplex bidirectional streaming voice interaction using Google Gemini Multimodal Live API (`BidiGenerateContent`) over WebSockets. Ingests 16kHz PCM audio in 32ms/64ms chunks and outputs 24kHz native speech (`Puck` voice) with instant barge-in/interruption support. |
| **FR-02** | **Persistent Warm Vision (`see_object`)** | Persistent in-memory `picamera2` stream (320x240 RGB888) with stale-frame purging. Executes one-shot scene inspection via asynchronous REST API calls (Ollama Cloud Vision or Gemini 3.5 Flash) with optional live 160x120 thumbnail streaming to ESP32 Web UI. |
| **FR-03** | **Dynamic OLED Visor & Web Dashboard** | ESP32 Soft-AP (`WALL-E_AP` @ `http://192.168.4.17`) hosting real-time animated CSS OLED visor eyes (`TALKING`, `LISTEN`, `THINK`, `HAPPY`, `ANGRY`, `SAD`, `IDLE`), live camera preview container, and scrolling serial debug terminal (`/getStatus` AJAX polled every 200ms). |
| **FR-04** | **4-Wheel Differential Movement (`move_robot`)** | 4-channel DC motor drive via 74HC595 shift register and hardware PWM on L293D shield. Features calibrated per-command auto-stop: 3.0s for `FORWARD`/`BACKWARD` and 0.7s for `LEFT`/`RIGHT` spins. |
| **FR-05** | **Master-Slave Persistent Serial Protocol** | Thread-safe persistent UART serial link (`/dev/serial0` or `/dev/ttyUSB0`) with non-blocking background ACK/log reader thread for zero-latency command dispatch. |
| **FR-06** | **Persistent Conversation Memory** | SQLite WAL-mode database (`conversation_memory.py`) recording all timestamped user, assistant, and tool interactions, automatically formatting and injecting recent history into Gemini session instructions. |
| **FR-07** | **Autonomous Agent Tools** | High-speed tools: IP-cached live weather (Open-Meteo), parallel web search (DuckDuckGo + Wikipedia), live date/time info, and persistent user fact retention (`remember_fact` in `memory.json`). |
| **FR-08** | **Ultra-Low Resource Footprint** | Headless architecture running in < 80 MB RAM on Raspberry Pi 3B+ (1GB RAM) with sub-100ms first-byte voice latency. |

---

## 4. Non-Functional Requirements
- **Voice Turnaround Latency:** First-byte audio latency < 150ms from end of user utterance to speaker playback start.
- **Vision Latency:** Camera capture to spoken description turnaround < 1.2s.
- **Power Autonomy:** Continuous 4 to 6 hours runtime on 3S LiPo battery (11.1V 4500mAh) with dual buck conversion (5.0V logic, 6.0V motors).
- **Safety:** Automatic motor timeout (3.0s translation, 0.7s rotation) to prevent runaway conditions.
- **Thermal & Resource Efficiency:** CPU usage kept under 25% on Raspberry Pi 3B+ during live listening.