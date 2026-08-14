/*
  WALL_E_ESP32_FAST.ino

  Optimized ESP32 firmware for low-latency UART command execution.

  Changes:
  - No Wi-Fi/web server in production loop.
  - Non-blocking byte-level UART parser.
  - No large String allocation for commands.
  - Long IMG: payloads are discarded safely.
  - Motor auto-stop remains.
*/

#define ENABLE_ACK 1
#define ENABLE_AUTO_STOP 1

#define MOTOR_SPEED 200
#define MOTOR_RUN_MS 3000

#define PWM_FREQ 1000
#define PWM_RES 8

#define MAX_CMD_LEN 64

// L293D motor shield shift register pins
#define DIR_CLK 16
#define DIR_EN 17
#define DIR_SER 5
#define DIR_LATCH 18

// Motor PWM pins
#define PWM_M1 19
#define PWM_M2 23
#define PWM_M3 25
#define PWM_M4 26

unsigned long motorStartTime = 0;
bool motorRunning = false;

char cmdBuf[MAX_CMD_LEN + 1];
uint16_t cmdLen = 0;
bool cmdOverflow = false;

char currentEyeState[24] = "IDLE";

void shiftWrite(uint8_t data) {
  digitalWrite(DIR_LATCH, LOW);
  shiftOut(DIR_SER, DIR_CLK, MSBFIRST, data);
  digitalWrite(DIR_LATCH, HIGH);
}

void setMotorSpeeds(uint8_t speed) {
  ledcWrite(PWM_M1, speed);
  ledcWrite(PWM_M2, speed);
  ledcWrite(PWM_M3, speed);
  ledcWrite(PWM_M4, speed);
}

void motorForward() {
  shiftWrite(0xD8);
  setMotorSpeeds(MOTOR_SPEED);
  motorStartTime = millis();
  motorRunning = true;
}

void motorBackward() {
  shiftWrite(0x27);
  setMotorSpeeds(MOTOR_SPEED);
  motorStartTime = millis();
  motorRunning = true;
}

void motorLeft() {
  shiftWrite(0xC6);
  setMotorSpeeds(MOTOR_SPEED);
  motorStartTime = millis();
  motorRunning = true;
}

void motorRight() {
  shiftWrite(0x39);
  setMotorSpeeds(MOTOR_SPEED);
  motorStartTime = millis();
  motorRunning = true;
}

void motorStop() {
  shiftWrite(0x00);
  setMotorSpeeds(0);
  motorRunning = false;
}

void setEyeState(const char *state) {
  strncpy(currentEyeState, state, sizeof(currentEyeState) - 1);
  currentEyeState[sizeof(currentEyeState) - 1] = '\0';
}

bool executeCommand(char *cmd) {
  if (cmd == nullptr || cmd[0] == '\0') {
    return false;
  }

  // Discard image payloads without allocating memory.
  if (strncmp(cmd, "IMG:", 4) == 0) {
    return false;
  }

  if (strcmp(cmd, "FORWARD") == 0) {
    motorForward();
    return true;
  }

  if (strcmp(cmd, "BACKWARD") == 0) {
    motorBackward();
    return true;
  }

  if (strcmp(cmd, "LEFT") == 0) {
    motorLeft();
    return true;
  }

  if (strcmp(cmd, "RIGHT") == 0) {
    motorRight();
    return true;
  }

  if (strcmp(cmd, "STOP") == 0) {
    motorStop();
    return true;
  }

  if (strcmp(cmd, "EYES_LISTEN") == 0 || strcmp(cmd, "LISTEN") == 0) {
    setEyeState("LISTEN");
    return true;
  }

  if (strcmp(cmd, "EYES_THINKING") == 0 || strcmp(cmd, "THINK") == 0) {
    setEyeState("THINK");
    return true;
  }

  if (strcmp(cmd, "EYES_TALKING") == 0 || strcmp(cmd, "SPEAK") == 0) {
    setEyeState("EYES_TALKING");
    return true;
  }

  if (strcmp(cmd, "EYES_NORMAL") == 0 || strcmp(cmd, "IDLE") == 0) {
    setEyeState("IDLE");
    return true;
  }

  if (strcmp(cmd, "HAPPY") == 0) {
    setEyeState("HAPPY");
    return true;
  }

  if (strcmp(cmd, "ANGRY") == 0) {
    setEyeState("ANGRY");
    return true;
  }

  if (strcmp(cmd, "SAD") == 0) {
    setEyeState("SAD");
    return true;
  }

  if (strcmp(cmd, "BOOT") == 0) {
    setEyeState("IDLE");
    return true;
  }

  return false;
}

void handleSerial() {
  while (Serial.available() > 0) {
    char c = static_cast<char>(Serial.read());

    if (c == '\n') {
      if (!cmdOverflow && cmdLen > 0) {
        cmdBuf[cmdLen] = '\0';

        bool ok = executeCommand(cmdBuf);

#if ENABLE_ACK
        if (ok) {
          Serial.print("ACK_");
          Serial.println(cmdBuf);
        }
#endif
      }

      cmdLen = 0;
      cmdOverflow = false;
    } else if (c == '\r') {
      // Ignore carriage return.
    } else {
      if (!cmdOverflow && cmdLen < MAX_CMD_LEN) {
        cmdBuf[cmdLen++] = c;
      } else {
        cmdOverflow = true;
      }
    }
  }
}

void setup() {
  Serial.setRxBufferSize(1024);
  Serial.begin(115200);

  pinMode(DIR_CLK, OUTPUT);
  pinMode(DIR_EN, OUTPUT);
  pinMode(DIR_SER, OUTPUT);
  pinMode(DIR_LATCH, OUTPUT);

  // Enable shift register outputs, active LOW.
  digitalWrite(DIR_EN, LOW);

  // Clear shift register.
  shiftWrite(0x00);

  ledcAttach(PWM_M1, PWM_FREQ, PWM_RES);
  ledcAttach(PWM_M2, PWM_FREQ, PWM_RES);
  ledcAttach(PWM_M3, PWM_FREQ, PWM_RES);
  ledcAttach(PWM_M4, PWM_FREQ, PWM_RES);

  setMotorSpeeds(0);

  Serial.println("BOOT WALL_E_FAST");
}

void loop() {
  handleSerial();

#if ENABLE_AUTO_STOP
  if (motorRunning && (millis() - motorStartTime >= MOTOR_RUN_MS)) {
    motorStop();
  }
#endif
}