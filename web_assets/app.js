const $ = id => document.getElementById(id);
const state = {user:null, csrf:'', authMode:'login', page:'dashboard', mode:'demo', preferences:null, providers:null, snapshot:null, alerts:[]};
const channelNames = {email:'E-mail', sms:'SMS', whatsapp:'WhatsApp'};
const pageNames = {dashboard:['VISÃO GERAL','Seu ambiente, sob controle.'], preferences:['MEUS ALERTAS','Os avisos, do seu jeito.'], history:['HISTÓRICO','Cada alerta tem uma história.'], wifi:['WI-FI DA PLACA','Conecte a placa à sua rede.'], mobile:['NO IPHONE','ClimaGuard, sempre por perto.'], services:['SERVIÇOS DE ENVIO','Conecte os canais de aviso.']};
const escape = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = value => Number(value).toLocaleString('pt-BR',{maximumFractionDigits:1,minimumFractionDigits:1});
let toastTimer, polling = false;

function toast(message,error=false){clearTimeout(toastTimer);$('toast').textContent=message;$('toast').classList.toggle('error',error);$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,6500)}
async function api(path,body){
 const response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},body:body===undefined?undefined:JSON.stringify(body)});
 let data;try{data=await response.json()}catch{throw Error('Feche e abra o ClimaGuard. Se o problema continuar, instale a versão mais recente.')}
 if(!response.ok){if(response.status===401&&state.user){state.user=null;showAccess()}throw Error(data.error||'Não foi possível concluir. Tente novamente.')}
 if(data.csrf_token)state.csrf=data.csrf_token;
 return data;
}
function showAccess(){ $('boot').hidden=true;$('application').hidden=true;$('auth').hidden=false;clearMobilePair(); }
function authMode(mode){state.authMode=mode;const register=mode==='register';$('name-field').hidden=!register;$('confirm-field').hidden=!register;$('auth-name').required=register;$('auth-confirm').required=register;$('auth-password').autocomplete=register?'new-password':'current-password';$('auth-title').textContent=register?'Crie sua conta':'Entre na sua conta';$('auth-description').textContent=register?'Seu limite e seus canais ficam salvos para você.':'Acompanhe o ambiente e configure seus alertas.';$('auth-submit').textContent=register?'Criar conta e continuar →':'Entrar no painel →';$('register-tab').classList.toggle('active',register);$('login-tab').classList.toggle('active',!register);$('auth-error').textContent='' }
$('login-tab').addEventListener('click',()=>authMode('login'));
$('register-tab').addEventListener('click',()=>authMode('register'));
$('auth-form').addEventListener('submit',async event=>{
 event.preventDefault();$('auth-error').textContent='';
 if(state.authMode==='register'&&$('auth-password').value!==$('auth-confirm').value){$('auth-error').textContent='As senhas precisam ser iguais.';return}
 const button=$('auth-submit');button.disabled=true;
 try{const data=await api('/api/'+state.authMode,{name:$('auth-name').value,email:$('auth-email').value,password:$('auth-password').value});state.user=data.user;$('auth-password').value='';$('auth-confirm').value='';await enterApp()}catch(error){$('auth-error').textContent=error.message}finally{button.disabled=false}
});
$('logout').addEventListener('click',async()=>{try{await api('/api/logout',{});state.user=null;state.snapshot=null;state.alerts=[];clearWifiCard();showAccess()}catch(error){toast(error.message,true)}});

