package br.com.climaguard.app;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.*;
import android.text.InputType;
import android.view.*;
import android.widget.*;
import org.json.JSONObject;
import java.text.SimpleDateFormat;
import java.util.*;

public class MainActivity extends Activity {
    private static final int GREEN = Color.rgb(22, 104, 82), INK = Color.rgb(20, 57, 51), MUTED = Color.rgb(86, 112, 105);
    private static final int BACKGROUND = Color.rgb(241, 247, 243), ORANGE = Color.rgb(171, 94, 26);
    private final Handler handler = new Handler(Looper.getMainLooper());
    private BoardClient client;
    private TextView status, detail, temperature, humidity, energy, sensorHint, boardInfo;
    private Button scanButton, chooseButton;
    private TrendView trend;
    private long drawnSample = -1;
    private final Runnable refresh = new Runnable() {
        @Override public void run() { render(); handler.postDelayed(this, 500); }
    };

    private int dp(float value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(INK); getWindow().setNavigationBarColor(BACKGROUND);
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setStatusBarColor(BACKGROUND);
        } else {
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        }
        LinearLayout outer = new LinearLayout(this); outer.setOrientation(LinearLayout.VERTICAL); outer.setBackgroundColor(BACKGROUND);
        if (Build.VERSION.SDK_INT >= 35) {
            outer.setOnApplyWindowInsetsListener((v, insets) -> {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                v.setPadding(bars.left, bars.top, bars.right, bars.bottom); return insets;
            });
        }
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true);
        LinearLayout body = new LinearLayout(this); body.setOrientation(LinearLayout.VERTICAL); body.setPadding(dp(22), dp(22), dp(22), dp(32));
        scroll.addView(body); outer.addView(scroll); setContentView(outer);
        if (Build.VERSION.SDK_INT >= 30) outer.post(() -> {
            WindowInsetsController controller = outer.getWindowInsetsController();
            if (controller != null) controller.setSystemBarsAppearance(
                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS);
        });
        LinearLayout brand = new LinearLayout(this); brand.setGravity(Gravity.CENTER_VERTICAL);
        ImageView icon = new ImageView(this); icon.setImageResource(br.com.climaguard.app.R.drawable.app_icon);
        icon.setBackground(background(INK, 0)); icon.setClipToOutline(true);
        brand.addView(icon, new LinearLayout.LayoutParams(dp(48), dp(48)));
        TextView title = text("ClimaGuard", 28, INK, true); title.setPadding(dp(12), 0, 0, 0); brand.addView(title); body.addView(brand);
        add(body, text("Seu ambiente, acompanhado de perto.", 15, MUTED, false), 10);

        LinearLayout connection = card(body, 22);
        status = text("●  Procurando a placa", 19, ORANGE, true); connection.addView(status);
        detail = text("Conecte o celular ao mesmo Wi-Fi da placa.", 14, MUTED, false); add(connection, detail, 8);
        boardInfo = text("", 12, MUTED, false); add(connection, boardInfo, 7);

        LinearLayout readings = new LinearLayout(this); readings.setOrientation(LinearLayout.HORIZONTAL);
        temperature = metric(readings, "TEMPERATURA", "— °C");
        humidity = metric(readings, "UMIDADE", "— %");
        add(body, readings, 18);
        LinearLayout power = card(body, 14); power.addView(text("ESTADO DE ENERGIA", 11, MUTED, true));
        energy = text("Aguardando leitura", 21, INK, true); add(power, energy, 8);
        sensorHint = text("", 13, MUTED, false); add(body, sensorHint, 8);

        LinearLayout history = card(body, 14); history.addView(text("Últimas temperaturas", 18, INK, true));
        add(history, text("Leituras recebidas enquanto o aplicativo está aberto.", 12, MUTED, false), 5);
        trend = new TrendView(); add(history, trend, 12);

        scanButton = button("Procurar placa na rede", true); add(body, scanButton, 18);
        scanButton.setOnClickListener(v -> { if (client != null) client.scan(); });
        chooseButton = button("Escolher placa", false); add(body, chooseButton, 7);
        chooseButton.setOnClickListener(v -> choose());
        Button manual = button("Conectar pelo IP", false); add(body, manual, 7); manual.setOnClickListener(v -> manual());
        Button wifi = button("Trocar o Wi-Fi da placa", false); add(body, wifi, 7); wifi.setOnClickListener(v -> wifiHelp());
        add(body, text("Acesso direto pela rede local • Android 1.0.1", 12, MUTED, false), 24);
    }

    @Override protected void onStart() {
        super.onStart();
        client = new BoardClient(this, () -> { }); client.start(); drawnSample = -1;
        handler.post(refresh);
    }
    @Override protected void onStop() {
        handler.removeCallbacksAndMessages(null);
        if (client != null) client.close();
        super.onStop();
    }

    private TextView text(String value, float size, int color, boolean bold) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        if (bold) view.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        view.setLineSpacing(dp(3), 1); return view;
    }
    private GradientDrawable background(int color, int stroke) {
        GradientDrawable d = new GradientDrawable(); d.setColor(color); d.setCornerRadius(dp(18));
        if (stroke != 0) d.setStroke(dp(1), stroke); return d;
    }
    private void add(LinearLayout parent, View view, int top) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        p.topMargin = dp(top); parent.addView(view, p);
    }
    private LinearLayout card(LinearLayout parent, int top) {
        LinearLayout box = new LinearLayout(this); box.setOrientation(LinearLayout.VERTICAL); box.setPadding(dp(18), dp(18), dp(18), dp(18));
        box.setBackground(background(Color.WHITE, Color.rgb(218, 230, 221))); add(parent, box, top); return box;
    }
    private TextView metric(LinearLayout row, String label, String value) {
        LinearLayout box = new LinearLayout(this); box.setOrientation(LinearLayout.VERTICAL); box.setPadding(dp(15), dp(19), dp(12), dp(19));
        box.setBackground(background(Color.WHITE, Color.rgb(218, 230, 221)));
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1);
        if (row.getChildCount() > 0) p.leftMargin = dp(10); row.addView(box, p);
        box.addView(text(label, 10, MUTED, true)); TextView number = text(value, 30, INK, true); add(box, number, 10); return number;
    }
    private Button button(String label, boolean primary) {
        Button b = new Button(this); b.setText(label); b.setTextSize(15); b.setAllCaps(false);
        b.setTextColor(primary ? Color.WHITE : GREEN); b.setMinHeight(dp(53));
        b.setPadding(dp(10), dp(10), dp(10), dp(10));
        b.setBackground(background(primary ? GREEN : Color.WHITE, primary ? 0 : Color.rgb(201, 220, 208)));
        return b;
    }
    private String number(JSONObject reading, String key, String unit) {
        if (reading == null || reading.isNull(key)) return "— " + unit;
        return String.format(new Locale("pt", "BR"), "%.1f %s", reading.optDouble(key), unit);
    }
    private void render() {
        if (client == null) return;
        boolean online = client.online(); JSONObject reading = client.latest();
        long age = client.age();
        status.setText(online ? "●  Placa conectada" : (client.scanning() && reading == null ? "●  Procurando a placa" : "●  Sem comunicação"));
        status.setTextColor(online ? GREEN : ORANGE);
        if (online) detail.setText("Leitura atualizada há " + (age / 1000) + " s • conexão direta pelo Wi-Fi");
        else if (!client.hasWifi()) detail.setText("Conecte o celular ao mesmo Wi-Fi da placa. Os dados móveis podem continuar ligados.");
        else if (!client.error().isEmpty()) detail.setText(client.error());
        else if (client.selected().isEmpty() && client.boards().size() > 1) detail.setText("Mais de uma placa encontrada. Toque em Escolher placa.");
        else detail.setText("Aguardando uma leitura nova. Confira se a placa está ligada na fonte.");
        boardInfo.setText(client.selected().isEmpty() ? "Busca automática ativa" : client.selected() + "  •  " + client.address());
        temperature.setText(number(online ? reading : null, "temperature", "°C"));
        humidity.setText(number(online ? reading : null, "humidity", "%"));
        energy.setText(!online ? "Aguardando leitura" : reading.isNull("energy") ? "Energia não verificada" : reading.optBoolean("energy") ? "Energia presente" : "Energia ausente");
        energy.setTextColor(online && !reading.isNull("energy") && !reading.optBoolean("energy") ? ORANGE : INK);
        sensorHint.setText(online && reading.isNull("temperature") ? "A placa está conectada, mas o sensor não forneceu temperatura e umidade. Confira a ligação do sensor." : "");
        sensorHint.setVisibility(sensorHint.getText().length() == 0 ? View.GONE : View.VISIBLE);
        scanButton.setText(client.scanning() ? "Procurando…" : "Procurar placa na rede"); scanButton.setEnabled(!client.scanning());
        chooseButton.setVisibility(client.boards().size() > 1 ? View.VISIBLE : View.GONE);
        java.util.List<BoardClient.Sample> samples = client.history();
        long newest = samples.isEmpty() ? 0 : samples.get(samples.size() - 1).received;
        if (newest != drawnSample) { drawnSample = newest; trend.set(samples); }
    }

    private void choose() {
        if (client == null) return;
        java.util.List<BoardClient.Board> boards = client.boards();
        String[] labels = new String[boards.size()];
        for (int i = 0; i < boards.size(); i++) labels[i] = boards.get(i).id + "\n" + boards.get(i).ip;
        new AlertDialog.Builder(this).setTitle("Escolha a placa").setItems(labels, (dialog, i) -> client.select(boards.get(i).id)).setNegativeButton("Voltar", null).show();
    }
    private void manual() {
        EditText input = new EditText(this); input.setSingleLine(); input.setInputType(InputType.TYPE_CLASS_PHONE);
        input.setHint("192.168.1.13"); input.setText(client == null ? "" : client.address()); input.setPadding(dp(22), dp(12), dp(22), dp(12));
        LinearLayout form = new LinearLayout(this); form.setOrientation(LinearLayout.VERTICAL); form.addView(input);
        TextView error = text("", 13, ORANGE, false); error.setPadding(dp(22), 0, dp(22), dp(8)); error.setVisibility(View.GONE); form.addView(error);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("IP local da placa")
            .setMessage("Informe o endereço da placa no mesmo Wi-Fi do celular.")
            .setView(form).setPositiveButton("Conectar", null).setNegativeButton("Cancelar", null).create();
        dialog.setOnShowListener(v -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(button -> {
            try { if (client != null) client.manual(input.getText().toString().trim()); dialog.dismiss(); }
            catch (IllegalArgumentException e) { error.setText(e.getMessage()); error.setVisibility(View.VISIBLE); }
        })); dialog.show();
    }
    private void wifiHelp() {
        new AlertDialog.Builder(this).setTitle("Trocar o Wi-Fi da placa")
            .setMessage("1. Com a placa ligada, segure FLASH por 3 segundos e solte.\n\n2. Nas configurações de Wi-Fi do celular, conecte à rede ClimaGuard da placa usando a senha do seu cartão. Mantenha a conexão mesmo que apareça ‘sem internet’.\n\n3. Abra a configuração abaixo, escolha um Wi-Fi de 2,4 GHz e salve.\n\n4. Volte o celular para o novo Wi-Fi e toque em Procurar placa.")
            .setPositiveButton("Abrir configuração", (dialog, which) -> {
                try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("http://192.168.4.1/"))); }
                catch (ActivityNotFoundException e) { Toast.makeText(this, "Abra http://192.168.4.1/ no navegador.", Toast.LENGTH_LONG).show(); }
            }).setNegativeButton("Fechar", null).show();
    }

    private final class TrendView extends View {
        private java.util.List<BoardClient.Sample> samples = new ArrayList<>();
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        TrendView() { super(MainActivity.this); setMinimumHeight(dp(156)); setContentDescription("Gráfico das últimas temperaturas recebidas nesta sessão"); }
        void set(java.util.List<BoardClient.Sample> value) { samples = value; invalidate(); }
        @Override protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            float width = getWidth(), height = getHeight(), left = dp(40), right = width - dp(8), top = dp(14), bottom = height - dp(28);
            ArrayList<BoardClient.Sample> valid = new ArrayList<>();
            for (BoardClient.Sample s : samples) if (!s.json.isNull("temperature")) valid.add(s);
            paint.setTextSize(dp(12)); paint.setColor(MUTED); paint.setStyle(Paint.Style.FILL);
            if (valid.isEmpty()) { canvas.drawText("Aguardando as primeiras leituras…", 0, height / 2, paint); return; }
            double min = Double.POSITIVE_INFINITY, max = Double.NEGATIVE_INFINITY;
            for (BoardClient.Sample s : valid) { min = Math.min(min, s.json.optDouble("temperature")); max = Math.max(max, s.json.optDouble("temperature")); }
            min = Math.floor(min - .5); max = Math.ceil(max + .5);
            for (int i = 0; i <= 2; i++) {
                float y = top + (bottom - top) * i / 2;
                paint.setColor(Color.rgb(222, 233, 224)); paint.setStrokeWidth(dp(1)); canvas.drawLine(left, y, right, y, paint);
                paint.setColor(MUTED); canvas.drawText(String.format(Locale.ROOT, "%.0f°", max - (max - min) * i / 2), 0, y + dp(4), paint);
            }
            long first = valid.get(0).received, last = valid.get(valid.size() - 1).received;
            Path path = new Path(); float lastX = left, lastY = top;
            for (int i = 0; i < valid.size(); i++) {
                BoardClient.Sample s = valid.get(i);
                float x = left + (right - left) * (s.received - first) / Math.max(1, last - first);
                float y = bottom - (float) ((s.json.optDouble("temperature") - min) / (max - min)) * (bottom - top);
                if (i == 0) path.moveTo(x, y); else if (s.received - valid.get(i - 1).received > 8000) path.moveTo(x, y); else path.lineTo(x, y);
                lastX = x; lastY = y;
            }
            paint.setColor(GREEN); paint.setStrokeWidth(dp(3)); paint.setStyle(Paint.Style.STROKE); canvas.drawPath(path, paint);
            paint.setStyle(Paint.Style.FILL); canvas.drawCircle(lastX, lastY, dp(4), paint);
            paint.setColor(MUTED); SimpleDateFormat time = new SimpleDateFormat("HH:mm:ss", new Locale("pt", "BR"));
            canvas.drawText(time.format(new Date(first)), left, height - dp(6), paint);
            if (last - first > 1000) {
                String label = time.format(new Date(last)); canvas.drawText(label, right - paint.measureText(label), height - dp(6), paint);
            }
        }
    }
}
