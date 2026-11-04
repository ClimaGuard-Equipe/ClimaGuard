# ClimaGuard no iPhone

O aplicativo Windows 1.6 inclui uma versão para abrir pelo Safari e adicionar à Tela de Início. O layout se adapta ao iPhone 15, 15 Pro Max e 16 Pro Max. Não exige Mac, Xcode nem publicação na App Store.

O iPhone acompanha temperatura, umidade, estado da chave de energia, gráfico e os avisos da conta autorizada. A configuração de limites, destinatários e serviços de envio continua no computador. A tela recebe atualizações enquanto está aberta; o envio de notificações continua pelos canais configurados no PC, sem web push próprio.

## Uma vez no computador

1. Instale a versão 1.6 do ClimaGuard e mantenha o programa aberto.
2. Instale o [Tailscale para Windows](https://tailscale.com/download/windows). A instalação pode exigir autorização de administrador do Windows.
3. Entre com uma conta pessoal. O plano Personal atende ao uso pessoal deste projeto; confira o plano no cadastro.
4. Abra **No iPhone** no ClimaGuard. Se necessário, crie sua conta do ClimaGuard ou entre na conta cujos avisos deseja acompanhar.
5. Clique em **Preparar acesso remoto**. Se aparecer um link de autorização de HTTPS, abra-o, aprove no Tailscale e clique no botão novamente.
6. Quando aparecer o endereço `https://NOME.DO.COMPUTADOR.ts.net:8443`, o acesso privado estará pronto. O endereço real é determinado pela sua conta Tailscale.

## Em cada iPhone

1. Instale o [Tailscale pela App Store](https://apps.apple.com/app/tailscale/id1470499037), entre na mesma conta pessoal e autorize a configuração VPN quando o iOS solicitar. Mantenha o Tailscale conectado.
2. No ClimaGuard do computador, clique em **Gerar código para um iPhone**.
3. Escaneie o QR Code com a câmera e abra no Safari. Dê um nome ao aparelho, como “iPhone 15 Pro Max”, e autorize.
4. No Safari, use **Compartilhar → Adicionar à Tela de Início**. Ative **Abrir como App da Web**, se a opção aparecer, e toque em **Adicionar**.
5. Abra pelo novo ícone. Se o ícone pedir autorização novamente, gere outro código no computador e digite-o. O Safari e o app da Tela de Início podem manter sessões separadas.
6. Repita para os outros dois iPhones, gerando um código novo para cada um.

Cada código vale por 5 minutos e é usado uma vez. A autorização de cada aparelho vale por 30 dias, pode ser renovada com outro código e pode ser removida individualmente pelo computador.

## Fora de casa

Mantenha o computador ligado, sem suspensão, com o ClimaGuard, Tailscale e internet funcionando. A placa fica na rede Wi-Fi do computador; o iPhone pode usar 4G/5G ou outro Wi-Fi. O telefone precisa continuar conectado ao Tailscale.

Para conferir o acesso externo, desligue apenas o Wi-Fi de um iPhone, mantenha os dados móveis e o Tailscale ativos, abra o ícone e confira se a hora da última leitura continua mudando. A resposta do acesso remoto depende da conexão móvel. A medição física permanece no intervalo de aproximadamente 2,1 segundos.

Sem acesso ao computador, a interface informa indisponibilidade. Apenas os arquivos da interface são guardados para abertura sem conexão; leituras e avisos nunca são tratados como dados ao vivo a partir do cache.

## Detalhes para manutenção

O serviço móvel usa `127.0.0.1:5003`, separado do painel administrativo em `127.0.0.1:5000`. O Tailscale Serve fornece HTTPS privado na porta 8443, sem habilitar Funnel nem publicar o painel de configuração. Outros serviços existentes nas portas 443 ou 8443 são preservados; uma ocupação da 8443 impede a preparação automática.

As autorizações são guardadas em `%LOCALAPPDATA%\ClimaGuard\.mobile-devices.json`, apenas como hashes de tokens. Os códigos de uso único ficam em memória e expiram. Senhas e chaves dos provedores não são enviadas ao celular. O cookie da autorização usa Secure, HttpOnly e SameSite=Strict. Nenhuma senha da conta do ClimaGuard é digitada no celular.

Fontes: [Adicionar um app da web ao iPhone — Apple](https://support.apple.com/guide/iphone/iphea86e5236/ios), [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve), [Plano pessoal do Tailscale](https://tailscale.com/pricing).
