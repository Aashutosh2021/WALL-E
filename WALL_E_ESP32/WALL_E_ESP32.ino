#include <WiFi.h>
#include <WebServer.h>

// --- Network Configurations ---
const char* ssid = "WALL-E_AP";         // ESP32 Access Point Name
const char* password = "password2026";    // AP Password (Min 8 chars)

// Static IP Configuration
IPAddress local_IP(192, 168, 4, 17);
IPAddress gateway(192, 168, 4, 1);
IPAddress subnet(255, 255, 255, 0);

WebServer server(80);

// --- Circular Buffer for Live Web Logs ---
const int MAX_LOGS = 30;
String logBuffer[MAX_LOGS];
int logIndex = 0;

// Function to add a log message with a timestamp
void appendLog(String message) {
  unsigned long ms = millis();
  String timestamp = "[" + String(ms / 1000.0, 2) + "s] ";
  
  logBuffer[logIndex] = timestamp + message;
  logIndex = (logIndex + 1) % MAX_LOGS;
  
  // Serial Monitor monitor pe bhi debug print hoga
  Serial.println(timestamp + message); 
}

// --- HTML + JS Webpage Layout ---
void handleRoot() {
  String html = "<!DOCTYPE html><html><head>";
  html += "<title>WALL-E Hardware Debug Console</title>";
  html += "<meta name='viewport' content='width=device-width, initial-scale=1'>";
  html += "<style>";
  html += "body { font-family: 'Segoe UI', Arial, sans-serif; background-color: #1e1e24; color: #f4f4f9; padding: 20px; margin: 0; }";
  html += ".container { max-width: 900px; margin: 0 auto; }";
  html += "h2 { color: #ff9f1c; border-bottom: 2px solid #ff9f1c; padding-bottom: 10px; font-weight: 500; }";
  html += "#console { background-color: #0b0c10; border: 1px solid #45f3ff; border-radius: 8px; padding: 15px; height: 450px; overflow-y: auto; font-family: 'Courier New', monospace; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }";
  html += ".log-entry { margin-bottom: 8px; line-height: 1.4; border-left: 3px solid #4e4e50; padding-left: 8px; }";
  html += ".cmd-in { color: #4dfd60; }";      // Incoming commands = Green
  html += ".cmd-exec { color: #ff9f1c; }";    // Execution status = Orange
  html += ".sys-info { color: #00d2ff; }";    // System Info = Blue
  html += "footer { margin-top: 20px; text-align: center; color: #666; font-size: 0.9em; }";
  html += "</style>";
  
  // Auto-refresh script (Every 1 second AJAX pull)
  html += "<script>";
  html += "setInterval(function() {";
  html += "  var xhttp = new XMLHttpRequest();";
  html += "  xhttp.onreadystatechange = function() {";
  html += "    if (this.readyState == 4 && this.status == 200) {";
  html += "      var el = document.getElementById('console');";
  html += "      var isScrolledToBottom = el.scrollHeight - el.clientHeight <= el.scrollTop + 1;";
  html += "      el.innerHTML = this.responseText;";
  html += "      if(isScrolledToBottom) { el.scrollTop = el.scrollHeight; }";
  html += "    }";
  html += "  };";
  html += "  xhttp.open('GET', '/getLogs', true);";
  html += "  xhttp.send();";
  html += "}, 1000);";
  html += "</script>";
  
  html += "</head><body><div class='container'>";
  html += "<h2>🤖 WALL-E Robot Hardware Live Debug Console</h2>";
  html += "<div id='console'>";
  
  // Load initial logs
  for (int i = 0; i < MAX_LOGS; i++) {
    int idx = (logIndex + i) % MAX_LOGS;
    if (logBuffer[idx].length() > 0) {
      html += "<div class='log-entry'>" + logBuffer[idx] + "</div>";
    }
  }
  
  html += "</div>";
  html += "<footer>ESP32 IP: 192.168.4.17 | Baud Rate: 115200</footer>";
  html += "</div></body></html>";
  
  server.send(200, "text/html", html);
}

// --- AJAX Endpoint to fetch logs asynchronously ---
void handleGetLogs() {
  String response = "";
  for (int i = 0; i < MAX_LOGS; i++) {
    int idx = (logIndex + i) % MAX_LOGS;
    if (logBuffer[idx].length() > 0) {
      String line = logBuffer[idx];
      
      // Syntax highlighting tags for display formatting
      if (line.indexOf("UART Rx:") != -1) {
        response += "<div class='log-entry cmd-in'>" + line + "</div>";
      } else if (line.indexOf("Executed:") != -1) {
        response += "<div class='log-entry cmd-exec'>" + line + "</div>";
      } else {
        response += "<div class='log-entry sys-info'>" + line + "</div>";
      }
    }
  }
  server.send(200, "text/plain", response);
}

// --- Dynamic Hardware Command Processor ---
void executeCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  // 1. Handle Eye States
  if (cmd == "BOOT") {
    appendLog("Executed: Visual State -> Triggered BOOT Sequence.");
  } else if (cmd == "IDLE") {
    appendLog("Executed: Visual State -> Eyes Set to Normal Idle.");
  } else if (cmd == "LISTEN") {
    appendLog("Executed: Visual State -> Eyes Set to Listening Glowing Mode.");
  } else if (cmd == "SPEAK") {
    appendLog("Executed: Visual State -> Eyes Set to Speaking Animation.");
  } else if (cmd == "THINK") {
    appendLog("Executed: Visual State -> Eyes Set to Thinking Processing Style.");
  } else if (cmd == "STOP") {
    appendLog("Executed: System State -> Emergency Halt Activated.");
    
  // 2. Handle Motor Movements (e.g., MOVE_FORWARD_500)
  } else if (cmd.startsWith("MOVE_")) {
    appendLog("Executed: Motor Drive -> Command parsed: " + cmd);
  } else {
    appendLog("Executed: WARNING -> Unknown or unmapped packet input: " + cmd);
  }
}

void setup() {
  // Serial0 configuration for standard USB PC debug
  Serial.begin(115200);
  
  // Hardware Serial2 configuration for Raspberry Pi connection
  // ESP32 Pins: RX2 = GPIO 16, TX2 = GPIO 17
  Serial2.begin(115200, SERIAL_8N1, 16, 17);

  appendLog("System Booting Up...");

  // Setup Soft Access Point
  WiFi.softAPConfig(local_IP, gateway, subnet);
  WiFi.softAP(ssid, password);

  appendLog("Soft-AP Started. SSID: " + String(ssid));
  appendLog("Static Web Server Live at http://192.168.4.17");

  // Web Server Routing paths
  server.on("/", handleRoot);
  server.on("/getLogs", handleGetLogs);
  server.begin();
}

void loop() {
  server.handleClient();

  // Ab Serial2 ki jagah direct Serial (USB) se read karenge
  if (Serial.available() > 0) {
    String incomingCmd = Serial.readStringUntil('\n');
    incomingCmd.trim();
    
    if (incomingCmd.length() > 0) {
      appendLog("USB Rx: Received command -> '" + incomingCmd + "'");
      executeCommand(incomingCmd);
      
      // Pi ko wapas confirmation bhejne ke liye bhi direct Serial use hoga
      Serial.println("ACK_" + incomingCmd); 
    }
  }
}