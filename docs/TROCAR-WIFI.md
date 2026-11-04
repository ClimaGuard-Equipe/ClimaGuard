# Trocar o Wi-Fi sem regravar a placa

Requer firmware e aplicativo 1.4 ou superior. Depois dessa atualização, mudar de rede não exige alterar código, instalar Arduino nem gravar novamente.

## Pelo celular, sem cabo

1. Guarde uma foto do cartão com QR Code da sua placa. Ele aparece em **Wi-Fi da placa → Configurar pelo celular sem cabo / cartão da placa** após **Verificar placa USB**. O cartão entregue com a placa também pode ser usado, inclusive em outro computador.
2. Ligue a placa normalmente e aguarde cerca de 5 segundos. Com ela **já ligada**, segure **FLASH por 3 segundos** e solte. Não mantenha FLASH pressionado enquanto liga ou reinicia: isso inicia o modo de gravação da placa.
3. Conecte o celular ao Wi-Fi **ClimaGuard-XXXXXX** da placa usando o QR Code ou a senha do cartão.
4. Abra **http://192.168.4.1**. Se o celular avisar que essa rede não tem internet, permaneça conectado; isso é normal.
5. Selecione a nova rede de **2,4 GHz**, informe a senha e toque em **Salvar e conectar**. Também é possível digitar o nome de uma rede oculta.
6. Aguarde a confirmação. Depois, volte o celular e o computador à mesma rede da placa e abra o ClimaGuard.

Se a placa não conseguir entrar na rede conhecida por cerca de 30 segundos, ela abre a rede de configuração automaticamente. Isso permite configurá-la em outra casa sem acesso ao roteador anterior. A senha da rede de configuração é exclusiva da placa e permanece no cartão.

## Pelo aplicativo com USB

1. Conecte a placa à USB do computador e feche o Monitor Serial do Arduino.
2. Abra **Wi-Fi da placa** no menu lateral ou **Configurar Wi-Fi pela USB** na Visão geral. Essa tela funciona mesmo quando a placa está sem conexão à rede.
3. Escolha a porta USB (por exemplo, COM9). Use **Atualizar portas USB** se conectou o cabo depois de abrir a tela e **Verificar placa USB** para confirmar a placa. Preencha o nome e a senha do novo Wi-Fi de 2,4 GHz.
4. Clique em **Salvar Wi-Fi na placa pela USB** e aguarde o teste da conexão.
5. Se necessário, conecte também o computador ao novo roteador e use **Procurar placa**. Depois a placa pode voltar à fonte.

**Verificar placa USB** também salva o cartão e o QR Code da rede de configuração. Eles ficam na seção **Configurar pelo celular sem cabo / cartão da placa**. **Abrir configuração sem apertar BOOT** permite continuar pelo celular.

## Como a configuração é preservada

As credenciais são salvas na memória da placa somente após ela conectar com sucesso à nova rede. Se a senha ou rede falhar, a configuração anterior é mantida e você pode tentar novamente. A gravação usa um arquivo temporário e substituição no LittleFS, para não apagar antes de ter uma configuração válida.

A configuração persiste ao desligar e também tem prioridade sobre os valores iniciais do firmware. O aplicativo não guarda a senha do Wi-Fi nas preferências, no histórico nem nos provedores de envio. A senha é transmitida somente pela USB local ou pelo portal da rede de configuração da própria placa.

O portal de configuração só aceita alterações pela interface Wi-Fi de configuração. Outros aparelhos conectados ao roteador continuam podendo ler os sensores, mas não conseguem usar esse portal para trocar a rede. Os formulários também usam um código de sessão para evitar requisições de outras páginas.

O modo de configuração fecha automaticamente depois de uma configuração bem-sucedida ou após 10 minutos se a placa já estiver conectada. Enquanto ela estiver sem conexão, permanece disponível para permitir recuperação. A página oferece a opção de fechar a configuração.

O modelo atual é o ESP32 DevKit V1, com DHT22 no GPIO4 e entrada do ZMPT101B no GPIO34. O firmware legado da NodeMCU ESP8266 também mantém suporte à troca de rede. A troca de Wi-Fi não altera o programa de medição nem configura e-mail, SMS ou WhatsApp; esses serviços permanecem no computador.

## Desenvolver e compilar

Use o core ESP8266 3.1.2, ArduinoJson 7.4.3, DHT sensor library 1.4.7 e Adafruit Unified Sensor 1.1.15. Além do SSID e senha iniciais, `config.h` define `WIFI_SETUP_PASSWORD`, uma senha exclusiva de 8 a 63 caracteres para a rede de configuração. Esse arquivo é privado e não entra no Git nem no instalador.

O protocolo serial identifica a placa antes de receber as credenciais e associa cada resposta ao identificador da requisição. Operações concorrentes e uma placa diferente da selecionada são rejeitadas. Os cartões locais ficam em `%LOCALAPPDATA%\ClimaGuard\.wifi-setup-cards.json`, acessíveis no painel somente ao administrador. A configuração direta pela USB pode ser feita por qualquer conta local autenticada; ela não revela o cartão privado.
