#include <WebServer.h>
#include <WiFi.h>

// --- Network Configurations ---
const char *ssid = "WALL-E_AP";
const char *password = "password123";
IPAddress local_IP(192, 168, 4, 17);
IPAddress gateway(192, 168, 4, 1);
IPAddress subnet(255, 255, 255, 0);
WebServer server(80);

// --- L293D Motor Shield Shift Register Pins ---
#define DIR_CLK 16   // Shift Register Clock (Digital Pin 4 on shield)
#define DIR_EN 17    // Shift Register Output Enable (Digital Pin 7)
#define DIR_SER 5    // Shift Register Data (Digital Pin 8)
#define DIR_LATCH 18 // Shift Register Latch (Digital Pin 12)

// PWM Pins for motor speed (All 4 motors)
#define PWM_M1 19 // M1 PWM (D11)
#define PWM_M2 23 // M2 PWM (D3)
#define PWM_M3 25 // M3 PWM (D5)
#define PWM_M4 26 // M4 PWM (D6)

// PWM config
#define PWM_FREQ 1000
#define PWM_RES 8 // 8-bit resolution (0-255)

#define MOTOR_SPEED 200 // Default speed (0-255)

// --- Dynamic auto-stop durations ---
// Forward/backward need distance; left/right are angular spins and must be
// short.
#define MOTOR_RUN_MS 3000 // 3.0s for FORWARD / BACKWARD
#define TURN_RUN_MS 1500  // 0.7s for LEFT / RIGHT (~90° turn — CALIBRATE THIS)

// --- Hardwired UART2 link to Raspberry Pi ---
// GPIO16/17 (silkscreen RX2/TX2) are taken by the shift register,
// so the Pi link uses custom free pins.
#define PI_RX_PIN 4  // ESP32 RX  <- wire to Raspberry Pi GPIO14 (TXD, pin 8)
#define PI_TX_PIN 27 // ESP32 TX  -> wire to Raspberry Pi GPIO15 (RXD, pin 10)

// Motor auto-stop timer
unsigned long motorStartTime = 0;
unsigned long currentRunTime = MOTOR_RUN_MS; // per-command duration
bool motorRunning = false;

// --- System State & Circular Buffer for Logs ---
String currentEyeState = "IDLE";
String currentImageB64 = "";
const int MAX_LOGS = 30;
String logBuffer[MAX_LOGS];
int logIndex = 0;

// --- Non-blocking UART Parser State ---
#define MAX_CMD_LEN 128
char cmdBuf[MAX_CMD_LEN + 1];
uint16_t cmdLen = 0;

void appendLog(const char *message) {
  unsigned long ms = millis();
  String timestamp = "[" + String(ms / 1000.0, 2) + "s] ";
  logBuffer[logIndex] = timestamp + message;
  logIndex = (logIndex + 1) % MAX_LOGS;
  Serial.println(timestamp + message);
}