async function enterApp(){
 $('boot').hidden=true;$('auth').hidden=true;$('application').hidden=false;
 $('user-name').textContent=state.user.name;$('avatar').textContent=state.user.name.slice(0,1).toUpperCase();$('user-role').textContent=state.user.admin?'Administrador':'Minha conta';$('services-nav').hidden=!state.user.admin;
 $('wifi-nav').hidden=false;$('wifi-shortcut').hidden=false;$('wifi-wireless').hidden=!state.user.admin;
 const data=await api('/api/preferences');state.preferences=data.preferences;state.providers=data.providers;fillPreferences();setMode('real');navigate('dashboard');await refresh();
}
function navigate(page){
 if(page==='services'&&!state.user?.admin)return;
 state.page=page;for(const key of Object.keys(pageNames))$('page-'+key).hidden=key!==page;
 document.querySelectorAll('[data-page]').forEach(button=>{button.classList.toggle('active',button.dataset.page===page);button.setAttribute('aria-current',button.dataset.page===page?'page':'false')});
 $('page-caption').textContent=pageNames[page][0];$('page-title').textContent=pageNames[page][1];
 if(page==='mobile')loadMobile().catch(error=>toast(error.message,true));
 if(page==='wifi')loadWifi().catch(error=>$('wifi-message').textContent=error.message);
 if(page==='services')loadServices().catch(error=>toast(error.message,true));
 if(page==='history')loadHistory().catch(error=>toast(error.message,true));
 if(page==='dashboard')setTimeout(drawChart,20);
}
document.querySelectorAll('[data-page]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.page)));
document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.go)));
function setMode(mode){
 state.mode=mode;state.snapshot=null;$('mode-demo').classList.toggle('active',mode==='demo');$('mode-real').classList.toggle('active',mode==='real');
 $('demo-controls').hidden=mode!=='demo';$('real-help').hidden=mode!=='real';
 $('source-banner').classList.toggle('demo-notice',mode==='demo');
 $('source-banner').innerHTML=mode==='demo'?'<span aria-hidden="true">✦</span><div><strong>Modo de demonstração</strong><p>Cenários simulados. Nenhuma mensagem será enviada por estes controles.</p></div><span class="tag">SIMULADO</span>':'<span aria-hidden="true">◉</span><div><strong>Leituras da placa real</strong><p>O aplicativo busca a placa na rede e consulta os sensores por Wi-Fi. Pode ficar ligada somente na fonte. Sem dados recentes, os valores ficam indisponíveis.</p></div><span class="tag">AO VIVO</span>';
 refresh().catch(error=>toast(error.message,true));
}
$('mode-demo').addEventListener('click',()=>setMode('demo'));$('mode-real').addEventListener('click',()=>setMode('real'));
function fillPreferences(){
 const p=state.preferences;for(const [id,key] of [['pref-enabled','enabled'],['pref-temperature','temperature_enabled'],['pref-power','power_enabled'],['pref-consent','consent']])$(id).checked=p[key];
 $('pref-threshold').value=p.threshold;$('pref-cooldown').value=String(p.cooldown_minutes);$('pref-email').value=p.email;$('pref-phone').value=p.phone;
 document.querySelectorAll('[name=channel]').forEach(input=>input.checked=p.channels.includes(input.value));renderReadiness();renderRules();
}
function renderReadiness(){
 if(!state.providers||!state.preferences)return;
 const p=state.preferences,s=state.providers;
 for(const key of Object.keys(channelNames))$('ready-'+key).textContent=s.ready[key]?'Configurado':'A configurar';
 $('delivery-note').textContent=s.live_enabled?'Envios reais liberados pelo administrador. Confira os canais e autorize os destinatários acima.':'Envios reais estão desativados. Você pode salvar suas regras e demonstrar os avisos sem enviar mensagens.';
 document.querySelectorAll('[data-test]').forEach(button=>{const key=button.dataset.test;button.disabled=!(s.live_enabled&&s.ready[key]&&p.enabled&&p.consent&&p.channels.includes(key));button.title=button.disabled?'Configure o serviço e salve suas preferências com autorização antes de testar.':'Enviar uma mensagem real para o destinatário salvo'});
}
function renderRules(){
 const p=state.preferences;if(!p)return;$('threshold-badge').textContent='Limite: '+number(p.threshold)+' °C';
 $('rules-summary').innerHTML=`<span class="rule-pill">${p.enabled?'Alertas ativos':'Alertas desativados'}</span><div class="rule-line">${p.temperature_enabled?'↑ Acima de <strong>'+escape(number(p.threshold))+' °C</strong>':'Temperatura: desativada'}</div><div class="rule-line">${p.power_enabled?'ϟ Avisar na <strong>falta de energia</strong>':'Energia: desativada'}</div><div class="rule-line">${escape(p.channels.map(c=>channelNames[c]).join(' · ')||'Nenhum canal selecionado')}</div><div class="rule-line">${state.providers?.live_enabled?'Serviços reais liberados':'Demonstração disponível sem credenciais'}</div>`;
}
$('preferences-form').addEventListener('submit',async event=>{
 event.preventDefault();const button=event.submitter;button.disabled=true;$('preferences-saved').textContent='';
 const data={enabled:$('pref-enabled').checked,temperature_enabled:$('pref-temperature').checked,power_enabled:$('pref-power').checked,consent:$('pref-consent').checked,threshold:Number($('pref-threshold').value),cooldown_minutes:Number($('pref-cooldown').value),channels:[...document.querySelectorAll('[name=channel]:checked')].map(i=>i.value),email:$('pref-email').value,phone:$('pref-phone').value};
 try{const result=await api('/api/preferences',data);state.preferences=result.preferences;renderReadiness();renderRules();$('preferences-saved').textContent='Preferências salvas neste notebook.';toast('Preferências salvas. Você já pode testar um cenário.')}catch(error){toast(error.message,true)}finally{button.disabled=false}
});
async function refresh(){
 if(!state.user||polling)return;polling=true;const mode=state.mode;
 try{let data=await api('/api/status?source='+mode);if(mode!==state.mode)return;
  // Start an explicitly simulated, normal scenario for a first demonstration.
  // Never create substitute readings in the real-device stream.
  if(mode==='demo'&&!data.latest){
   const baseline=Math.max(-40,Math.min(80,data.preferences.threshold-2));
   await api('/api/demo',{temperature:baseline,humidity:50,energy:true});
   if(mode!==state.mode)return;
   data=await api('/api/status?source=demo');
   if(mode!==state.mode)return;
   $('demo-temperature').value=baseline;$('demo-humidity').value=50;$('demo-energy').value='true';
  }
  state.snapshot=data;state.providers=data.providers;renderConnection(data.connection,data.device_online);renderDashboard();renderReadiness();renderRules();if(state.page==='history')await loadHistory()}
 catch(error){renderConnection({state:'offline',label:'Servidor indisponível',online:false,error:'Abra o aplicativo ClimaGuard para restabelecer a comunicação.',devices:[],interfaces:[]},false);$('device-status').textContent='Servidor indisponível';$('temperature').textContent='—';$('humidity').textContent='—';$('energy').className='energy-value';$('energy').innerHTML='<span class="status-dot"></span><span>Sem conexão</span>';if(!state.snapshot)toast(error.message,true)}finally{polling=false}
}
function renderDashboard(){
 const s=state.snapshot,v=s.latest,available=s.online&&v;
 $('temperature').innerHTML=available&&typeof v.temperature==='number'?escape(number(v.temperature))+' <small>°C</small>':'—';
 $('humidity').innerHTML=available&&typeof v.humidity==='number'?escape(number(v.humidity))+' <small>%</small>':'—';
 let note='Aguardando dados';if(available)note=v.temperature===null?'Sensor sem leitura válida':v.temperature>state.preferences.threshold?'Acima do seu limite de alerta':'Dentro do limite configurado';if(s.source==='demo'&&available)note='Simulação • '+note;if(!s.online&&s.source==='real')note='Ligue a placa na fonte, confira o Wi-Fi e mantenha o ClimaGuard aberto no mesmo roteador';$('temperature-note').textContent=note;
 $('energy-title').textContent=s.source==='demo'?'Energia simulada':'Estado de energia';$('energy-note').textContent=s.source==='demo'?'Simulação do cenário':'Presença de energia informada pela placa';
 const power=s.connection?.device?.power;const powerLabels={disabled:'Sensor desativado: confira a montagem e calibre para ativar.',starting:'Aguardando leitura do sensor.',no_signal:'Sem sinal válido do sensor.',clipped:'Sinal fora da faixa: confira o ajuste e o divisor.',timing:'Amostragem indisponível.',unstable:'Sinal instável.',adc_error:'Falha na leitura analógica.',present:'Sensor ativo: energia presente.',absent:'Sensor ativo: energia ausente.'};$('device-power').hidden=s.source!=='real'||!power;if(power){$('power-state-note').textContent=powerLabels[power.state]||'Energia não verificada.';if(s.source==='real')$('energy-note').textContent=power.enabled?'Sensor AC ZMPT101B':'ZMPT101B desativado • aguarda calibração';}
 const energy=$('energy');energy.className='energy-value'+(available&&v.energy!==null?(v.energy?' good':' bad'):'');energy.innerHTML='<span class="status-dot"></span><span>'+(!available?(s.source==='demo'?'Aguardando':'Sem dados'):v.energy===true?'Presente':v.energy===false?'Ausente':'Não verificada')+'</span>';
 $('device-status').textContent=s.device_online?'Recebendo leituras da placa':'Sem dados recentes da placa';
 $('last-update').textContent=v?(s.source==='demo'?'Cenário aplicado: ':'Última leitura: ')+new Date(v.received_at*1000).toLocaleTimeString('pt-BR'):'Nenhuma leitura';
 $('chart-empty').hidden=s.history.some(r=>typeof r.temperature==='number');drawChart();
}
function drawChart(){
 const canvas=$('chart');if($('page-dashboard').hidden)return;const box=canvas.getBoundingClientRect();if(!box.width)return;
 const ratio=window.devicePixelRatio||1;canvas.width=Math.round(box.width*ratio);canvas.height=Math.round(230*ratio);const x=canvas.getContext('2d');x.scale(ratio,ratio);
 const width=box.width,height=230,pad={l:38,r:12,t:12,b:25},w=width-pad.l-pad.r,h=height-pad.t-pad.b;
 const rows=state.snapshot?.history||[],valid=rows.filter(r=>typeof r.temperature==='number'),limit=state.preferences?.threshold??30;
 const low=Math.min(...valid.map(r=>r.temperature),limit,25)-2,high=Math.max(...valid.map(r=>r.temperature),limit,30)+2;
 const py=t=>pad.t+h-(t-low)/(high-low)*h;
 x.font='10px Segoe UI, sans-serif';x.strokeStyle='#e9eee6';x.fillStyle='#9aa693';x.lineWidth=1;
 for(let i=0;i<4;i++){const y=pad.t+i*h/3;x.beginPath();x.moveTo(pad.l,y);x.lineTo(width-pad.r,y);x.stroke();x.fillText(Math.round(high-i*(high-low)/3)+'°',0,y+3)}
 x.setLineDash([4,4]);x.strokeStyle='#c9aa69';x.beginPath();x.moveTo(pad.l,py(limit));x.lineTo(width-pad.r,py(limit));x.stroke();x.setLineDash([]);
 if(rows.length){let pen=false;x.strokeStyle='#4d9670';x.lineWidth=2.5;x.beginPath();rows.forEach((row,i)=>{if(typeof row.temperature!=='number'){pen=false;return}const px=pad.l+(rows.length===1?w/2:i/(rows.length-1)*w),y=py(row.temperature);pen?x.lineTo(px,y):x.moveTo(px,y);pen=true});x.stroke();for(const [i,row] of rows.entries()){if(typeof row.temperature!=='number')continue;const px=pad.l+(rows.length===1?w/2:i/(rows.length-1)*w);x.fillStyle='#4d9670';x.beginPath();x.arc(px,py(row.temperature),2.5,0,Math.PI*2);x.fill()}x.fillStyle='#9aa693';x.fillText(new Date(rows[0].received_at*1000).toLocaleTimeString('pt-BR'),pad.l,height-4);if(rows.length>1){const label=new Date(rows.at(-1).received_at*1000).toLocaleTimeString('pt-BR');x.fillText(label,width-pad.r-x.measureText(label).width,height-4)}}
}
window.addEventListener('resize',drawChart);
async function applyDemo(row){
 try{await api('/api/demo',row);await refresh();toast(state.preferences.enabled?'Cenário aplicado. Consulte os avisos simulados no histórico.':'Cenário aplicado. Ative suas regras em Meus alertas para gerar avisos simulados.')}catch(error){toast(error.message,true)}
}
document.querySelectorAll('[data-scenario]').forEach(button=>button.addEventListener('click',async()=>{
 const threshold=state.preferences.threshold;let row={temperature:Math.max(-40,threshold-2),humidity:50,energy:true};
 if(button.dataset.scenario==='hot'){if(threshold>=80){toast('O limite de 80 °C não pode ser ultrapassado pelo intervalo deste sensor. Escolha um limite menor.',true);return}row.temperature=Math.min(80,threshold+2)}
 if(button.dataset.scenario==='off')row.energy=false;
 if(button.dataset.scenario==='sensor'){row.temperature=null;row.humidity=null}
 if(row.temperature!==null){$('demo-temperature').value=row.temperature;$('demo-humidity').value=row.humidity}$('demo-energy').value=String(row.energy);
 button.disabled=true;try{await applyDemo(row)}finally{button.disabled=false}
}));
$('demo-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;try{await applyDemo({temperature:Number($('demo-temperature').value),humidity:Number($('demo-humidity').value),energy:$('demo-energy').value==='true'})}finally{button.disabled=false}});
const statusNames={simulated:'Simulado',queued:'Na fila',sending:'Enviando',accepted:'Aceito pelo serviço',delivered:'Entregue',read:'Lido',failed:'Falha no envio',blocked:'Não enviado'};
async function loadHistory(){const data=await api('/api/alerts');state.alerts=data.alerts;renderHistory()}
function renderHistory(){
 const filter=$('history-filter').value,rows=state.alerts.filter(a=>filter==='all'||a.source===filter),root=$('history-list');
 if(!rows.length){root.innerHTML='<div class="empty-state"><span aria-hidden="true">◷</span><h2>Nenhum aviso por aqui ainda.</h2><p>Salve suas preferências, ative os alertas e aplique um cenário acima do limite ou sem energia na demonstração.</p></div>';return}
 root.innerHTML=rows.map(row=>`<article class="history-item"><div class="history-icon" aria-hidden="true">${row.kind==='power'?'ϟ':row.kind==='temperature'?'↑':'✉'}</div><div><h3>${row.kind==='power'?(row.source==='demo'?'Falta de energia simulada':'Ausência de energia'):row.kind==='temperature'?'Temperatura acima do limite':'Teste de envio real'}</h3><p>${row.source==='demo'?'Demonstração':row.source==='test'?'Teste solicitado':'Placa real'} · ${escape(channelNames[row.channel])} · ${escape(row.destination)}</p><p class="message">${escape(row.message)}</p><p class="detail">${escape(row.detail)}</p>${row.channel==='whatsapp'&&row.source!=='demo'&&row.provider_id&&row.status!=='read'?`<button type="button" class="secondary delivery-check" data-delivery="${row.id}">Consultar entrega</button>`:''}</div><div><span class="status-tag ${escape(row.status)}">${escape(statusNames[row.status]||row.status)}</span><time datetime="${new Date(row.created*1000).toISOString()}">${new Date(row.created*1000).toLocaleString('pt-BR')}</time></div></article>`).join('');
}
$('history-filter').addEventListener('change',renderHistory);
$('history-list').addEventListener('click',async event=>{
 const button=event.target.closest('[data-delivery]');if(!button)return;
 button.disabled=true;
 try{const result=await api(`/api/alerts/${button.dataset.delivery}/delivery`,{});await loadHistory();toast(result.detail,result.status==='failed')}catch(error){toast(error.message,true)}finally{button.disabled=false}
});
document.querySelectorAll('[data-test]').forEach(button=>button.addEventListener('click',async()=>{
 const channel=button.dataset.test,destination=channel==='email'?state.preferences.email:state.preferences.phone;
 if(!window.confirm(`Enviar uma mensagem REAL por ${channelNames[channel]} para ${destination}? O serviço pode cobrar pelo envio.`))return;
 button.disabled=true;try{await api('/api/test-message',{channel,confirm:true});toast('Teste real colocado na fila. Veja o resultado no histórico.');navigate('history')}catch(error){toast(error.message,true)}finally{renderReadiness()}
}));
async function loadServices(){
 const data=await api('/api/providers'),p=data.providers;state.providers=p;
 for(const input of $('services-form').querySelectorAll('input[name], select[name], textarea[name]')){input.value=p.fields[input.name]||'';if(p.saved?.[input.name])input.placeholder='Credencial salva • deixe vazio para manter'}
 $('services-live').checked=p.live_enabled;toggleWhatsAppProvider();renderReadiness();
 if($('whatsapp-provider').value==='wppconnect')await loadLocalWhatsApp();
}
function toggleWhatsAppProvider(){const local=$('whatsapp-provider').value==='wppconnect';$('whatsapp-local-panel').hidden=!local;$('twilio-whatsapp-settings').hidden=local}
$('whatsapp-provider').addEventListener('change',()=>{toggleWhatsAppProvider();if($('whatsapp-provider').value==='wppconnect')loadLocalWhatsApp().catch(error=>toast(error.message,true))});
async function loadLocalWhatsApp(action){
 const result=await api('/api/whatsapp/local',action?{action}:undefined),c=result.connection;
 state.providers=result.providers;renderReadiness();
 $('whatsapp-local-status').textContent=c.detail;
 const qr=$('whatsapp-local-qr');
 if(c.state==='qr'&&typeof c.qr==='string'&&/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(c.qr)){qr.src=c.qr;qr.hidden=false}else{qr.hidden=true;qr.removeAttribute('src')}
 $('whatsapp-connect').disabled=['starting','connected'].includes(c.state);$('whatsapp-close').disabled=['idle','unavailable'].includes(c.state);
}
for(const [id,action] of [['whatsapp-connect','connect'],['whatsapp-close','close']])$(id).addEventListener('click',async()=>{
 $(id).disabled=true;
 try{await loadLocalWhatsApp(action)}catch(error){toast(error.message,true);$(id).disabled=false}
});
setInterval(()=>{if(state.user?.admin&&state.page==='services'&&!document.hidden&&$('whatsapp-provider').value==='wppconnect')loadLocalWhatsApp().catch(()=>{})},3000);
$('services-form').addEventListener('submit',async event=>{
 event.preventDefault();const button=event.submitter;button.disabled=true;const data=Object.fromEntries(new FormData(event.target));data.live_enabled=$('services-live').checked;
 try{const result=await api('/api/providers',data);state.providers=result.providers;for(const input of event.target.querySelectorAll('input[type=password]'))input.value='';await loadServices();renderRules();$('services-saved').textContent='Configuração salva. Nenhuma mensagem de teste foi enviada.';toast('Serviços salvos. Use Meus alertas para autorizar e testar um destinatário.')}catch(error){toast(error.message,true)}finally{button.disabled=false}
});
setInterval(()=>{if(state.user&&!document.hidden)refresh()},250);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&state.user)refresh()});
try{const result=await api('/api/session');state.user=result.user;if(state.user)await enterApp();else showAccess()}catch(error){$('boot').textContent=error.message}

