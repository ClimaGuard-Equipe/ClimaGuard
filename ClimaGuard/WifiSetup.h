#pragma once
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <DNSServer.h>
#include "WifiPortal.h"
#if defined(ESP32)
#include <esp_wifi.h>
#endif

#ifndef WIFI_SETUP_PASSWORD
#error Defina WIFI_SETUP_PASSWORD no config.h (8 a 63 caracteres).
#endif
static_assert(sizeof(WIFI_SETUP_PASSWORD) >= 9 && sizeof(WIFI_SETUP_PASSWORD) <= 64, "Senha da rede de configuracao deve ter 8 a 63 caracteres.");

namespace WifiSetup {
DNSServer dns;
String ssid, password, candidateSsid, candidatePassword, apSsid, csrfToken, requestId, serialInput;
String state = "idle", errorMessage;
String errorCode;
volatile uint8_t lastDisconnectReason = 0;
unsigned long prepareAt = 0, lastTryAt = 0;
uint8_t connectionTries = 0;
int lastBeginStatus = 0;
bool filesystem = false, savedProfile = false, active = false, pending = false, attemptStarted = false;
bool serialOverflow = false, buttonHandled = false;
bool usbScanActive = false;
unsigned long disconnectedAt = 0, portalStartedAt = 0, attemptAt = 0, savedAt = 0, closeAt = 0, buttonAt = 0, lastSaveAttempt = 0;

String randomToken() {
  char buffer[17];
#if defined(ESP8266)
  snprintf(buffer, sizeof(buffer), "%08lx%08lx", (unsigned long)ESP.random(), (unsigned long)ESP.random());
#else
  snprintf(buffer, sizeof(buffer), "%08lx%08lx", (unsigned long)esp_random(), (unsigned long)esp_random());
#endif
  return String(buffer);
}

bool validCredentials(const String &name, const String &key) {
  if (name.length() < 1 || name.length() > 32 || key.length() > 64) return false;
  if (key.length() && key.length() < 8) return false;
  if (key.length() == 64) for (unsigned int i = 0; i < key.length(); ++i) if (!isxdigit(key[i])) return false;
  return true;
}

bool storeProfile(const String &name, const String &key) {
  if (!filesystem) return false;
  JsonDocument doc;
  doc["version"] = 1; doc["ssid"] = name; doc["password"] = key;
  File file = LittleFS.open("/wifi.tmp", "w");
  if (!file) return false;
  size_t bytes = serializeJson(doc, file);
  file.close();
  if (!bytes || !LittleFS.rename("/wifi.tmp", "/wifi.json")) return false;
  return true;
}

void serialReply(const char *event, bool ok, const String &message = "", bool card = false) {
  JsonDocument reply;
  reply["app"] = "ClimaGuard"; reply["id"] = deviceId;
  reply["event"] = event; reply["ok"] = ok; reply["request_id"] = requestId;
  reply["message"] = message;
  reply["error_code"] = errorCode;
  reply["disconnect_reason"] = lastDisconnectReason;
  if (String(event) == "wifi_status") {
    reply["state"] = state; reply["pending"] = pending; reply["ssid"] = ssid;
    reply["target_ssid"] = pending ? candidateSsid : "";
    reply["connected"] = WiFi.status() == WL_CONNECTED;
    reply["ip"] = WiFi.localIP().toString(); reply["status"] = (int)WiFi.status();
    reply["filesystem"] = filesystem; reply["profile_saved"] = savedProfile;
    reply["tries"] = connectionTries;
    reply["begin_status"] = lastBeginStatus;
  }
  if (String(event) == "wifi_scan" || String(event) == "wifi_scan_results") {
    int count = WiFi.scanComplete(); reply["scanning"] = count == WIFI_SCAN_RUNNING;
    reply["scan_status"] = count;
    JsonArray networks = reply["networks"].to<JsonArray>();
    for (int i = 0; i < count && networks.size() < 25; ++i) {
      bool seen = false;
      for (JsonObject item : networks) if (item["ssid"].as<String>() == WiFi.SSID(i)) { seen = true; break; }
      if (seen) continue;
      JsonObject item = networks.add<JsonObject>(); item["ssid"] = WiFi.SSID(i);
      item["rssi"] = WiFi.RSSI(i); item["channel"] = WiFi.channel(i);
      item["security"] = (int)WiFi.encryptionType(i);
    }
  }
  if (card) { reply["ap_ssid"] = apSsid; reply["ap_password"] = WIFI_SETUP_PASSWORD; }
  if (ok && String(event) == "wifi_result") { reply["ssid"] = ssid; reply["ip"] = WiFi.localIP().toString(); }
  serializeJson(reply, Serial); Serial.println();
}

void openPortal() {
  if (!active) {
    WiFi.mode(WIFI_AP_STA);
    active = WiFi.softAP(apSsid.c_str(), WIFI_SETUP_PASSWORD);
    if (active) dns.start(53, "*", WiFi.softAPIP());
  }
  portalStartedAt = millis(); closeAt = 0; savedAt = 0;
  csrfToken = randomToken() + randomToken();
  if (!pending) { state = "idle"; errorMessage = ""; }
  if (!pending && WiFi.scanComplete() != WIFI_SCAN_RUNNING) { WiFi.scanDelete(); WiFi.scanNetworks(true); }
}

void closePortal() {
  dns.stop(); WiFi.softAPdisconnect(true); WiFi.mode(WIFI_STA);
  active = false; closeAt = 0;
}

bool portalClient() {
  return active && server.client().localIP() == WiFi.softAPIP();
}

bool permitted(bool write = false) {
  if (!portalClient()) { server.send(403, "application/json", "{\"error\":\"Conecte-se a rede de configuracao da placa.\"}"); return false; }
  if (write && (server.arg("csrf") != csrfToken || !csrfToken.length())) {
    server.send(403, "application/json", "{\"error\":\"Atualize a pagina e tente novamente.\"}"); return false;
  }
  return true;
}

void sendJson(JsonDocument &doc, int code = 200) {
  String output; serializeJson(doc, output);
  server.sendHeader("Cache-Control", "no-store");
  server.send(code, "application/json", output);
}

void disconnectStation() {
#if defined(ESP32)
  // Arduino-ESP32 3.3.x WiFi.disconnect() returns early while still connecting.
  // Cancel at the driver so set_config/scan can switch away from an absent SSID.
  esp_wifi_disconnect();
#else
  WiFi.disconnect();
#endif
}

bool beginAttempt(const String &name, const String &key) {
  if (pending || !validCredentials(name, key)) return false;
  candidateSsid = name; candidatePassword = key;
  pending = true; attemptStarted = false; state = "connecting"; errorMessage = ""; errorCode = "";
  connectionTries = 0; attemptAt = prepareAt = millis();
  WiFi.setAutoReconnect(false);
#if defined(ESP32)
  // scanDelete frees results; it does not stop the driver's active scan.
  esp_wifi_scan_stop();
#endif
  WiFi.scanDelete(); disconnectStation();
  lastDisconnectReason = 0;
  return true;
}

void registerRoutes() {
  server.on("/", HTTP_GET, []() {
    if (portalClient()) { server.sendHeader("Cache-Control", "no-store"); server.send_P(200, "text/html; charset=utf-8", WIFI_PORTAL); }
    else server.send(200, "text/html; charset=utf-8", "<meta name='viewport' content='width=device-width'><h1>Wi-Fi do ClimaGuard</h1><p>Com a placa ligada, segure FLASH por 3 segundos e solte. Conecte o celular a rede ClimaGuard da placa usando a senha do seu cartao. Abra http://192.168.4.1 e escolha o novo Wi-Fi.</p>");
  });
  server.on("/wifi/state", HTTP_GET, []() {
    if (!permitted()) return;
    JsonDocument doc; doc["state"] = state; doc["csrf"] = csrfToken;
    doc["ssid"] = pending ? candidateSsid : ssid; doc["ip"] = WiFi.localIP().toString(); doc["error"] = errorMessage;
    sendJson(doc);
  });
  server.on("/wifi/networks", HTTP_GET, []() {
    if (!permitted()) return;
    JsonDocument doc; int count = WiFi.scanComplete();
    doc["scanning"] = count == WIFI_SCAN_RUNNING;
    JsonArray networks = doc["networks"].to<JsonArray>();
    for (int i = 0; i < count && i < 25; ++i) {
      if (!WiFi.SSID(i).length()) continue;
      JsonObject item = networks.add<JsonObject>(); item["ssid"] = WiFi.SSID(i); item["rssi"] = WiFi.RSSI(i);
#if defined(ESP8266)
      item["open"] = WiFi.encryptionType(i) == ENC_TYPE_NONE;
#else
      item["open"] = WiFi.encryptionType(i) == WIFI_AUTH_OPEN;
#endif
    }
    sendJson(doc);
  });
  server.on("/wifi/scan", HTTP_POST, []() {
    if (!permitted(true)) return;
    if (!pending && WiFi.scanComplete() != WIFI_SCAN_RUNNING) { WiFi.scanDelete(); WiFi.scanNetworks(true); }
    server.send(202, "application/json", "{\"ok\":true}");
  });
  server.on("/wifi/save", HTTP_POST, []() {
    if (!permitted(true)) return;
    if (!validCredentials(server.arg("ssid"), server.arg("password"))) {
      server.send(400, "application/json", "{\"error\":\"Confira o nome da rede e a senha (8 a 63 caracteres, ou vazia para rede aberta).\"}"); return;
    }
    requestId = "";
    if (!beginAttempt(server.arg("ssid"), server.arg("password"))) { server.send(409, "application/json", "{\"error\":\"Aguarde a tentativa atual.\"}"); return; }
    server.send(202, "application/json", "{\"ok\":true}");
  });
  server.on("/wifi/close", HTTP_POST, []() {
    if (!permitted(true)) return;
    server.send(200, "application/json", "{\"ok\":true}");
    if (!pending) closeAt = millis();
  });
}

void begin() {
  pinMode(0, INPUT_PULLUP);
  apSsid = "ClimaGuard-" + deviceId.substring(deviceId.length() - 6); apSsid.toUpperCase();
  apSsid.replace("CLIMAGUARD", "ClimaGuard");
#if defined(ESP8266)
  filesystem = LittleFS.begin();
#else
  filesystem = LittleFS.begin(true);
#endif
  ssid = WIFI_SSID; password = WIFI_PASSWORD;
  if (filesystem) {
    File file = LittleFS.open("/wifi.json", "r");
    JsonDocument doc;
    if (file && file.size() < 512 && !deserializeJson(doc, file) && doc["version"] == 1) {
      String storedName = doc["ssid"] | "", storedKey = doc["password"] | "";
      if (validCredentials(storedName, storedKey)) { ssid = storedName; password = storedKey; savedProfile = true; }
    }
    if (file) file.close();
  }
  registerRoutes();
#if defined(ESP32)
  WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
    if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED && info.wifi_sta_disconnected.reason != WIFI_REASON_ASSOC_LEAVE)
      lastDisconnectReason = info.wifi_sta_disconnected.reason;
  });
