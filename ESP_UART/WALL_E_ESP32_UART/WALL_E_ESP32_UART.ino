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
#define DIR_CLK    16
#define DIR_EN     17
#define DIR_SER     5
#define DIR_LATCH  18

// PWM Pins for motor speed (All 4 motors)
#define PWM_M1     19
#define PWM_M2     23
#define PWM_M3     25
#define PWM_M4     26

#define PWM_FREQ   1000
#define PWM_RES    8

// --- Motor Default Timing & Speeds ---
#define MOTOR_SPEED         200  // Straight speed (0-255)
#define TURN_SPEED          170  // Turning speed (0-255)
#define DEFAULT_MOVE_MS    2000  // Forward/Backward default time (2s)
#define DEFAULT_TURN_MS     450  // Left/Right ~90 degree turn time (450ms)

// --- Hardwired UART2 link to Raspberry Pi ---
#define PI_RX_PIN  4    // ESP32 RX <- Pi GPIO14 (Pin 8)
#define PI_TX_PIN  27   // ESP32 TX -> Pi GPIO15 (Pin 10)

// Dynamic Motor Auto-Stop Timer
unsigned long motorStartTime = 0;
unsigned long currentMotorDuration = 0;
bool motorRunning = false;

// --- System State & Circular Buffer for Logs ---
String currentEyeState = "IDLE";
String currentImageB64 = "";
const int MAX_LOGS = 20; // Reduced from 30 to keep RAM & AJAX fast
String logBuffer[MAX_LOGS];
int logIndex = 0;

void appendLog(String message) {
  unsigned long ms = millis();
  String timestamp = "[" + String(ms / 1000.0, 2) + "s] ";
  logBuffer[logIndex] = timestamp + message;
  logIndex = (logIndex + 1) % MAX_LOGS;
  Serial.println(timestamp + message);
}

// Clean out any non-printable UART noise bytes
String sanitizeCommand(String raw) {
  String clean = "";
  for (unsigned int i = 0; i < raw.length(); i++) {
    char c = raw.charAt(i);
    if (c >= 32 && c <= 126) { // Printable ASCII only
      clean += c;
    }
  }
  clean.trim();
  return clean;
}