function renderConnection(c,legacyOnline=false){
 if(!c)return;
 let mode=c.state,label=c.label;
 if(legacyOnline&&!c.selected){mode='connected';label='Recebendo leituras da placa';}
 const pill=$('connection-pill');pill.className='connection-pill '+mode;$('connection-pill-text').textContent=label;$('connection-title').textContent=label;
 const parts=[];
 if(c.device){parts.push(c.device.model+' · '+c.device.ip);parts.push(c.device.id);}
 if(c.last_contact)parts.push('Última comunicação: '+new Date(c.last_contact*1000).toLocaleTimeString('pt-BR'));
 if(c.error&&!c.online)parts.push(c.error);
 if(!parts.length)parts.push(c.state==='choose'?'Mais de uma placa encontrada. Selecione a que deseja acompanhar.':'Ligue a placa na fonte e mantenha os aparelhos no mesmo roteador.');
 $('connection-detail').textContent=parts.join(' • ');
 $('connection-adapters').textContent=c.interfaces?.length?'Redes verificadas: '+c.interfaces.map(i=>i.name+' ('+i.ip+')').join(' · '):'Verificando conexões de rede…';
 $('device-search').disabled=!!c.scanning;$('device-search').textContent=c.scanning?'Procurando…':'Procurar placa';
 const choices=c.devices||[],select=$('device-select');
 const signature=JSON.stringify(choices.map(d=>[d.id,d.ip]));
 if(select.dataset.devices!==signature){select.innerHTML=choices.map(d=>'<option value="'+escape(d.id)+'">'+escape(d.model+' · '+d.ip+' · '+d.id)+'</option>').join('');select.dataset.devices=signature;}
 if(c.selected&&choices.some(d=>d.id===c.selected))select.value=c.selected;
 $('device-choices').hidden=choices.length<2;$('device-select-button').disabled=!state.user?.admin;
 $('device-manual').hidden=!state.user?.admin;$('wifi-current').textContent=c.device?.wifi_ssid?'Wi-Fi atual da placa: '+c.device.wifi_ssid:'';
}
$('connection-pill').addEventListener('click',()=>{navigate('dashboard');$('connection-panel').scrollIntoView({behavior:'smooth',block:'center'});});
$('device-search').addEventListener('click',async()=>{
 $('device-search').disabled=true;
 try{await api('/api/device/network',{action:'scan'});toast('Busca iniciada nas conexões de rede deste computador.');await refresh();}catch(error){toast(error.message,true);$('device-search').disabled=false;}
});
$('device-select-button').addEventListener('click',async()=>{
 try{await api('/api/device/network',{action:'select',id:$('device-select').value});toast('Placa selecionada. Aguardando a próxima leitura.');await refresh();}catch(error){toast(error.message,true);}
});
$('device-ip-form').addEventListener('submit',async event=>{
 event.preventDefault();
 try{await api('/api/device/network',{action:'connect',ip:$('device-ip').value.trim()});toast('Verificando a placa nesse endereço.');await refresh();}catch(error){toast(error.message,true);}
});

