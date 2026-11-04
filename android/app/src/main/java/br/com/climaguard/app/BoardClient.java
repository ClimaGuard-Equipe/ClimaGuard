package br.com.climaguard.app;

import android.content.Context;
import android.net.*;
import android.net.wifi.WifiManager;
import android.os.SystemClock;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

/** All board I/O stays on Wi-Fi, including when mobile data or a VPN is active. */
final class BoardClient {
    interface Listener { void changed(); }
    static final class Board {
        final String id, ip, model;
        final long seen;
        Board(String id, String ip, String model) {
            this.id = id; this.ip = ip; this.model = model; seen = SystemClock.elapsedRealtime();
        }
    }
    static final class Sample {
        final JSONObject json;
        final long received = System.currentTimeMillis();
        Sample(JSONObject json) { this.json = json; }
    }
    private final Context context;
    private final Listener listener;
    private final ConnectivityManager connectivity;
    private final ScheduledExecutorService poller = Executors.newSingleThreadScheduledExecutor();
    private final ScheduledExecutorService scanner = Executors.newSingleThreadScheduledExecutor();
    private final LinkedHashMap<String, Board> boards = new LinkedHashMap<>();
    private final ArrayList<Sample> history = new ArrayList<>();
    private ReadingState freshness = new ReadingState();
    private WifiManager.MulticastLock multicast;
    private volatile boolean running, scanning;
    private final AtomicReference<String> manual = new AtomicReference<>("");
    private String selected, ip, error = "Conecte o celular ao mesmo Wi-Fi da placa.";
    private JSONObject latest;
    private final ConnectivityManager.NetworkCallback callback = new ConnectivityManager.NetworkCallback() {
        @Override public void onAvailable(Network network) { scan(); }
        @Override public void onLost(Network network) { listener.changed(); }
        @Override public void onLinkPropertiesChanged(Network network, LinkProperties properties) { scan(); }
    };

    BoardClient(Context context, Listener listener) {
        this.context = context.getApplicationContext(); this.listener = listener;
        connectivity = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        android.content.SharedPreferences prefs = context.getSharedPreferences("board", Context.MODE_PRIVATE);
        selected = prefs.getString("id", ""); ip = prefs.getString("ip", "");
    }

    void start() {
        running = true;
        WifiManager wifi = (WifiManager) context.getSystemService(Context.WIFI_SERVICE);
        multicast = wifi.createMulticastLock("ClimaGuard discovery"); multicast.setReferenceCounted(false); multicast.acquire();
        connectivity.registerNetworkCallback(new NetworkRequest.Builder().addTransportType(NetworkCapabilities.TRANSPORT_WIFI).build(), callback);
        poller.scheduleWithFixedDelay(this::poll, 0, 250, TimeUnit.MILLISECONDS);
        scanner.scheduleWithFixedDelay(this::discover, 0, 20, TimeUnit.SECONDS);
    }

    void close() {
        running = false; poller.shutdownNow(); scanner.shutdownNow();
        try { connectivity.unregisterNetworkCallback(callback); } catch (IllegalArgumentException ignored) { }
        if (multicast != null && multicast.isHeld()) multicast.release();
    }

    void scan() {
        if (!running || scanner.isShutdown() || scanning) return;
        try { scanner.execute(this::discover); } catch (RejectedExecutionException ignored) { }
    }

    private List<Network> wifiNetworks() {
        List<Network> result = new ArrayList<>();
        for (Network n : connectivity.getAllNetworks()) {
            NetworkCapabilities caps = connectivity.getNetworkCapabilities(n);
            if (caps != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) result.add(n);
        }
        return result;
    }

    private boolean reachable(Network network, String address) {
        final long candidate;
        try { candidate = LanAddress.parse(address); } catch (IllegalArgumentException e) { return false; }
        LinkProperties props = connectivity.getLinkProperties(network);
        if (props == null) return false;
        for (LinkAddress link : props.getLinkAddresses()) {
            if (!(link.getAddress() instanceof Inet4Address)) continue;
            try {
                if (LanAddress.onLink(candidate, LanAddress.parse(link.getAddress().getHostAddress()), link.getPrefixLength())) return true;
            } catch (IllegalArgumentException ignored) { }
        }
        return false;
    }

    void manual(String address) {
        LanAddress.parse(address);
        if (wifiNetworks().stream().noneMatch(n -> reachable(n, address)))
            throw new IllegalArgumentException("Esse IP não pertence ao Wi-Fi do celular. Confira a rede e o IP da placa.");
        manual.set(address); synchronized (this) { error = "Conferindo o endereço…"; }
        listener.changed();
    }

