# ESP32 DevKit V1 e ZMPT101B

Esta revisão parte do firmware 1.5 e mantém o protocolo de rede 2, a descoberta UDP na porta 5002, a consulta HTTP em `/climaguard/status` e o DHT22 a cada 2,1 segundos. O ESP32 usa o firmware `1.5.2-devkit-wifi`; a compilação para a NodeMCU ESP8266 continua com a chave digital anterior.

## Placa e sensores

| Componente | Ligação de baixa tensão no ESP32 DevKit V1 |
| --- | --- |
| DHT22/AM2302 VCC | 3V3 |
| DHT22 DATA | GPIO4, também marcado D4 em algumas placas |
| DHT22 GND | GND |
| Pull-up do DHT22 | 4,7 kΩ entre DATA e 3V3; 10 kΩ pode funcionar com fios curtos |
| ZMPT101B OUT | GPIO34, com adaptação de tensão se a saída do módulo exceder a faixa da entrada |
| ZMPT101B GND | GND do circuito de baixa tensão |
| ZMPT101B VCC | Alimentação regulada compatível com o módulo; nos módulos de 5 V, usar 5 V verificados |

O módulo pode incluir amplificador, ajuste de ganho e polarização do sinal. Confirme a faixa completa de OUT na alimentação especificada para a sua variante. A ligação direta ao GPIO34 é adequada quando toda a forma de onda cabe na faixa de medição do ADC, de aproximadamente 0,15 a 3,1 V na configuração usada pelo projeto. Se a saída puder exceder essa faixa, use uma interface adequada.

Para um módulo cuja saída está limitada a 0–5 V, um exemplo de divisor é:

```text
OUT do módulo ── 10 kΩ ──┬── GPIO34 (ADC1)
                         │
                       10 kΩ
                         │
                    GND baixa tensão
```

Esse divisor reduz pela metade a tensão e a amplitude do sinal. Confirme que a forma de onda resultante continua dentro da faixa do ADC e tem amplitude suficiente para calibrar. A atenuação configurada no software não protege o pino contra sobretensão. O GPIO34 pertence ao ADC1 e pode ser utilizado junto com o Wi-Fi.

**A parte AC exige montagem e conferência por professor ou técnico qualificado, com isolamento e proteção física. Não use a protoboard para a rede elétrica. Nunca ligue fase/neutro aos GPIOs, ao GND do ESP32 ou ao USB. Para gravar pelo computador, deixe a entrada AC do módulo desligada.** Este documento descreve a interface de baixa tensão, não um procedimento de montagem da rede elétrica.

## Primeiro uso e calibração

O sensor começa **desativado** e o firmware informa `energy: null`. Isso significa energia não verificada, não falta de energia. Assim, enquanto o ZMPT não estiver montado, ele não gera uma condição falsa de ausência de energia.

Depois de a montagem protegida estar conferida:

1. Alimente a placa de maneira independente do computador.
2. Com a placa já ligada, segure **BOOT por três segundos** e solte. Não mantenha BOOT pressionado ao ligar a placa.
3. Conecte o celular à rede de configuração ClimaGuard usando o cartão da **placa nova**.
4. Abra `http://192.168.4.1/` e toque em **Configurar o sensor de energia ZMPT101B**. Também pode abrir `http://192.168.4.1/power`.
5. Com uma condição de referência conhecida de AC presente e a montagem protegida, confirme a caixa e toque em **Calibrar e ativar**. Se o sinal estiver ausente, saturado ou sem qualidade suficiente de 50/60 Hz, a ativação é recusada.
6. A referência fica salva na memória da placa. Volte o celular à rede do roteador e procure a placa no aplicativo.

O sistema coleta janelas de aproximadamente 200 ms em uma tarefa separada. Calcula a amplitude RMS do sinal analógico após remover o nível DC, verifica a componente de 50/60 Hz e confirma mudanças em duas janelas. Os limiares são 35% da referência para presença e 20% para ausência, com histerese. Ruído forte sem componente AC reconhecível, saturação, falha de amostragem e sinal incompatível tornam a energia indisponível; não equivalem automaticamente a falta de energia.

A calibração é de **presença/ausência**, não de tensão em volts. O código não inventa valores de 127 ou 220 V. Para medição de tensão absoluta seria necessária outra calibração e validação com instrumento apropriado.

O ESP32 precisa continuar alimentado quando a rede monitorada faltar. Se ele também desligar, o aplicativo observará perda de comunicação; a placa não poderá transmitir a ausência de energia. Use alimentação de reserva se esse for o objetivo.

## Comunicação e compatibilidade

Cada placa tem uma identidade derivada do MAC. A placa nova exige uma nova busca/seleção; o aplicativo preserva a identificação anterior para evitar trocar de aparelho silenciosamente. Não reutilize o IP da placa antiga como garantia de endereço fixo.

Leituras válidas do DHT22 continuam funcionando com o aplicativo Windows 1.5 mesmo enquanto `energy` está nulo. O receptor atualizado também aceita o diagnóstico explícito do ZMPT quando todos os sensores estão indisponíveis. Mensagens e rótulos do código atualizado diferenciam o estado real dos cenários simulados. Atualizar o firmware não substitui sozinho o executável Windows já instalado.

O ponto de acesso do iPhone deve estar com **Maximizar Compatibilidade** ativo para o ESP32 usar 2,4 GHz. O nome da rede deve ser preservado exatamente, inclusive eventuais espaços ao final.

## Compilar

Use **ESP32 Dev Module** (`esp32:esp32:esp32`) para o ESP32 clássico ESP-WROOM-32, e não uma variante C3/S3 ou NodeMCU ESP8266. Dependências: DHT sensor library, Adafruit Unified Sensor e ArduinoJson. O ambiente desta revisão usa Arduino-ESP32 3.3.2.

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32 ClimaGuard
arduino-cli upload --fqbn esp32:esp32:esp32 --port COM9 ClimaGuard
```

Não compartilhe `ClimaGuard/config.h`, cópias completas da flash, binários com credenciais ou o cartão privado da rede de configuração. O arquivo de exemplo não contém credenciais.

## Diagnóstico USB

115200 baud, JSON em uma linha com `request_id` de 32 caracteres hexadecimais. Comandos: `power_status`, `power_disable`, `power_selftest`. O teste interno exercita sinais sintéticos de 50/60 Hz, ausência, entrada sem sinal, saturação e confirmação de estado; não injeta leituras no aplicativo nem aciona notificações. `power_calibrate` exige `reference_ac_present: true` e uma referência física válida. Prefira a página de configuração para uso normal.

## Referências

- [ADC no Arduino-ESP32 — Espressif](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html)
- [Canais ADC e limitação de ADC2 com Wi-Fi — Espressif](https://docs.espressif.com/projects/esp-idf/en/v4.4.8/esp32/api-reference/peripherals/adc.html)
- [Exemplo de datasheet de módulo ZMPT101B — ADIY](https://adiy.in/wp-content/uploads/2023/07/ADIY-ZMPT101B-AC-Single-Phase-Voltage-Sensor-Module_datasheet.pdf): confirme as especificações do módulo efetivamente comprado.