void handleRoot() {
  String html = "<!DOCTYPE html><html><head>";
  html += "<title>WALL-E Hardware Debug & Eye Display</title>";
  html += "<meta name='viewport' content='width=device-width, initial-scale=1'>";
  html += "<style>";
  html += "body { font-family: 'Segoe UI', Arial, sans-serif; background-color: #121214; color: #f4f4f9; padding: 15px; margin: 0; }";
  html += ".container { max-width: 850px; margin: 0 auto; }";
  html += "h2 { color: #ff9f1c; text-align: center; margin-bottom: 15px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }";
  html += ".visor-box { background: #000; border: 3px solid #333; border-radius: 20px; padding: 25px; margin-bottom: 20px; box-shadow: 0 0 20px rgba(0,210,255,0.2); text-align: center; position: relative; }";
  html += ".eye-frame { display: flex; justify-content: center; align-items: center; gap: 40px; height: 130px; }";
  html += ".eye { width: 90px; height: 90px; background: #00d2ff; border-radius: 50%; box-shadow: 0 0 25px #00d2ff, inset 0 0 15px #fff; transition: all 0.2s ease-in-out; position: relative; }";
  html += ".eye-status-tag { margin-top: 15px; font-family: monospace; font-size: 1.1em; color: #ff9f1c; letter-spacing: 2px; }";
  html += "@keyframes talk { 0%, 100% { transform: scaleY(1); } 50% { transform: scaleY(0.3); } }";
  html += ".state-EYES_TALKING .eye, .state-SPEAK .eye { animation: talk 0.25s infinite alternate; background: #00ff88; box-shadow: 0 0 25px #00ff88; }";
  html += ".state-LISTEN .eye { transform: scale(1.15); background: #45f3ff; box-shadow: 0 0 35px #45f3ff; }";
  html += "@keyframes pulse { 0% { opacity: 0.3; } 100% { opacity: 1; } }";
  html += ".state-THINK .eye { animation: pulse 0.5s infinite alternate; background: #ffbe0b; box-shadow: 0 0 25px #ffbe0b; }";
  html += ".state-HAPPY .eye { border-radius: 50% 50% 15% 15%; transform: scaleY(0.8); background: #ff007f; box-shadow: 0 0 25px #ff007f; }";
  html += ".state-ANGRY .eye.left { transform: rotate(20deg) scaleY(0.7); background: #ff3333; box-shadow: 0 0 25px #ff3333; }";
  html += ".state-ANGRY .eye.right { transform: rotate(-20deg) scaleY(0.7); background: #ff3333; box-shadow: 0 0 25px #ff3333; }";
  html += ".state-SAD .eye.left { transform: rotate(-15deg) scaleY(0.7); background: #3a86ff; }";
  html += ".state-SAD .eye.right { transform: rotate(15deg) scaleY(0.7); background: #3a86ff; }";
  html += ".state-STOP .eye { background: #333; box-shadow: none; }";
  html += "#console { background-color: #0b0c10; border: 1px solid #1f242d; border-radius: 10px; padding: 15px; height: 300px; overflow-y: auto; font-family: 'Courier New', monospace; font-size: 0.9em; box-shadow: inset 0 0 10px rgba(0,0,0,0.8); }";
  html += ".log-entry { margin-bottom: 6px; line-height: 1.3; border-left: 3px solid #333; padding-left: 8px; }";
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
  html += "      document.getElementById('state-text').innerText = 'STATE: ' + state;";
  html += "      var imgContainer = document.getElementById('camera-preview');";
  html += "      if (imgB64.length > 0) {";
  html += "        imgContainer.innerHTML = \"<img src='data:image/jpeg;base64,\" + imgB64 + \"' style='width:160px; height:120px; border-radius:10px; border:2px solid #00d2ff; box-shadow: 0 0 15px rgba(0, 210, 255, 0.5);'>\";";
  html += "        imgContainer.style.display = 'block';";
  html += "      } else {";
  html += "        imgContainer.style.display = 'none';";
  html += "        imgContainer.innerHTML = '';";
  html += "      }";
  html += "      var el = document.getElementById('console');";
  html += "      var isScrolledToBottom = el.scrollHeight - el.clientHeight <= el.scrollTop + 2;";
  html += "      el.innerHTML = logsHtml;";
  html += "      if(isScrolledToBottom) { el.scrollTop = el.scrollHeight; }";
  html += "    }";
  html += "  };";
  html += "  xhttp.open('GET', '/getStatus', true);";
  html += "  xhttp.send();";
  html += "}, 250);";
  html += "</script></head><body><div class='container'>";
  html += "<h2>WALL-E AI Companion Screen Preview</h2>";
  html += "<div id='visor' class='visor-box state-IDLE'>";
  html += "  <div class='eye-frame'><div class='eye left'></div><div class='eye right'></div></div>";
  html += "  <div id='state-text' class='eye-status-tag'>STATE: IDLE</div>";
  html += "</div>";
  html += "<div id='camera-preview' style='display:none; text-align:center; margin-bottom:15px;'></div>";
  html += "<div id='console'>Initializing Console...</div>";
  html += "<footer style='text-align:center; margin-top:10px; color:#555; font-size:0.8em;'>ESP32 Live Screen Mirror | IP: 192.168.4.17</footer>";
  html += "</div></body></html>";
  server.send(200, "text/html", html);
}