    synchronized void select(String id) {
        Board b = boards.get(id);
        if (b == null) return;
        setSelection(id, b.ip); listener.changed();
    }

    private void setSelection(String id, String address) {
        if (!selected.equals(id)) { latest = null; freshness = new ReadingState(); history.clear(); }
        selected = id; ip = address;
        context.getSharedPreferences("board", Context.MODE_PRIVATE).edit().putString("id", id).putString("ip", address).apply();
    }

    synchronized List<Board> boards() {
        long now = SystemClock.elapsedRealtime();
        List<Board> result = new ArrayList<>();
        for (Board b : boards.values()) if (now - b.seen < 60000 || b.id.equals(selected)) result.add(b);
        return result;
    }
    synchronized String selected() { return selected; }
    synchronized String address() { return ip; }
    synchronized String error() { return error; }
    synchronized JSONObject latest() { return latest; }
    synchronized List<Sample> history() { return new ArrayList<>(history); }
    synchronized boolean online() { return freshness.online(SystemClock.elapsedRealtime()) && hasWifi(); }
    synchronized long age() { return freshness.age(SystemClock.elapsedRealtime()); }
    boolean scanning() { return scanning; }
    boolean hasWifi() { return !wifiNetworks().isEmpty(); }

    private void discover() {
        if (!running || scanning) return;
        scanning = true; listener.changed();
        byte[] random = new byte[8]; new SecureRandom().nextBytes(random);
        StringBuilder text = new StringBuilder(); for (byte b : random) text.append(String.format(Locale.ROOT, "%02x", b & 255));
        String nonce = text.toString();
        byte[] request = ("CLIMAGUARD_FIND_V2 " + nonce).getBytes(StandardCharsets.US_ASCII);
        try {
            for (Network n : wifiNetworks()) {
                if (!running) return;
                LinkProperties props = connectivity.getLinkProperties(n);
                if (props == null) continue;
                try (DatagramSocket socket = new DatagramSocket()) {
                    n.bindSocket(socket); socket.setBroadcast(true); socket.setSoTimeout(200);
                    Set<String> destinations = new HashSet<>(); destinations.add("255.255.255.255");
                    for (LinkAddress link : props.getLinkAddresses()) {
                        if (!(link.getAddress() instanceof Inet4Address) || link.getPrefixLength() > 30 || link.getPrefixLength() < 1) continue;
                        long local = LanAddress.parse(link.getAddress().getHostAddress());
                        long mask = (0xffffffffL << (32 - link.getPrefixLength())) & 0xffffffffL;
                        destinations.add(LanAddress.format((local & mask) | (~mask & 0xffffffffL)));
                    }
                    for (String destination : destinations) {
                        try { socket.send(new DatagramPacket(request, request.length, InetAddress.getByName(destination), 5002)); }
                        catch (IOException ignored) { }
                    }
                    long end = SystemClock.elapsedRealtime() + 1400;
                    while (running && SystemClock.elapsedRealtime() < end) {
                        DatagramPacket response = new DatagramPacket(new byte[1025], 1025);
                        try { socket.receive(response); } catch (SocketTimeoutException timeout) { continue; }
                        if (response.getLength() > 1024 || response.getPort() != 5002) continue;
                        try {
                            JSONObject value = new JSONObject(new String(response.getData(), 0, response.getLength(), StandardCharsets.UTF_8));
                            identity(value);
                            if (!nonce.equals(value.optString("nonce")) || value.optInt("port") != 80) continue;
                            String address = response.getAddress().getHostAddress();
                            if (!reachable(n, address)) continue;
                            synchronized (this) {
                                String id = value.getString("id");
                                if (boards.size() >= 64 && !boards.containsKey(id)) continue;
                                boards.put(id, new Board(id, address, value.getString("model")));
                                if (selected.equals(id)) {
                                    if (!ip.equals(address)) setSelection(id, address);
                                }
                            }
                        } catch (JSONException | IllegalArgumentException ignored) { }
                    }
                } catch (IOException | IllegalArgumentException ignored) { }
            }
            synchronized (this) {
                boards.entrySet().removeIf(e -> SystemClock.elapsedRealtime() - e.getValue().seen > 60000 && !e.getKey().equals(selected));
                if (selected.isEmpty() && boards.size() == 1) {
                    Board b = boards.values().iterator().next(); setSelection(b.id, b.ip);
                }
            }
        } finally { scanning = false; listener.changed(); }
    }

    private static void identity(JSONObject value) throws JSONException {
        Object protocol = value.opt("protocol");
        if (!"ClimaGuard".equals(value.optString("app")) || !(protocol instanceof Integer) || ((Integer) protocol) != 2
            || !value.optString("id").matches("cg-[0-9a-f]{12}")
            || !("ESP8266".equals(value.optString("model")) || "ESP32".equals(value.optString("model"))))
            throw new JSONException("O endereço não é uma placa ClimaGuard compatível.");
    }

