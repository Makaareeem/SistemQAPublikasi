const assert = require('node:assert/strict');
const {parseFrame, consumeStream, safeURL, pages, userMessage} = require('../web/app.js');
const {questionIssue} = require('../web/question-validation.js');
const rules = require('../web/question-rules.json');
const cases = require('./question_validation_cases.json');
for (const [question, expected] of cases) assert.equal(questionIssue(question, rules), expected, JSON.stringify(question));
for (const [code, message] of Object.entries(rules.messages)) assert.equal(userMessage(422, code), message);
assert.equal(questionIssue('cek', null), null); // API supplies semantic validation if rules are unavailable.
(async () => {
  assert.match(userMessage(429), /antrean penuh/);
  assert.match(userMessage(503, 'model_timeout'), /waktu terlalu lama/);
  assert.doesNotMatch(userMessage(500, 'Traceback secret/path'), /Traceback|secret/);
  assert.equal(safeURL('javascript:alert(1)'), '');
  assert.equal(safeURL('https://www.bps.go.id/'), 'https://www.bps.go.id/');
  assert.equal(pages({page_start:9,page_end:null}), 'Hal. 9');
  assert.equal(pages({page_start:9,page_end:10}), 'Hal. 9–10');
  assert.equal(parseFrame(': ping'), null);
  assert.equal(parseFrame('event: token\ndata: {"text":"hi"}').payload.text, 'hi');
  const wire=': ping\r\n\r\nevent: token\r\ndata: {"text":"é — statistik"}\r\n\r\nevent: done\r\ndata: {"answer":"ok"}\r\n\r\n';
  const bytes=new TextEncoder().encode(wire);
  const stream=new ReadableStream({start(c){for(const b of bytes)c.enqueue(Uint8Array.of(b));c.close();}});
  const events=[]; await consumeStream(stream,(event,payload)=>events.push([event,payload]));
  assert.equal(events.length,2); assert.equal(events[0][1].text,'é — statistik'); assert.equal(events[1][0],'done');
  const broken=new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('event: token\ndata: {"text":"partial"}\n\n'));c.close();}});
  await assert.rejects(()=>consumeStream(broken,()=>{}), /terputus/);
  const terminal=new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('event: done\ndata: {"answer":"ok"}'));c.close();}});
  await consumeStream(terminal,()=>{});
  console.log('Frontend checks passed: URL validation, pages, SSE CRLF, fragmented UTF-8, comments, EOF and disconnect.');
})().catch(error=>{console.error(error);process.exitCode=1;});