// --- HTML + CSS3 + Dynamic Eye Animations Page ---
void handleRoot() {
  String html = "<!DOCTYPE html><html><head>";
  html += "<title>WALL-E Hardware Debug & Eye Display</title>";
  html +=
      "<meta name='viewport' content='width=device-width, initial-scale=1'>";
  html += "<style>";
  html +=
      "body { font-family: 'Segoe UI', Arial, sans-serif; background-color: "
      "#121214; color: #f4f4f9; padding: 15px; margin: 0; }";
  html += ".container { max-width: 850px; margin: 0 auto; }";
  html += "h2 { color: #ff9f1c; text-align: center; margin-bottom: 15px; "
          "font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }";
  html +=
      ".visor-box { background: #000; border: 3px solid #333; border-radius: "
      "20px; padding: 25px; margin-bottom: 20px; box-shadow: 0 0 20px "
      "rgba(0,210,255,0.2); text-align: center; position: relative; }";
  html += ".eye-frame { display: flex; justify-content: center; align-items: "
          "center; gap: 40px; height: 130px; }";
  html += ".eye { width: 90px; height: 90px; background: #00d2ff; "
          "border-radius: 50%; box-shadow: 0 0 25px #00d2ff, inset 0 0 15px "
          "#fff; transition: all 0.2s ease-in-out; position: relative; }";
  html += ".eye-status-tag { margin-top: 15px; font-family: monospace; "
          "font-size: 1.1em; color: #ff9f1c; letter-spacing: 2px; }";
  html += "@keyframes talk { 0%, 100% { transform: scaleY(1); } 50% { "
          "transform: scaleY(0.3); } }";
  html += ".state-EYES_TALKING .eye, .state-SPEAK .eye { animation: talk 0.25s "
          "infinite alternate; background: #00ff88; box-shadow: 0 0 25px "
          "#00ff88; }";
  html += ".state-LISTEN .eye { transform: scale(1.15); background: #45f3ff; "
          "box-shadow: 0 0 35px #45f3ff; }";
  html += "@keyframes pulse { 0% { opacity: 0.3; } 100% { opacity: 1; } }";
  html += ".state-THINK .eye { animation: pulse 0.5s infinite alternate; "
          "background: #ffbe0b; box-shadow: 0 0 25px #ffbe0b; }";
  html += ".state-HAPPY .eye { border-radius: 50% 50% 15% 15%; transform: "
          "scaleY(0.8); background: #ff007f; box-shadow: 0 0 25px #ff007f; }";
  html += ".state-ANGRY .eye.left { transform: rotate(20deg) scaleY(0.7); "
          "background: #ff3333; box-shadow: 0 0 25px #ff3333; }";
  html += ".state-ANGRY .eye.right { transform: rotate(-20deg) scaleY(0.7); "
          "background: #ff3333; box-shadow: 0 0 25px #ff3333; }";
  html += ".state-SAD .eye.left { transform: rotate(-15deg) scaleY(0.7); "
          "background: #3a86ff; }";
  html += ".state-SAD .eye.right { transform: rotate(15deg) scaleY(0.7); "
          "background: #3a86ff; }";
  html += ".state-STOP .eye { background: #333; box-shadow: none; }";
  html += "#console { background-color: #0b0c10; border: 1px solid #1f242d; "
          "border-radius: 10px; padding: 15px; height: 300px; overflow-y: "
          "auto; font-family: 'Courier New', monospace; font-size: 0.9em; "
          "box-shadow: inset 0 0 10px rgba(0,0,0,0.8); }";
  html += ".log-entry { margin-bottom: 6px; line-height: 1.3; border-left: 3px "
          "solid #333; padding-left: 8px; }";
  html += ".cmd-in { color: #00ff88; border-color: #00ff88; }";
  html += ".cmd-exec { color: #ff9f1c; border-color: #ff9f1c; }";
  html += ".sys-info { color: #00d2ff; border-color: #00d2ff; }";
  html += "</style>";
  html += "<script>";
  html += "setInterval(function() {";
  html += "  var xhttp = new XMLHttpRequest();";
  html += "  xhttp.onreadystatechange = function() {";
  html += "    if (this.readyState == 4 && this.status == 200) {";
  html += "      var parts = this.responseText.split('|||');";
  html += "      var state = parts[0] ? parts[0].trim() : 'IDLE';";
  html += "      var logsHtml = parts.length > 1 ? parts[1] : '';";
  html += "      var imgB64 = parts.length > 2 ? parts[2].trim() : '';";
  html += "      var visor = document.getElementById('visor');";
  html += "      visor.className = 'visor-box state-' + state;";
  html += "      document.getElementById('state-text').innerText = 'STATE: ' + "
          "state;";
  html += "      var imgContainer = document.getElementById('camera-preview');";
  html += "      if (imgB64.length > 0) {";
  html += "        imgContainer.innerHTML = \"<img "
          "src='data:image/jpeg;base64,\" + imgB64 + \"' style='width:160px; "
          "height:120px; border-radius:10px; border:2px solid #00d2ff; "
          "box-shadow: 0 0 15px rgba(0, 210, 255, 0.5);'>\";";
  html += "        imgContainer.style.display = 'block';";
  html += "      } else {";
  html += "        imgContainer.style.display = 'none';";
  html += "        imgContainer.innerHTML = '';";
  html += "      }";
  html += "      var el = document.getElementById('console');";
  html += "      var isScrolledToBottom = el.scrollHeight - el.clientHeight <= "
          "el.scrollTop + 2;";
  html += "      el.innerHTML = logsHtml;";
  html += "      if(isScrolledToBottom) { el.scrollTop = el.scrollHeight; }";
  html += "    }";
  html += "  };";
  html += "  xhttp.open('GET', '/getStatus', true);";
  html += "  xhttp.send();";
  html += "}, 200);";
  html += "</script>";
  html += "</head><body><div class='container'>";
  html += "<h2>WALL-E AI Companion Screen Preview</h2>";
  html += "<div id='visor' class='visor-box state-IDLE'>";
  html += "  <div class='eye-frame'>";
  html += "    <div class='eye left'></div>";
  html += "    <div class='eye right'></div>";
  html += "  </div>";
  html += "  <div id='state-text' class='eye-status-tag'>STATE: IDLE</div>";
  html += "</div>";
  html += "<div id='camera-preview' style='display:none; text-align:center; "
          "margin-bottom:15px;'></div>";
  html += "<div id='console'>Initializing Console...</div>";
  html +=
      "<footer style='text-align:center; margin-top:10px; color:#555; "
      "font-size:0.8em;'>ESP32 Live Screen Mirror | IP: 192.168.4.17</footer>";
  html += "</div></body></html>";
  server.send(200, "text/html", html);
}