function clearWifiCard(){$('wifi-card').hidden=true;$('wifi-qr').removeAttribute('src');$('wifi-card-password').textContent='';$('wifi-password').value='';$('wifi-ssid').value='';$('wifi-message').textContent='';$('wifi-usb-status').textContent='Conecte a placa e atualize a lista de portas.';}
function showWifiCard(card){
 const valid=card&&typeof card.qr==='string'&&/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(card.qr);
 $('wifi-card').hidden=!valid;$('wifi-card-missing').hidden=!!valid;
 if(valid){$('wifi-qr').src=card.qr;$('wifi-card-ssid').textContent=card.ssid;$('wifi-card-password').textContent=card.password;}
}
let wifiWorking=false;
function wifiBusy(busy){wifiWorking=busy;for(const id of ['wifi-refresh','wifi-port','wifi-ssid','wifi-password','wifi-show'])$(id).disabled=busy;for(const id of ['wifi-capture','wifi-open','wifi-save'])$(id).disabled=busy||!$('wifi-port').value;$('wifi-usb-form').setAttribute('aria-busy',String(busy));}
async function loadWifi(){
 if(wifiWorking||!state.user)return;
 wifiBusy(true);
 try{const r=await api('/api/device/wifi/usb'),select=$('wifi-port'),previous=select.value,ports=r.ports||[];
  select.innerHTML='<option value="">'+(ports.length?'Selecione a porta USB':'Nenhuma porta USB encontrada')+'</option>'+ports.map(p=>'<option value="'+escape(p.device)+'">'+escape(p.device+' — '+p.description)+'</option>').join('');
  if(ports.some(p=>p.device===previous))select.value=previous;else if(ports.length===1)select.value=ports[0].device;
  $('wifi-usb-status').textContent=ports.length?'Porta disponível. Use “Verificar placa USB” para confirmar o ESP32 antes de salvar.':'Nenhuma porta encontrada. Confira o cabo USB de dados e clique em “Atualizar portas USB”.';
  if(state.user.admin){const card=await api('/api/device/wifi');showWifiCard(card.card);}
 }finally{wifiBusy(false);}
}
$('wifi-refresh').addEventListener('click',()=>loadWifi().catch(error=>$('wifi-message').textContent=error.message));
$('wifi-port').addEventListener('change',()=>{showWifiCard(null);$('wifi-message').textContent='';$('wifi-usb-status').textContent='Use “Verificar placa USB” para identificar esta porta.';wifiBusy(false);});
for(const [id,action] of [['wifi-capture','capture'],['wifi-open','portal']])$(id).addEventListener('click',async()=>{
 wifiBusy(true);$('wifi-message').textContent='Identificando a placa na USB. Aguarde…';
 try{const r=await api(action==='capture'?'/api/device/wifi/usb':'/api/device/wifi',{action:action==='capture'?'identify':action,port:$('wifi-port').value});if(r.card)showWifiCard(r.card);$('wifi-usb-status').textContent='Placa ClimaGuard verificada: '+(r.id||r.card.id)+' · '+$('wifi-port').value;if(action==='capture'&&state.user.admin){const card=await api('/api/device/wifi');showWifiCard(card.card);}$('wifi-message').textContent=action==='portal'?'Rede de configuração aberta. Use o QR Code no celular e acesse 192.168.4.1.':'Placa identificada pela USB. Preencha o novo Wi-Fi e clique em Salvar.';}catch(e){$('wifi-message').textContent=e.message;}finally{wifiBusy(false);}
});
$('wifi-show').addEventListener('change',()=>{$('wifi-password').type=$('wifi-show').checked?'text':'password';});
$('wifi-usb-form').addEventListener('submit',async event=>{
 event.preventDefault();wifiBusy(true);$('wifi-message').textContent='Testando a nova rede pela USB. Aguarde até 40 segundos. A conexão de rede pode interromper por alguns instantes.';
 const password=$('wifi-password').value;$('wifi-password').value='';
 try{const r=await api('/api/device/wifi/usb',{action:'save',port:$('wifi-port').value,ssid:$('wifi-ssid').value,password});$('wifi-message').textContent=r.message+(r.ip?' IP: '+r.ip:'');toast('Wi-Fi salvo na placa.');}catch(e){$('wifi-message').textContent=e.message;}finally{wifiBusy(false);$('wifi-password').value='';}
});

