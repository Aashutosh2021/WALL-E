#include <WebServer.h>
#include <WiFi.h>

// --- Network Configurations ---
const char *ssid = "WALL-E_AP";       // ESP32 Access Point Name
const char *password = "password123"; // AP Password (Min 8 chars)

// Static IP Configuration
IPAddress local_IP(192, 168, 4, 17);
IPAddress gateway(192, 168, 4, 1);
IPAddress subnet(255, 255, 255, 0);

WebServer server(80);

// --- L293D Motor Shield Shift Register Pins ---
// 74HC595 shift register controls motor direction on the L293D shield
#define DIR_CLK    16   // Shift Register Clock (Digital Pin 4 on shield)
#define DIR_EN     17   // Shift Register Output Enable (Digital Pin 7)
#define DIR_SER     5   // Shift Register Data (Digital Pin 8)
#define DIR_LATCH  18   // Shift Register Latch (Digital Pin 12)

// PWM Pins for motor speed (All 4 motors)
#define PWM_M1     19   // M1 PWM (D11)
#define PWM_M2     23   // M2 PWM (D3)
#define PWM_M3     25   // M3 PWM (D5)
#define PWM_M4     26   // M4 PWM (D6)

// PWM config
#define PWM_FREQ   1000
#define PWM_RES    8     // 8-bit resolution (0-255)

#define MOTOR_SPEED 200  // Default speed (0-255)
#define MOTOR_RUN_MS 3000 // Auto-stop after 3 seconds

// Motor auto-stop timer
unsigned long motorStartTime = 0;
bool motorRunning = false;

// --- System State & Circular Buffer for Logs ---
String currentEyeState = "IDLE"; // Track current visual eye state
String currentImageB64 = ""; // Base64 thumbnail string for web UI
const int MAX_LOGS = 30;
String logBuffer[MAX_LOGS];
int logIndex = 0;

void appendLog(String message) {
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

  // --- OLED Head Visor & Eye CSS Styles ---
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

  // --- Dynamic CSS State Animations ---
  // 1. TALKING / SPEAK Animation (Pulsing height)
  html += "@keyframes talk { 0%, 100% { transform: scaleY(1); } 50% { "
          "transform: scaleY(0.3); } }";
  html += ".state-EYES_TALKING .eye, .state-SPEAK .eye { animation: talk 0.25s "
          "infinite alternate; background: #00ff88; box-shadow: 0 0 25px "
          "#00ff88; }";

  // 2. LISTEN Animation (Wide glowing eyes)
  html += ".state-LISTEN .eye { transform: scale(1.15); background: #45f3ff; "
          "box-shadow: 0 0 35px #45f3ff; }";

  // 3. THINK Animation (Pulse glow)
  html += "@keyframes pulse { 0% { opacity: 0.3; } 100% { opacity: 1; } }";
  html += ".state-THINK .eye { animation: pulse 0.5s infinite alternate; "
          "background: #ffbe0b; box-shadow: 0 0 25px #ffbe0b; }";

  // 4. HAPPY Animation (Curved Arcs)
  html += ".state-HAPPY .eye { border-radius: 50% 50% 15% 15%; transform: "
          "scaleY(0.8); background: #ff007f; box-shadow: 0 0 25px #ff007f; }";

  // 5. ANGRY Animation (Slanted Eyebrows)
  html += ".state-ANGRY .eye.left { transform: rotate(20deg) scaleY(0.7); "
          "background: #ff3333; box-shadow: 0 0 25px #ff3333; }";
  html += ".state-ANGRY .eye.right { transform: rotate(-20deg) scaleY(0.7); "
          "background: #ff3333; box-shadow: 0 0 25px #ff3333; }";

  // 6. SAD Animation (Droopy Eyes)
  html += ".state-SAD .eye.left { transform: rotate(-15deg) scaleY(0.7); "
          "background: #3a86ff; }";
  html += ".state-SAD .eye.right { transform: rotate(15deg) scaleY(0.7); "
          "background: #3a86ff; }";

  // 7. STOP / BOOT
  html += ".state-STOP .eye { background: #333; box-shadow: none; }";

  // --- Terminal Console CSS ---
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

  // --- AJAX Auto-Refresh Script ---
  html += "<script>";
  html += "setInterval(function() {";
  html += "  var xhttp = new XMLHttpRequest();";
  html += "  xhttp.onreadystatechange = function() {";
  html += "    if (this.readyState == 4 && this.status == 200) {";
  html += "      var parts = this.responseText.split('|||');";
  html += "      var state = parts[0] ? parts[0].trim() : 'IDLE';";
  html += "      var logsHtml = parts.length > 1 ? parts[1] : '';";
  html += "      var imgB64 = parts.length > 2 ? parts[2].trim() : '';";

  // Update Eye Screen CSS Class dynamically
  html += "      var visor = document.getElementById('visor');";
  html += "      visor.className = 'visor-box state-' + state;";
  html += "      document.getElementById('state-text').innerText = 'STATE: ' + state;";

  // Update Camera Preview Image
  html += "      var imgContainer = document.getElementById('camera-preview');";
  html += "      if (imgB64.length > 0) {";
  html += "        imgContainer.innerHTML = \"<img src='data:image/jpeg;base64,\" + imgB64 + \"' style='width:160px; height:120px; border-radius:10px; border:2px solid #00d2ff; box-shadow: 0 0 15px rgba(0, 210, 255, 0.5);'>\";";
  html += "        imgContainer.style.display = 'block';";
  html += "      } else {";
  html += "        imgContainer.style.display = 'none';";
  html += "        imgContainer.innerHTML = '';";
  html += "      }";

  // Update Console Logs
  html += "      var el = document.getElementById('console');";
  html += "      var isScrolledToBottom = el.scrollHeight - el.clientHeight <= el.scrollTop + 2;";
  html += "      el.innerHTML = logsHtml;";
  html += "      if(isScrolledToBottom) { el.scrollTop = el.scrollHeight; }";
  html += "    }";
  html += "  };";
  html += "  xhttp.open('GET', '/getStatus', true);";
  html += "  xhttp.send();";
  html += "}, 200);"; // Fast 200ms polling for smooth eye state switching
  html += "</script>";

  html += "</head><body><div class='container'>";
  html += "<h2>WALL-E AI Companion Screen Preview</h2>";

  // OLED Visor Screen Markup
  html += "<div id='visor' class='visor-box state-IDLE'>";
  html += "  <div class='eye-frame'>";
  html += "    <div class='eye left'></div>";
  html += "    <div class='eye right'></div>";
  html += "  </div>";
  html += "  <div id='state-text' class='eye-status-tag'>STATE: IDLE</div>";
  html += "</div>";

  // Camera Preview Container (Hidden by default)
  html += "<div id='camera-preview' style='display:none; text-align:center; margin-bottom:15px;'></div>";

  // Terminal Console Markup
  html += "<div id='console'>Initializing Console...</div>";
  html +=
      "<footer style='text-align:center; margin-top:10px; color:#555; "
      "font-size:0.8em;'>ESP32 Live Screen Mirror | IP: 192.168.4.17</footer>";
  html += "</div></body></html>";

  server.send(200, "text/html", html);
}