#endif
  WiFi.begin(ssid.c_str(), password.c_str());
  disconnectedAt = millis();
}

void processSerial() {
  int budget = 96;
  while (Serial.available() && budget-- > 0) {
    char character = Serial.read();
    if (character == '\r') continue;
    if (character != '\n') {
      if (!serialOverflow && serialInput.length() < 768) serialInput += character;
      else { serialInput = ""; serialOverflow = true; }
      continue;
    }
    if (serialOverflow) { serialOverflow = false; serialInput = ""; continue; }
    JsonDocument doc;
    DeserializationError invalid = deserializeJson(doc, serialInput, DeserializationOption::NestingLimit(2));
    serialInput = "";
    if (invalid) continue;
    String id = doc["request_id"] | "";
    if (id.length() != 32) continue;
    bool hex = true; for (unsigned int i = 0; i < id.length(); ++i) if (!isxdigit(id[i])) hex = false;
    if (!hex) continue;
    String command = doc["command"] | "";
    if (pending && command != "wifi_status") continue;
    String previousRequestId = requestId;
    requestId = id;
    if (command == "wifi_status") {
      serialReply("wifi_status", true);
      if (pending) requestId = previousRequestId;
    }
    else if (command == "wifi_scan") {
      if (WiFi.scanComplete() != WIFI_SCAN_RUNNING) {
        if (WiFi.status() != WL_CONNECTED) {
          WiFi.setAutoReconnect(false); disconnectStation();
          delay(250); // USB maintenance only: let the asynchronous disconnect finish.
        }
        WiFi.scanDelete(); WiFi.scanNetworks(true); usbScanActive = true;
      }
      serialReply("wifi_scan", true);
    }
    else if (command == "wifi_scan_results") serialReply("wifi_scan_results", true);
    else if (command == "wifi_card") serialReply("wifi_card", true, "", true);
    else if (command == "wifi_portal") { openPortal(); serialReply("wifi_portal", active, active ? "Configuracao aberta." : "Falha ao abrir configuracao."); }
    else if (command == "set_wifi") {
      String name = doc["ssid"] | "", key = doc["password"] | "";
      if (!beginAttempt(name, key)) serialReply("wifi_result", false, "Confira o nome da rede e a senha.");
    }
#if defined(ESP32)
    else if (command.startsWith("power_")) handlePowerSerial(doc);
#endif
  }
}

