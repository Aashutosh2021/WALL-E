#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// L293D Shift Register Pins
#define DIR_CLK   16
#define DIR_EN    17
#define DIR_SER   5
#define DIR_LATCH 18

// PWM Speed Pins
#define PWM_L     19
#define PWM_R     23  // GPIO 21 free for OLED SDA

void setup() {
  Serial.begin(115200);

  // Pin Configuration
  pinMode(DIR_CLK, OUTPUT);
  pinMode(DIR_EN, OUTPUT);
  pinMode(DIR_SER, OUTPUT);
  pinMode(DIR_LATCH, OUTPUT);
  pinMode(PWM_L, OUTPUT);
  pinMode(PWM_R, OUTPUT);

  digitalWrite(DIR_EN, LOW); // Enable L293D logic

  // OLED Initialization
  if(!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("OLED Allocation Failed"));
  } else {
    drawEyesNormal();
  }

  stopMotors();
  Serial.println("ESP32_READY");
}

void setMotorState(uint8_t state) {
  digitalWrite(DIR_LATCH, LOW);
  shiftOut(DIR_SER, DIR_CLK, MSBFIRST, state);
  digitalWrite(DIR_LATCH, HIGH);
  
  // Motor speed (0-255)
  analogWrite(PWM_L, 220);
  analogWrite(PWM_R, 220);
}

// Movement Controls
void moveForward()  { setMotorState(0b10100000); drawEyesNormal(); }
void moveBackward() { setMotorState(0b01010000); drawEyesNormal(); }
void turnLeft()     { setMotorState(0b01100000); drawEyesNormal(); }
void turnRight()    { setMotorState(0b10010000); drawEyesNormal(); }
void stopMotors()   { setMotorState(0b00000000); drawEyesNormal(); }

// WALL-E Animated Eyes
void drawEyesNormal() {
  display.clearDisplay();
  // Left Eye
  display.fillRoundRect(25, 15, 30, 35, 8, SSD1306_WHITE);
  // Right Eye
  display.fillRoundRect(73, 15, 30, 35, 8, SSD1306_WHITE);
  display.display();
}

void loop() {
  // Listen for commands from Raspberry Pi
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();

    if (command == "FORWARD") moveForward();
    else if (command == "BACKWARD") moveBackward();
    else if (command == "LEFT") turnLeft();
    else if (command == "RIGHT") turnRight();
    else if (command == "STOP") stopMotors();
  }
}