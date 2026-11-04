# ClimaGuard no Android

O APK instala diretamente no Android 8 ou superior, incluindo o Redmi Note 12. O aplicativo consulta a placa pelo Wi-Fi local: **o computador pode ficar desligado**. A placa continua ligada apenas na fonte e conectada ao roteador.

## Instalar e conectar

1. Copie `ClimaGuard-Android-1.0.1.apk` para o celular pelo cabo USB, pendrive compatível ou transferência de arquivos.
2. Abra o APK no gerenciador de arquivos. Se o Android pedir, autorize essa instalação pelo aplicativo que abriu o arquivo. O próprio usuário deve confirmar a instalação.
3. Abra o ícone **ClimaGuard** e conecte o Redmi ao mesmo roteador da placa.
4. Toque em **Procurar placa na rede**. Se encontrar uma única placa, o aplicativo conecta automaticamente. Quando houver mais de uma, use **Escolher placa**.
5. Se o roteador bloquear a busca, use **Conectar pelo IP**. O endereço precisa pertencer à rede Wi-Fi do celular e responder com a identificação ClimaGuard. Use o endereço atual da sua placa, informado pelo roteador ou pela equipe que a preparou.

As bandas de 2,4 e 5 GHz podem ser usadas, desde que o roteador permita a comunicação entre elas. A placa usa 2,4 GHz. Redes de visitantes e isolamento entre dispositivos podem impedir a conexão. O aplicativo direciona as consultas pela interface Wi-Fi, mesmo com dados móveis ligados.

O indicador fica verde somente com leituras novas e contato recente. Temperatura e umidade atualizam conforme o sensor, a cada aproximadamente 2,1 segundos. O aplicativo consulta a placa a cada 250 ms após a resposta anterior. O estado de energia vem do firmware: ZMPT101B no ESP32, após calibração, ou chave simuladora na NodeMCU legada. A interface não mede a tensão da rede em volts.

O gráfico mostra as últimas 120 leituras desta sessão. Ao sair do aplicativo, as consultas param; ao voltar, ele retoma a conexão. Não há serviço de monitoramento em segundo plano nesta versão. Sensor com falha aparece sem valores de temperatura/umidade, mantendo a indicação da comunicação da placa.

## Trocar o Wi-Fi

O botão **Trocar o Wi-Fi da placa** explica o procedimento do firmware atual: segurar FLASH por três segundos com a placa já ligada, entrar na rede ClimaGuard usando a senha do cartão e abrir `http://192.168.4.1/`. Depois de salvar, reconecte o Redmi ao novo Wi-Fi e procure a placa.

A revisão Android 1.0.1 também aceita o diagnóstico do ZMPT101B no ESP32 DevKit V1. Energia nula aparece como não verificada, sem indicar uma falta de energia inexistente.

## Alcance desta versão

Esta versão é de **acesso local**, conforme solicitado. Não usa Firebase, Tailscale nem servidor no computador. Não oferece acesso por 4G/5G fora de casa. Os envios de e-mail, SMS e WhatsApp continuam pertencendo ao aplicativo Windows e exigem que ele esteja funcionando e configurado. O APK não executa os serviços de envio nem os altera.

A placa com firmware 1.5.0 já oferece o protocolo necessário; não é preciso atualizar a placa para usar este APK. A consulta local usa o HTTP disponibilizado pela placa, destinado à rede doméstica. Não encaminhe a porta da placa para a internet.

## Desenvolvimento e assinatura

Projeto nativo Java em `android/`, sem dependências de interface externas. Compilação com JDK 17, Gradle 8.11.1, Android Gradle Plugin 8.10.1, SDK 36 e Build Tools 35.0.0:

```powershell
.\packaging\build_android.ps1 -OutputDir 'C:\caminho\para\entregas'
```

O script executa os testes de protocolo, o lint, compila e verifica a assinatura do APK. A chave de assinatura fica em `%LOCALAPPDATA%\ClimaGuard\android-signing\release.jks`; a senha é protegida pelo Windows para este usuário em `password.dpapi`. Preserve essa pasta e a conta Windows: atualizações devem ser assinadas com a mesma chave. O APK não contém essa chave privada, credenciais do Wi-Fi ou tokens dos provedores de envio.

O aplicativo solicita apenas internet, estado da rede e bloqueio multicast para descoberta. Para o SDK alvo 36, a permissão de acesso local é implícita com INTERNET, conforme a [documentação do Android](https://developer.android.com/privacy-and-security/local-network-permission). A publicação futura com SDK alvo 37 exige implementar a nova permissão em tempo de execução.
