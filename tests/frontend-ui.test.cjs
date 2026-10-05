// UI lifecycle regressions; fake time makes all notice durations deterministic.
const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const assert = require('node:assert/strict');
class Element {
  constructor() {
    this.children=[]; this.style={}; this.dataset={}; this.attributes={}; this.events={}; this.value=''; this.classes=new Set();
    this.classList={toggle:(n,on)=>on?this.classes.add(n):this.classes.delete(n),add:n=>this.classes.add(n)};
  }
  setAttribute(k,v){this.attributes[k]=v;}
  addEventListener(k,f){this.events[k]=f;}
  append(...nodes){for(const n of nodes){n.parentElement=this;this.children.push(n);}}
  appendChild(n){this.append(n);}
  replaceChildren(...nodes){this.children=[];this.append(...nodes);}
  remove(){this.parentElement.children=this.parentElement.children.filter(n=>n!==this);}
  get firstElementChild(){return this.children[0];}
  querySelector(){return null;}
  focus(){context.document.activeElement=this;}
  scrollIntoView(options){this.scrolled=options;}
}
let clock=0,nextTimer=0;
const timers=new Map();
const context=vm.createContext({URL, AbortController,console,
  setTimeout:(fn,ms)=>{const id=++nextTimer;timers.set(id,{fn,at:clock+ms});return id;},
  clearTimeout:id=>timers.delete(id)
});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8'),context);
const ids=Object.fromEntries(['notifications','q','error','questionCount','btn','model','cancelBtn','summaryCancelBtn','questionForm','thinkBody','thinkArrow','thinkToggle','sources','sourceCount','srcSection','answer','ansCard','answerState','backToResults','editQuestionBtn','questionSummary','summaryQuestion','answerTitle','answerQuestion','modalOverlay'].map(k=>[k,new Element()]));
const options=[new Element(),new Element()];
context.document={getElementById:k=>ids[k],createElement:tag=>{const n=new Element();n.tagName=tag;return n;},createTextNode:text=>({textContent:text}),querySelectorAll:()=>options,body:new Element()};
context.window={matchMedia:()=>({matches:true})};
const run=code=>vm.runInContext(code,context);
function advance(ms){clock+=ms;for(const [id,t] of [...timers])if(t.at<=clock){timers.delete(id);t.fn();}}
run("notifyUser('Info');notifyUser('Warning','warning');notifyUser('Error','error')");
assert.equal(ids.notifications.children.length,3);
advance(5000);assert.equal(ids.notifications.children.length,2);
advance(2000);assert.equal(ids.notifications.children.length,1);
advance(1000);assert.equal(ids.notifications.children.length,0);assert.equal(timers.size,0);
run("notifyUser('1');notifyUser('2');notifyUser('3');notifyUser('4')");
assert.equal(ids.notifications.children.length,3);assert.equal(timers.size,3);
ids.notifications.children[0].children[1].events.click();
assert.equal(ids.notifications.children.length,2);assert.equal(timers.size,2);
run('clearNotices()');assert.equal(timers.size,0);assert.equal(ids.notifications.children.length,0);
run("setFeedback('Periksa topik','warning',true);notifyUser('Periksa topik','warning')");
advance(7000);
assert.equal(ids.error.textContent,'Periksa topik');assert.equal(ids.q.attributes['aria-invalid'],'true');
run('setFeedback()');assert.equal(ids.error.style.display,'none');assert.equal(ids.q.attributes['aria-invalid'],'false');
ids.q.value='a'.repeat(1400);run('updateQuestion()');
assert.equal(ids.questionCount.textContent,'1.400 / 1.500');assert.ok(ids.questionCount.classes.has('near-limit'));
run('setBusy(true)');assert.ok(ids.q.disabled);assert.ok(options.every(o=>o.disabled));assert.equal(ids.cancelBtn.hidden,false);
run('setStyle("ringkas")');assert.equal(run('responseStyle'),'detail');
run('setBusy(false)');assert.equal(ids.q.disabled,false);assert.ok(options.every(o=>!o.disabled));assert.equal(ids.cancelBtn.hidden,true);
run('setThink(true);toggleThink()');assert.equal(ids.thinkToggle.attributes['aria-expanded'],'false');assert.equal(run('thinkTouched'),true);
// Final answers cancel scheduled provisional renders; stale tokens cannot overwrite them.
let frame;
context.requestAnimationFrame=fn=>{frame=fn;return 1;};
context.cancelAnimationFrame=()=>{frame=null;};
run("queueAnswer('Belum selesai');flushAnswer();renderAnswer('Jawaban akhir.')");
assert.equal(frame,null);assert.equal(ids.answer.children.at(-1).textContent,'Jawaban akhir.');
console.log('UI lifecycle checks passed: all notice timeouts, manual dismissal, notice cap, persistent feedback, counter, busy controls, panel state and final streaming answer.');

