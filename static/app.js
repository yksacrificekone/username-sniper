const $ = id => document.getElementById(id);

const API = '/api/check';

const CHARSETS = {
  letters: 'abcdefghijklmnopqrstuvwxyz',
  letters_and_numbers: 'abcdefghijklmnopqrstuvwxyz0123456789',
  all: 'abcdefghijklmnopqrstuvwxyz0123456789-'
};

let running = false;
let intervalId = null;
let rate = 4;
let hits = [];
let logItems = [];

function $(id){return document.getElementById(id)}

async function checkUsername(name){
  try{
    const res = await fetch(API, { method: 'POST', headers: { 'Content-Type':'application/json' }, body: JSON.stringify({ username: name }) });
    return await res.json();
  }catch(e){
    return { ok: false, status: 'error', msg: e.message };
  }
}

function randomCombo(minLen, maxLen, charset){
  const len = Math.floor(Math.random()*(maxLen-minLen+1))+minLen;
  let out = '';
  for(let i=0;i<len;i++) out += charset[Math.floor(Math.random()*charset.length)];
  // sanitize: ensure regex rules (no leading/trailing hyphen, no double hyphen)
  out = out.replace(/--+/g,'-');
  out = out.replace(/^-+/,'').replace(/-+$/,'');
  if(!out) return randomCombo(minLen,maxLen,charset);
  return out;
}

function appendLog(msg, kind='info'){
  logItems.unshift({ts:new Date().toLocaleTimeString(),msg,kind});
  if(logItems.length>200) logItems.pop();
  renderLog();
}

function renderLog(){
  const el = $('log'); el.innerHTML='';
  logItems.forEach(it=>{
    const d = document.createElement('div'); d.className='log-item '+it.kind; d.textContent = `[${it.ts}] ${it.msg}`; el.appendChild(d);
  })
}

function renderHits(){
  const el = $('hits'); el.innerHTML = '';
  hits.forEach(h=>{ const d = document.createElement('div'); d.textContent='@'+h; d.className='hit'; el.appendChild(d); });
  $('avail-count').textContent = `(${hits.length})`;
}

async function doCheck(name){
  appendLog(`checking @${name}`,'info');
  const r = await checkUsername(name);
  if(!r.ok){ appendLog(`error checking @${name}: ${r.msg||'unknown'}`,'error'); return; }
  if(r.status==='available'){ hits.unshift(name); renderHits(); appendLog(`@${name} → available`,'good'); }
  else if(r.status==='taken'){ appendLog(`@${name} → taken`,'muted'); }
  else if(r.status==='ratelimit'){ appendLog(`@${name} → ratelimited`,'warn'); }
  else appendLog(`@${name} → ${r.status}`,'error');
}

function startSniper(){
  if(running) return; running=true; $('btn-start').disabled=true; $('btn-stop').disabled=false; $('btn-clear').disabled=true; appendLog('sniper started','info');
  const minLen = parseInt($('min-len').value)||3; const maxLen = parseInt($('max-len').value)||5; const charset = CHARSETS[$('charset').value]||CHARSETS.letters_and_numbers;
  const rateInput = parseInt($('rate').value)||4;
  rate = rateInput;
  intervalId = setInterval(()=>{
    const name = randomCombo(minLen,maxLen,charset);
    doCheck(name);
  }, Math.max(50, 1000/Math.max(1,rate)));
}

function stopSniper(){
  if(!running) return; running=false; $('btn-start').disabled=false; $('btn-stop').disabled=true; $('btn-clear').disabled=false; appendLog('sniper stopped','info');
  if(intervalId) clearInterval(intervalId); intervalId=null;
}

function clearAll(){ hits=[]; renderHits(); appendLog('cleared hits','info'); }

window.addEventListener('load',()=>{
  $('rate').addEventListener('input', ()=>{ $('rate-val').textContent = $('rate').value });
  $('btn-check').addEventListener('click', async ()=>{ const v = $('manual').value.trim(); if(!v) return; await doCheck(v); });
  $('btn-start').addEventListener('click', startSniper);
  $('btn-stop').addEventListener('click', stopSniper);
  $('btn-clear').addEventListener('click', clearAll);
});