// --- Combined AJAX Status Endpoint (Eye State + Logs) ---
void handleGetStatus() {
  String logsHtml = "";
  for (int i = 0; i < MAX_LOGS; i++) {
    int idx = (logIndex + i) % MAX_LOGS;
    if (logBuffer[idx].length() > 0) {
      String line = logBuffer[idx];
      if (line.indexOf("USB Rx:") != -1) {
        logsHtml += "<div class='log-entry cmd-in'>" + line + "</div>";
      } else if (line.indexOf("Executed:") != -1) {
        logsHtml += "<div class='log-entry cmd-exec'>" + line + "</div>";
      } else {
        logsHtml += "<div class='log-entry sys-info'>" + line + "</div>";
      }
    }
  }

  // Send Delimiter separated string: STATE|||LOGS|||IMAGE
  String response = currentEyeState + "|||" + logsHtml + "|||" + currentImageB64;
  server.send(200, "text/plain", response);
}

// --- 74HC595 Shift Register Driver ---
void shiftWrite(uint8_t data) {
  // Latch LOW to start shifting
  digitalWrite(DIR_LATCH, LOW);
  
  // Use built-in shiftOut for reliable timing
  shiftOut(DIR_SER, DIR_CLK, MSBFIRST, data);
  
  // Latch HIGH to push data to output pins
  digitalWrite(DIR_LATCH, HIGH);
}

