# Pinout & Wiring Matrix

## 1. Power Distribution Network (PDN)

| Source                                    | Target Module          | Target Pin       | Voltage       |
| :---------------------------------------- | :--------------------- | :--------------- | :------------ |
| **3S LiPo (+)**                     | Main Toggle Switch     | In               | 11.1V - 12.6V |
| **Main Switch Out**                 | Buck Converter#1 Input | `IN+`          | 11.1V - 12.6V |
| **Main Switch Out**                 | Buck Converter#2 Input | `IN+`          | 11.1V - 12.6V |
| **3S LiPo (-)**                     | Buck#1 & #2 Common GND | `IN-`          | 0V (GND)      |
| **Buck #1 Output (Adjust to 5.0V)** | Raspberry Pi 3B+       | Pin 2 (`5V`)   | 5.0V DC       |
| **Buck #1 Output (Adjust to 5.0V)** | ESP32 Board            | Pin`VIN / 5V`  | 5.0V DC       |
| **Buck #2 Output (Adjust to 6.0V)** | L293D Motor Shield     | `EXT_PWR (+M)` | 6.0V DC       |

---

## 2. Hardware USB Serial Link (Pi 3B+ to ESP32)

#### 
    Connect ESP32 to Raspberry pi with USB Cable

## 3. OLED Display (0.96" SSD1306) to ESP32

| OLED Pin      | ESP32 Pin                      | Function  |
| :------------ | :----------------------------- | :-------- |
| **VCC** | **3.3V** or **5V** | Power     |
| **GND** | **GND**                  | Ground    |
| **SDA** | **GPIO 21**              | I2C Data  |
| **SCL** | **GPIO 22**              | I2C Clock |

---

## 4. L293D Motor Shield to ESP32 Header Jumper Wiring

| L293D Shield Header Pin              | ESP32 GPIO Pin    | Function                     |
| :----------------------------------- | :---------------- | :--------------------------- |
| **Digital Pin 4 (DIR_CLK)**    | **GPIO 16** | Shift Register Clock         |
| **Digital Pin 7 (DIR_EN)**     | **GPIO 17** | Shift Register Output Enable |
| **Digital Pin 8 (DIR_SER)**    | **GPIO 5**  | Shift Register Data          |
| **Digital Pin 12 (DIR_LATCH)** | **GPIO 18** | Shift Register Latch         |
| **Digital Pin 11 (PWM_L)**     | **GPIO 19** | Left Motor Speed             |
| **Digital Pin 3 (PWM_R)**      | **GPIO 23** | Right Motor Speed            |
