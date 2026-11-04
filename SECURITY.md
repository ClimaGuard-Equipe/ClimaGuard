# Segurança e dados privados

Use o ClimaGuard em uma rede de confiança. As leituras do ESP32 são locais e o painel principal do computador fica restrito ao próprio computador. Não exponha as portas do aplicativo ou da placa à internet. O acesso opcional do iPhone utiliza Tailscale e autorização própria.

Não inclua em commits, issues, comentários ou releases:

- `ClimaGuard/config.h`, senhas de Wi-Fi e cartões de configuração;
- chaves de Resend/Twilio, tokens, `.providers.json`, `.device-token` e `.session-secret`;
- bancos de dados, logs com informações pessoais, sessões WebView e sessões de WhatsApp;
- chaves de assinatura Android, arquivos DPAPI e backups completos da flash;
- dependências, ambientes locais e instaladores no histórico Git.

Se uma chave for exposta, revogue-a no provedor e gere outra. Apagar a linha em um commit novo não remove a exposição do histórico. Preserve os dados necessários para investigar sem republicar o segredo.

Para relatar uma vulnerabilidade, use o [canal privado do GitHub, se habilitado](https://github.com/ClimaGuard-Equipe/ClimaGuard/security/advisories/new), ou contate um mantenedor por um canal privado já conhecido. Não publique o segredo em uma issue para pedir ajuda.

O projeto é acadêmico. A montagem com tensão de rede deve ser feita e conferida por pessoa qualificada, com isolamento e proteção física. O software não transforma uma montagem improvisada em um equipamento certificado.