// --- Combined AJAX Status Endpoint (Eye State + Logs + Image) ---
void handleGetStatus() {
  String logsHtml = "";
  for (int i = 0; i < MAX_LOGS; i++) {
    int idx = (logIndex + i) % MAX_LOGS;
    if (logBuffer[idx].length() > 0) {
      String line = logBuffer[idx];
      if (line.indexOf("UART2 Rx:") != -1) {
        logsHtml += "<div class='log-entry cmd-in'>" + line + "</div>";
      } else if (line.indexOf("Executed:") != -1 ||
                 line.indexOf("Motor:") != -1) {
        logsHtml += "<div class='log-entry cmd-exec'>" + line + "</div>";
      } else {
        logsHtml += "<div class='log-entry sys-info'>" + line + "</div>";
      }
    }
  }
  // Delimiter-separated payload: STATE|||LOGS|||IMAGE
  String response =
      currentEyeState + "|||" + logsHtml + "|||" + currentImageB64;
  server.send(200, "text/plain", response);
}

// --- 74HC595 Shift Register Driver ---
void shiftWrite(uint8_t data) {
  digitalWrite(DIR_LATCH, LOW);
  shiftOut(DIR_SER, DIR_CLK, MSBFIRST, data);
  digitalWrite(DIR_LATCH, HIGH);
}

/*
 * Adafruit L293D Motor Shield v1 — Shift Register Bit Mapping:
 * FORWARD : 0xD8 | BACKWARD: 0x27 | LEFT: 0xC6 | RIGHT: 0x39
 */

void setMotorSpeeds(int speed) {
  ledcWrite(PWM_M1, speed);
  ledcWrite(PWM_M2, speed);
  ledcWrite(PWM_M3, speed);
  ledcWrite(PWM_M4, speed);
}

void motorForward() {
  shiftWrite(0xD8);
  setMotorSpeeds(MOTOR_SPEED);
  motorStartTime = millis();
  currentRunTime = MOTOR_RUN_MS; // 3.0s
  motorRunning = true;
  appendLog("Motor: FORWARD (3.0s)");
}

void motorBackward() {
  shiftWrite(0x27);
  setMotorSpeeds(MOTOR_SPEED);
  motorStartTime = millis();
  currentRunTime = MOTOR_RUN_MS; // 3.0s
  motorRunning = true;
  appendLog("Motor: BACKWARD (3.0s)");
}

void motorLeft() {
  shiftWrite(0xC6);
  setMotorSpeeds(MOTOR_SPEED);
  motorStartTime = millis();
  currentRunTime = TURN_RUN_MS; // 0.7s short spin
  motorRunning = true;
  appendLog("Motor: LEFT turn (0.7s)");
}

void motorRight() {
  shiftWrite(0x39);
  setMotorSpeeds(MOTOR_SPEED);
  motorStartTime = millis();
  currentRunTime = TURN_RUN_MS; // 0.7s short spin
  motorRunning = true;
  appendLog("Motor: RIGHT turn (0.7s)");
}

void motorStop() {
  shiftWrite(0x00);
  setMotorSpeeds(0);
  motorRunning = false;
  appendLog("Motor: STOPPED");
}

