# Placa autônoma e busca na rede

A placa executa as medições sozinha, ligada apenas à fonte USB. O computador procura a placa e consulta os dados pela rede local. A placa usa Wi-Fi de 2,4 GHz; o computador pode estar no Wi-Fi ou na Ethernet do mesmo roteador.

## Uso diário

1. Use a placa já programada com o firmware atual e o aplicativo da versão publicada.
2. Ligue a placa na fonte e abra o ClimaGuard.
3. O aplicativo verifica todas as interfaces IPv4 ativas, incluindo cabo e Wi-Fi. Com uma única placa encontrada, conecta automaticamente. Com mais de uma, pede a seleção.
4. O indicador no alto da janela mostra **Placa conectada** apenas com amostras recentes. O cartão **Placa na rede** informa modelo, IP e horário da última comunicação.
5. **Procurar placa** repete a descoberta. **Conectar pelo IP da placa** é uma alternativa para roteadores que bloqueiam broadcast entre Ethernet e Wi-Fi.

Se o endereço da placa mudar, o aplicativo a procura pelo identificador persistente. Se a comunicação parar, o indicador muda para **Sem comunicação** em até 20 segundos. Respostas HTTP com amostras congeladas não mantêm o indicador verde. A demonstração não conta como prova de comunicação física.

## Outro computador

Instale o aplicativo no outro computador, crie sua conta e abra **Placa real**. Não é necessário copiar o token, a senha da conta ou o endereço do primeiro notebook. Vários computadores podem consultar a mesma placa sem mudar seu destino ou disputar o envio das leituras.

Cada instalação mantém seus próprios usuários, preferências, credenciais de provedores e histórico. Configure notificações nos computadores que devem enviar os relatórios. A conexão pelo cabo precisa pertencer à mesma rede local da placa; redes de convidados, isolamento de clientes ou roteadores separados podem impedir a comunicação. Se o acesso direto ao IP também falhar, é necessário conferir a configuração da rede.

## Protocolo

O computador envia `CLIMAGUARD_FIND_V2` com um identificador aleatório por UDP 5002 em cada interface de rede. A placa responde ao endereço e porta de origem com o mesmo identificador, seu ID estável, modelo e a porta do serviço. O aplicativo verifica a resposta e consulta `GET /climaguard/status` por HTTP na porta 80 da placa.

O serviço da placa fornece somente leituras locais: temperatura, umidade, estado de energia, identificação e sequência. Não fornece senha do Wi-Fi, token do receptor ou credenciais de envio, e não permite comandos nem alterações de configuração. As leituras ficam acessíveis aos dispositivos da rede local. Não configure redirecionamento de portas no roteador.

Cada amostra tem sequência, identificador de inicialização e idade. O PC descarta amostras repetidas, inválidas ou antigas e usa somente amostras novas para alimentar o histórico e as regras de alerta. A busca aceita somente IPs das redes locais das interfaces ativas, sem seguir redirecionamentos HTTP ou consultar URLs fornecidas por anúncios.

O aplicativo Windows usa conexões de saída para procurar e ler a placa; o painel fica em `127.0.0.1:5000`. O modo antigo de recebimento HTTP permanece disponível com `--legacy-network` para manutenção de firmware anterior. A ponte USB é opcional com `--usb`; não a use junto com a leitura de rede da mesma placa.

## Gravação

A placa atual é o ESP32 DevKit V1, ESP-WROOM-32, com perfil `esp32:esp32:esp32`. O DHT22 usa GPIO4; o ZMPT101B usa GPIO34/ADC1 com adaptação de tensão e calibração. Veja [o guia do ESP32](ESP32-DEVKIT-ZMPT.md). A NodeMCU ESP8266 continua como compatibilidade legada, descrita em [Montagem anterior](legado/MONTAGEM-NODEMCU.md).

`ClimaGuard/config.h` precisa apenas de `WIFI_SSID` e `WIFI_PASSWORD`, conforme o exemplo. O arquivo é privado e ignorado pelo Git. A placa não precisa conhecer o endereço do PC nem sua chave local. O instalador atualiza o aplicativo do PC; a gravação inicial ou atualização do firmware da placa requer cabo USB de dados e a ferramenta de gravação.

## Funcionamento e limites

No firmware 1.5, as medições são atualizadas a cada 2,1 segundos, respeitando o intervalo mínimo de 2 segundos do DHT22/AM2302. Mudanças na chave são publicadas após 80 ms de estabilização, sem esperar a próxima medição de temperatura. O computador consulta a placa a cada 200 ms e o painel a cada 250 ms; a busca na rede acontece em paralelo. Novos alertas despertam a fila de envio após serem salvos. A rede, o tempo físico de resposta do sensor e os serviços de mensagens podem acrescentar demora; esses intervalos não garantem entrega instantânea. O Wi-Fi tenta reconectar automaticamente. As amostras antigas não ficam armazenadas na placa; após uma interrupção, o PC volta a receber as próximas.

O notebook recebe e guarda as leituras e executa os envios por Resend, Twilio e WPPConnect. A conexão da placa não comprova a entrega das notificações. O computador precisa permanecer ligado, sem suspensão, e com internet para os envios.

Na NodeMCU legada, a chave simula presença de energia. No ESP32, o ZMPT101B detecta presença/ausência de AC somente após a configuração descrita no guia do sensor. Se a própria placa perder toda a alimentação, não consegue fornecer um aviso. Não conecte os pinos à rede elétrica de 127/220 V.
