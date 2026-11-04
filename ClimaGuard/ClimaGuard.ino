#if defined(ESP8266)
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
ESP8266WebServer server(80);
const char *MODEL = "ESP8266";
#elif defined(ESP32)
#include <WiFi.h>
#include <WebServer.h>
#include <esp_system.h>
#include <esp_mac.h>
WebServer server(80);
const char *MODEL = "ESP32";
#else
#error Selecione uma placa ESP8266 ou ESP32.
#endif
#include <WiFiUdp.h>
#include <DHT.h>
#include <ArduinoJson.h>
#include "config.h"

// NodeMCU: GPIO4 = D2, GPIO14 = D5. Confirm wiring on another model.
DHT dht(4, DHT22);
const uint8_t ENERGY_PIN = 14;
// DHT22/AM2302 supports one new measurement every two seconds.
const unsigned long SENSOR_INTERVAL = 2100, WIFI_RETRY_INTERVAL = 30000;
WiFiUDP discovery;
bool discoveryReady = false, sensorRead = false, switchPending = true;
bool rawEnergy, stableEnergy;
float temperature = NAN, humidity = NAN;
unsigned long switchChangedAt = 0, lastWifiAttempt = 0, lastSensorRead = 0, lastReadingAt = 0;
uint32_t sequence = 0;
String deviceId, bootId;
#if defined(ESP32)
void handlePowerSerial(JsonDocument &doc);
#endif
#include "WifiSetup.h"
#include "PowerMonitor.h"

String identity() {
  return "{\"app\":\"ClimaGuard\",\"protocol\":2,\"id\":\"" + deviceId +
    "\",\"model\":\"" + MODEL + "\",\"firmware\":\"" +
#if defined(ESP32)
    "1.5.2-devkit-wifi\"";
#else
    "1.5.0\"";
#endif
}

String reading() {
  bool sensorOK = !isnan(temperature) && !isnan(humidity);
  String payload = identity() + ",\"boot_id\":\"" + bootId + "\",\"sequence\":" + String(sequence);
  payload += ",\"sample_age_ms\":" + String(millis() - lastReadingAt);
  payload += ",\"temperature\":";
  payload += sensorOK ? String(temperature, 1) : "null";
  payload += ",\"humidity\":";
  payload += sensorOK ? String(humidity, 1) : "null";
  payload += ",\"energy\":";
#if defined(ESP32)
  payload += PowerMonitor::detector.known ? (PowerMonitor::detector.present ? "true" : "false") : "null";
  JsonDocument power; PowerMonitor::snapshot(power.to<JsonObject>());
  String powerJson; serializeJson(power, powerJson); payload += ",\"power\":" + powerJson;
#else
  payload += stableEnergy ? "true" : "false";
#endif
  JsonDocument wifi;
  wifi["ssid"] = WifiSetup::ssid; wifi["profile_saved"] = WifiSetup::savedProfile;
  wifi["setup_active"] = WifiSetup::active; wifi["setup_ssid"] = WifiSetup::apSsid;
  String wifiJson; serializeJson(wifi, wifiJson);
  payload += ",\"wifi\":" + wifiJson + "}";
  return payload;
}

void networkServices() {
  server.handleClient();
  if (WiFi.status() != WL_CONNECTED) {
    if (discoveryReady) discovery.stop();
    discoveryReady = false;
    return;
  }
  if (!discoveryReady) {
    discoveryReady = discovery.begin(5002);
    if (discoveryReady) Serial.println("IP_ESP: " + WiFi.localIP().toString());
  }
  int length = discovery.parsePacket();
  if (length <= 0) return;
  if (length != 35) {
    while (discovery.available()) discovery.read();
    return;
  }
  char buffer[36];
  int received = discovery.read(buffer, sizeof(buffer) - 1);
  if (received != 35) return;
  buffer[received] = 0;
  String request(buffer);
  if (!request.startsWith("CLIMAGUARD_FIND_V2 ")) return;
  String nonce = request.substring(19);
  for (unsigned int i = 0; i < nonce.length(); ++i)
    if (!((nonce[i] >= '0' && nonce[i] <= '9') || (nonce[i] >= 'a' && nonce[i] <= 'f'))) return;
  String response = identity() + ",\"nonce\":\"" + nonce + "\",\"port\":80}";
  discovery.beginPacket(discovery.remoteIP(), discovery.remotePort());
  discovery.print(response);
  discovery.endPacket();
}

