# -*- coding: utf-8 -*-
"""状态页与管理后台的 HTML。纯前端，靠 /api 跟后端聊。"""

# 一份共用的设计 token + 基础组件样式，两个页面各自内联一份。
_BASE_CSS = """
  :root{
    --bg:#0b1120; --surface:#121a2b; --surface-2:#1a2438;
    --line:rgba(148,163,184,.14); --line-strong:rgba(148,163,184,.28);
    --text:#e6ebf4; --muted:#8a97ad; --faint:#5b6678;
    --brand:#6366f1; --brand-ink:#c7d2fe;
    --ok:#34d399; --warn:#fbbf24; --bad:#f87171; --info:#60a5fa;
    --radius:14px; --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.25);
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;
    background:radial-gradient(1200px 600px at 80% -10%,rgba(99,102,241,.12),transparent 60%),var(--bg);
    color:var(--text); line-height:1.55; -webkit-font-smoothing:antialiased;
  }
  a{color:var(--brand-ink);text-decoration:none}
  a:hover{text-decoration:underline}
  .muted{color:var(--muted)} .faint{color:var(--faint)}
  .wrap{max-width:1120px;margin:0 auto;padding:0 24px}
  .topbar{
    position:sticky;top:0;z-index:5;backdrop-filter:blur(10px);
    background:rgba(11,17,32,.72);border-bottom:1px solid var(--line);
  }
  .topbar .wrap{display:flex;align-items:center;justify-content:space-between;gap:16px;height:64px}
  .brand{display:flex;align-items:center;gap:10px;font-weight:650;font-size:16px;letter-spacing:.2px}
  .brand .mark{width:26px;height:26px;border-radius:8px;
    background:linear-gradient(135deg,var(--brand),#8b5cf6);display:grid;place-items:center;
    font-size:14px;color:#fff}
  .btn{
    appearance:none;border:1px solid var(--line-strong);background:var(--surface-2);
    color:var(--text);padding:9px 14px;border-radius:10px;font-size:13.5px;cursor:pointer;
    transition:.15s;display:inline-flex;align-items:center;gap:7px;font-weight:500;
  }
  .btn:hover{border-color:var(--brand);background:#22304d}
  .btn:disabled{opacity:.55;cursor:not-allowed}
  .btn.primary{background:var(--brand);border-color:var(--brand);color:#fff}
  .btn.primary:hover{background:#4f52e0}
  .btn.ghost{background:transparent}
  .btn.danger{color:var(--bad);border-color:rgba(248,113,113,.35)}
  .btn.danger:hover{background:rgba(248,113,113,.12);border-color:var(--bad)}
  .btn.sm{padding:5px 10px;font-size:12.5px;border-radius:8px}
  .card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}
  .dot{width:9px;height:9px;border-radius:50%;display:inline-block;flex:none}
  .dot.ok{background:var(--ok);box-shadow:0 0 0 3px rgba(52,211,153,.18)}
  .dot.bad{background:var(--bad);box-shadow:0 0 0 3px rgba(248,113,113,.18)}
  .dot.warn{background:var(--warn);box-shadow:0 0 0 3px rgba(251,191,36,.18)}
  .dot.unknown{background:var(--faint);box-shadow:0 0 0 3px rgba(91,102,120,.18)}
  .badge{font-size:12px;font-weight:600;padding:3px 9px;border-radius:999px;
    border:1px solid transparent;white-space:nowrap}
  .badge.healthy{color:var(--ok);background:rgba(52,211,153,.12);border-color:rgba(52,211,153,.3)}
  .badge.suspect{color:var(--warn);background:rgba(251,191,36,.12);border-color:rgba(251,191,36,.3)}
  .badge.down,.badge.rebooting{color:var(--bad);background:rgba(248,113,113,.12);border-color:rgba(248,113,113,.3)}
  .badge.recovering{color:var(--info);background:rgba(96,165,250,.12);border-color:rgba(96,165,250,.3)}
  .toast{position:fixed;right:20px;bottom:20px;display:flex;flex-direction:column;gap:8px;z-index:50}
  .toast .t{background:var(--surface-2);border:1px solid var(--line-strong);border-radius:10px;
    padding:11px 15px;font-size:13.5px;box-shadow:var(--shadow);animation:slide .25s ease;max-width:340px}
  .toast .t.ok{border-color:rgba(52,211,153,.4)} .toast .t.err{border-color:rgba(248,113,113,.4);color:var(--bad)}
  @keyframes slide{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
  @keyframes spin{to{transform:rotate(360deg)}}
  .spin{display:inline-block;width:13px;height:13px;border:2px solid rgba(255,255,255,.3);
    border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite}
"""

