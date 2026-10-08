import { marked } from 'marked';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/common';
export const esc = (s='') => String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const icon = name => `<i data-lucide="${name}"></i>`;
export function prose(text) {
  const el=document.createElement('div');
  el.innerHTML=DOMPurify.sanitize(marked.parse(text,{gfm:true}),{FORBID_TAGS:['img','iframe','style','form'],FORBID_ATTR:['style']});
  el.querySelectorAll('a').forEach(a=>{a.target='_blank';a.rel='noopener noreferrer';});
  el.querySelectorAll('pre code').forEach(c=>{if(c.textContent.length<60000)hljs.highlightElement(c);});
  return el.innerHTML;
}
export function highlight(code,lang){return code.length<100000&&hljs.getLanguage(lang)?hljs.highlight(code,{language:lang}).value:esc(code);}
export function sources(items={}) {
  const entries=Object.entries(items);if(!entries.length)return '';
  return `<details class="sources"><summary>${icon('book-open')} ${entries.length} podcast sources ${icon('chevron-right')}</summary><div class="source-list">${entries.map(([id,s])=>{
    let url='';try{const u=new URL(s.source_url);if(['http:','https:'].includes(u.protocol))url=u.href;}catch{}
    return `<div class="source"><span class="citation">${esc(id)}</span><div>${url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)} ${icon('external-link')}</a>`:`<strong>${esc(s.title)}</strong>`}<p>${esc(s.guest||'Lenny’s Podcast')}${Number.isFinite(s.start_seconds)?` · ${Math.floor(s.start_seconds/60)}:${String(Math.floor(s.start_seconds%60)).padStart(2,'0')}`:''}</p><details><summary>View passage</summary><p>${esc(s.text)}</p></details></div></div>`;
  }).join('')}</div></details>`;
}
export function artifactCard(m,i,chat){const a=m.artifact;return `<button class="artifact-card" data-action="artifact" data-chat="${esc(chat)}" data-index="${i}"><span class="file-icon">${icon(a.language==='markdown'?'file-text':'code-2')}</span><span><strong>${esc(a.title)}</strong><small>${a.language==='markdown'?'Markdown document':esc(a.language.toUpperCase())+' artifact'} · Open to preview</small></span>${icon('arrow-up-right')}</button>`;}
export const prompts=[
  ['Improve activation','What can I learn from Lenny’s guests about improving user activation?'],
  ['Write about product-market fit','Write an essay for founders about finding product-market fit.'],
  ['A simple growth calculator','Build a simple interactive HTML growth calculator with starting users, monthly growth rate, and months.']
];
export function welcome(){return `<section class="welcome"><div class="welcome-mark">${icon('book-open')}</div><h1>A little insight.<br>A better next move.</h1><p>Think through your next growth challenge with<br class="desktop-break"> the best ideas from Lenny’s Podcast.</p><div class="suggestions">${prompts.map(([title,prompt])=>`<button data-action="suggest" data-prompt="${esc(prompt)}"><span>${esc(title)}</span>${icon('arrow-up-right')}</button>`).join('')}</div><div class="welcome-foot">Ask a question. Write an essay. Build something useful.</div></section>`;}