// A finished response takes focus away from the input and leaves an editable summary.
ids.answerQuestion.textContent='Apa itu IPM?';ids.q.value='Apa itu IPM?';
run('completeResultView()');
assert.equal(ids.questionForm.hidden,true);assert.equal(ids.questionSummary.hidden,false);
assert.equal(ids.summaryQuestion.textContent,'Apa itu IPM?');
assert.equal(context.document.activeElement,ids.answerTitle);
assert.equal(ids.ansCard.scrolled.behavior,'instant');
run('openQuestionEditor()');
assert.equal(ids.questionForm.hidden,false);assert.equal(ids.questionSummary.hidden,true);
assert.equal(context.document.activeElement,ids.q);assert.equal(ids.backToResults.hidden,false);
ids.q.value='Draf pertanyaan berikutnya';run('returnToResults()');
assert.equal(ids.q.value,'Draf pertanyaan berikutnya');
assert.equal(ids.summaryQuestion.textContent,'Apa itu IPM?');
assert.equal(context.document.activeElement,ids.answerTitle);
run("setFeedback('Periksa pertanyaan','warning',true)");
assert.equal(ids.questionForm.hidden,false,'Feedback must not be hidden in the collapsed form');
run('setBusy(true);returnToResults()');
assert.equal(ids.questionForm.hidden,false,'Cannot hide cancellation controls during a request');
assert.equal(ids.backToResults.disabled,true);run('setBusy(false)');
const dialogFocus=new Element();context.document.activeElement=dialogFocus;ids.modalOverlay.open=true;
run('focusResults()');
assert.equal(context.document.activeElement,dialogFocus,'Finishing must not steal focus from a guide');
assert.equal(run('lastFocus'),ids.answerTitle);ids.modalOverlay.open=false;
const card=run("relatedPublication({document_title:'Judul panjang <script>',bps_url:'https://www.bps.go.id/',page_start:4,page_end:6,document_year:2024})");
assert.equal(card.tagName,'a');assert.equal(card.target,'_blank');assert.equal(card.rel,'noopener noreferrer');
assert.equal(card.children[1].textContent,'Judul panjang <script>');
assert.equal(card.children[2].children[0].textContent,'Hal. 4\u20136');
assert.equal(card.children[2].children[1].textContent,'Terbit 2024');
const unavailable=run("relatedPublication({document_title:'Tanpa tautan',bps_url:'javascript:alert(1)'})");
assert.equal(unavailable.tagName,'article');assert.equal(unavailable.href,undefined);
assert.equal(unavailable.children.at(-1).textContent,'Tautan belum tersedia');
console.log('Results UI checks passed: focus, collapsed editor, draft preservation, modal focus, feedback visibility, busy controls and safe related-publication cards.');

// The form must already be compact during retrieval, before any answer/final event.
run("setBusy(true);beginResultView('Pertanyaan sedang diproses')");
assert.equal(ids.questionForm.hidden,true);
assert.equal(ids.questionSummary.hidden,false);
assert.equal(ids.summaryQuestion.textContent,'Pertanyaan sedang diproses');
assert.equal(ids.summaryCancelBtn.hidden,false);
assert.equal(ids.summaryCancelBtn.disabled,false);
assert.equal(ids.editQuestionBtn.hidden,true);
run('openQuestionEditor()');assert.equal(ids.questionForm.hidden,true);
run("setFeedback('Proses terputus');setBusy(false)");
assert.equal(ids.questionForm.hidden,false);
assert.equal(ids.summaryCancelBtn.hidden,true);
assert.equal(ids.editQuestionBtn.hidden,false);
console.log('Compact search checks passed: editor hidden during retrieval, cancel visible, edit locked while busy and failures reopen the editor.');