void tick() {
  processSerial();
  if (usbScanActive && WiFi.scanComplete() != WIFI_SCAN_RUNNING) {
    usbScanActive = false; WiFi.setAutoReconnect(true);
  }
  if (active) dns.processNextRequest();
  if (digitalRead(0) == LOW) {
    if (!buttonAt) buttonAt = millis();
    if (!buttonHandled && millis() - buttonAt >= 3000) {
      buttonHandled = true; openPortal();
      if (WiFi.scanComplete() != WIFI_SCAN_RUNNING) { WiFi.scanDelete(); WiFi.scanNetworks(true); }
    }
  } else { buttonAt = 0; buttonHandled = false; }
  if (pending && !attemptStarted && millis() - prepareAt >= 250) {
    lastDisconnectReason = 0;
    lastBeginStatus = (int)WiFi.begin(candidateSsid.c_str(), candidatePassword.c_str());
    lastTryAt = millis(); ++connectionTries; ::lastWifiAttempt = millis(); attemptStarted = true;
  }
  if (pending && millis() - attemptAt >= 1500 && WiFi.status() == WL_CONNECTED && WiFi.SSID() == candidateSsid) {
    if (storeProfile(candidateSsid, candidatePassword)) {
      ssid = candidateSsid; password = candidatePassword; savedProfile = true;
      state = "saved"; savedAt = millis();
      serialReply("wifi_result", true, "Rede salva na placa.");
    } else {
      state = "error"; errorMessage = "Nao foi possivel salvar na memoria. A rede anterior foi mantida.";
      errorCode = "storage_failed";
      disconnectStation(); WiFi.begin(ssid.c_str(), password.c_str());
      ::lastWifiAttempt = millis();
      serialReply("wifi_result", false, errorMessage);
    }
    pending = false; candidatePassword = ""; WiFi.setAutoReconnect(true);
  } else if (pending && millis() - attemptAt >= 28000) {
    pending = false; state = "error"; errorMessage = "A nova rede nao conectou. Confira a senha e use Wi-Fi 2,4 GHz. A rede anterior foi mantida.";
    uint8_t reason = lastDisconnectReason;
    errorCode = reason == 201 ? "network_not_found" :
                (reason == 15 || reason == 204) ? "handshake_timeout" :
                reason == 202 ? "authentication_failed" :
                reason == 203 ? "association_failed" :
                reason == 2 ? "authentication_timeout" :
                reason == 200 ? "signal_lost" :
                WiFi.status() == WL_IDLE_STATUS ? "ip_timeout" : "connection_timeout";
    candidatePassword = ""; disconnectStation(); WiFi.begin(ssid.c_str(), password.c_str()); WiFi.setAutoReconnect(true);
    ::lastWifiAttempt = millis();
    serialReply("wifi_result", false, errorMessage);
  } else if (pending && attemptStarted && connectionTries < 3 && millis() - lastTryAt >= 8000 && WiFi.status() != WL_IDLE_STATUS) {
    // A hotspot can miss a first association; retry within the same bounded test.
    disconnectStation(); attemptStarted = false; prepareAt = millis();
  }
  if (!pending) {
    if (WiFi.status() == WL_CONNECTED) {
      disconnectedAt = millis();
      if (!savedProfile && (!lastSaveAttempt || millis() - lastSaveAttempt >= 30000)) {
        lastSaveAttempt = millis(); savedProfile = storeProfile(ssid, password);
      }
    } else if (millis() - disconnectedAt >= 30000 && !active) {
      openPortal(); if (WiFi.scanComplete() != WIFI_SCAN_RUNNING) WiFi.scanNetworks(true);
    }
    if (active && ((savedAt && millis() - savedAt >= 60000) ||
        (closeAt && millis() - closeAt >= 1500) ||
        (WiFi.status() == WL_CONNECTED && millis() - portalStartedAt >= 600000))) closePortal();
  }
}
} // namespace WifiSetup