STATUS_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>服务器监控</title>
<style>
__BASE__
  main{padding:28px 0 60px}
  .live{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted)}
  .live .pulse{width:8px;height:8px;border-radius:50%;background:var(--ok);
    box-shadow:0 0 0 0 rgba(52,211,153,.5);animation:beat 2s infinite}
  @keyframes beat{0%{box-shadow:0 0 0 0 rgba(52,211,153,.45)}70%{box-shadow:0 0 0 7px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}
  .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:24px}
  .stat{padding:16px 18px}
  .stat .n{font-size:30px;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums}
  .stat .l{font-size:12.5px;color:var(--muted);margin-top:4px}
  .sec-title{display:flex;align-items:center;justify-content:space-between;margin:0 0 14px}
  .sec-title h2{font-size:15px;margin:0;font-weight:600}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:14px;margin-bottom:32px}
  .srv{padding:16px 18px;position:relative;overflow:hidden}
  .srv::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--faint)}
  .srv.healthy::before{background:var(--ok)} .srv.suspect::before{background:var(--warn)}
  .srv.down::before,.srv.rebooting::before{background:var(--bad)} .srv.recovering::before{background:var(--info)}
  .srv .head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}
  .srv .name{font-weight:600;font-size:15px;display:flex;align-items:center;gap:9px;min-width:0}
  .srv .name span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .kv{display:flex;justify-content:space-between;gap:12px;font-size:13px;padding:3px 0}
  .kv .k{color:var(--muted)} .kv .v{color:var(--text);text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .empty{padding:48px;text-align:center;color:var(--muted)}
  .ev{padding:0;overflow:hidden}
  .ev .row{display:grid;grid-template-columns:150px 1fr;gap:14px;padding:11px 18px;border-top:1px solid var(--line);font-size:13px;align-items:baseline}
  .ev .row:first-child{border-top:0}
  .ev .when{color:var(--faint);font-variant-numeric:tabular-nums}
  .ev .who{color:var(--muted);margin-right:8px}
  .ev .lv{font-size:11px;padding:1px 7px;border-radius:6px;margin-right:8px;font-weight:600}
  .lv.critical{color:var(--bad);background:rgba(248,113,113,.12)}
  .lv.warning{color:var(--warn);background:rgba(251,191,36,.12)}
  .lv.info{color:var(--info);background:rgba(96,165,250,.12)}
  @media(max-width:560px){.ev .row{grid-template-columns:1fr}.ev .when{order:2}}
</style>
</head>
<body>
<div class="topbar"><div class="wrap">
  <div class="brand"><span class="mark">◎</span> 服务器监控</div>
  <div style="display:flex;align-items:center;gap:18px">
    <div class="live"><span class="pulse"></span><span id="lastrun">连接中…</span></div>
    <a class="btn ghost sm" href="manage">管理后台</a>
  </div>
</div></div>

<main class="wrap">
  <div class="stats" id="stats"></div>
  <div class="sec-title"><h2>服务器</h2><span class="muted" id="srvcount"></span></div>
  <div class="grid" id="grid"></div>
  <div class="sec-title"><h2>最近事件</h2></div>
  <div class="card ev" id="events"></div>
</main>

<script>
const STATE_CN={healthy:"正常",suspect:"疑似异常",down:"宕机",rebooting:"重启中",recovering:"恢复中"};
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function powerDot(o){return o===true?['ok','在线']:o===false?['bad','离线']:['unknown','未知'];}

async function load(){
  let d;
  try{ d=await (await fetch('api/status')).json(); }
  catch(e){ $('lastrun').textContent='无法连接后端'; return; }

  $('lastrun').textContent='最后检测 '+(d.last_run?fmt(d.last_run):'尚未运行');
  const servers=d.servers||[];
  const c={healthy:0,suspect:0,down:0,rebooting:0,recovering:0};
  servers.forEach(s=>c[s.state]=(c[s.state]||0)+1);
  const problem=c.down+c.rebooting+c.suspect+c.recovering;

  $('stats').innerHTML=[
    ['总数',servers.length,''],
    ['正常',c.healthy,'var(--ok)'],
    ['疑似异常',c.suspect,'var(--warn)'],
    ['宕机 / 处理中',c.down+c.rebooting+c.recovering,problem?'var(--bad)':''],
  ].map(([l,n,col])=>`<div class="card stat"><div class="n" style="color:${col||'var(--text)'}">${n}</div><div class="l">${l}</div></div>`).join('');

  $('srvcount').textContent=servers.length?`共 ${servers.length} 台`:'';
  $('grid').innerHTML=servers.length?servers.map(s=>{
    const [dc,dl]=powerDot(s.online);
    return `<div class="card srv ${esc(s.state)}">
      <div class="head">
        <div class="name"><span class="dot ${dc}"></span><span>${esc(s.name)}</span></div>
        <span class="badge ${esc(s.state)}">${STATE_CN[s.state]||esc(s.state)}</span>
      </div>
      <div class="kv"><span class="k">电源</span><span class="v">${dl} · ${esc(s.status_text||'-')}</span></div>
      <div class="kv"><span class="k">ID</span><span class="v">${esc(s.id)}</span></div>
      <div class="kv"><span class="k">IP</span><span class="v">${esc(s.ip||'-')}</span></div>
      <div class="kv"><span class="k">最后检测</span><span class="v faint">${s.last_check?fmt(s.last_check):'-'}</span></div>
    </div>`;
  }).join(''):`<div class="card empty">还没有监控项。到 <a href="manage">管理后台</a> 添加，或让程序自动发现。</div>`;

  const ev=d.events||[];
  $('events').innerHTML=ev.length?ev.slice(0,30).map(e=>`
    <div class="row">
      <span class="when">${fmt(e.time)}</span>
      <span><span class="lv ${esc(e.level)}">${esc(e.level)}</span><span class="who">${esc(e.name)}</span>${esc(e.message)}</span>
    </div>`).join(''):`<div class="empty">暂无事件</div>`;
}
function fmt(iso){ // 2026-01-02T03:04:05+08:00 -> 01-02 03:04:05
  try{const d=new Date(iso);if(isNaN(d))return iso;
    const p=n=>String(n).padStart(2,'0');
    return `${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }catch(e){return iso;}
}
load(); setInterval(load,15000);
</script>
</body>
</html>""".replace("__BASE__", _BASE_CSS)


ADMIN_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>监控管理后台</title>
<style>
__BASE__
  main{padding:28px 0 60px}
  .login{max-width:380px;margin:8vh auto 0;padding:28px}
  .login h2{margin:0 0 4px;font-size:18px}
  .field{margin-bottom:2px}
  label{display:block;font-size:12.5px;color:var(--muted);margin:14px 0 6px}
  input,select{width:100%;padding:10px 12px;border:1px solid var(--line-strong);
    background:var(--surface-2);color:var(--text);border-radius:10px;font-size:14px;transition:.15s}
  input:focus,select:focus{outline:none;border-color:var(--brand);box-shadow:0 0 0 3px rgba(99,102,241,.2)}
  .panel{display:none}
  section.card{padding:20px 22px;margin-bottom:20px}
  section h2{font-size:15px;margin:0 0 4px;font-weight:600}
  section .hint{font-size:12.5px;color:var(--muted);margin-bottom:8px}
  .grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:0 18px}
  .actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}
  table{width:100%;border-collapse:collapse;font-size:13.5px;margin-top:12px}
  th{text-align:left;font-weight:600;color:var(--muted);font-size:12px;padding:8px 10px;border-bottom:1px solid var(--line-strong)}
  td{padding:10px;border-bottom:1px solid var(--line);vertical-align:middle}
  tr:last-child td{border-bottom:0}
  .tbl-actions{display:flex;gap:6px;justify-content:flex-end}
  .pill{font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid var(--line-strong);color:var(--muted)}
  .pill.on{color:var(--ok);border-color:rgba(52,211,153,.35);background:rgba(52,211,153,.1)}
  .empty-row td{text-align:center;color:var(--muted);padding:26px}
</style>
</head>
<body>
<div class="topbar"><div class="wrap">
  <div class="brand"><span class="mark">◎</span> 监控管理后台</div>
  <a class="btn ghost sm" href="./">← 状态页</a>
</div></div>

<main class="wrap">
  <div class="card login" id="login">
    <h2>登录</h2>
    <p class="muted" style="margin:0">输入管理密码（ADMIN_TOKEN）继续。</p>
    <div class="field">
      <label>管理密码</label>
      <input type="password" id="token" placeholder="••••••••" autofocus>
    </div>
    <div class="actions"><button class="btn primary" id="loginBtn" onclick="doLogin()" style="width:100%;justify-content:center">进入</button></div>
  </div>

  <div class="panel" id="panel">
    <section class="card">
      <h2>服务商与策略</h2>
      <div class="hint">凭据也可以只在环境变量里配；这里填了会覆盖。</div>
      <div class="grid2">
        <div><label>API 地址</label><input id="base_url"></div>
        <div><label>账号（手机号 / 邮箱）</label><input id="account"></div>
        <div><label>API 密钥</label><input id="api_key" type="password"></div>
        <div><label>默认动作</label><select id="action">
          <option value="on">关机时开机 (on)</option>
          <option value="hard_reboot">关机时硬重启 (hard_reboot)</option>
        </select></div>
        <div><label>疑似阈值（连续几次异常判宕机）</label><input id="suspect_threshold" type="number" min="1"></div>
        <div><label>动作冷却（秒）</label><input id="reboot_cooldown" type="number" min="0"></div>
        <div><label>恢复超时（秒）</label><input id="recover_timeout" type="number" min="0"></div>
        <div><label>动作次数上限（0 = 不限）</label><input id="reboot_limit" type="number" min="0"></div>
        <div><label>统计窗口</label><select id="reboot_limit_window">
          <option value="hour">每小时</option><option value="day">每天</option></select></div>
        <div><label>运行模式</label><select id="dry_run">
          <option value="false">自动执行动作</option><option value="true">仅检测（DRY_RUN）</option></select></div>
        <div><label>通知类型</label><select id="webhook_type">
          <option value="custom">自定义 Webhook</option><option value="pushplus">PushPlus</option></select></div>
        <div><label>通知地址 / Token</label><input id="webhook_url" placeholder="Webhook URL 或 PushPlus Token"></div>
      </div>
      <div class="hint" style="margin-top:14px">提示：状态识别不出来（未知）时会一律硬重启，不受“默认动作”影响。</div>
      <div class="actions"><button class="btn primary" id="saveBtn" onclick="saveSettings()">保存设置</button></div>
    </section>

    <section class="card">
      <h2>服务器</h2>
      <div class="hint">按 ID 添加要盯的机器；留空不管，可点“自动发现”从账户拉取。</div>
      <div class="grid2">
        <div><label>服务器 ID</label><input id="s_id"></div>
        <div><label>名称（可选）</label><input id="s_name"></div>
        <div><label>IP（可选）</label><input id="s_ip"></div>
      </div>
      <div class="actions">
        <button class="btn primary" id="addBtn" onclick="addServer()">添加 / 更新</button>
        <button class="btn" id="discBtn" onclick="discover()">自动发现</button>
        <button class="btn" id="runBtn" onclick="runNow()">立即检测一次</button>
      </div>
      <table>
        <thead><tr><th>ID</th><th>名称</th><th>IP</th><th>启用</th><th>状态</th><th></th></tr></thead>
        <tbody id="srvbody"></tbody>
      </table>
    </section>
  </div>
</main>
<div class="toast" id="toast"></div>

<script>
const STATE_CN={healthy:"正常",suspect:"疑似异常",down:"宕机",rebooting:"重启中",recovering:"恢复中"};
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let TOKEN=sessionStorage.getItem('adm_token')||'';

function toast(msg,kind='ok'){
  const t=document.createElement('div');t.className='t '+kind;t.textContent=msg;
  $('toast').appendChild(t);setTimeout(()=>t.remove(),3200);
}
async function api(path,method='GET',body=null){
  const opt={method,headers:{'Content-Type':'application/json','X-Admin-Token':TOKEN}};
  if(body)opt.body=JSON.stringify(body);
  const r=await fetch('api/'+path,opt);
  if(r.status===401)throw new Error('unauthorized');
  const d=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(d.error||('HTTP '+r.status));
  return d;
}
async function busy(btn,fn){
  const el=$(btn),txt=el.innerHTML;el.disabled=true;el.innerHTML='<span class="spin"></span>处理中';
  try{await fn();}catch(e){toast(e.message==='unauthorized'?'登录已失效，请重新登录':('出错：'+e.message),'err');
    if(e.message==='unauthorized')logout();}
  finally{el.disabled=false;el.innerHTML=txt;}
}
function logout(){sessionStorage.removeItem('adm_token');$('panel').style.display='none';$('login').style.display='block';}

function doLogin(){
  TOKEN=$('token').value.trim();
  if(!TOKEN){toast('请输入密码','err');return;}
  sessionStorage.setItem('adm_token',TOKEN);
  busy('loginBtn',async()=>{await refreshConfig();$('login').style.display='none';$('panel').style.display='block';});
}
$('token').addEventListener('keydown',e=>{if(e.key==='Enter')doLogin();});

async function refreshConfig(){
  const cfg=await api('admin/config');
  const p=cfg.provider||{},s=cfg.settings||{};
  $('base_url').value=p.base_url||'';
  $('account').value=p.account||'';
  $('api_key').value='';$('api_key').placeholder=p.api_key_set?'已设置，留空则不修改':'尚未设置';
  ['action','suspect_threshold','reboot_cooldown','recover_timeout','reboot_limit','reboot_limit_window','webhook_type','webhook_url']
    .forEach(k=>{if($(k)&&s[k]!=null)$(k).value=s[k];});
  $('dry_run').value=String(!!s.dry_run);
  renderServers(cfg);
}
function renderServers(cfg){
  const state=cfg.state||{},rows=(cfg.servers||[]);
  $('srvbody').innerHTML=rows.length?rows.map(s=>{
    const st=state[String(s.id)]||{},on=s.enabled!==false;
    const badge=st.state?`<span class="badge ${esc(st.state)}">${STATE_CN[st.state]||esc(st.state)}</span>`:'<span class="faint">-</span>';
    return `<tr>
      <td>${esc(s.id)}</td><td>${esc(s.name||'')}</td><td>${esc(s.ip||'-')}</td>
      <td><span class="pill ${on?'on':''}">${on?'启用':'停用'}</span></td>
      <td>${badge}</td>
      <td><div class="tbl-actions">
        <button class="btn sm" onclick="toggleSrv('${esc(s.id)}')">${on?'停用':'启用'}</button>
        <button class="btn sm danger" onclick="delSrv('${esc(s.id)}')">删除</button>
      </div></td></tr>`;
  }).join(''):'<tr class="empty-row"><td colspan="6">还没有服务器，添加一个或点“自动发现”。</td></tr>';
}

function saveSettings(){busy('saveBtn',async()=>{
  const body={provider:{base_url:$('base_url').value.trim(),account:$('account').value.trim()},
    settings:{action:$('action').value,suspect_threshold:+$('suspect_threshold').value,
      reboot_cooldown:+$('reboot_cooldown').value,recover_timeout:+$('recover_timeout').value,
      reboot_limit:+$('reboot_limit').value,reboot_limit_window:$('reboot_limit_window').value,
      dry_run:$('dry_run').value==='true',webhook_type:$('webhook_type').value,webhook_url:$('webhook_url').value.trim()}};
  if($('api_key').value)body.provider.api_key=$('api_key').value;
  await api('admin/config','POST',body);await refreshConfig();toast('设置已保存');
});}
function addServer(){busy('addBtn',async()=>{
  const id=$('s_id').value.trim();if(!id){toast('请填服务器 ID','err');return;}
  await api('admin/server','POST',{id,name:$('s_name').value.trim(),ip:$('s_ip').value.trim(),enabled:true});
  $('s_id').value=$('s_name').value=$('s_ip').value='';await refreshConfig();toast('已保存');
});}
async function delSrv(id){if(!confirm('删除服务器 '+id+'？'))return;
  try{await api('admin/server','DELETE',{id});await refreshConfig();toast('已删除');}catch(e){toast('出错：'+e.message,'err');}}
async function toggleSrv(id){try{await api('admin/server/toggle','POST',{id});await refreshConfig();}catch(e){toast('出错：'+e.message,'err');}}
function discover(){busy('discBtn',async()=>{const r=await api('admin/discover','POST');await refreshConfig();toast('自动发现新增 '+(r.added||0)+' 台');});}
function runNow(){busy('runBtn',async()=>{const r=await api('admin/run','POST');await refreshConfig();toast('检测完成，共 '+((r.summary||{}).total||0)+' 台');});}

if(TOKEN)busy('loginBtn',async()=>{await refreshConfig();$('login').style.display='none';$('panel').style.display='block';});
</script>
</body>
</html>""".replace("__BASE__", _BASE_CSS)
