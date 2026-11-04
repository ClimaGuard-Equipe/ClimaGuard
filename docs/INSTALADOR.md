# Instalação do ClimaGuard no Windows

Para instalar e começar, siga o [guia do usuário](GUIA-DO-USUARIO.md). O arquivo público atual é **ClimaGuard-Instalador-1.6.4-x64.exe**, disponível em [Releases](https://github.com/ClimaGuard-Equipe/ClimaGuard/releases/tag/v1.6.4).

## Compatibilidade

- Windows 10/11 de 64 bits, instalado para o usuário atual.
- Python e bibliotecas incluídos. Não é necessário instalar ferramentas de desenvolvimento.
- Microsoft WebView2; se estiver ausente, o instalador oficial incluído precisa de internet.
- Chrome ou Edge instalado para usar o WhatsApp local com WPPConnect.
- Placa já programada para leituras reais. O instalador não grava firmware nem instala drivers USB de terceiros.

## Arquivos e atualização

O programa fica em `%LOCALAPPDATA%\Programs\ClimaGuard`. Dados pessoais ficam em `%LOCALAPPDATA%\ClimaGuard`, separados do programa. Atualizar ou desinstalar preserva a pasta de dados. Cada computador mantém suas próprias contas e configurações.

O aplicativo abre o painel em uma janela e mantém os serviços locais enquanto estiver aberto. O painel usa `127.0.0.1:5000` e o serviço opcional do iPhone usa `127.0.0.1:5003`. Feche instâncias de desenvolvimento que já utilizem essas portas.

O instalador do projeto ainda não possui assinatura digital própria. O componente WebView2 incluído tem assinatura da Microsoft. Não desative o antivírus para instalar; use a origem oficial do projeto e respeite as regras do computador.

## Verificação opcional do download

A versão publicada inclui `SHA256SUMS.txt`. Usuários técnicos podem comparar o SHA-256 do EXE baixado com esse arquivo. Um hash confirma integridade em relação ao manifesto; não substitui uma assinatura digital.

As instruções para compilar e publicar uma versão estão em [DESENVOLVIMENTO.md](DESENVOLVIMENTO.md).
