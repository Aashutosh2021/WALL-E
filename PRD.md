# Product Requirement Document (PRD) - WALL-E AI Companion Robot

## 1. Project Vision & Objective
To build an interactive, autonomous, low-cost mini AI companion robot named **WALL-E**. The robot combines natural multilingual voice interaction, real-time camera vision, animated OLED expressions, and differential motor movement into a compact desktop-friendly chassis, powered by Cloud LLM APIs (Google Gemini 2.5) and edge computing (Raspberry Pi 3B+ & ESP32).

---

## 2. Target Audience & Use Cases
- **Educational / Developer Demo:** Demonstrating dual-microcontroller (Master-Slave) robotics architecture.
- **Personal AI Desktop Companion:** Autonomous voice assistant that can answer questions, recognize objects via camera, and drive on commands.
- **STEM & Robotics Enthusiasts:** Low-cost substitute for expensive commercial desktop robots.

---

## 3. Key Functional Features

| Feature ID | Feature Name | Description |
| :--- | :--- | :--- |
| **FR-01** | **Multilingual Voice AI** | Conversational voice interaction using Google Gemini 2.5 Flash LLM with support for Hindi & English. |
| **FR-02** | **Computer Vision** | Real-time video feed via local web server and instant object detection using Pi Camera + Gemini Vision API. |
| **FR-03** | **Expressive OLED Eyes** | Dynamic eye expressions (Listening, Thinking, Speaking, Normal) on 0.96" SSD1306 OLED display. |
| **FR-04** | **Differential Movement** | 2-wheel/4-wheel motor drive (Forward, Backward, Left, Right, Stop) driven by ESP32 + L293D Shield. |
| **FR-05** | **Master-Slave Communication** | Zero-latency local Hardware UART Serial communication (`/dev/serial0` @ 115200 Baud). |
| **FR-06** | **Low RAM Footprint** | Headless OS setup running under 120 MB RAM footprint on Raspberry Pi 3B+ (1GB RAM). |

---

## 4. Non-Functional Requirements
- **Latency:** Voice response latency < 2.5 seconds (Speech-to-Text -> Gemini API -> Edge-TTS -> Speaker).
- **Power Autonomy:** Continuous runtime of 4 to 6 hours using 3S LiPo battery (4500mAh).
- **Safety:** Independent dual voltage regulation (LM2596 Buck Converters) preventing motor noise brownouts on Raspberry Pi.
- **Thermal Management:** CPU usage kept under 35% on Pi 3B+ during idle listening.