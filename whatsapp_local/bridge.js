'use strict';
// Local transport only. It never reads conversations, contacts, or incoming messages.
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { create } = require('@wppconnect-team/wppconnect');
const puppeteer = require('puppeteer');

const directory = process.env.CLIMAGUARD_WPP_DATA;
const secret = process.env.CLIMAGUARD_WPP_SECRET;
if (!directory || !secret || secret.length < 32) process.exit(2);
fs.mkdirSync(directory, { recursive: true });
let client, browser, starting = false, closing = false;
let state = { state: 'idle', detail: 'Clique em Conectar WhatsApp para começar.', qr: '' };
const receiptsPath = path.join(directory, 'receipts.json');
let receipts = {};
try { receipts = JSON.parse(fs.readFileSync(receiptsPath, 'utf8')); } catch (_) {}
function persist() {
  receipts = Object.fromEntries(Object.entries(receipts).slice(-300));
  fs.writeFileSync(receiptsPath + '.tmp', JSON.stringify(receipts));
  fs.renameSync(receiptsPath + '.tmp', receiptsPath);
}
function setState(next, detail) { state = { state: next, detail, qr: next === 'qr' ? state.qr : '' }; }
function recordAck(id, ack) {
  for (const row of Object.values(receipts)) if (row.messageId === id) {
    // Delivery can advance, but a delayed acknowledgement cannot undo read/delivered.
    if (Number.isFinite(ack) && (ack < 0 || ack > (row.ack ?? 0))) row.ack = ack;
  }
  persist();
}
async function connect() {
  if (starting || closing || (client && state.state === 'connected')) return;
  starting = true;
  setState('starting', 'Preparando a conexão com o WhatsApp. Aguarde o QR Code.');
  try {
    if (browser) { try { await browser.close(); } catch (_) {} }
    client = null;
    browser = await puppeteer.launch({ headless: true, executablePath: process.env.CLIMAGUARD_WPP_BROWSER,
      userDataDir: path.join(directory, 'browser'), defaultViewport: { width: 1100, height: 800 } });
    client = await create({
      session: 'climaguard', browser, headless: true, useChrome: false, waitForLogin: true,
      deviceName: 'ClimaGuard', whatsappVersion: '', disableGoogleAnalytics: true,
      logQR: false, disableWelcome: true, updatesLog: false, autoClose: 0,
      tokenStore: 'file', folderNameToken: path.join(directory, 'tokens'),
      puppeteerOptions: { executablePath: process.env.CLIMAGUARD_WPP_BROWSER,
        userDataDir: path.join(directory, 'browser'), defaultViewport: { width: 1100, height: 800 } },
      catchQR: (qr) => { if (!closing) state = { state: 'qr', qr, detail: 'No celular: WhatsApp → Aparelhos conectados → Conectar um aparelho. Escaneie este QR Code.' }; },
      statusFind: (status) => {
        if (closing) return;
        if (status === 'qrReadSuccess' || status === 'isLogged') setState('starting', 'Celular vinculado. Finalizando a conexão…');
        if (['browserClose', 'serverClose', 'desconnectedMobile', 'deleteToken'].includes(status)) {
          client = null; setState('disconnected', 'WhatsApp desconectado. Clique em Conectar WhatsApp para tentar novamente.');
        }
      }
    });
    if (closing) { await client.close(); return; }
    setState('connected', 'WhatsApp conectado neste notebook. Você já pode testar o envio em Meus alertas.');
    client.onAck((event) => {
      const id = typeof event.id === 'string' ? event.id : event.id?._serialized;
      if (id) recordAck(id, Number(event.ack));
    });
    client.onStateChange((value) => {
      if (value === 'CONNECTED') setState('connected', 'WhatsApp conectado neste notebook.');
      else if (['UNPAIRED', 'UNPAIRED_IDLE', 'CONFLICT'].includes(value)) {
        setState('disconnected', 'A sessão do WhatsApp foi desconectada. Reconecte pelo aplicativo.');
      }
    });
  } catch (_) {
    client = null;
    if (browser) { try { await browser.close(); } catch (_) {} browser = null; }
    if (!closing) setState('error', 'Não foi possível conectar ao WhatsApp. Confira a internet e tente novamente. Se continuar, atualize o ClimaGuard.');
  } finally { starting = false; }
}
function json(res, status, data) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(data));
}
async function body(req) {
  let text = '';
  for await (const chunk of req) { text += chunk; if (text.length > 12000) throw new Error('size'); }
  return JSON.parse(text);
}
async function shutdown() {
  if (closing) return;
  closing = true;
  const timer = setTimeout(() => process.exit(0), 5000);
  try { if (client) await client.close(); else if (browser) await browser.close(); } catch (_) {}
  clearTimeout(timer); server.close(() => process.exit(0));
}
const server = http.createServer(async (req, res) => {
  const supplied = req.headers.authorization || '';
  const expected = 'Bearer ' + secret;
  const actualBytes = Buffer.from(supplied), expectedBytes = Buffer.from(expected);
  if (actualBytes.length !== expectedBytes.length || !crypto.timingSafeEqual(actualBytes, expectedBytes) || req.headers.origin) {
    return json(res, 403, { error: 'Acesso local não autorizado.' });
  }
  try {
    if (req.url === '/status' && req.method === 'GET') return json(res, 200, state);
    if (req.url === '/connect' && req.method === 'POST') { connect(); return json(res, 202, state); }
    if (req.url === '/close' && req.method === 'POST') { json(res, 200, { ok: true }); shutdown(); return; }
    if (req.url === '/send' && req.method === 'POST') {
      const data = await body(req);
      if (!/^\+[1-9]\d{6,14}$/.test(data.phone) || typeof data.message !== 'string' || !data.message || data.message.length > 3000 || !/^\d+-\d+$/.test(data.requestId)) {
        return json(res, 400, { error: 'Dados do aviso inválidos.' });
      }
      const previous = Object.entries(receipts).find(([, row]) => row.requestId === data.requestId);
      if (previous) {
        if (previous[1].messageId) return json(res, 200, { id: 'wpp:' + previous[0] });
        return json(res, 409, { error: 'Este aviso já teve uma tentativa de envio. Consulte o histórico antes de repetir.' });
      }
      if (!client || state.state !== 'connected') return json(res, 409, { error: 'Conecte o WhatsApp em Serviços de envio antes de enviar mensagens.' });
      const key = crypto.randomUUID();
      receipts[key] = { requestId: data.requestId, ack: 0 }; persist();
      try {
        const message = await client.sendText(data.phone.slice(1) + '@c.us', data.message);
        const id = typeof message.id === 'string' ? message.id : message.id?._serialized;
        if (!id || message.erro || message.isErro) throw new Error('send');
        receipts[key].messageId = id;
        receipts[key].ack = Number(message.ack) || 0;
        persist();
        return json(res, 200, { id: 'wpp:' + key });
      } catch (_) { return json(res, 502, { error: 'O WhatsApp não confirmou o envio. Confira a conexão e o histórico antes de tentar novamente.' }); }
    }
    if (req.url?.startsWith('/delivery/') && req.method === 'GET') {
      const row = receipts[req.url.slice('/delivery/'.length)];
      if (!row?.messageId) return json(res, 404, { error: 'Comprovante local não encontrado. A entrega não pôde ser confirmada.' });
      if (client && state.state === 'connected') {
        try { const message = await client.getMessageById(row.messageId); if (message) recordAck(row.messageId, Number(message.ack)); } catch (_) {}
      }
      const ack = row.ack || 0;
      const status = ack < 0 ? 'failed' : ack >= 3 ? 'read' : ack >= 2 ? 'delivered' : 'accepted';
      return json(res, 200, { status, detail: ack < 0 ? 'O WhatsApp informou falha no envio.' : ack >= 3 ? 'O WhatsApp confirmou a leitura.' : ack >= 2 ? 'O WhatsApp confirmou a entrega.' : 'Envio registrado no WhatsApp; a entrega ao destinatário ainda não foi confirmada.' });
    }
    json(res, 404, { error: 'Operação não encontrada.' });
  } catch (_) { json(res, 400, { error: 'Não foi possível processar esta operação.' }); }
});
server.listen(0, '127.0.0.1', () => {
  fs.writeFileSync(path.join(directory, 'control.json'), JSON.stringify({ port: server.address().port, pid: process.pid }));
});
// Closing the application also closes this process and its dedicated browser profile.
process.stdin.resume();
process.stdin.on('end', shutdown);
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
