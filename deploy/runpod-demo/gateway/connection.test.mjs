import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
const script = fs.readFileSync(new URL('./demo-connection.js',import.meta.url),'utf8');
function setup(fetch) {
  const nodes = {status:{dataset:{}},demoConnection:{hidden:true},model:{value:'gemma2-base'}};
  const context = vm.createContext({
    window:{},document:{getElementById:id=>nodes[id]},fetch,AbortController,DOMException,Date,
    setTimeout,clearTimeout,friendlyError:message=>new Error(message)
  });
  vm.runInContext(script,context);
  return {context,nodes};
}
test('ready backend is checked before asking, using GET only',async()=>{
  let calls=0;
  const {context,nodes}=setup(async(url,options)=>{
    calls++; assert.equal(url,'/api/wake'); assert.equal(options.method,undefined);
    return Response.json({ready:true,inference_reachable:true,available_models:['gemma2-base']});
  });
  await context.waitForDemoServer(new AbortController().signal);
  assert.equal(calls,1); assert.equal(nodes.status.dataset.state,'ready');
});
test('missing model fails instead of silently changing selected model',async()=>{
  const {context}=setup(async()=>Response.json({ready:true,inference_reachable:true,available_models:['llama3.2-base']}));
  await assert.rejects(context.waitForDemoServer(new AbortController().signal),/Model pilihan/);
});
test('cancellation while waiting prevents further requests',async()=>{
  const abort=new AbortController();
  let calls=0;
  const {context,nodes}=setup(async()=>{
    calls++; abort.abort(); return Response.json({code:'server_warming'},{status:503});
  });
  await assert.rejects(context.waitForDemoServer(abort.signal),{name:'AbortError'});
  assert.equal(calls,1); assert.match(nodes.demoConnection.textContent,/dibatalkan/);
});
test('configuration failure is not retried for five minutes',async()=>{
  let calls=0;
  const {context}=setup(async()=>{calls++;return Response.json({code:'demo_not_configured'},{status:503});});
  await assert.rejects(context.waitForDemoServer(new AbortController().signal),/Konfigurasi demo/);
  assert.equal(calls,1);
});