void handleGetStatus() {
  String logsHtml = "";
  for (int i = 0; i < MAX_LOGS; i++) {
    int idx = (logIndex + i) % MAX_LOGS;
    if (logBuffer[idx].length() > 0) {
      String line = logBuffer[idx];
      if (line.indexOf("UART2 Rx:") != -1) {
        logsHtml += "<div class='log-entry cmd-in'>" + line + "</div>";
      } else if (line.indexOf("Executed:") != -1 || line.indexOf("Motor:") != -1) {
        logsHtml += "<div class='log-entry cmd-exec'>" + line + "</div>";
      } else {
        logsHtml += "<div class='log-entry sys-info'>" + line + "</div>";
      }
    }
  }
  String response = currentEyeState + "|||" + logsHtml + "|||" + currentImageB64;
  server.send(200, "text/plain", response);
}

void shiftWrite(uint8_t data) {
  digitalWrite(DIR_LATCH, LOW);
  shiftOut(DIR_SER, DIR_CLK, MSBFIRST, data);
  digitalWrite(DIR_LATCH, HIGH);
}

void setMotorSpeeds(int speed) {
  ledcWrite(PWM_M1, speed);
  ledcWrite(PWM_M2, speed);
  ledcWrite(PWM_M3, speed);
  ledcWrite(PWM_M4, speed);
}

void motorForward(unsigned long duration = DEFAULT_MOVE_MS, int speed = MOTOR_SPEED) {
  shiftWrite(0xD8);
  setMotorSpeeds(speed);
  currentMotorDuration = duration;
  motorStartTime = millis();
  motorRunning = true;
  appendLog("Motor: FORWARD (" + String(duration) + "ms)");
}

void motorBackward(unsigned long duration = DEFAULT_MOVE_MS, int speed = MOTOR_SPEED) {
  shiftWrite(0x27);
  setMotorSpeeds(speed);
  currentMotorDuration = duration;
  motorStartTime = millis();
  motorRunning = true;
  appendLog("Motor: BACKWARD (" + String(duration) + "ms)");
}

void motorLeft(unsigned long duration = DEFAULT_TURN_MS, int speed = TURN_SPEED) {
  shiftWrite(0xC6);
  setMotorSpeeds(speed);
  currentMotorDuration = duration;
  motorStartTime = millis();
  motorRunning = true;
  appendLog("Motor: LEFT turn (" + String(duration) + "ms)");
}

void motorRight(unsigned long duration = DEFAULT_TURN_MS, int speed = TURN_SPEED) {
  shiftWrite(0x39);
  setMotorSpeeds(speed);
  currentMotorDuration = duration;
  motorStartTime = millis();
  motorRunning = true;
  appendLog("Motor: RIGHT turn (" + String(duration) + "ms)");
}

void motorStop() {
  shiftWrite(0x00);
  setMotorSpeeds(0);
  motorRunning = false;
  appendLog("Motor: STOPPED");
}

