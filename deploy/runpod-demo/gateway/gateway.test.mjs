import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import worker from './worker.mjs';
globalThis.crypto ??= webcrypto;
const originalFetch = globalThis.fetch;
const env = {
  DEMO_PASSWORD: 'test-demo-password', DEMO_USER: 'demo',
  RUNPOD_API_KEY: 'provider-secret-test-only',
  RUNPOD_ORIGIN: 'https://example123.api.runpod.ai',
  ASSETS: {fetch: async () => new Response('static page')}
};
function request(path, method = 'GET', options = {}) {
  return new Request('https://demo.example' + path, {
    method, ...options, headers: {
      Authorization: 'Basic ' + btoa('demo:' + env.DEMO_PASSWORD),
      ...(method === 'POST' ? {'Content-Type': 'application/json'} : {}),
      ...options.headers
    }, ...(method === 'POST' ? {body: options.body ?? JSON.stringify({question:'Apa itu IPM?'})} : {})
  });
}
test.afterEach(() => { globalThis.fetch = originalFetch; });
test('missing demo configuration fails closed', async () => {
  assert.equal((await worker.fetch(request('/'), {...env, DEMO_PASSWORD:''})).status, 503);
});
test('anonymous visitor cannot invoke GPU or see page', async () => {
  globalThis.fetch = () => { throw Error('must not contact upstream'); };
  assert.equal((await worker.fetch(new Request('https://demo.example/api/wake'), env)).status, 401);
});
test('static page and initial health do not wake a GPU', async () => {
  globalThis.fetch = () => { throw Error('must not contact upstream'); };
  assert.equal(await (await worker.fetch(request('/'), env)).text(), 'static page');
  const data = await (await worker.fetch(request('/api/health'), env)).json();
  assert.equal(data.ready, false);
  assert.equal(data.deployment_mode, 'on_demand');
});
test('evaluation and arbitrary API routes are inaccessible', async () => {
  for (const path of ['/api/eval/ask','/api/tags','/api/unknown']) {
    assert.equal((await worker.fetch(request(path,'POST'),env)).status,404);
  }
});
test('provider URL cannot point at another host', async () => {
  assert.equal((await worker.fetch(request('/api/wake'), {...env,RUNPOD_ORIGIN:'https://example.org/'})).status,503);
});
test('cross-origin POST is rejected before contacting provider', async () => {
  assert.equal((await worker.fetch(request('/api/ask','POST',{headers:{Origin:'https://attacker.example'}}),env)).status,403);
});
test('body limit applies even without Content-Length', async () => {
  assert.equal((await worker.fetch(request('/api/ask','POST',{body:'x'.repeat(17000)}),env)).status,400);
});
test('wake uses provider credential server-side and filters health payload', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url,'https://example123.api.runpod.ai/api/health');
    assert.equal(options.headers.Authorization,'Bearer ' + env.RUNPOD_API_KEY);
    return Response.json({ready:true,inference_reachable:true,available_models:['gemma2-base'],private:'do not expose'});
  };
  const response = await worker.fetch(request('/api/wake'),env);
  const body = await response.text();
  assert.equal(response.status,200);
  assert.ok(!body.includes('private') && !body.includes(env.RUNPOD_API_KEY));
});
test('provider auth/configuration errors do not reveal raw diagnostics', async () => {
  globalThis.fetch = async () => new Response('secret provider traceback',{status:403});
  const response = await worker.fetch(request('/api/wake'),env);
  assert.equal(await response.text(),'{"code":"demo_not_configured"}');
});
test('failed POST is not retried', async () => {
  let attempts = 0;
  globalThis.fetch = async () => { attempts++; return new Response('provider traceback',{status:502}); };
  const response = await worker.fetch(request('/api/ask/stream','POST'),env);
  assert.equal(attempts,1);
  assert.equal(response.status,503);
  assert.ok(!(await response.text()).includes('traceback'));
});
test('SSE is streamed and browser cancellation reaches upstream', async () => {
  let upstreamSignal, cancelled = false;
  const encoder = new TextEncoder();
  globalThis.fetch = async (_url, options) => {
    upstreamSignal = options.signal;
    return new Response(new ReadableStream({
      start(controller) { controller.enqueue(encoder.encode('event: queued\ndata: {}\n\n')); },
      cancel() { cancelled = true; }
    }));
  };
  const response = await worker.fetch(request('/api/ask/stream','POST'),env);
  const reader = response.body.getReader();
  assert.match(new TextDecoder().decode((await reader.read()).value),/queued/);
  await reader.cancel();
  assert.equal(upstreamSignal.aborted,true);
  assert.equal(cancelled,true);
});