    static void validate(JSONObject value) throws JSONException {
        identity(value);
        Object seq = value.opt("sequence"), age = value.opt("sample_age_ms");
        if (!(seq instanceof Integer || seq instanceof Long) || ((Number) seq).longValue() < 1
            || !(age instanceof Integer || age instanceof Long) || ((Number) age).longValue() < 0 || ((Number) age).longValue() >= 15000
            || !value.optString("boot_id").matches("[0-9a-f]{16}") || !value.has("energy")
            || (!(value.opt("energy") instanceof Boolean) && !value.isNull("energy")))
            throw new JSONException("A placa ainda não forneceu uma leitura válida e recente.");
        if (!value.has("temperature") || !value.has("humidity")) throw new JSONException("Leitura incompleta.");
        boolean noTemp = value.isNull("temperature"), noHum = value.isNull("humidity");
        if (noTemp != noHum) throw new JSONException("Leitura incompleta do sensor.");
        if (noTemp && value.isNull("energy")) {
            JSONObject power = value.optJSONObject("power");
            if (power == null || !"ZMPT101B".equals(power.optString("type")) || !(power.opt("valid") instanceof Boolean)
                || power.optBoolean("valid") || !Arrays.asList("disabled","starting","no_signal","clipped","timing","unstable","adc_error").contains(power.optString("state")))
                throw new JSONException("Sensores indisponíveis sem diagnóstico da placa.");
        }
        if (!noTemp) {
            Object t = value.opt("temperature"), h = value.opt("humidity");
            if (!(t instanceof Number) || !(h instanceof Number)) throw new JSONException("Leitura inválida.");
            double temp = ((Number)t).doubleValue(), hum = ((Number)h).doubleValue();
            if (!Double.isFinite(temp) || !Double.isFinite(hum) || temp < -40 || temp > 80 || hum < 0 || hum > 100)
                throw new JSONException("Leitura fora da faixa do sensor.");
        }
    }

    private JSONObject read(Network network, String address) throws IOException, JSONException {
        HttpURLConnection connection = (HttpURLConnection) network.openConnection(new URL("http://" + address + "/climaguard/status"));
        connection.setConnectTimeout(1100); connection.setReadTimeout(1100);
        connection.setInstanceFollowRedirects(false); connection.setUseCaches(false);
        connection.setRequestProperty("Cache-Control", "no-store");
        try {
            if (connection.getResponseCode() != 200) throw new IOException("Status indisponível");
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream input = connection.getInputStream()) {
                byte[] block = new byte[1024]; int count;
                while ((count = input.read(block)) != -1) {
                    if (bytes.size() + count > 8192) throw new IOException("Resposta inválida");
                    bytes.write(block, 0, count);
                }
            }
            JSONObject json = new JSONObject(bytes.toString(StandardCharsets.UTF_8.name())); validate(json); return json;
        } finally { connection.disconnect(); }
    }

    private void poll() {
        if (!running) return;
        String target, expected, requested = manual.getAndSet("");
        synchronized (this) { target = requested.isEmpty() ? ip : requested; expected = selected; }
        if (target.isEmpty()) return;
        try {
            Network network = null;
            for (Network candidate : wifiNetworks()) if (reachable(candidate, target)) { network = candidate; break; }
            if (network == null) throw new IOException("Wi-Fi indisponível");
            JSONObject json = read(network, target);
            synchronized (this) {
                if (requested.isEmpty() && (!expected.equals(selected) || !target.equals(ip))) return;
                if (requested.isEmpty() && !expected.equals(json.getString("id")))
                    throw new JSONException("Esse IP agora pertence a outra placa. Use Procurar placa.");
                if (!running) return;
                if (!requested.isEmpty()) setSelection(json.getString("id"), target);
                boards.put(selected, new Board(selected, target, json.getString("model")));
                error = "";
                if (freshness.accept(json.getString("boot_id"), json.getLong("sequence"), json.getLong("sample_age_ms"), SystemClock.elapsedRealtime())) {
                    latest = json; history.add(new Sample(json));
                    if (history.size() > 120) history.remove(0);
                }
            }
        } catch (IOException error) {
            synchronized (this) { this.error = "A placa não respondeu. Confira a fonte e o Wi-Fi."; }
        } catch (JSONException | IllegalArgumentException error) {
            synchronized (this) { this.error = error.getMessage(); }
        } catch (RuntimeException error) {
            synchronized (this) { this.error = "Não foi possível consultar a placa. Toque em Procurar placa."; }
        }
        listener.changed();
    }
}
