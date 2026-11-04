# WhatsApp no próprio notebook

O ClimaGuard 1.1 inclui o WPPConnect 2.3.5, um projeto brasileiro de código aberto.
O aplicativo inicia uma sessão própria e isolada do Chrome/Edge e conversa com ela
somente pelo endereço local do notebook, com uma chave aleatória por execução.
Não há cadastro nem mensalidade de empresa de API para esta opção.

1. Abra **Serviços de envio** como administrador.
2. Em **Serviço de WhatsApp**, selecione **WPPConnect**.
3. Clique em **Conectar WhatsApp / atualizar QR Code**.
4. No celular, abra **WhatsApp → Aparelhos conectados → Conectar um aparelho**.
5. Leia o QR Code e aguarde o estado **WhatsApp conectado**.
6. Em **Meus alertas**, salve o número autorizado e clique em **WhatsApp** para testar.
7. Consulte **Histórico**. Aceito não significa entrega confirmada; use **Consultar entrega**.

A vinculação permite enviar mensagens pela conta conectada ao notebook. Para
revogar o acesso, remova o dispositivo pelo próprio WhatsApp. **Pausar conexão**
fecha a sessão local sem apagar o vínculo do celular. Ao reabrir o aplicativo,
uma sessão existente pode ser retomada. Fechar o ClimaGuard encerra o processo
auxiliar e seu navegador. Nenhuma conversa recebida ou lista de contatos é
solicitada pela integração do ClimaGuard.

O aplicativo, o notebook e a internet precisam permanecer disponíveis. Use Edge
ou Chrome atualizado. Esta integração não é oficial da Meta; mudanças no WhatsApp
podem exigir atualização e podem causar desconexões ou bloqueios. Prefira um
número destinado ao projeto. O funcionamento deve ser validado com um envio real.

As credenciais de e-mail e SMS são independentes da escolha do WhatsApp.
O modo de demonstração não envia mensagens para nenhum canal.

## Compilação e manutenção

`packaging/prepare_whatsapp.py` obtém o Node.js oficial com SHA-256 verificado e
instala as dependências exatas do `package-lock.json`, sem scripts de instalação
nem download de navegador. O instalador inclui o runtime, as bibliotecas e suas
licenças, mas não inclui sessões de WhatsApp ou credenciais do usuário.

O código da integração fica em `whatsapp_local/bridge.js` e `whatsapp_local.py`.
A biblioteca WPPConnect fica como arquivos substituíveis em `node_modules`.
Fonte upstream: https://github.com/wppconnect-team/wppconnect
Licença da biblioteca instalada: LGPL-3.0-or-later. O runtime Node.js inclui
seu próprio arquivo `Node-LICENSE.txt`.

O audit de dependências identificou avisos em utilitários transitivos de FTP e
extração de arquivos usados pelas ferramentas de download do Puppeteer. O
ClimaGuard usa um navegador já instalado, não oferece downloads nem extração
por HTTP e não recebe destinos de rede ou arquivos do usuário nessa integração.
Reavalie esses avisos ao atualizar WPPConnect/Puppeteer; não faça downgrade da
biblioteca para suprimir o relatório.
