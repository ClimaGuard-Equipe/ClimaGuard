const $=id=>document.getElementById(id);
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=value=>Number(value).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1});
let authorized=false,busy=false,snapshot=null,lastDraw=null,view='overview',timer;
const names={email:'E-mail',sms:'SMS',whatsapp:'WhatsApp'};
const statuses={queued:'Na fila',sending:'Enviando',accepted:'Aceito pelo serviço',delivered:'Entregue',read:'Lido',failed:'Falhou',blocked:'Bloqueado'};
const code=new URLSearchParams(location.hash.slice(1)).get('code');
if(code&&/^[0-9]{8}$/.test(code))$('pair-code').value=code;
if(location.hash)history.replaceState(null,'',location.pathname);
async function api(path,body){
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),6000);
 try{const response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',signal:controller.signal,headers:body===undefined?{}:{'Content-Type':'application/json','X-ClimaGuard-Mobile':'1'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();if(!response.ok){const error=Error(data.error||'Não foi possível conectar ao computador.');error.status=response.status;throw error}return data;
 }finally{clearTimeout(timeout)}
}
function pairing(){authorized=false;snapshot=null;$('boot').hidden=true;$('app').hidden=true;$('pairing').hidden=false;}
function toast(message){$('notice').textContent=message;$('notice').hidden=false;clearTimeout(timer);timer=setTimeout(()=>$('notice').hidden=true,6000);}
$('pair-form').addEventListener('submit',async event=>{event.preventDefault();$('pair-error').textContent='';$('pair-button').disabled=true;try{await api('/api/pair',{code:$('pair-code').value,name:$('device-name').value});$('pair-code').value='';authorized=true;await refresh();}catch(error){$('pair-error').textContent=error.message;}finally{$('pair-button').disabled=false;}});
function connection(good,label,detail){$('connection').className='connection '+(good?'good':'bad');$('connection-label').textContent=label;$('connection-detail').textContent=detail;}
function unavailable(label,detail){connection(false,label,detail);$('temperature').textContent='—';$('humidity').textContent='—';$('energy').textContent='Sem dados';$('energy').className='small-value energy';$('temperature-note').textContent='Aguardando uma leitura recente';document.querySelector('.temperature-card').classList.remove('warning');$('last-reading').textContent='Sem comunicação recente';}
async function refresh(){
 if(busy)return;busy=true;
 try{const data=await api('/api/status');snapshot=data;authorized=true;$('boot').hidden=true;$('pairing').hidden=true;$('app').hidden=false;render(data);}
 catch(error){if(error.status===401){pairing();return}if(!authorized){$('boot').hidden=true;$('pairing').hidden=false;$('pair-error').textContent='Computador indisponível. Confirme se o ClimaGuard e o Tailscale estão abertos e conectados.';}else unavailable('Computador indisponível','Confira o Tailscale e a conexão com a internet.');}
 finally{busy=false;}
}
function render(data){
 const v=data.latest,online=data.online&&v;
 $('phone-name').textContent=data.device_name;$('threshold').textContent='Seu limite: '+number(data.preferences.threshold)+' °C';
 if(online){connection(true,'Placa conectada',data.connection.model+' · via seu computador');$('temperature').innerHTML=typeof v.temperature==='number'?number(v.temperature)+' <small>°C</small>':'—';$('humidity').innerHTML=typeof v.humidity==='number'?number(v.humidity)+'<small> %</small>':'—';$('energy').textContent=v.energy===true?'Presente':v.energy===false?'Ausente':'Sem dados';$('energy').className='small-value energy '+(v.energy===true?'good':v.energy===false?'bad':'');
  const hot=typeof v.temperature==='number'&&v.temperature>data.preferences.threshold;document.querySelector('.temperature-card').classList.toggle('warning',hot);$('temperature-note').textContent=v.temperature===null?'Sensor sem leitura válida':hot?'Acima do limite configurado':'Dentro do seu limite';$('last-reading').textContent='Última leitura às '+new Date(v.received_at*1000).toLocaleTimeString('pt-BR');
 }else unavailable('Sem comunicação com a placa','O computador está online. Confira a alimentação e o Wi-Fi da placa.');
 $('rules-title').textContent=data.preferences.enabled?'Seus alertas estão ativos':'Seus alertas estão desativados';$('rules-detail').textContent=(data.preferences.temperature_enabled?'Temperatura acima de '+number(data.preferences.threshold)+' °C. ':'')+(data.preferences.power_enabled?'Aviso quando a placa confirmar ausência de energia. ':'')+(data.preferences.channels.length?'Canais: '+data.preferences.channels.map(c=>names[c]).join(', ')+'.':'');
 const signature=JSON.stringify(data.alerts);if($('alerts').dataset.signature!==signature){$('alerts').dataset.signature=signature;$('alerts').innerHTML=data.alerts.length?data.alerts.map(a=>`<article class="card alert"><div class="alert-top"><h2>${escape(a.kind==='temperature'?'Temperatura acima do limite':a.kind==='power'?'Ausência de energia':'Teste solicitado')}<br><span class="subtle">${escape(names[a.channel])}</span></h2><span class="status ${escape(a.status)}">${escape(statuses[a.status]||a.status)}</span></div><p>${escape(a.message)}</p><p class="subtle">${escape(a.detail)}</p><time>${new Date(a.created*1000).toLocaleString('pt-BR')}</time></article>`).join(''):'<article class="card empty"><h2>Seu histórico começa aqui.</h2><p>Quando o computador registrar um aviso real ou um teste solicitado, ele aparecerá nesta tela.</p></article>';}
 const marker=v?.received_at;if(marker!==lastDraw){lastDraw=marker;drawChart();}
}
function drawChart(){
 if(view!=='overview'||!snapshot)return;const canvas=$('chart'),box=canvas.getBoundingClientRect();if(!box.width)return;
 const ratio=window.devicePixelRatio||1,w=box.width,h=150;canvas.width=Math.round(w*ratio);canvas.height=h*ratio;const c=canvas.getContext('2d');c.scale(ratio,ratio);
 const rows=snapshot.history||[],valid=rows.filter(r=>typeof r.temperature==='number');if(!valid.length){$('chart-caption').textContent='Aguardando leituras de temperatura.';return;}
 const threshold=snapshot.preferences.threshold,low=Math.min(threshold,...valid.map(r=>r.temperature))-1,high=Math.max(threshold,...valid.map(r=>r.temperature))+1,p={l:31,r:8,t:12,b:18},x=i=>p.l+(w-p.l-p.r)*(rows.length===1?.5:i/(rows.length-1)),y=t=>p.t+(high-t)/(high-low)*(h-p.t-p.b);
 c.font='9px -apple-system, sans-serif';for(let n=0;n<3;n++){const t=low+(high-low)*n/2;c.strokeStyle='#e8eee8';c.lineWidth=1;c.beginPath();c.moveTo(p.l,y(t));c.lineTo(w-p.r,y(t));c.stroke();c.fillStyle='#8a9a8c';c.fillText(t.toFixed(1),0,y(t)+3);}
 c.setLineDash([4,4]);c.strokeStyle='#c7aa69';c.beginPath();c.moveTo(p.l,y(threshold));c.lineTo(w-p.r,y(threshold));c.stroke();c.setLineDash([]);
 c.strokeStyle='#27785b';c.lineWidth=2.5;c.beginPath();let pen=false;rows.forEach((row,i)=>{if(typeof row.temperature!=='number'){pen=false;return}if(pen)c.lineTo(x(i),y(row.temperature));else c.moveTo(x(i),y(row.temperature));pen=true;});c.stroke();const last=rows.at(-1);if(typeof last.temperature==='number'){c.fillStyle='#27785b';c.beginPath();c.arc(x(rows.length-1),y(last.temperature),3,0,2*Math.PI);c.fill();}
 $('chart-caption').textContent='De '+new Date(rows[0].received_at*1000).toLocaleTimeString('pt-BR')+' a '+new Date(rows.at(-1).received_at*1000).toLocaleTimeString('pt-BR')+' · linha pontilhada: seu limite';
}
document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{view=button.dataset.view;for(const name of ['overview','alerts','access'])$('view-'+name).hidden=name!==view;document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-current',b===button?'page':'false');});window.scrollTo(0,0);if(view==='overview')drawChart();}));
$('refresh').addEventListener('click',()=>refresh());
$('logout').addEventListener('click',async()=>{try{await api('/api/logout',{});pairing();toast('Este iPhone foi desconectado.');}catch{toast('Não foi possível desconectar agora. Tente novamente ou remova o aparelho pelo computador.');}});
setInterval(()=>{if(authorized&&!document.hidden)refresh();},500);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});window.addEventListener('resize',drawChart);
if('serviceWorker' in navigator&&window.isSecureContext)navigator.serviceWorker.register('/sw.js').catch(()=>{});
await refresh();
