#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""状态页与管理后台的 HTML（纯前端，通过 /api 与后端交互）。"""

STATUS_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>服务器监控状态</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         background:#0f172a; color:#e2e8f0; }
  header { padding:20px 24px; border-bottom:1px solid #1e293b; display:flex;
           align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; }
  h1 { font-size:20px; margin:0; }
  .muted { color:#94a3b8; font-size:13px; }
  main { padding:24px; max-width:1100px; margin:0 auto; }
  .summary { display:flex; gap:16px; flex-wrap:wrap; margin-bottom:20px; }
  .card { background:#1e293b; border-radius:12px; padding:16px 20px; flex:1; min-width:140px; }
  .card .n { font-size:28px; font-weight:600; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:14px; }
  .srv { background:#1e293b; border-radius:12px; padding:16px; border-left:4px solid #64748b; }
  .srv.healthy { border-color:#22c55e; }
  .srv.suspect { border-color:#eab308; }
  .srv.down, .srv.rebooting { border-color:#ef4444; }
  .srv.recovering { border-color:#3b82f6; }
  .srv h3 { margin:0 0 8px; font-size:16px; display:flex; justify-content:space-between; }
  .badge { font-size:12px; padding:2px 8px; border-radius:999px; background:#334155; }
  .row { font-size:13px; color:#cbd5e1; margin:3px 0; }
  a.link { color:#60a5fa; text-decoration:none; font-size:13px; }
  .events { margin-top:28px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { text-align:left; padding:8px; border-bottom:1px solid #1e293b; }
  .lv-critical { color:#f87171; } .lv-warning { color:#fbbf24; } .lv-info { color:#93c5fd; }
</style>
</head>
<body>
<header>
  <div><h1>🖥️ 服务器监控状态</h1><div class="muted" id="lastrun">加载中…</div></div>
  <div><a class="link" href="admin">管理后台 →</a></div>
</header>
<main>
  <div class="summary" id="summary"></div>
  <div class="grid" id="grid"></div>
  <div class="events">
    <h2 style="font-size:16px;">最近事件</h2>
    <table><thead><tr><th>时间</th><th>服务器</th><th>级别</th><th>信息</th></tr></thead>
    <tbody id="events"></tbody></table>
  </div>
</main>
<script>
const STATE_CN = {healthy:"正常",suspect:"疑似异常",down:"宕机",rebooting:"重启中",recovering:"恢复中"};
async function load(){
  const r = await fetch('api/status'); const d = await r.json();
  document.getElementById('lastrun').textContent = '最后检测：' + (d.last_run || '尚未运行');
  const servers = d.servers || [];
  const counts = {healthy:0,suspect:0,down:0,rebooting:0,recovering:0};
  servers.forEach(s => { counts[s.state] = (counts[s.state]||0)+1; });
  document.getElementById('summary').innerHTML =
    `<div class="card"><div class="n">${servers.length}</div><div class="muted">监控总数</div></div>
     <div class="card"><div class="n" style="color:#22c55e">${counts.healthy}</div><div class="muted">正常</div></div>
     <div class="card"><div class="n" style="color:#eab308">${counts.suspect}</div><div class="muted">疑似异常</div></div>
     <div class="card"><div class="n" style="color:#ef4444">${counts.down+counts.rebooting}</div><div class="muted">宕机/重启</div></div>`;
  document.getElementById('grid').innerHTML = servers.map(s => `
    <div class="srv ${s.state}">
      <h3>${s.name} <span class="badge">${STATE_CN[s.state]||s.state}</span></h3>
      <div class="row">ID：${s.id}</div>
      <div class="row">IP：${s.ip||'-'}</div>
      <div class="row">状态：${s.online===true?'🟢 在线':(s.online===false?'🔴 离线':'⚪ 未知')} (${s.status_text||'-'})</div>
      <div class="row muted">检测：${s.last_check||'-'}</div>
    </div>`).join('') || '<div class="muted">暂无监控项，请到管理后台添加或等待自动发现。</div>';
  document.getElementById('events').innerHTML = (d.events||[]).slice(0,30).map(e => `
    <tr><td class="muted">${e.time}</td><td>${e.name}</td>
    <td class="lv-${e.level}">${e.level}</td><td>${e.message}</td></tr>`).join('');
}
load(); setInterval(load, 15000);
</script>
</body>
</html>"""


ADMIN_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>监控管理后台</title>
<style>
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; background:#0f172a; color:#e2e8f0; }
  header { padding:20px 24px; border-bottom:1px solid #1e293b; }
  main { padding:24px; max-width:900px; margin:0 auto; }
  h1{font-size:20px;margin:0} h2{font-size:16px;margin-top:28px;border-bottom:1px solid #1e293b;padding-bottom:8px}
  label{display:block;font-size:13px;color:#94a3b8;margin:10px 0 4px}
  input,select{width:100%;padding:9px;border:1px solid #334155;background:#1e293b;color:#e2e8f0;border-radius:8px;font-size:14px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  button{margin-top:16px;padding:10px 18px;border:0;border-radius:8px;background:#2563eb;color:#fff;font-size:14px;cursor:pointer}
  button.sec{background:#334155} button.danger{background:#dc2626}
  table{width:100%;border-collapse:collapse;font-size:13px;margin-top:12px}
  th,td{text-align:left;padding:8px;border-bottom:1px solid #1e293b}
  .msg{margin-top:12px;font-size:13px} .ok{color:#22c55e} .err{color:#f87171}
  .row-inline{display:flex;gap:8px;align-items:flex-end}
  a.link{color:#60a5fa;text-decoration:none}
</style>
</head>
<body>
<header><h1>⚙️ 监控管理后台</h1> <a class="link" href="./">← 返回状态页</a></header>
<main>
  <div id="authbox">
    <label>管理密码（ADMIN_TOKEN）</label>
    <input type="password" id="token" placeholder="输入管理密码">
    <button onclick="saveToken()">进入</button>
    <div class="msg err" id="autherr"></div>
  </div>

  <div id="panel" style="display:none">
    <h2>服务商 / 全局设置</h2>
    <div class="grid2">
      <div><label>API 地址</label><input id="base_url"></div>
      <div><label>账号（手机号/邮箱）</label><input id="account"></div>
      <div><label>API 密钥</label><input id="api_key" type="password" placeholder="留空则不修改"></div>
      <div><label>动作</label><select id="action"><option value="on">开机 (on)</option><option value="hard_reboot">硬重启 (hard_reboot)</option></select></div>
      <div><label>疑似阈值（次）</label><input id="suspect_threshold" type="number"></div>
      <div><label>动作冷却（秒）</label><input id="reboot_cooldown" type="number"></div>
      <div><label>恢复超时（秒）</label><input id="recover_timeout" type="number"></div>
      <div><label>动作次数上限（0=不限）</label><input id="reboot_limit" type="number"></div>
      <div><label>统计窗口</label><select id="reboot_limit_window"><option value="hour">每小时</option><option value="day">每天</option></select></div>
      <div><label>仅模拟 DRY_RUN</label><select id="dry_run"><option value="false">否（自动执行）</option><option value="true">是（只检测）</option></select></div>
      <div><label>通知类型</label><select id="webhook_type"><option value="custom">自定义 Webhook</option><option value="pushplus">PushPlus</option></select></div>
      <div><label>通知地址 / Token</label><input id="webhook_url" placeholder="Webhook URL 或 PushPlus Token"></div>
    </div>
    <button onclick="saveSettings()">保存设置</button>
    <span class="msg" id="setmsg"></span>

    <h2>监控服务器</h2>
    <div class="grid2">
      <div><label>服务器 ID</label><input id="s_id"></div>
      <div><label>名称</label><input id="s_name"></div>
      <div><label>IP（可选）</label><input id="s_ip"></div>
    </div>
    <button onclick="addServer()">添加 / 更新</button>
    <button class="sec" onclick="discover()">从账户自动发现</button>
    <button class="sec" onclick="runNow()">立即检测一次</button>
    <span class="msg" id="srvmsg"></span>
    <table><thead><tr><th>ID</th><th>名称</th><th>IP</th><th>启用</th><th>状态</th><th>操作</th></tr></thead>
    <tbody id="srvbody"></tbody></table>
  </div>
</main>
<script>
let TOKEN = sessionStorage.getItem('adm_token') || '';
function hdr(){ return {'Content-Type':'application/json','X-Admin-Token':TOKEN}; }
function saveToken(){ TOKEN = document.getElementById('token').value.trim(); sessionStorage.setItem('adm_token',TOKEN); init(); }
async function api(path, method='GET', body=null){
  const opt={method,headers:hdr()}; if(body) opt.body=JSON.stringify(body);
  const r=await fetch('api/'+path,opt);
  if(r.status===401){ throw new Error('unauthorized'); }
  return r.json();
}
async function init(){
  try{
    const cfg = await api('admin/config');
    document.getElementById('authbox').style.display='none';
    document.getElementById('panel').style.display='block';
    const p=cfg.provider,s=cfg.settings;
    base_url.value=p.base_url||''; account.value=p.account||''; api_key.value='';
    action.value=s.action||'on'; suspect_threshold.value=s.suspect_threshold;
    reboot_cooldown.value=s.reboot_cooldown; recover_timeout.value=s.recover_timeout;
    reboot_limit.value=s.reboot_limit; reboot_limit_window.value=s.reboot_limit_window;
    dry_run.value=String(s.dry_run); webhook_type.value=s.webhook_type||'custom';
    webhook_url.value=s.webhook_url||'';
    renderServers(cfg);
  }catch(e){ document.getElementById('autherr').textContent='密码错误或未授权'; }
}
function renderServers(cfg){
  const state=cfg.state||{};
  document.getElementById('srvbody').innerHTML=(cfg.servers||[]).map(s=>{
    const st=state[String(s.id)]||{};
    return `<tr><td>${s.id}</td><td>${s.name||''}</td><td>${s.ip||'-'}</td>
      <td>${s.enabled!==false?'✅':'❌'}</td><td>${st.state||'-'}</td>
      <td><button class="sec" onclick="toggleSrv('${s.id}')">启停</button>
      <button class="danger" onclick="delSrv('${s.id}')">删除</button></td></tr>`;
  }).join('');
}
async function saveSettings(){
  const body={provider:{base_url:base_url.value,account:account.value},settings:{
    action:action.value,suspect_threshold:+suspect_threshold.value,reboot_cooldown:+reboot_cooldown.value,
    recover_timeout:+recover_timeout.value,reboot_limit:+reboot_limit.value,reboot_limit_window:reboot_limit_window.value,
    dry_run:dry_run.value==='true',webhook_type:webhook_type.value,webhook_url:webhook_url.value}};
  if(api_key.value) body.provider.api_key=api_key.value;
  await api('admin/config','POST',body);
  document.getElementById('setmsg').className='msg ok'; document.getElementById('setmsg').textContent='已保存';
}
async function addServer(){
  await api('admin/server','POST',{id:s_id.value.trim(),name:s_name.value.trim(),ip:s_ip.value.trim(),enabled:true});
  s_id.value=s_name.value=s_ip.value=''; refresh('已添加/更新');
}
async function delSrv(id){ await api('admin/server','DELETE',{id}); refresh('已删除'); }
async function toggleSrv(id){ await api('admin/server/toggle','POST',{id}); refresh('已切换'); }
async function discover(){ const r=await api('admin/discover','POST'); refresh('已发现 '+(r.added||0)+' 台'); }
async function runNow(){ document.getElementById('srvmsg').textContent='检测中…'; await api('admin/run','POST'); refresh('检测完成'); }
async function refresh(msg){ const cfg=await api('admin/config'); renderServers(cfg);
  const m=document.getElementById('srvmsg'); m.className='msg ok'; m.textContent=msg||''; }
if(TOKEN) init();
</script>
</body>
</html>"""
