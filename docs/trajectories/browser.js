'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const short = oid => oid ? oid.slice(0,10) : '—';
const pretty = value => JSON.stringify(value,null,2);
let catalog, data, conversation, event, tab='activity', side='after', file='', fileQuery='', loadVersion=0;
const objectLink = oid => data.evidence.objects.includes(oid) ? `<a href="data/objects/${esc(oid)}" download="${esc(oid)}.git-object">${esc(oid)}</a>` : esc(oid);
const code = text => `<pre>${esc(text)}</pre>`;
function argumentsHTML(args) {
 if(args && typeof args==='object' && typeof args.content==='string') {const {content,...rest}=args;return code(pretty(rest))+'<h3>File content supplied</h3>'+code(content);}
 return code(pretty(args));
}
const toolRecords = entry => entry.records.filter(r=>r.type==='tool');
function label(entry) {
 const tools=toolRecords(entry);
 if(tools.length) return tools.map(t=>t.name).join(', ');
 if(entry.messages.length) return entry.messages.map(m=>m.role==='user'?'User message':m.blocks.some(b=>b.type==='tool_use')?'Agent requests tools':'Agent response').join(', ');
 return ({'conversation.root':'Conversation created','request.admit':'Turn queued','request.claim':'Turn started','request.terminal':'Turn finished','subagent.terminal':'Child finished','conversation.fork':'Conversation forked'})[entry.kind]||entry.kind;
}
function messageText(message) { return message.blocks.map(b=>b.text||b.thinking||b.name||'').join('\n'); }
function snippet(entry) {
 const tool=toolRecords(entry)[0];
 if(tool) return tool.observation ? observationText(tool.observation) : tool.status;
 return entry.messages.map(messageText).join('\n')||entry.changes.map(c=>c.path).join(', ');
}
function observationText(value) {
 if(typeof value==='string') return value;
 if(value?.content) return value.content.map(x=>x.text||pretty(x)).join('\n');
 return pretty(value);
}
function updateURL() {
 const u=new URL(location.href);
 for(const [k,v] of Object.entries({example:data.id,conversation:conversation.id,event:event.oid,tab,file:file||null})) { if(v) u.searchParams.set(k,v); else u.searchParams.delete(k); }
 history.replaceState(null,'',u);
}
function selectConversation(id, oid) {
 conversation=data.conversations.find(c=>c.id===id)||data.conversations.find(c=>c.id===data.root);
 event=conversation.events.find(e=>e.oid===oid)||[...conversation.events].reverse().find(e=>e.changes.length&&e.kind!=='conversation.root')||conversation.events.at(-1);
 file=''; side='after'; $('search').value='';
 render();
 const active=document.querySelector('#events .event.active'), container=document.querySelector('.timeline');
 if(active && matchMedia('(min-width:801px)').matches) container.scrollTop+=active.getBoundingClientRect().top-container.getBoundingClientRect().top-document.querySelector('.timeline-top').offsetHeight-8;
}
function renderConversations() {
 const roots=data.conversations.filter(c=>!c.identity.owner||!data.conversations.some(x=>x.id===c.identity.owner.parent));
 function node(c) {
  const children=data.conversations.filter(x=>x.identity.owner?.parent===c.id);
  const toolCount=c.events.reduce((n,e)=>n+toolRecords(e).filter(t=>t.status!=='started').length,0);
  return `<div><button data-conversation="${esc(c.id)}" class="${c.id===conversation.id?'active':''}" aria-current="${c.id===conversation.id?'true':'false'}">${esc(c.title)}<small>${c.id===data.root?'Main conversation':'Child agent'} · ${toolCount} tool results</small></button>${children.length?`<div class="child">${children.map(node).join('')}</div>`:''}</div>`;
 }
 $('conversations').innerHTML=roots.map(node).join('');
 $('conversations').querySelectorAll('button').forEach(b=>b.onclick=()=>selectConversation(b.dataset.conversation));
}
function renderEvents() {
 $('conversation-title').textContent=conversation.title;
 const q=$('search').value.toLowerCase(), filter=$('filter').value;
 const visible=conversation.events.filter(e=>(filter==='all'||filter==='changes'&&e.changes.length||filter==='activity'&&(e.messages.length||e.records.some(r=>r.type==='tool'||r.type==='child')))&&(label(e)+' '+snippet(e)+' '+pretty(e.changes)+' '+pretty(e.messages)).toLowerCase().includes(q));
 $('events').innerHTML=visible.length?visible.map(e=>`<button role="listitem" class="event ${event.oid===e.oid?'active':''}" data-event="${esc(e.oid)}"><div class="event-meta"><span>Commit ${e.ordinal+1}</span><span>${esc(short(e.oid))}</span></div><div class="event-label">${esc(label(e))}${e.changes.length?`<span class="badge">${e.changes.length} file${e.changes.length===1?'':'s'}</span>`:''}</div><div class="event-snippet">${esc(snippet(e).slice(0,280))}</div></button>`).join(''):'<p class="empty">No matching events.</p>';
 $('events').querySelectorAll('button').forEach(b=>b.onclick=()=>{event=conversation.events.find(e=>e.oid===b.dataset.event);file='';side='after';renderEvents();renderDetail();updateURL();});
}
function diffHTML(change) {
 const status=!change.before?'Added':!change.after?'Deleted':'Modified';
 let body=change.patch===null?'<p class="hint">Binary content or mode change. Open the file to inspect its recorded identity.</p>':`<div class="diff-wrap"><pre class="diff">${change.patch.split('\n').map(line=>`<span class="${line.startsWith('@@')?'location':line.startsWith('+')?'add':line.startsWith('-')?'remove':''}">${esc(line)}</span>`).join('')}</pre></div>`;
 return `<div class="diff-header"><span class="badge">${status}</span><button data-file="${esc(change.path)}">${esc(change.path)}</button></div>${body}`;
}
function activity() {
 let out='';
 for(const m of event.messages) {
  out+=`<div class="role">${esc(m.role)}${m.model?' · '+esc(m.model):''}</div>`;
  for(const b of m.blocks) {
   if(b.text||b.thinking) out+=`<div class="prose">${esc(b.text||b.thinking)}</div>`;
   else if(b.type==='tool_use') out+=`<div class="block"><strong>${esc(b.name)}</strong><div class="hash">${esc(b.id)}</div>${argumentsHTML(b.resolved_arguments)}</div>`;
   else out+=code(pretty(b));
  }
 }
 for(const r of event.records) {
  if(r.type==='tool') {
   const declaration=conversation.events.flatMap(e=>e.messages).flatMap(m=>m.blocks).find(b=>b.type==='tool_use'&&b.id===r.id);
   out+=`<div class="block"><strong>${esc(r.name)}</strong><span class="badge">${esc(r.status)}</span>${declaration?argumentsHTML(declaration.resolved_arguments):''}${r.task?`<p><button data-open-request>Inspect recorded compute request</button></p>`:''}${r.observation!==null&&r.observation!==undefined?`<h3>Recorded tool output</h3>${code(observationText(r.observation))}`:''}</div>`;
  } else if(r.type==='child') {
   const child=data.conversations.find(c=>c.id===r.id);
   out+=`<div class="block"><strong>${r.status==='running'?'Child started':'Child finished'}</strong><p>${esc(child?.title||r.id)}</p><button data-child="${esc(r.id)}">Open child conversation</button></div>`;
  } else if(r.type==='request') out+=`<p class="hint">Turn status: ${esc(r.status)}${r.model?' · '+esc(r.model):''}</p>`;
 }
 if(event.changes.length) out+=`<h3>${event.kind==='conversation.root'?'Initial files':'File changes at this commit'}</h3>${event.changes.map(diffHTML).join('')}`;
 return out||'<p class="empty">This commit records lifecycle metadata. Open the raw record for its details.</p>';
}
function filesView() {
 const tree=side==='before'?event.before_tree:event.tree;
 const snapshot=tree&&data.snapshots[tree];
 const paths=Object.keys(snapshot?.files||{}).sort();
 if(!paths.includes(file)) file=paths.find(p=>event.changes.some(c=>c.path===p))||paths[0]||'';
 const info=snapshot?.files[file], blob=info&&data.blobs[info.oid];
 const source=Object.keys(snapshot?.sources||{}).sort((a,b)=>b.length-a.length).find(p=>file.startsWith(p+'/'));
 const filtered=paths.filter(p=>p.toLowerCase().includes(fileQuery.toLowerCase()));
 return `<div class="file-toolbar"><label>Snapshot <select id="side"><option value="after" ${side==='after'?'selected':''}>After this event</option><option value="before" ${side==='before'?'selected':''}>Before this event</option></select></label><span>${paths.length} files</span></div><p class="hash">Conversation tree: ${tree?objectLink(tree):'No previous snapshot'}</p><div class="file-browser"><div class="file-list"><input id="file-search" aria-label="Filter filenames" placeholder="Filter files" value="${esc(fileQuery)}">${filtered.map(p=>`<button class="${p===file?'active':''}" data-file="${esc(p)}">${esc(p)}</button>`).join('')}</div><div class="file-content">${info?`<strong>${esc(file)}</strong><p class="hash">Blob: ${objectLink(info.oid)} · ${blob.size} bytes${info.mode==='120000'?' · symlink target':''}</p>${source?`<p class="hash">Source commit: ${objectLink(snapshot.sources[source])}</p>`:''}${blob.binary?'<p>Binary file. Download the original Git object using its hash above.</p>':code(blob.text)}`:'<p class="empty">No files in this snapshot.</p>'}</div></div>`;
}
function requestsView() {
 const ids=[...new Set(event.records.flatMap(r=>r.type==='tool'&&r.task?[r.task]:r.type==='request'?[r.id]:[]))];
 if(!ids.length) return '<p class="empty">No compute request is attached to this event. Select a task-start or task-completion commit.</p>';
 return ids.map(id=>{
  const req=data.requests[id];
  if(!req) return `<p>Request ${esc(id)} was not exported.</p>`;
  return `<h3>Recorded request</h3><p class="hash">${objectLink(id)}</p>${req.entries.map(row=>`<div class="request-row"><strong>${esc(row.name)}</strong><span class="badge">${row.mode==='40000'?'tree':row.mode==='160000'?'commit':'file'}</span><div class="hash">${objectLink(row.oid)}</div>${row.text!==undefined&&row.text!==null?code(row.text):''}${row.snapshot?`<details><summary>Captured input files</summary>${Object.keys(data.snapshots[row.snapshot].files).sort().map(p=>`<div class="hash">${esc(p)} · ${esc(short(data.snapshots[row.snapshot].files[p].oid))}</div>`).join('')}</details>`:''}</div>`).join('')}<p class="hint">The request identifies the worker image by hash. Image layers are not included in this browser export. Source files and command arguments captured here are available in full.</p>`;
 }).join('');
}
function renderDetail() {
 $('event-heading').innerHTML=`<h2>${esc(label(event))}</h2><div class="hash">${esc(event.kind)} · ${objectLink(event.oid)}</div>`;
 document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab);b.setAttribute('aria-pressed',b.dataset.tab===tab?'true':'false');});
 $('detail').innerHTML=tab==='files'?filesView():tab==='request'?requestsView():tab==='record'?`<p>Parsed directly from the recorded Git commit. Download the original object using the commit hash above.</p>${code(pretty(event))}`:activity();
 $('detail').querySelectorAll('[data-child]').forEach(b=>b.onclick=()=>selectConversation(b.dataset.child));
 $('detail').querySelectorAll('[data-file]').forEach(b=>b.onclick=()=>{file=b.dataset.file;tab='files';if(!data.snapshots[event.tree].files[file])side='before';renderDetail();updateURL();});
 $('detail').querySelectorAll('[data-open-request]').forEach(b=>b.onclick=()=>{tab='request';renderDetail();updateURL();});
 if($('side')) $('side').onchange=()=>{side=$('side').value;renderDetail();};
 if($('file-search')) $('file-search').oninput=()=>{const input=$('file-search');fileQuery=input.value;const pos=input.selectionStart;renderDetail();$('file-search').focus();$('file-search').setSelectionRange(pos,pos);};
}
function render(){renderConversations();renderEvents();renderDetail();updateURL();}
async function loadExample(id, fromURL=false) {
 const version=++loadVersion;
 $('notice').hidden=false;$('notice').textContent='Loading captured run…';$('browser').hidden=true;
 try {
  const entry=catalog.examples.find(e=>e.id===id)||catalog.examples[0];
  const response=await fetch('data/'+entry.id+'.json');if(!response.ok)throw Error('Could not load example: '+response.status);
  const loaded=await response.json();if(version!==loadVersion)return;data=loaded;
  const q=new URLSearchParams(location.search);tab=fromURL&&['activity','files','request','record'].includes(q.get('tab'))?q.get('tab'):'activity';
  $('example').value=entry.id;$('description').textContent=data.description;
  $('highlights').innerHTML=(entry.highlights?.length?'<span>Key moments</span>':'')+(entry.highlights||[]).map((h,i)=>`<button data-highlight="${i}">${esc(h.label)}</button>`).join('');
  $('highlights').querySelectorAll('button').forEach(b=>b.onclick=()=>{const h=entry.highlights[Number(b.dataset.highlight)];tab='activity';selectConversation(h.conversation,h.event);});
  const count=data.conversations.reduce((n,c)=>n+c.events.length,0), calls=data.conversations.reduce((n,c)=>n+c.events.reduce((n,e)=>n+toolRecords(e).filter(r=>r.status!=='started').length,0),0);
  $('facts').innerHTML=`<span>${data.conversations.length} conversations</span><span>${count} commits</span><span>${calls} tool results</span><span>${data.evidence.objects.length} captured Git objects</span>`;
  $('download').href='data/'+data.id+'.json';$('notice').hidden=true;$('browser').hidden=false;
  const first=entry.highlights?.[0];
  selectConversation(fromURL&&q.get('conversation')?q.get('conversation'):(first?.conversation||data.root),fromURL&&q.get('event')?q.get('event'):first?.event);
  if(fromURL&&q.get('file')){file=q.get('file');renderDetail();updateURL();}
 } catch(error){$('notice').textContent=error.message;$('browser').hidden=true;}
}
$('search').oninput=renderEvents;$('filter').onchange=renderEvents;
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;renderDetail();updateURL();});
$('example').onchange=()=>loadExample($('example').value);
(async()=>{try{const r=await fetch('data/index.json');if(!r.ok)throw Error('Example index could not be loaded.');catalog=await r.json();$('example').innerHTML=catalog.examples.map(e=>`<option value="${esc(e.id)}">${esc(e.title)}</option>`).join('');await loadExample(new URLSearchParams(location.search).get('example'),true);}catch(e){$('notice').textContent=e.message;}})();
