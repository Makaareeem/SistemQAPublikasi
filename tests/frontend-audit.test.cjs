const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const {serverError, userMessage} = require('../web/app.js');
assert.match(serverError(503,{code:'model_memory',request_id:'a'.repeat(32)}).message,/Memori.*aaaaaaaa/);
assert.doesNotMatch(serverError(503,{code:'<secret>',request_id:'secret/path'}).message,/secret|path/);
assert.match(userMessage(503,'queue_timeout'),/antrean habis/);
class Element {
  constructor(){this.children=[];this.style={};this.value='';this.textContent='';this.disabled=false;this.attributes={};this.dataset={};}
  setAttribute(k,v){this.attributes[k]=v;}
  addEventListener(){}
  append(...nodes){for(const n of nodes){n.parentElement=this;this.children.push(n);}}
  appendChild(n){this.append(n);}
  replaceChildren(...nodes){this.children=[];this.append(...nodes);}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(n=>n!==this);}
  focus(){this.focused=true;}
}
const ids=Object.fromEntries(['q','notifications','btn','model','cancelBtn','summaryCancelBtn','answer','ansCard','sources','source-1','source-2','error','questionForm','thinkCard','backToResults','editQuestionBtn'].map(id=>[id,new Element()]));
ids.q.value='cek';ids.answer.textContent='Jawaban sebelumnya';ids.ansCard.style.display='block';ids.sources.children=['sumber lama'];
let requests=0;
const context=vm.createContext({console,URL,AbortController,setTimeout:()=>1,clearTimeout:()=>{},
  fetch:async()=>{requests++;return {ok:false,status:422,json:async()=>({detail:{code:'question_needs_topic'}})};}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/question-validation.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8'),context);
context.document={
  getElementById:id=>ids[id] || null, querySelectorAll:()=>[],
  createElement:()=>new Element(),createTextNode:text=>({textContent:text}),
  body:{classList:{remove(){throw Error('Rejected input must preserve landing page');}}}
};
context.rules=require('../web/question-rules.json');
(async()=>{
  vm.runInContext('questionRules = rules',context);
  await vm.runInContext('ask()',context);
  assert.equal(requests,0);
  assert.equal(ids.notifications.children.at(-1).className,'notice notice-warning');
  vm.runInContext('questionRules = null',context);
  await vm.runInContext('ask()',context);
  assert.equal(requests,1);
  assert.equal(ids.answer.textContent,'Jawaban sebelumnya');
  assert.deepEqual(ids.sources.children,['sumber lama']);
  assert.equal(ids.ansCard.style.display,'block');
  assert.equal(ids.q.disabled,false);
  assert.equal(ids.q.focused,true);
  const nodes=vm.runInContext("answerNodes('Data [1, 2].')",context);
  assert.equal(nodes[1].href,'#source-1');
  assert.equal(nodes[2].href,'#source-2');
  console.log('Audit UI passed: validation retains results, request IDs are sanitized, grouped citations link to sources.');
})().catch(e=>{console.error(e);process.exitCode=1;});
