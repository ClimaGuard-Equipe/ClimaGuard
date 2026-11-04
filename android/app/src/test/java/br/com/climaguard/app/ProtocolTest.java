package br.com.climaguard.app;

import org.json.*;
import org.junit.Test;
import static org.junit.Assert.*;

public class ProtocolTest {
    private JSONObject reading() throws JSONException {
        return new JSONObject("{\"app\":\"ClimaGuard\",\"protocol\":2,\"id\":\"cg-c4d8d502586a\",\"model\":\"ESP8266\",\"boot_id\":\"0123456789abcdef\",\"sequence\":12,\"sample_age_ms\":20,\"temperature\":29.3,\"humidity\":51.4,\"energy\":true}");
    }
    @Test public void acceptsRealFirmwareAndSensorFailureWithoutInventingValues() throws Exception {
        JSONObject value = reading(); BoardClient.validate(value);
        value.put("temperature", JSONObject.NULL).put("humidity", JSONObject.NULL); BoardClient.validate(value);
        value.remove("temperature"); assertThrows(JSONException.class, () -> BoardClient.validate(value));
    }
    @Test public void zmptDisabledIsUnknownRatherThanPowerFailure() throws Exception {
        JSONObject value = reading().put("energy", JSONObject.NULL); BoardClient.validate(value);
        value.put("temperature", JSONObject.NULL).put("humidity", JSONObject.NULL);
        assertThrows(JSONException.class, () -> BoardClient.validate(value));
        value.put("power", new JSONObject("{\"type\":\"ZMPT101B\",\"valid\":false,\"state\":\"disabled\"}"));
        BoardClient.validate(value);
        value.getJSONObject("power").put("valid", true);
        assertThrows(JSONException.class, () -> BoardClient.validate(value));
    }
    @Test public void rejectsWrongDeviceProtocolAndUntrustedData() throws Exception {
        String[] keys = {"app", "protocol", "id", "model", "boot_id", "sequence", "sample_age_ms", "temperature", "humidity", "energy"};
        Object[] invalid = {"other", "2", "bad-id", "PC", "short", 1.5, 15000, "30", 101, "true"};
        for (int i = 0; i < keys.length; i++) {
            JSONObject value = reading().put(keys[i], invalid[i]);
            assertThrows(keys[i], JSONException.class, () -> BoardClient.validate(value));
        }
        JSONObject incomplete = reading().put("temperature", JSONObject.NULL);
        assertThrows(JSONException.class, () -> BoardClient.validate(incomplete));
    }
    @Test public void repeatedHttpSuccessCannotKeepFrozenSensorOnline() {
        ReadingState state = new ReadingState();
        assertTrue(state.accept("0123456789abcdef", 1, 100, 10000));
        assertTrue(state.online(10000));
        assertFalse(state.accept("0123456789abcdef", 1, 100, 18000));
        assertFalse(state.online(18000));
        assertFalse(state.accept("0123456789abcdef", 1, 0, 19000));
        assertFalse(state.online(19000));
    }
    @Test public void contactLossStaleSamplesAndRestartAreTracked() {
        ReadingState state = new ReadingState();
        assertFalse(state.online(0));
        state.accept("0123456789abcdef", 30, 50, 10000);
        assertFalse(state.online(12500));
        assertFalse(state.accept("0123456789abcdef", 29, 0, 13000));
        assertTrue(state.accept("fedcba9876543210", 1, 10, 13000));
        assertTrue(state.online(13000));
        state.accept("fedcba9876543210", 2, 9000, 14000);
        assertFalse(state.online(14000));
        assertThrows(IllegalArgumentException.class, () -> state.accept("x", 3, 0, 15000));
    }
    @Test public void onlyUnambiguousPrivateLocalIpv4DestinationsAreAllowed() {
        String[] bad = {"localhost", "127.0.0.1", "192.168.1.13/path", "8.8.8.8", "169.254.1.1", "224.0.0.1", "192.168.001.13", "192.168.1.256", "172.32.1.1"};
        for (String ip : bad) assertThrows(ip, IllegalArgumentException.class, () -> LanAddress.parse(ip));
        long local = LanAddress.parse("192.168.1.12");
        assertTrue(LanAddress.onLink(LanAddress.parse("192.168.1.13"), local, 24));
        assertFalse(LanAddress.onLink(local, local, 24));
        assertFalse(LanAddress.onLink(LanAddress.parse("192.168.1.255"), local, 24));
        assertFalse(LanAddress.onLink(LanAddress.parse("192.168.1.0"), local, 24));
        assertFalse(LanAddress.onLink(LanAddress.parse("192.168.2.13"), local, 24));
        assertEquals("172.31.1.1", LanAddress.format(LanAddress.parse("172.31.1.1")));
        assertEquals("10.0.0.3", LanAddress.format(LanAddress.parse("10.0.0.3")));
    }
}
