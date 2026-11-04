// Only the external WhatsApp library is faked; bridge HTTP/auth/storage stay real.
const fs = require('node:fs');
let count = 0;
const fake = { close: async()=>{}, onAck: ()=>{}, onStateChange: ()=>{},
  sendText: async(phone,text)=>{fs.writeFileSync(process.env.CLIMAGUARD_WPP_COUNT,String(++count));return {id:'synthetic-wa-'+count,ack:1};},
  getMessageById: async()=>({ack:3}) };
const Module = require('node:module');
const originalLoad = Module._load;
const fakes = new Map([
  ['@wppconnect-team/wppconnect',{create:async options=>{options.statusFind('qrReadSuccess');return fake;}}],
  ['puppeteer',{launch:async()=>({close:async()=>{}})}]
]);
Module._load = function(request, parent, isMain) {
  if (fakes.has(request)) return fakes.get(request);
  return originalLoad.call(this, request, parent, isMain);
};
