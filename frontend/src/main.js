import { createIcons, Plus, MessageSquare, PanelLeft, ArrowUp, FileText, Code2, ArrowUpRight, X, Copy, Download, Search, BookOpen, ChevronRight, Square, Trash2, RotateCcw, ExternalLink } from 'lucide';
import {esc,icon,prose,highlight,sources,artifactCard,welcome} from './render';
import 'highlight.js/styles/github.css';
import './style.css';
const icons={Plus,MessageSquare,PanelLeft,ArrowUp,FileText,Code2,ArrowUpRight,X,Copy,Download,Search,BookOpen,ChevronRight,Square,Trash2,RotateCcw,ExternalLink};
const $=s=>document.querySelector(s), key='lenny-workspace-v1';
const responseModel=m=>({'gpt-6-luna':'OpenAI','meta-llama/llama-3.1-8b-instruct':'Llama 3.1 8B'}[m.model]||'');
let chats=[],storageWarning='';
try{const saved=JSON.parse(localStorage.getItem(key)||'[]');chats=Array.isArray(saved)?saved.filter(c=>typeof c.id==='string'&&typeof c.title==='string'&&Array.isArray(c.messages)&&c.messages.every(m=>typeof m.content==='string'&&['user','assistant'].includes(m.role)&&(!m.artifact||['title','content','language'].every(k=>typeof m.artifact[k]==='string')))):[];}catch{storageWarning='Browser history is unavailable. Download important artifacts.';}
let active=null,provider='openai',draft='',busy=false,controller,selection=null,view='preview',library=false,mobileNav=false,collapsed=false,error='',filter='';
let focusRequest=null,artifactOrigin=null;
const focusIdentity=el=>el?.id?{id:el.id}:el?.dataset.action?{data:{...el.dataset}}:null;
const current=()=>chats.find(c=>c.id===active),messages=()=>current()?.messages||[],selected=()=>chats.find(c=>c.id===selection?.chat)?.messages[selection?.index];
function save(){try{localStorage.setItem(key,JSON.stringify(chats));}catch{storageWarning='History could not be saved. Download important artifacts.';}}
// Repair the earlier essay status copy while preserving the saved essay itself.
let repairedEssayMessages=false;
for(const chat of chats)for(const message of chat.messages){
  if(message.role==='assistant'&&message.artifact?.language==='markdown'&&
    (/^Complete Markdown essay\b/i.test(message.content)||/This draft is \d+ words; review its evidence limits before expanding it\./.test(message.content))){
    message.content='Your essay is ready.';repairedEssayMessages=true;
  }
}
if(repairedEssayMessages)save();
function render(){
  const restoreFocus=focusRequest||focusIdentity(document.activeElement);focusRequest=null;
  const item=selected(),a=item?.artifact;
  $('#app').innerHTML=`<div class="workspace ${collapsed?'collapsed':''} ${a?'has-artifact':''}">
  ${mobileNav?'<button class="scrim" data-action="nav" aria-label="Close navigation"></button>':''}
  <aside class="sidebar ${mobileNav?'mobile-open':''}">
    <a class="brand" href="/" aria-label="Lenny home"><span class="brand-mark">L<span>·</span></span><span>Lenny<small>Growth assistant</small></span></a>
    <button class="new-chat" data-action="new" ${busy?'disabled':''}>${icon('plus')} New conversation <kbd>Ctrl K</kbd></button>
    <nav aria-label="Workspace"><button class="nav-item ${!library?'active':''}" data-action="chats">${icon('message-square')} Conversations</button><button class="nav-item ${library?'active':''}" data-action="library">${icon('file-text')} Artifacts <span class="count">${chats.reduce((n,c)=>n+c.messages.filter(m=>m.artifact).length,0)}</span></button></nav>
    <div class="history-label">Recent conversations</div><label class="search">${icon('search')}<input id="search" aria-label="Search conversations" placeholder="Search conversations" value="${esc(filter)}"></label>
    <div class="history">${chats.filter(c=>c.title.toLowerCase().includes(filter.toLowerCase())).map(c=>`<div class="history-row ${c.id===active?'selected':''}"><button data-action="load" data-id="${esc(c.id)}" ${busy?'disabled':''}>${esc(c.title)}</button><button class="delete icon-button" data-action="delete" data-id="${esc(c.id)}" aria-label="Delete ${esc(c.title)}" ${busy?'disabled':''}>${icon('trash-2')}</button></div>`).join('')||`<p class="history-empty">${filter?'No matching conversations.':'Your next idea starts here.'}</p>`}</div>
    <div class="sidebar-bottom">${icon('book-open')}<div>Built on Lenny’s Podcast<small>Ideas with sources, ready to use.</small></div></div><div class="local-note">History stays in this browser.</div>
  </aside>
  <main class="main"><header class="topbar"><button class="icon-button" data-action="nav" aria-label="Toggle sidebar">${icon('panel-left')}</button><span class="breadcrumb">Workspace <span>/</span> <strong>${library?'Artifacts':esc(current()?.title||'New conversation')}</strong></span><span class="workspace-label">Your growth workspace</span></header>
  ${library?renderLibrary():`<div class="conversation" id="conversation">${messages().length?`<div class="message-list">${messages().map((m,i)=>`<article class="message ${m.role}">${m.role==='assistant'?`<div class="assistant-label"><span class="mini-mark">L·</span> Lenny${responseModel(m)?`<span class="response-model" data-model="${esc(m.model)}">${esc(responseModel(m))}</span>`:''}</div>`:''}<div class="message-content prose">${m.role==='user'?esc(m.content):prose(m.content)}</div>${m.artifact?artifactCard(m,i,active):''}${m.role==='assistant'?`${sources(m.sources)}<button class="copy-message icon-button" data-action="copy-message" data-index="${i}" aria-label="Copy response">${icon('copy')}</button>`:''}</article>`).join('')}${busy?`<div class="thinking" role="status"><span class="mini-mark">L·</span><span>Working on your request…</span><span class="dots"></span></div>`:''}</div>`:welcome()}</div>
  <div class="composer-area">${error?`<div class="error" role="alert">${esc(error)}<button data-action="retry" ${busy?'disabled':''}>${icon('rotate-ccw')} Retry</button></div>`:''}${storageWarning?`<p class="storage-warning" role="status">${esc(storageWarning)}</p>`:''}<form id="composer" class="composer"><label class="sr-only" for="prompt">Message Lenny</label><textarea id="prompt" rows="2" maxlength="12000" placeholder="Ask a growth question, write an essay, or build a tool…" ${busy?'disabled':''}>${esc(draft)}</textarea><div class="composer-bottom"><div class="composer-actions"><label class="sr-only" for="model">Model</label><select id="model" class="model-selector" ${busy?'disabled':''}><option value="openai" ${provider==='openai'?'selected':''}>OpenAI</option><option value="openrouter" ${provider==='openrouter'?'selected':''}>Llama 3.1 8B</option></select>${busy?`<button class="send" type="button" data-action="stop" aria-label="Stop waiting">${icon('square')}</button>`:`<button class="send" type="submit" aria-label="Send message" ${!draft.trim()?'disabled':''}>${icon('arrow-up')}</button>`}</div></div></form><p class="composer-note">Lenny chooses the right skill for your request. Podcast insights include sources.</p></div>`}
  </main>
  ${a?`<aside class="artifact-panel" aria-label="Artifact viewer"><header class="artifact-header"><div>${icon(a.language==='markdown'?'file-text':'code-2')}<span><strong>${esc(a.title)}</strong><small>${a.language==='markdown'?`${a.content.trim().split(/\s+/).length.toLocaleString()} words · Markdown`:esc(a.language.toUpperCase())+' artifact'}</small></span></div><button class="icon-button" data-action="close-artifact" aria-label="Close artifact">${icon('x')}</button></header><div class="artifact-toolbar"><div class="tabs" role="group" aria-label="Artifact view"><button data-action="view" data-view="preview" aria-pressed="${view==='preview'}" class="${view==='preview'?'chosen':''}">${a.language==='markdown'?'Read':a.language==='html'?'Preview':'Formatted'}</button><button data-action="view" data-view="source" aria-pressed="${view==='source'}" class="${view==='source'?'chosen':''}">Source</button></div><div class="artifact-actions"><button class="icon-button" data-action="copy-artifact" aria-label="Copy artifact">${icon('copy')}</button><button class="icon-button" data-action="download" aria-label="Download artifact">${icon('download')}</button></div></div><div class="artifact-body">${view==='source'?`<pre class="source-code"><code>${highlight(a.content,a.language)}</code></pre>`:a.language==='markdown'?`<div class="document prose">${prose(a.content)}${sources(item.sources)}</div>`:a.language==='html'?'<iframe id="preview" title="Generated HTML preview" sandbox="allow-scripts allow-forms" referrerpolicy="no-referrer"></iframe>':`<pre class="source-code"><code>${highlight(a.content,a.language)}</code></pre>`}</div><footer class="artifact-footer">${a.language==='html'?'Isolated preview · External connections are disabled':a.language==='markdown'?'Your ideas, ready to take with you.':'Code is displayed here; it has not been executed.'}</footer></aside>`:''}<div id="toast" role="status" class="toast" hidden></div></div>`;
  createIcons({icons,attrs:{'stroke-width':1.7}});
  if($('#preview')&&a){const policy="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'";$('#preview').srcdoc=`<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="${policy}"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{font-family:system-ui;margin:24px;color:#242924}*{box-sizing:border-box}</style></head><body>${a.content}</body></html>`;}
  bind();
  if(restoreFocus){const target=restoreFocus.id?document.getElementById(restoreFocus.id):Array.from(document.querySelectorAll('[data-action]')).find(el=>Object.entries(restoreFocus.data).every(([key,value])=>el.dataset[key]===value));(target||document.querySelector('[data-action="new"]'))?.focus({preventScroll:true});}
}
function renderLibrary(){const all=chats.flatMap(c=>c.messages.map((m,i)=>({c,m,i})).filter(x=>x.m.artifact));return `<section class="library"><h1>Your artifacts</h1><p>Essays, snippets, and small tools from your conversations.</p>${all.length?all.map(({c,m,i})=>artifactCard(m,i,c.id)).join(''):`<div class="library-empty">${icon('file-text')}<h2>Make your first artifact</h2><p>Ask Lenny to write an essay or build a simple tool.</p><button class="primary-button" data-action="new">Start a conversation ${icon('plus')}</button></div>`}</section>`;}
function scrollBottom(){requestAnimationFrame(()=>{const el=$('#conversation');if(el)el.scrollTop=el.scrollHeight;});}
function toast(text){const el=$('#toast');if(!el)return;el.textContent=text;el.hidden=false;setTimeout(()=>{if(el.isConnected)el.hidden=true;},2800);}
async function copy(text){try{await navigator.clipboard.writeText(text);toast('Copied to clipboard');}catch{toast('Clipboard unavailable. Use Download to save this artifact.');}}
function newChat(){if(busy)return;active=null;selection=null;library=false;mobileNav=false;draft='';error='';render();$('#prompt')?.focus();}
function bind(){
  $('#model')?.addEventListener('change',e=>{provider=e.target.value==='openrouter'?'openrouter':'openai';});
  $('#prompt')?.addEventListener('input',e=>{draft=e.target.value;$('[type="submit"]').disabled=!draft.trim();e.target.style.height='auto';e.target.style.height=Math.min(e.target.scrollHeight,160)+'px';});
  $('#prompt')?.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send();}});
  $('#composer')?.addEventListener('submit',e=>{e.preventDefault();send();});
  $('#search')?.addEventListener('input',e=>{filter=e.target.value;const pos=e.target.selectionStart;render();$('#search').focus();$('#search').setSelectionRange(pos,pos);});
  document.querySelectorAll('[data-action]').forEach(el=>el.addEventListener('click',()=>action(el)));
}
async function action(el){const d=el.dataset;switch(d.action){
  case 'new':newChat();break;
  case 'nav':if(innerWidth<=760)mobileNav=!mobileNav;else collapsed=!collapsed;render();break;
  case 'chats':library=false;mobileNav=false;render();scrollBottom();break;
  case 'library':library=true;mobileNav=false;render();break;
  case 'suggest':draft=d.prompt;render();$('#prompt')?.focus();break;
  case 'load':if(busy)return;active=d.id;selection=null;library=false;mobileNav=false;error='';draft='';render();scrollBottom();break;
  case 'delete':if(busy)return;if(!confirm('Delete this conversation and its artifacts from this browser?'))return;chats=chats.filter(c=>c.id!==d.id);if(active===d.id)active=null;if(selection?.chat===d.id)selection=null;save();render();break;
  case 'artifact':artifactOrigin=focusIdentity(el);focusRequest={data:{action:'close-artifact'}};selection={chat:d.chat,index:Number(d.index)};view='preview';mobileNav=false;render();break;
  case 'close-artifact':selection=null;focusRequest=artifactOrigin||{id:'prompt'};render();break;
  case 'view':view=d.view;render();break;
  case 'copy-message':await copy(messages()[Number(d.index)].content);break;
  case 'copy-artifact':await copy(selected().artifact.content);break;
  case 'download':{const a=selected().artifact;const ext={markdown:'md',html:'html',javascript:'js',python:'py',css:'css',json:'json',text:'txt'}[a.language]||'txt';const url=URL.createObjectURL(new Blob([a.content],{type:'text/plain;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=(a.title.replace(/[^a-z0-9 -]/gi,'').slice(0,70)||'artifact')+'.'+ext;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Artifact downloaded');break;}
  case 'stop':controller?.abort();break;
  case 'retry':await send(true);break;
}}
async function send(retry=false){
  if(busy||(!retry&&!draft.trim()))return;const text=retry?messages().at(-1)?.content:draft.trim();if(!text)return;
  if(!active){active=crypto.randomUUID();chats.unshift({id:active,title:text.slice(0,65),messages:[]});}
  const chat=current();const history=chat.messages.slice(0,retry?-1:undefined).slice(-1000).map(m=>({role:m.role,content:m.content.slice(0,16000),...(m.artifact?{artifact:{title:m.artifact.title.slice(0,512),language:m.artifact.language,content:m.artifact.content}}:{}),...(['podcast-qa','ship30-essay','simple-artifact'].includes(m.skill)?{skill:m.skill}:{})}));
  if(!retry)chat.messages.push({role:'user',content:text});draft='';busy=true;error='';library=false;save();render();scrollBottom();
  controller=new AbortController();const timer=setTimeout(()=>controller.abort('timeout'),240000);
  try{const response=await fetch('/api/v1/workspace/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,history,provider}),signal:controller.signal});const body=await response.json().catch(()=>({detail:'The server returned an unexpected response.'}));if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'The request could not be completed. Try a shorter message.');if(typeof body.message!=='string')throw new Error('The server returned an incomplete response. Please retry.');chat.messages.push({role:'assistant',content:body.message,artifact:body.artifact,sources:body.sources,coverage:body.coverage,skill:body.skill,provider:body.provider,model:body.model});if(body.artifact){selection={chat:chat.id,index:chat.messages.length-1};view='preview';}save();}
  catch(e){error=controller.signal.aborted?(controller.signal.reason==='timeout'?'This is taking longer than expected. Please retry.':'Stopped waiting. You can retry your message.'):e instanceof TypeError?'Cannot reach the assistant. Make sure the backend is running, then retry.':e.message;}
  finally{clearTimeout(timer);busy=false;controller=null;render();scrollBottom();$('#prompt')?.focus();}
}
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='k'){e.preventDefault();newChat();}if(e.key==='Escape'){focusRequest=selection?(artifactOrigin||{id:'prompt'}):{data:{action:'nav'}};selection=null;mobileNav=false;render();}});
render();
