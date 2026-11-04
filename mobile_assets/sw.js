const CACHE='climaguard-mobile-shell-v1';
const SHELL=['/','/assets/mobile.css?v=1','/assets/mobile.js?v=1','/assets/icon-180.png','/assets/icon-192.png','/assets/icon-512.png'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('climaguard-mobile-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);if(url.origin!==self.location.origin||event.request.method!=='GET')return;
 if(url.pathname.startsWith('/api/')){event.respondWith(fetch(event.request).catch(()=>new Response(JSON.stringify({error:'Computador indisponível. Confira o Tailscale e a conexão.'}),{status:503,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}})));return;}
 if(event.request.mode==='navigate'){event.respondWith(fetch(event.request).catch(()=>caches.match('/')));return;}
 if(SHELL.includes(url.pathname+url.search)||SHELL.includes(url.pathname))event.respondWith(caches.match(event.request).then(cached=>cached||fetch(event.request)));
});
