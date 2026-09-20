const $=id=>document.getElementById(id);
let state;
const params=new URLSearchParams(location.search);
$('private').checked=params.get('private')==='1';
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function nativeLink(source){
  const u=new URL('../trajectories/',new URL('mystery/',location.href));
  u.searchParams.set('remote',new URL('mystery/git',location.href).href);
  const latest=Object.values(state.heads).find(h=>h.conversation===source.conversation);
  u.searchParams.set('head',latest?.head||source.head);u.searchParams.set('conversation',source.conversation);
  u.searchParams.set('event',state.reply_events[source.head]||source.head);u.searchParams.set('tab','activity');return u.href;
}
function options(select,rows,value){select.replaceChildren(...rows.map(([id,title])=>{const n=el('option',title);n.value=id;return n;}));select.value=rows.some(([id])=>id===value)?value:rows[0][0];}
function populate(){
  const private_=$('private').checked;
  const chats=private_?[['*','All chats and actions'],...Object.entries(state.chats).map(([id,c])=>[id,c.title])]:[['drawing-room','Drawing room']];
  options($('chat'),chats,$('chat').value||params.get('chat')||'drawing-room');
  $('recipient').disabled=!private_;
  if(!private_)$('recipient').value='';
}
function content(event,container,depth=0){
  const p=event.payload;
  if(event.kind==='say')container.append(el('p',p.text));
  else if(event.kind==='share'){container.append(el('strong',p.card.title));container.append(el('p',p.card.text));}
  else if(event.kind==='forward'){
    container.append(el('p','Forwarded '+p.event));
    if(depth<4){const q=el('blockquote');q.append(el('small',state.cast[p.original.actor]?.name||p.original.actor));content(p.original,q,depth+1);container.append(q);}
  }else if(event.kind==='inspect'){
    container.append(el('p','Inspected the '+p.place+'.'));
    for(const card of Object.values(p.cards)){container.append(el('strong',card.title));container.append(el('p',card.text));}
  }else if(event.kind==='create')container.append(el('p','Opened “'+p.title+'”.'));
  else if(event.kind==='invite')container.append(el('p','Invited '+state.cast[p.role].name+' to “'+p.title+'”.'));
  else if(['accept','decline','leave'].includes(event.kind))container.append(el('p',({accept:'Joined the chat.',decline:'Declined the invitation.',leave:'Left the chat.'})[event.kind]));
  else if(event.kind==='ballot')container.append(el('p','Final accusation: '+(state.cast[p.suspect]?.name||p.suspect)+'. Estate: '+p.estate+'.\n'+p.reason));
  else if(event.kind==='error')container.append(el('p','Action was not applied: '+p.error));
  else container.append(el('p','Waited.'));
}
function render(){
  populate();
  const priv=$('private').checked,chat=$('chat').value,recipient=$('recipient').value,round=$('round').value;
  const u=new URL(location.href);u.searchParams.delete('private');u.searchParams.delete('chat');u.searchParams.delete('recipient');u.searchParams.delete('round');
  if(priv)u.searchParams.set('private','1');
  if(chat!=='drawing-room')u.searchParams.set('chat',chat);
  if(priv&&recipient)u.searchParams.set('recipient',recipient);
  if(round)u.searchParams.set('round',round);
  history.replaceState(null,'',u);
  const rows=state.events.filter(e=>(priv||e.payload.chat==='drawing-room')&&(chat==='*'||e.payload.chat===chat)&&(!priv||!recipient||e.visible_to.includes(recipient))&&(!round||String(e.round)===round));
  const nodes=rows.map(e=>{
    const card=el('article');card.id=e.id;
    const header=el('header',state.cast[e.actor].name+' · round '+e.round+' · '+(state.chats[e.payload.chat]?.title||'private action')+' · ');
    const anchor=el('a',e.id);anchor.href='#'+e.id;header.append(anchor);
    card.append(header);content(e,card);
    const foot=el('small','Delivered to: '+e.visible_to.map(r=>state.cast[r].name).join(', ')+' · ');
    const a=el('a','CAOS turn');a.href=nativeLink(e.source);foot.append(a);card.append(foot);return card;
  });
  $('events').replaceChildren(...(nodes.length?nodes:[el('p','No messages in this selection.')]));
}
async function load(){
  $('refresh').disabled=true;
  try{
    const response=await fetch('mystery/state.json',{cache:'no-store'});if(!response.ok)throw new Error('Snapshot unavailable ('+response.status+')');
    state=await response.json();
    $('status').textContent=(state.status==='budget-stopped'?'Stopped by budget guard':state.status)+' · '+state.turns.length+' applied character turns · '+(state.unapplied_turns?.length||0)+' additional replies not applied · updated '+new Date(state.updated*1000).toLocaleString();
    const extra=state.unapplied_turns||[];
    $('unapplied').hidden=extra.length===0;
    $('unapplied-replies').replaceChildren(...extra.map(row=>{
      const section=el('section');section.append(el('strong',state.cast[row.role].name+' · round '+row.round));
      const a=el('a','Original CAOS reply');a.href=nativeLink(row);const p=el('p');p.append(a);section.append(p);
      const detail=el('details');detail.append(el('summary','Read decision (not delivered)'),el('pre',JSON.stringify(row.decision,null,2)));section.append(detail);return section;
    }));
    options($('recipient'),[['','Everyone'],...Object.entries(state.cast).map(([id,r])=>[id,r.name])],$('recipient').value||params.get('recipient'));
    options($('round'),[['','All'],...Array.from({length:state.round},(_,i)=>[String(i+1),String(i+1)])],$('round').value||params.get('round'));
    $('chat').replaceChildren();
    populate();render();
    $('cast').replaceChildren(...Object.entries(state.heads).map(([id,source])=>{const p=el('p');const a=el('a',state.cast[id].name);a.href=nativeLink(source);p.append(a);return p;}));
    if(location.hash)document.getElementById(location.hash.slice(1))?.scrollIntoView();
  }catch(e){$('status').textContent=e.message;$('status').classList.add('error');}
  finally{$('refresh').disabled=false;}
}
for(const id of ['private','chat','recipient','round'])$(id).addEventListener('change',render);
$('refresh').addEventListener('click',load);
load();