async function loadMobile(){
 const userId=state.user?.id,result=await api('/api/mobile/access');if(state.user?.id!==userId)return;const a=result.access,r=a.remote;
 $('mobile-remote-status').textContent=a.error||r.detail;
 $('mobile-base-url').textContent=r.ready?'Endereço do seu ClimaGuard: '+r.url:'';
 $('mobile-generate').disabled=!(a.available&&r.ready);
 $('mobile-remote-prepare').hidden=!state.user?.admin;
 $('mobile-devices').innerHTML=a.devices.length?a.devices.map(d=>`<div class="mobile-device"><div><strong>${escape(d.name)}</strong><p class="small muted">Autorizado em ${new Date(d.created*1000).toLocaleDateString('pt-BR')} · válido até ${new Date(d.expires*1000).toLocaleDateString('pt-BR')}</p></div><button type="button" class="secondary" data-mobile-revoke="${escape(d.id)}">Remover acesso</button></div>`).join(''):'<p class="muted">Nenhum iPhone autorizado nesta conta.</p>';
}
function clearMobilePair(){ $('mobile-pair-card').hidden=true;$('mobile-access-qr').removeAttribute('src');$('mobile-code').textContent='';$('mobile-message').textContent='';$('mobile-devices').textContent='';$('mobile-approval').hidden=true;$('mobile-approval-link').removeAttribute('href'); }
$('mobile-refresh').addEventListener('click',()=>loadMobile().catch(e=>toast(e.message,true)));
$('mobile-remote-prepare').addEventListener('click',async()=>{
 $('mobile-remote-prepare').disabled=true;$('mobile-message').textContent='Preparando a conexão privada…';
 try{const result=await api('/api/mobile/access',{action:'remote'}),r=result.remote;$('mobile-message').textContent=r.detail;
  $('mobile-approval').hidden=!r.approval_url;if(r.approval_url)$('mobile-approval-link').href=r.approval_url;await loadMobile();
 }catch(e){$('mobile-message').textContent=e.message;}finally{$('mobile-remote-prepare').disabled=false;}
});
$('mobile-generate').addEventListener('click',async()=>{
 $('mobile-generate').disabled=true;
 try{const result=await api('/api/mobile/access',{action:'pair'}),p=result.pairing;$('mobile-access-qr').src=p.qr;$('mobile-code').textContent=p.code.slice(0,4)+' '+p.code.slice(4);$('mobile-code-expiry').textContent='Válido até '+new Date(p.expires*1000).toLocaleTimeString('pt-BR');$('mobile-pair-card').hidden=false;$('mobile-message').textContent='Escaneie com a câmera deste iPhone e abra no Safari.';}
 catch(e){$('mobile-message').textContent=e.message;}finally{await loadMobile().catch(()=>{});}
});
$('mobile-devices').addEventListener('click',async event=>{
 const button=event.target.closest('[data-mobile-revoke]');if(!button)return;button.disabled=true;
 try{await api('/api/mobile/access',{action:'revoke',id:button.dataset.mobileRevoke});await loadMobile();toast('Acesso deste aparelho removido.');}catch(e){toast(e.message,true);button.disabled=false;}
});
setInterval(()=>{if(state.user&&state.page==='mobile'&&!document.hidden)loadMobile().catch(()=>{});},5000);