/*
 * Adafruit L293D Motor Shield v1 — Shift Register Bit Mapping (from Motortest.ino):
 * 
 * M1_A = 2, M1_B = 3
 * M2_A = 1, M2_B = 4
 * M3_A = 5, M3_B = 7
 * M4_A = 0, M4_B = 6
 * 
 * Left side: M1 & M2. Right side: M3 & M4
 * 
 * FORWARD: M1_B, M2_B, M3_B, M4_B -> bits 3,4,6,7 -> 0b11011000 = 0xD8
 * BACKWARD: M1_A, M2_A, M3_A, M4_A -> bits 0,1,2,5 -> 0b00100111 = 0x27
 * LEFT: M1_A, M2_A (back), M3_B, M4_B (fwd) -> bits 1,2,6,7 -> 0b11000110 = 0xC6
 * RIGHT: M1_B, M2_B (fwd), M3_A, M4_A (back) -> bits 0,3,4,5 -> 0b00111001 = 0x39
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
  motorRunning = true;
  appendLog("Motor: FORWARD (3s)");
}

void motorBackward() {
  shiftWrite(0x27);
  setMotorSpeeds(MOTOR_SPEED);
  motorStartTime = millis();
  motorRunning = true;
  appendLog("Motor: BACKWARD (3s)");
}

void motorLeft() {
  shiftWrite(0xC6);
  setMotorSpeeds(MOTOR_SPEED);
  motorStartTime = millis();
  motorRunning = true;
  appendLog("Motor: LEFT turn (3s)");
}

void motorRight() {
  shiftWrite(0x39);
  setMotorSpeeds(MOTOR_SPEED);
  motorStartTime = millis();
  motorRunning = true;
  appendLog("Motor: RIGHT turn (3s)");
}

void motorStop() {
  shiftWrite(0x00);
  setMotorSpeeds(0);
  motorRunning = false;
  appendLog("Motor: STOPPED");
}

// --- Command Execution & State Switcher ---
void executeCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0)
    return;

  // --- Motor Commands ---
  if (cmd == "FORWARD") {
    motorForward();
    return;
  } else if (cmd == "BACKWARD") {
    motorBackward();
    return;
  } else if (cmd == "LEFT") {
    motorLeft();
    return;
  } else if (cmd == "RIGHT") {
    motorRight();
    return;
  } else if (cmd == "STOP") {
    motorStop();
    return;
  }

  // --- Image Commands ---
  if (cmd.startsWith("IMG:")) {
    currentImageB64 = cmd.substring(4); // Remove "IMG:"
    // Do not append this large string to the logs
    return;
  } else if (cmd == "IMG_CLEAR") {
    currentImageB64 = "";
    return;
  }

  // --- Eye State Commands ---
  if (cmd == "EYES_TALKING" || cmd == "SPEAK") {
    currentEyeState = "EYES_TALKING";
  } else if (cmd == "EYES_NORMAL" || cmd == "IDLE") {
    currentEyeState = "IDLE";
  } else if (cmd == "EYES_THINKING" || cmd == "THINK") {
    currentEyeState = "THINK";
  } else if (cmd == "LISTEN") {
    currentEyeState = "LISTEN";
  } else if (cmd == "HAPPY") {
    currentEyeState = "HAPPY";
  } else if (cmd == "ANGRY") {
    currentEyeState = "ANGRY";
  } else if (cmd == "SAD") {
    currentEyeState = "SAD";
  } else if (cmd == "BOOT") {
    currentEyeState = "IDLE";
  }

  appendLog("Executed: Eye Display -> Switched state to " + cmd);
}

void setup() {
  // Serial0 (USB to Raspberry Pi)
  Serial.begin(115200);
  
  // Increase RX buffer size to handle large base64 image strings safely
  Serial.setRxBufferSize(4096);

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

  // --- Initialize PWM for motor speed (ESP32 Arduino Core v3.x API) ---
  ledcAttach(PWM_M1, PWM_FREQ, PWM_RES);
  ledcAttach(PWM_M2, PWM_FREQ, PWM_RES);
  ledcAttach(PWM_M3, PWM_FREQ, PWM_RES);
  ledcAttach(PWM_M4, PWM_FREQ, PWM_RES);
  setMotorSpeeds(0);

  appendLog("Motor Shield initialized (Shift Register + PWM)");

  // Setup Soft Access Point
  WiFi.softAPConfig(local_IP, gateway, subnet);
  WiFi.softAP(ssid, password);

  appendLog("Soft-AP Started. SSID: " + String(ssid));
  appendLog("Static Web Server Live at http://192.168.4.17");

  server.on("/", handleRoot);
  server.on("/getStatus", handleGetStatus);
  server.begin();
}

void loop() {
  server.handleClient();

  // --- Auto-stop motor after 3 seconds ---
  if (motorRunning && (millis() - motorStartTime >= MOTOR_RUN_MS)) {
    motorStop();
  }

  // Read incoming USB commands from Raspberry Pi
  if (Serial.available() > 0) {
    String incomingCmd = Serial.readStringUntil('\n');
    incomingCmd.trim();

    if (incomingCmd.length() > 0) {
      appendLog("USB Rx: Received command -> '" + incomingCmd + "'");
      executeCommand(incomingCmd);

      // ACK Back to Pi
      Serial.println("ACK_" + incomingCmd);
    }
  }
}