void executeCommand(String cmd) {
  if (cmd.length() == 0) return;

  // 1. Handle Image Payload first (Before colon parser!)
  if (cmd.startsWith("IMG:")) {
    currentImageB64 = cmd.substring(4);
    appendLog("Executed: Camera Frame Updated");
    return;
  } else if (cmd == "IMG_CLEAR") {
    currentImageB64 = "";
    return;
  }

  // 2. Handle Packet Format -> DIRECTION:DURATION:SPEED (e.g., LEFT:450:170)
  int firstColon = cmd.indexOf(':');
  if (firstColon != -1) {
    String dir = cmd.substring(0, firstColon);
    dir.trim();
    int secondColon = cmd.indexOf(':', firstColon + 1);
    unsigned long dur = (dir == "LEFT" || dir == "RIGHT") ? DEFAULT_TURN_MS : DEFAULT_MOVE_MS;
    int spd = (dir == "LEFT" || dir == "RIGHT") ? TURN_SPEED : MOTOR_SPEED;

    if (secondColon != -1) {
      long parsedDur = cmd.substring(firstColon + 1, secondColon).toInt();
      int parsedSpd = cmd.substring(secondColon + 1).toInt();
      if (parsedDur > 0) dur = parsedDur;
      if (parsedSpd > 0) spd = constrain(parsedSpd, 0, 255);
    } else {
      long parsedDur = cmd.substring(firstColon + 1).toInt();
      if (parsedDur > 0) dur = parsedDur;
    }

    if (dir == "FORWARD") { motorForward(dur, spd); return; }
    else if (dir == "BACKWARD") { motorBackward(dur, spd); return; }
    else if (dir == "LEFT") { motorLeft(dur, spd); return; }
    else if (dir == "RIGHT") { motorRight(dur, spd); return; }
    else if (dir == "STOP") { motorStop(); return; }
  }

  // 3. Simple Motor Commands
  if (cmd == "FORWARD") { motorForward(); return; }
  else if (cmd == "BACKWARD") { motorBackward(); return; }
  else if (cmd == "LEFT") { motorLeft(); return; }
  else if (cmd == "RIGHT") { motorRight(); return; }
  else if (cmd == "STOP") { motorStop(); return; }

  // 4. Eye State Commands
  if (cmd == "EYES_TALKING" || cmd == "SPEAK") currentEyeState = "EYES_TALKING";
  else if (cmd == "EYES_NORMAL" || cmd == "IDLE") currentEyeState = "IDLE";
  else if (cmd == "EYES_THINKING" || cmd == "THINK") currentEyeState = "THINK";
  else if (cmd == "LISTEN") currentEyeState = "LISTEN";
  else if (cmd == "HAPPY") currentEyeState = "HAPPY";
  else if (cmd == "ANGRY") currentEyeState = "ANGRY";
  else if (cmd == "SAD") currentEyeState = "SAD";
  else if (cmd == "BOOT") currentEyeState = "IDLE";
  else {
    if (cmd.length() > 1) { // Ignore 1-char noise glitches
      appendLog("REJECTED unknown command -> '" + cmd + "'");
    }
    return;
  }

  appendLog("Executed: Eye State -> " + currentEyeState);
}

void setup() {
  Serial.begin(115200);

  Serial2.begin(9600, SERIAL_8N1, PI_RX_PIN, PI_TX_PIN);
  Serial2.setTimeout(35);
  Serial2.setRxBufferSize(4096);

  appendLog("System Booting Up...");

  pinMode(DIR_CLK, OUTPUT);
  pinMode(DIR_EN, OUTPUT);
  pinMode(DIR_SER, OUTPUT);
  pinMode(DIR_LATCH, OUTPUT);

  digitalWrite(DIR_EN, LOW);
  shiftWrite(0x00);

  ledcAttach(PWM_M1, PWM_FREQ, PWM_RES);
  ledcAttach(PWM_M2, PWM_FREQ, PWM_RES);
  ledcAttach(PWM_M3, PWM_FREQ, PWM_RES);
  ledcAttach(PWM_M4, PWM_FREQ, PWM_RES);
  setMotorSpeeds(0);

  appendLog("Motor Shield Initialized");

  WiFi.softAPConfig(local_IP, gateway, subnet);
  WiFi.softAP(ssid, password);

  appendLog("Soft-AP Live at http://192.168.4.17");

  server.on("/", handleRoot);
  server.on("/getStatus", handleGetStatus);
  server.begin();
}

void loop() {
  server.handleClient();

  // Dynamic auto-stop based on movement type (2000ms for move, 450ms for turn)
  if (motorRunning && (millis() - motorStartTime >= currentMotorDuration)) {
    motorStop();
  }

  // Read incoming commands from Raspberry Pi over UART2
  if (Serial2.available() > 0) {
    String rawCmd = Serial2.readStringUntil('\n');
    String incomingCmd = sanitizeCommand(rawCmd);

    if (incomingCmd.length() > 0) {
      if (incomingCmd.startsWith("IMG:")) {
        executeCommand(incomingCmd);
        Serial2.println("ACK_IMG"); // Fast ACK without echoing 4KB base64!
      } else {
        appendLog("UART2 Rx: Received command -> '" + incomingCmd + "'");
        executeCommand(incomingCmd);
        Serial2.println("ACK_" + incomingCmd);
      }
    }
  }
}
