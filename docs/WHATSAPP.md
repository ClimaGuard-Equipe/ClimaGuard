# WhatsApp com Twilio

O ClimaGuard envia as notificações pelo servidor Python do notebook. Não é necessário alterar o firmware da placa para configurar o WhatsApp.

O clone do Git não inclui credenciais, contas do painel nem o banco de dados do computador do seu colega. Configure os serviços neste notebook ou transfira esses dados por um meio privado. Não envie tokens no chat nem os publique no Git.

## 1. Primeiro confirme o teste na própria Twilio

1. Entre na conta usada no projeto em https://console.twilio.com/.
2. Abra **Try out WhatsApp / Send a WhatsApp message**. No console legado, procure **Messaging → Try it out → Send a WhatsApp message**.
3. Vincule **o celular que vai receber os alertas**: leia o QR code ou envie a mensagem `join ...` indicada pela sua conta para o número mostrado. Aguarde a confirmação no WhatsApp. Não invente o código `join`.
4. Envie a mensagem de exemplo pela própria Twilio e confirme que ela chegou no celular.
5. Na requisição de exemplo, identifique o **From** de WhatsApp e, quando houver, o **ContentSid** que começa com `HX`. Use o Account SID e o Auth Token da mesma conta ou subconta.

O remetente WhatsApp pode ser diferente do remetente de SMS. Copie os valores mostrados na sua conta; o número de teste pode variar. Verificar um número por SMS não substitui a vinculação do dispositivo ao WhatsApp.

Se o teste na Twilio falhar, consulte os logs dessa tentativa. Uma alteração no código do ClimaGuard não consegue concluir a vinculação de um celular nem liberar uma conta bloqueada pelo provedor.

## 2. Escolha o caminho da sua conta

### Novo trial da Twilio: comprovar o recebimento de um exemplo

Na aba **Serviços de envio** do ClimaGuard:

1. Escolha **Novo trial: somente mensagens predefinidas**.
2. Preencha Account SID, Auth Token e **Remetente WhatsApp**, com o `From` da etapa anterior. O prefixo `whatsapp:` é opcional nesse campo.
3. Preencha **Modelo WhatsApp (ContentSid)** com o `HX...` da requisição de teste que funcionou na Twilio.
4. O campo de variáveis é ignorado nesse modo: o novo trial aceita somente o modelo fornecido pela Twilio, sem personalizações.
5. Ative **Envios reais** e salve os serviços.

Esse caminho envia um exemplo fixo. Ele comprova a comunicação pelo WhatsApp, mas **não envia temperatura nem umidade**. Se o professor exigir os valores reais dentro da mensagem, será necessário um ambiente que permita conteúdo personalizado.

### Conta com conteúdo personalizado ou Sandbox legado: enviar o texto do alerta

1. Confirme que a sua conta permite mensagens personalizadas e escolha **Envio personalizado liberado / Sandbox legado**.
2. No Sandbox legado, faça o `join` indicado pela conta. A vinculação expira após três dias; refaça-a quando necessário.
3. Para texto livre, envie uma mensagem do seu celular para o remetente de WhatsApp da Twilio. Isso abre uma janela de atendimento de 24 horas.
4. Em **Serviços de envio**, configure as credenciais e o remetente WhatsApp; deixe **Modelo WhatsApp (ContentSid)** vazio. Se já havia um modelo salvo, apague o campo e salve novamente. Ative os envios reais.
5. Dentro da janela, o ClimaGuard enviará o texto do alerta. Para uma apresentação, envie uma nova mensagem do celular antes de começar.

Fora da janela de 24 horas, configure um modelo aprovado na Twilio. Para um modelo com a variável `{{1}}` reservada ao texto do alerta, use:

```json
{"1":"{message}"}
```

Se o modelo tiver outras variáveis, preencha todas conforme a definição aprovada. Exemplo para um modelo cujo primeiro campo seja o local e o segundo seja o alerta:

```json
{"1":"Laboratório","2":"{message}"}
```

`{message}` é substituído pelo texto gerado pelo ClimaGuard antes de a requisição ser enviada. Não coloque o alerta inteiro na variável de um modelo que espera outra informação, como a data de uma consulta. Use `{}` para testar modelos sem substituições; eles não servem para relatar os dados do sensor.

## 3. Teste no painel

1. Abra o ClimaGuard pelo ícone ou menu Iniciar.
2. Entre no painel em http://127.0.0.1:5000/. A primeira conta criada no notebook será administradora.
3. Em **Meus alertas**, ative os alertas, selecione WhatsApp e informe o destinatário com `+`, país, DDD e número, sem espaços. Use o mesmo número vinculado na Twilio.
4. Marque a autorização de envio e **salve as preferências**.
5. Clique em **WhatsApp** na área de teste e confirme o destinatário.
6. No **Histórico**, aguarde o processamento. Quando aparecer **Aceito pelo serviço**, clique em **Consultar entrega**. O botão consulta o envio existente; não manda outra mensagem.

**Entregue** e **Lido** dependem da confirmação da Twilio; a leitura depende também das configurações do destinatário. Se o resultado ainda estiver em processamento, aguarde alguns instantes e consulte novamente.

O modo **Demonstração** continua sem enviar mensagens externas. Para testar um alerta da placa, use o modo real, uma conta com conteúdo personalizado e uma leitura que ultrapasse o limite salvo. A condição precisa se recuperar e respeitar o intervalo mínimo antes de gerar outro alerta.

## Erros que o painel ajuda a identificar

| Código / resultado | O que conferir |
| --- | --- |
| 63007 | O `From` precisa estar habilitado para WhatsApp na mesma conta das credenciais; não copie automaticamente o remetente SMS. |
| 63015 | O celular destinatário precisa fazer o `join` no Sandbox correto. Refazer o `join` resolve vínculos expirados. |
| 63016 | Abra novamente a janela de 24 horas enviando uma mensagem do celular, ou use um modelo aprovado. |
| 21656 | As variáveis devem corresponder ao modelo, com valores de texto válidos. O novo trial envia apenas `ContentSid`. |
| 21608 | Verifique o destinatário na conta de teste da Twilio. |
| 20003 | Revise Account SID, Auth Token e a conta/subconta proprietária do remetente. |
| Aceito, mas não chega | Clique em **Consultar entrega** e confira os logs na Twilio. Não repita o envio antes de entender o resultado. |

A documentação da Twilio informa que o Sandbox pode sofrer restrições temporárias para alguns destinos, incluindo o Brasil. Se a vinculação e os parâmetros estiverem corretos e o teste no próprio console falhar, confira o código nos logs e entre em contato com o suporte da Twilio.

## Validação local

No ambiente de desenvolvimento, execute `python -m unittest discover -s tests -v`. Os testes usam destinatários e serviços simulados, incluindo as falhas após aceitação, e **não enviam mensagens externas**. Testes automatizados aprovados não confirmam o recebimento no celular; essa confirmação depende do teste real com a conta configurada.

Referências oficiais consultadas:

- [Novo trial de WhatsApp](https://www.twilio.com/docs/usage/trials/try-out-whatsapp)
- [Sandbox: vinculação, janela de atendimento e limitações](https://www.twilio.com/docs/whatsapp/sandbox)
- [Variáveis dos modelos](https://www.twilio.com/docs/content/using-variables-with-content-api)
- [Mensagens e consulta de status](https://www.twilio.com/docs/messaging/api/message-resource)
