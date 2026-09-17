'use strict';
const $ = id => document.getElementById(id);
let state = {cycles: []}, selected = null, toast;
function message(text) { $('message').textContent = text; $('message').hidden = false; clearTimeout(toast); toast = setTimeout(() => $('message').hidden = true, 9000); }
async function api(path, data) {
  const res = await fetch(path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Relay-Request':'1'},body:JSON.stringify(data)});
  const obj = await res.json(); if (!res.ok) throw new Error(obj.error || '请求失败'); return obj;
}
function node(tag, text, cls) { const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(cls)e.className=cls; return e; }
function current() { return state.cycles.find(c => c.id === Number(selected)); }
function render() {
  $('login').hidden=true; $('dashboard').hidden=false; $('logout').hidden=false;
  $('admin').hidden=state.role!=='admin';
  if(state.gateway_url) { $('gateway').href=state.gateway_url; }
  if (!state.cycles.some(c=>c.id===Number(selected))) selected=state.cycles[0]?.id;
  $('cycle-select').replaceChildren(...state.cycles.map(c=>{const o=node('option',c.name);o.value=c.id;return o;}));
  $('cycle-select').value=selected || ''; $('cycle-select').hidden=!state.cycles.length;
  const c=current(); $('empty').hidden=!!c; $('manage').hidden=!c||!!c.closed;
  $('cards').replaceChildren(); $('status').textContent=''; $('summary').replaceChildren();
  if(!c)return;
  const status=c.closed?'已封账':c.needs_review?'待管理员核对 · 当前比例暂供参考':!c.initialized?'等待首次采样 · 暂按人数平分':'进行中 · 当前预估';
  $('status').textContent=`${c.start} — ${c.end}  ·  ${status}`;
  for(const m of c.members){
    const card=node('article',undefined,'card'),head=node('div',undefined,'member-head');
    head.append(node('div',Array.from(m.name)[0],'avatar'),node('strong',m.name));
    const value=node('div',m.share.toFixed(2),'share');value.append(node('small','%'));
    const bar=node('progress');bar.max=100;bar.value=m.share;bar.setAttribute('aria-label',`${m.name}出资比例 ${m.share}%`);
    card.append(head,value,bar,node('p','出资比例 · 个人额度为估算'));$('cards').append(card);
  }
  $('summary').append(node('span',`${c.members.length} 位成员 · ${c.sampled?'更新于 '+new Date(c.sampled).toLocaleString('zh-CN'):'尚未采样'}`),node('strong','合计 100.00%'));
  if(state.role==='admin'){
    $('admin-issue').textContent=c.issue||'每分钟采样一次。检测到重置会暂停分配，核对后再继续。';
    $('admin-totals').textContent=`已记录 ${c.resets} 次重置。累计额度：`+c.member_config.map(m=>`${m.name} [${m.user_id}] ${Number(c.usage[m.user_id]).toFixed(4)}%`).join('；');
    $('events').replaceChildren(...c.events.map(e=>{const el=node('div',undefined,'event');el.append(node('strong',`${new Date(e.created).toLocaleString('zh-CN')} · ${e.kind}`),node('div',e.note),node('pre',e.payload));return el;}));
  }
}
async function run(button, fn){button.disabled=true;try{await fn();}catch(e){message(e.message);}finally{button.disabled=false;}}
$('login-form').addEventListener('submit',e=>{e.preventDefault();run(e.submitter,async()=>{await api('/api/login',{password:$('password').value});$('password').value='';state=await api('/api/overview');render();});});
$('logout').onclick=async()=>{await api('/api/logout',{});location.reload();};
$('cycle-select').onchange=e=>{selected=e.target.value;render();};
function pairs(raw){return raw.trim()?raw.trim().split(/\r?\n/).map(line=>{const parts=line.split(/[,，]/);if(parts.length!==2||!parts[0].trim()||!parts[1].trim())throw new Error('请按每行两个值、逗号分隔填写');return parts.map(x=>x.trim());}):[];}
$('create-form').onsubmit=e=>{e.preventDefault();run(e.submitter,async()=>{const f=new FormData(e.target);state=await api('/api/cycles',{name:f.get('name'),account:Number(f.get('account')),start:f.get('start'),end:f.get('end'),members:pairs(f.get('members')).map(([id,name])=>({user_id:Number(id),name}))});selected=null;render();e.target.reset();message('周期已创建，请确认首次采样基线');});};
$('adjust-form').onsubmit=e=>{e.preventDefault();run(e.submitter,async()=>{const f=new FormData(e.target),corrections={};for(const [id,v] of pairs(f.get('corrections'))){if(id in corrections)throw new Error('用户 ID 重复');if(!Number.isFinite(Number(v)))throw new Error('用量须为数值');corrections[id]=Number(v);}state=await api('/api/adjust',{cycle:current().id,resets:Number(f.get('resets')),corrections,note:f.get('note')});render();e.target.reset();message('已保存核对记录');});};
$('sample').onclick=e=>run(e.target,async()=>{try{state=await api('/api/sample',{cycle:current().id});render();message('采样完成');}finally{state=await api('/api/overview');render();}});
$('baseline').onclick=e=>run(e.target,async()=>{if(!confirm('已补记官方/重置卡次数，并核对、补录了采样空档消耗？建立基线不会自动补记这些数据。'))return;state=await api('/api/rebaseline',{cycle:current().id,confirmed:true});render();message('已建立新基线，继续自动采样');});
$('close').onclick=e=>run(e.target,async()=>{if(!confirm('确认已完成最后一次采样和漏记核对？本月比例将被冻结，无法再修改。'))return;state=await api('/api/close',{cycle:current().id,confirmed:true});render();message('本期已封账');});
api('/api/overview').then(s=>{state=s;render();}).catch(()=>{});
setInterval(async()=>{if($('dashboard').hidden)return;try{state=await api('/api/overview');render();}catch(e){message('刷新失败，请检查网络或重新登录');}},60000);
