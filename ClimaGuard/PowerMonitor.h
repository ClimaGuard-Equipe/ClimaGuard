#pragma once
#if defined(ESP32)
#include "PowerSignal.h"

namespace PowerMonitor {
constexpr uint8_t PIN = 34; // ADC1: continues working while Wi-Fi is active.
portMUX_TYPE mutex = portMUX_INITIALIZER_UNLOCKED;
PowerSignal::Frame sharedFrame, current;
PowerSignal::Detector detector;
uint32_t frameAt = 0, consumedAt = 0;
bool enabled = false, initialized = false;
float reference = 0;
String state = "disabled";

void acquire(void *) {
  uint16_t values[256]; uint32_t times[256];
  for (;;) {
    unsigned count = 0; uint32_t started = micros();
    do {
      times[count] = micros(); values[count] = analogRead(PIN); ++count;
      vTaskDelay(1);
    } while (count < 256 && uint32_t(micros() - started) < 200000);
    PowerSignal::Frame frame = PowerSignal::analyze(values, times, count);
    portENTER_CRITICAL(&mutex); sharedFrame = frame; frameAt = millis(); portEXIT_CRITICAL(&mutex);
  }
}

bool save(bool nextEnabled, float nextReference) {
  if (!WifiSetup::filesystem) return false;
  JsonDocument doc; doc["version"] = 1; doc["enabled"] = nextEnabled; doc["reference_adc_rms"] = nextReference;
  File file = LittleFS.open("/power.tmp", "w"); if (!file) return false;
  size_t written = serializeJson(doc, file); file.close();
  if (!written || !LittleFS.rename("/power.tmp", "/power.json")) return false;
  enabled = nextEnabled; reference = nextReference; detector.reset(); return true;
}

void tick() {
  PowerSignal::Frame frame; uint32_t updated;
  portENTER_CRITICAL(&mutex); frame = sharedFrame; updated = frameAt; portEXIT_CRITICAL(&mutex);
  if (!updated || uint32_t(millis() - updated) > 1000) { detector.reset(); state = enabled ? "starting" : "disabled"; return; }
  if (updated == consumedAt) return;
  consumedAt = updated; current = frame;
  detector.update(frame, enabled && initialized, reference);
  state = !enabled ? "disabled" : !initialized ? "adc_error" : !frame.valid ? frame.error :
    detector.known ? (detector.present ? "present" : "absent") : "unstable";
}

void snapshot(JsonObject doc) {
  doc["type"] = "ZMPT101B"; doc["pin"] = PIN; doc["enabled"] = enabled;
  doc["valid"] = detector.known; doc["state"] = state;
  doc["adc_bias"] = current.mean; doc["adc_ac_rms"] = current.rms; doc["coherence"] = current.coherence;
  doc["reference_adc_rms"] = reference; doc["calibrated"] = reference >= 25;
  doc["voltage_calibrated"] = false; // No fictitious 127/220 V values.
}

bool calibrate() {
  tick();
  uint32_t updated;
  portENTER_CRITICAL(&mutex); updated = frameAt; portEXIT_CRITICAL(&mutex);
  return updated && uint32_t(millis() - updated) <= 500 && initialized && current.valid && current.rms >= 25 && current.rms <= 1200 && current.coherence >= .8f && save(true, current.rms);
}

void reply(const char *event, bool ok, const char *message = "") {
  JsonDocument doc; doc["app"] = "ClimaGuard"; doc["id"] = deviceId;
  doc["event"] = event; doc["request_id"] = WifiSetup::requestId; doc["ok"] = ok; doc["message"] = message;
  snapshot(doc["power"].to<JsonObject>()); serializeJson(doc, Serial); Serial.println();
}

const char PORTAL[] PROGMEM = R"HTML(<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Energia do ClimaGuard</title><style>body{font:16px/1.5 system-ui;background:#eff5f1;color:#153f36;margin:24px auto;max-width:520px;padding:16px}main{background:white;padding:24px;border-radius:18px}button{padding:14px;border:0;border-radius:10px;background:#176a52;color:white;font:inherit;width:100%;margin:8px 0}pre{white-space:pre-wrap;background:#eff5f1;padding:14px}label{display:block;margin:18px 0}a{color:#176a52}</style><main><h1>Sensor de energia</h1><p>ZMPT101B no GPIO34. A saída deve estar adaptada para a entrada de 3,3 V do ESP32. A ligação à rede elétrica deve ser feita por pessoa qualificada, com o circuito protegido.</p><p>O sensor começa desativado. A calibração abaixo aprende o sinal de uma condição conhecida <strong>com energia presente</strong>. Ela serve para detectar presença/ausência; não mede a tensão da tomada em volts.</p><pre id="status">Lendo sensor…</pre><label><input type="checkbox" id="confirm">A montagem foi conferida e há energia AC presente no sensor.</label><button id="calibrate">Calibrar e ativar</button><button id="disable">Desativar sensor</button><p id="message" role="status"></p><a href="/">Voltar ao Wi-Fi</a></main><script>let token='';const $=id=>document.getElementById(id);async function state(){try{const r=await fetch('/power/state',{cache:'no-store'});const v=await r.json();if(!r.ok)throw Error(v.error);token=v.csrf;const p=v.power;const labels={disabled:'Sensor desativado — energia não verificada',starting:'Aguardando leitura',adc_error:'Falha na leitura analógica',present:'Energia presente',absent:'Energia ausente',no_signal:'Sem sinal válido do sensor',clipped:'Sinal saturado — confira o ajuste e o divisor',timing:'Amostragem indisponível',unstable:'Sinal instável'};$('status').textContent=(labels[p.state]||'Energia não verificada')+'\nSinal AC (unidades ADC): '+p.adc_ac_rms.toFixed(1)+'\nQualidade 50/60 Hz: '+Math.round(p.coherence*100)+'%\nAtivado: '+(p.enabled?'sim':'não');}catch(e){$('status').textContent='Conecte à rede de configuração da placa e recarregue.';}}async function save(calibrate){if(calibrate&&!$('confirm').checked){$('message').textContent='Confira a montagem e confirme a condição de referência.';return;}try{const r=await fetch('/power/save',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({csrf:token,action:calibrate?'calibrate':'disable',confirmed:calibrate?'yes':'no'})});const v=await r.json();$('message').textContent=v.message||v.error;state();}catch(e){$('message').textContent='Não foi possível salvar. Tente novamente.';}}$('calibrate').onclick=()=>save(true);$('disable').onclick=()=>save(false);state();setInterval(state,1000);</script></html>)HTML";

void begin() {
  pinMode(PIN, INPUT); analogReadResolution(12); analogSetPinAttenuation(PIN, ADC_11db);
  if (WifiSetup::filesystem) {
    File file = LittleFS.open("/power.json", "r"); JsonDocument doc;
    if (file && !deserializeJson(doc, file)) {
      float stored = doc["reference_adc_rms"] | 0.f;
      if (doc["version"] == 1 && stored >= 25 && stored <= 1200) { reference = stored; enabled = doc["enabled"] | false; }
    }
  }
  initialized = xTaskCreatePinnedToCore(acquire, "climaguard-adc", 4096, nullptr, 1, nullptr, 0) == pdPASS;
  server.on("/power", HTTP_GET, []() { if (WifiSetup::permitted()) { server.sendHeader("Cache-Control", "no-store"); server.send_P(200, "text/html; charset=utf-8", PORTAL); } });
  server.on("/power/state", HTTP_GET, []() {
    if (!WifiSetup::permitted()) return;
    JsonDocument doc; doc["csrf"] = WifiSetup::csrfToken; snapshot(doc["power"].to<JsonObject>()); WifiSetup::sendJson(doc);
  });
  server.on("/power/save", HTTP_POST, []() {
    if (!WifiSetup::permitted(true)) return;
    bool disable = server.arg("action") == "disable";
    bool ok = disable ? save(false, reference) : server.arg("action") == "calibrate" && server.arg("confirmed") == "yes" && calibrate();
    JsonDocument doc; doc["ok"] = ok;
    if (ok) doc["message"] = disable ? "Sensor desativado. Energia nao verificada." : "Referencia salva. Sensor ativado.";
    else doc["error"] = "Sem referencia AC valida. Confira a montagem, o divisor e o ajuste do modulo. Nada foi ativado.";
    WifiSetup::sendJson(doc, ok ? 200 : 400);
  });
}
} // namespace PowerMonitor

void handlePowerSerial(JsonDocument &doc) {
  String command = doc["command"] | "";
  if (command == "power_selftest") {
    unsigned passed = PowerSignal::selfTest();
    JsonDocument reply; reply["app"] = "ClimaGuard"; reply["event"] = "power_selftest"; reply["request_id"] = WifiSetup::requestId;
    reply["passed"] = passed; reply["total"] = 10; reply["ok"] = passed == 10; serializeJson(reply, Serial); Serial.println();
  } else if (command == "power_status") PowerMonitor::reply("power_status", true);
  else if (command == "power_disable") PowerMonitor::reply("power_result", PowerMonitor::save(false, PowerMonitor::reference));
  else if (command == "power_calibrate") PowerMonitor::reply("power_result", doc["reference_ac_present"].is<bool>() && doc["reference_ac_present"].as<bool>() && PowerMonitor::calibrate());
}
#endif
