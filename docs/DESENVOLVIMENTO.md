# Desenvolvimento e manutenção

Quem só quer instalar deve seguir o [guia do usuário](GUIA-DO-USUARIO.md).

## Executar o código no Windows

Requisitos: Python 3.11 ou superior e, para a janela nativa, as dependências de `requirements-desktop.txt`.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python.exe desktop.py
```

O ponto de entrada é `desktop.py`. Os antigos lançadores `.cmd`, `iniciar_completo.py` e `server.py` foram retirados para evitar dois caminhos de inicialização diferentes. A ponte `receber_usb.py` continua como manutenção interna; o uso normal é Wi-Fi. As opções `--usb` e `--legacy-network` são destinadas à manutenção, não ao primeiro uso.

Para usar o WhatsApp ao executar do código, instale Node.js/npm e execute `python packaging/prepare_whatsapp.py` com o mesmo ambiente Python. A preparação verifica o Node oficial, instala as dependências fixadas pelo lockfile e não baixa um navegador. Chrome ou Edge deve estar instalado. Na instalação pelo EXE, essa preparação já acompanha o aplicativo.

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe packaging/check_publication.py --working-tree
```

Os testes usam serviços simulados, diretórios temporários e não enviam mensagens reais. Os testes do bridge local também usam um Node de teste. O workflow do GitHub prepara esse runtime e executa os testes sem credenciais.

## Preparar uma placa nova

Essa etapa requer uma pessoa que conheça a montagem e uma placa conectada por USB **com a entrada AC do ZMPT101B desconectada**.

1. Confira [ESP32-DEVKIT-ZMPT.md](ESP32-DEVKIT-ZMPT.md), especialmente os limites do GPIO e a montagem protegida do sensor.
2. Instale Arduino IDE, o pacote **esp32 by Espressif Systems**, DHT sensor library, Adafruit Unified Sensor e ArduinoJson. A revisão validada usa Arduino-ESP32 3.3.2, ArduinoJson 7.4.3, DHT 1.4.7 e Adafruit Unified Sensor 1.1.15.
3. Copie `ClimaGuard/config.h.example` para `ClimaGuard/config.h`. Preencha os campos localmente e escolha uma senha exclusiva para a rede de configuração da placa.
4. Abra `ClimaGuard/ClimaGuard.ino`, selecione **ESP32 Dev Module**, perfil `esp32:esp32:esp32`, e a porta da placa.
5. Feche qualquer programa que use essa porta e grave o firmware. O instalador Windows não executa essa operação.
6. Use **Wi-Fi da placa** no aplicativo para salvar a rede do usuário. Entregue o cartão privado da rede de configuração ao proprietário por um meio privado.

O firmware atual do ESP32 é `1.5.2-devkit-wifi`. Mantém o protocolo 2 e corrige a troca de rede enquanto o Wi-Fi anterior está fora de alcance. O programa faz a medição de DHT22 a cada 2,1 segundos. O ZMPT101B começa desativado e só deve ser calibrado após conferir a interface de baixa tensão e uma referência AC conhecida.

Para a NodeMCU ESP8266 legada, use `esp8266:esp8266:nodemcuv2` e a [montagem anterior](legado/MONTAGEM-NODEMCU.md). Não transfira a ligação AC do ESP32 para essa montagem com chave.

## Gerar o instalador Windows

Em Windows x64, instale `requirements-desktop.txt`, Node.js/npm, Inno Setup e obtenha o bootstrapper oficial do Microsoft WebView2. Não use um ambiente Python modificado por outra aplicação para gerar o executável.

```powershell
.\packaging\build_windows.ps1 -Python '.\.venv\Scripts\python.exe' `
  -IsccPath 'C:\ferramentas\Inno Setup 6\ISCC.exe' `
  -Bootstrapper 'C:\ferramentas\MicrosoftEdgeWebview2Setup.exe' `
  -OutputDir '.\dist'
```

O script executa os testes, prepara Node/WPPConnect, confere a assinatura Microsoft do WebView2, gera o executável e executa sua verificação de inicialização antes de criar o instalador. Os intermediários ficam em `work/windows-build/`.

O build inclui somente os arquivos definidos em `packaging/ClimaGuard.spec`. Contas, credenciais, cartões de Wi-Fi, sessões de WhatsApp e firmware com segredos não devem fazer parte do pacote.

## Publicar uma versão

1. Atualize a versão em `desktop.py`, `index.html`, `packaging/installer.iss`, `packaging/version_info.txt`, ajuda, documentação e links de download. Preserve o AppId do instalador.
2. Revise o Git e rode `python packaging/check_publication.py --working-tree`. Depois de preparar o commit, execute também sem essa opção para conferir o conteúdo exato do índice.
3. Gere o instalador e valide `ClimaGuard.exe --self-test relatorio.json`, sem envios reais. Confira uma instalação limpa ou com dados temporários.
4. Envie o commit e crie uma tag para esse mesmo código, por exemplo `v1.6.4`.
5. Crie uma **Release**, anexe o EXE, o guia e `SHA256SUMS.txt` e só publique após conferir os arquivos. Binários devem ir nos arquivos da Release, não no histórico Git.
6. Verifique o link de download sem autenticação. Mantenha as versões anteriores para quem precisa consultar histórico.

Nunca publique `config.h`, flash completa da placa, bancos de dados, chaves de assinatura ou sessões pessoais. O scanner ajuda a detectar erros comuns, mas não substitui a revisão dos arquivos. Veja [SECURITY.md](../SECURITY.md).
