# System Architecture & Flowcharts

## 1. Block Diagram Architecture

                   [ 3S 11.1V LiPo Battery ]
                              │
     ┌────────────────────────┴────────────────────────┐
     ▼                                                 ▼
[ Buck Converter #1 (5.0V 3A) ]                 [ Buck Converter #2 (6.0V 2A) ]
│                                                 │
├───────────────────────┐                         │
▼                       ▼                         ▼
[ Raspberry Pi 3B+ ]      [ ESP32 Board ]       [ L293D Motor Shield ]
(Master Brain)            (Slave Driver)                 │
│                       │                         ▼
├── CSI Pi Camera              ├─ 0.96" OLED Eyes    [ 2x TT Motors ]
├── USB Microphone             │
└── Audio Amp / Speaker        └────── Hardware UART (/dev/serial0) ──────┘


---

## 2. Interaction Flowchart

   [ User Speaks into USB Mic ]
                │
                ▼
    [ Pi: SpeechRecognition ]
                │
                ▼
  [ Transcribed Text String ]
                │
                ▼
 [ Gemini 2.5 Flash AI Processing ]
                │
 ┌──────────────┴──────────────┐
 ▼                             ▼
[ Generated Text ]         [ Tool Triggered? ]
│                             │
▼                             ├─ Yes ──► Send "FORWARD\n" to Serial ──► [ ESP32 Motors Move ]
[ Edge-TTS Audio ]                 │
│                             └─ No ───► Send "EYES_TALKING\n" ───────► [ ESP32 Eyes Animate ]
▼
[ Audio Played on Speaker ]