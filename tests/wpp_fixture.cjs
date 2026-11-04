// Only the external WhatsApp library is faked; bridge HTTP/auth/storage stay real.
const fs = require('node:fs');
let count = 0;
const fake = { close: async()=>{}, onAck: ()=>{}, onStateChange: ()=>{},
  sendText: async(phone,text)=>{fs.writeFileSync(process.env.CLIMAGUARD_WPP_COUNT,String(++count));return {id:'synthetic-wa-'+count,ack:1};},
  getMessageById: async()=>({ack:3}) };
for (const [name,value] of [
  ['@wppconnect-team/wppconnect',{create:async options=>{options.statusFind('qrReadSuccess');return fake;}}],
  ['puppeteer',{launch:async()=>({close:async()=>{}})}]
]) { const id = require.resolve('../whatsapp_local/node_modules/'+name);require.cache[id]={id,filename:id,loaded:true,exports:value}; }