void setup() {
  Serial.begin(115200);
#if defined(ESP8266)
  pinMode(ENERGY_PIN, INPUT); // Legacy NodeMCU switch, never the ZMPT101B output.
  rawEnergy = stableEnergy = digitalRead(ENERGY_PIN) == HIGH;
#endif
  dht.begin();
#if defined(ESP8266)
  WiFi.persistent(false);
#endif
  WiFi.mode(WIFI_STA);
#if defined(ESP8266)
  WiFi.setSleepMode(WIFI_NONE_SLEEP);
#else
  WiFi.setSleep(false);
#endif
  WiFi.setAutoReconnect(true);
  lastWifiAttempt = millis();
#if defined(ESP32)
  // Arduino-ESP32 3.x may report a zero interface MAC before WiFi.begin().
  uint8_t mac[6];
  if (esp_read_mac(mac, ESP_MAC_WIFI_STA) != ESP_OK) {
    Serial.println("ERRO: nao foi possivel ler o MAC do chip.");
    for (;;) delay(1000);
  }
  char id[16];
  snprintf(id, sizeof(id), "cg-%02x%02x%02x%02x%02x%02x", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  deviceId = id;
#else
  deviceId = "cg-" + WiFi.macAddress();
  deviceId.replace(":", ""); deviceId.toLowerCase();
#endif
  char nonce[17];
#if defined(ESP8266)
  snprintf(nonce, sizeof(nonce), "%08lx%08lx", (unsigned long)ESP.random(), (unsigned long)ESP.random());
#else
  snprintf(nonce, sizeof(nonce), "%08lx%08lx", (unsigned long)esp_random(), (unsigned long)esp_random());
#endif
  bootId = nonce;
  WifiSetup::begin();
#if defined(ESP32)
  PowerMonitor::begin();
#endif
  // Telemetry never exposes passwords; configuration uses the setup AP or USB.
  server.on("/climaguard/status", HTTP_GET, []() {
    server.sendHeader("Cache-Control", "no-store");
    server.send(sequence ? 200 : 503, "application/json", sequence ? reading() : "{\"error\":\"iniciando\"}");
  });
  server.onNotFound([]() {
    if (WifiSetup::portalClient()) { server.sendHeader("Location", "http://192.168.4.1/"); server.send(302, "text/plain", ""); }
    else server.send(404, "application/json", "{\"error\":\"not found\"}");
  });
  server.begin();
  Serial.println("ClimaGuard: DHT22 GPIO4 a cada 2,1 s; Wi-Fi configuravel");
#if defined(ESP32)
  Serial.println("ESP32 DevKit V1: ZMPT101B no GPIO34; calibre antes de ativar.");
#endif
}

void loop() {
  WifiSetup::tick();
  networkServices();
  if (!WifiSetup::pending && !WifiSetup::usbScanActive && WiFi.scanComplete() != WIFI_SCAN_RUNNING && WiFi.status() != WL_CONNECTED && millis() - lastWifiAttempt >= WIFI_RETRY_INTERVAL) {
    lastWifiAttempt = millis();
    WifiSetup::disconnectStation();
    WiFi.begin(WifiSetup::ssid.c_str(), WifiSetup::password.c_str());
    Serial.println("WIFI: reconectando");
  }
#if defined(ESP32)
  bool previousKnown = PowerMonitor::detector.known, previousEnergy = PowerMonitor::detector.present;
  PowerMonitor::tick();
  if (previousKnown != PowerMonitor::detector.known || (PowerMonitor::detector.known && previousEnergy != PowerMonitor::detector.present)) switchPending = true;
#else
  bool sample = digitalRead(ENERGY_PIN) == HIGH;
  if (sample != rawEnergy) { rawEnergy = sample; switchChangedAt = millis(); }
  if (millis() - switchChangedAt >= 80 && stableEnergy != rawEnergy) {
    stableEnergy = rawEnergy;
    switchPending = true;
  }
#endif
  if (millis() < SENSOR_INTERVAL && !sensorRead) { delay(5); return; }
  bool sensorDue = !sensorRead || millis() - lastSensorRead >= SENSOR_INTERVAL;
  if (!switchPending && !sensorDue) { delay(5); return; }
  // Energy transitions publish immediately without postponing the next DHT read.
  if (sensorDue) {
    humidity = dht.readHumidity();
    temperature = dht.readTemperature();
    lastSensorRead = millis();
    sensorRead = true;
  }
  lastReadingAt = millis();
  switchPending = false;
  ++sequence;
  Serial.println(reading());
}