// --- Zero-allocation command execution using C-strings ---
void executeCommand(char *cmd) {
  // Motor commands
  if (strcmp(cmd, "FORWARD") == 0) {
    motorForward();
    return;
  }
  if (strcmp(cmd, "BACKWARD") == 0) {
    motorBackward();
    return;
  }
  if (strcmp(cmd, "LEFT") == 0) {
    motorLeft();
    return;
  }
  if (strcmp(cmd, "RIGHT") == 0) {
    motorRight();
    return;
  }
  if (strcmp(cmd, "STOP") == 0) {
    motorStop();
    return;
  }

  // Image commands
  if (strncmp(cmd, "IMG:", 4) == 0) {
    currentImageB64 = String(cmd + 4);
    return; // never log the base64 blob
  }
  if (strcmp(cmd, "IMG_CLEAR") == 0) {
    currentImageB64 = "";
    return;
  }

  // Eye state commands
  if (strcmp(cmd, "EYES_TALKING") == 0 || strcmp(cmd, "SPEAK") == 0) {
    currentEyeState = "EYES_TALKING";
  } else if (strcmp(cmd, "EYES_NORMAL") == 0 || strcmp(cmd, "IDLE") == 0) {
    currentEyeState = "IDLE";
  } else if (strcmp(cmd, "EYES_THINKING") == 0 || strcmp(cmd, "THINK") == 0) {
    currentEyeState = "THINK";
  } else if (strcmp(cmd, "LISTEN") == 0) {
    currentEyeState = "LISTEN";
  } else if (strcmp(cmd, "HAPPY") == 0) {
    currentEyeState = "HAPPY";
  } else if (strcmp(cmd, "ANGRY") == 0) {
    currentEyeState = "ANGRY";
  } else if (strcmp(cmd, "SAD") == 0) {
    currentEyeState = "SAD";
  } else if (strcmp(cmd, "BOOT") == 0) {
    currentEyeState = "IDLE";
  } else {
    // Unmatched command — UART corruption/noise. Log as REJECTED, not Executed.
    String msg = "REJECTED unknown/corrupt command -> '";
    msg += cmd;
    msg += "'";
    appendLog(msg.c_str());
    return;
  }

  String msg = "Executed: Eye Display -> ";
  msg += cmd;
  appendLog(msg.c_str());
}

// --- Non-blocking byte-level UART parser (never stalls the loop) ---
void handleUART() {
  while (Serial2.available() > 0) {
    char c = Serial2.read();

    if (c == '\n') {
      cmdBuf[cmdLen] = '\0';
      if (cmdLen > 0) {
        String rx = "UART2 Rx: '";
        rx += cmdBuf;
        rx += "'";
        appendLog(rx.c_str());

        executeCommand(cmdBuf);

        // ACK back to Pi
        Serial2.print("ACK_");
        Serial2.println(cmdBuf);
      }
      cmdLen = 0;
    } else if (c != '\r') {
      if (cmdLen < MAX_CMD_LEN) {
        cmdBuf[cmdLen++] = c;
      } else {
        cmdLen = 0; // Overflow protection — discard and resync
      }
    }
  }
}

void setup() {
  // Serial0 (USB) — programming/debug ONLY. Pi link is on Serial2.
  Serial.begin(115200);

  // Hardwired UART2 to Raspberry Pi @ 115200 for low latency
  Serial2.begin(115200, SERIAL_8N1, PI_RX_PIN, PI_TX_PIN);
  Serial2.setRxBufferSize(4096);

  appendLog("System Booting Up...");

  // --- Initialize L293D Motor Shield Shift Register Pins ---
  pinMode(DIR_CLK, OUTPUT);
  pinMode(DIR_EN, OUTPUT);
  pinMode(DIR_SER, OUTPUT);
  pinMode(DIR_LATCH, OUTPUT);

  // Enable shift register outputs (active LOW)
  digitalWrite(DIR_EN, LOW);

  // Clear shift register — all motors off
  shiftWrite(0x00);

  // --- Initialize PWM (ESP32 Arduino Core v3.x API) ---
  ledcAttach(PWM_M1, PWM_FREQ, PWM_RES);
  ledcAttach(PWM_M2, PWM_FREQ, PWM_RES);
  ledcAttach(PWM_M3, PWM_FREQ, PWM_RES);
  ledcAttach(PWM_M4, PWM_FREQ, PWM_RES);
  setMotorSpeeds(0);

  appendLog("Motor Shield initialized (Shift Register + PWM)");

  // Setup Soft Access Point + Web Dashboard
  WiFi.softAPConfig(local_IP, gateway, subnet);
  WiFi.softAP(ssid, password);
  appendLog("Soft-AP Started. SSID: WALL-E_AP");
  appendLog("Web Server Live at http://192.168.4.17");

  server.on("/", handleRoot);
  server.on("/getStatus", handleGetStatus);
  server.begin();
}

void loop() {
  server.handleClient();

  // --- Dynamic auto-stop: uses per-command duration ---
  if (motorRunning && (millis() - motorStartTime >= currentRunTime)) {
    motorStop();
  }

  // Read incoming commands from Raspberry Pi (hardwired UART2)
  handleUART();
}