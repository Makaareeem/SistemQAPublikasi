const API = (typeof window !== 'undefined' ? window.API_BASE || '' : '').replace(/\/$/, '');
let busy = false, controller = null, responseStyle = 'detail', thinkOpen = true;
let questionRules = null, hasCompletedResult = false;
let twTimer = null, lastFocus = null, queueTimer = null, thinkTouched = false;
let answerFrame = null, pendingAnswer = '', sourceSignature = '';
const noticeTimers = new Map();
const NOTICE_DURATION = {info: 5000, warning: 7000, error: 8000};
const MODEL_LABELS = {
  'llama3.2-finetuned': 'Llama 3.2 \u00b7 Fine-tuned', 'llama3.2-base': 'Llama 3.2 \u00b7 Dasar',
  'gemma2-finetuned': 'Gemma 2 \u00b7 Fine-tuned', 'gemma2-base': 'Gemma 2 \u00b7 Dasar'
};
const modelLabel = key => MODEL_LABELS[key] || key || 'Model lokal';
const el = id => document.getElementById(id);
function node(tag, text, className) {
  const n = document.createElement(tag);
  if (text !== undefined && text !== null) n.textContent = String(text);
  if (className) n.className = className;
  return n;
}

function userMessage(status, code) {
  const messages = {
    model_timeout: 'Model membutuhkan waktu terlalu lama. Coba kembali dengan pertanyaan lebih spesifik.',
    model_unavailable: 'Layanan jawaban belum dapat dihubungi. Silakan coba beberapa saat lagi.',
    model_memory: 'Memori layanan model tidak mencukupi. Tutup aplikasi berat atau minta pengelola menyesuaikan penggunaan memori, lalu coba kembali.',
    model_context: 'Konteks yang diterima model melebihi kapasitasnya. Coba pertanyaan lebih spesifik atau pilih model lain.',
    model_busy: 'Layanan model sedang sibuk. Tunggu sebentar lalu coba kembali.',
    model_failed: 'Model gagal memproses jawaban. Coba kembali atau pilih model lain.',
    model_stream_interrupted: 'Koneksi model terputus sebelum jawaban selesai. Silakan coba kembali.',
    model_invalid_response: 'Layanan model mengirim respons yang tidak dapat dibaca. Silakan coba kembali.',
    model_incomplete_response: 'Model mencapai batas panjang sebelum menyelesaikan kalimat. Coba pertanyaan yang lebih spesifik.',
    model_empty_response: 'Model tidak menghasilkan jawaban. Silakan coba kembali atau pilih model lain.',
    context_unavailable: 'Sumber ditemukan, tetapi teksnya belum dapat dimuat dalam kapasitas model. Coba pertanyaan lebih spesifik.',
    queue_timeout: 'Waktu tunggu antrean habis. Server masih sibuk; silakan coba kembali.',
    model_missing: 'Model pilihan belum tersedia. Silakan pilih model lain.',
    processing_failed: 'Jawaban belum berhasil diproses. Silakan coba kembali.',
    question_empty: 'Tuliskan pertanyaan terlebih dahulu.',
    question_too_long: 'Pertanyaan terlalu panjang. Ringkas hingga maksimal 1.500 karakter.',
    question_invalid: 'Pertanyaan harus berupa teks yang dapat dibaca. Hapus karakter yang tidak wajar, lalu coba kembali.',
    question_needs_topic: 'Apa yang ingin Anda ketahui? Tuliskan topik atau pertanyaan statistiknya, misalnya IPM atau kemiskinan Jawa Tengah tahun 2024.',
    invalid_request: 'Periksa pertanyaan dan pilihan Anda, lalu coba kembali.'
  };
  return messages[code] || ({
    400: 'Pilihan model atau permintaan belum sesuai. Periksa pilihan Anda.',
    422: 'Pertanyaan atau pilihan belum sesuai. Periksa dan coba kembali.',
    429: 'Server sedang sibuk dan antrean penuh. Tunggu sebentar lalu coba kembali.',
    503: 'Layanan sedang belum siap atau mengalami gangguan. Coba beberapa saat lagi.',
    504: 'Waktu tunggu habis. Silakan coba kembali.',
    0: 'Koneksi ke layanan terputus. Periksa koneksi dan coba kembali.'
  })[status] || 'Permintaan belum berhasil diproses. Silakan coba kembali.';
}
function serverError(status, data = {}) {
  const detail = data.detail && typeof data.detail === 'object' ? data.detail : data;
  const requestId = /^[a-f0-9]{32}$/i.test(detail.request_id || '') ? detail.request_id.slice(0, 8) : '';
  return friendlyError(userMessage(status, detail.code) + (requestId ? ' ID pemeriksaan: ' + requestId + '.' : ''));
}
function friendlyError(message) {
  const error = new Error(message); error.userFacing = true; return error;
}
function dismissNotice(toast) {
  clearTimeout(noticeTimers.get(toast)); noticeTimers.delete(toast); toast.remove();
}
function clearNotices() { for (const toast of [...noticeTimers.keys()]) dismissNotice(toast); }
function notifyUser(message, kind = 'info') {
  if (!Object.hasOwn(NOTICE_DURATION, kind)) kind = 'info';
  const host = el('notifications'), toast = node('div', null, 'notice notice-' + kind);
  toast.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  const close = node('button', '\u00d7', 'notice-close');
  close.type = 'button'; close.setAttribute('aria-label', 'Tutup pemberitahuan');
  close.addEventListener('click', () => dismissNotice(toast));
  toast.append(node('span', message), close); host.appendChild(toast);
  noticeTimers.set(toast, setTimeout(() => dismissNotice(toast), NOTICE_DURATION[kind]));
  while (host.children.length > 3) dismissNotice(host.firstElementChild);
  return toast;
}
function setFeedback(message = '', kind = 'error', invalid = false) {
  if (message && el('questionForm').hidden) setComposerCollapsed(false);
  const box = el('error');
  box.textContent = message; box.style.display = message ? 'block' : 'none'; box.dataset.kind = kind;
  el('q').setAttribute('aria-invalid', String(invalid));
}
function updateQuestion() {
  const count = el('q').value.length;
  el('questionCount').textContent = count.toLocaleString('id-ID') + ' / 1.500';
  el('questionCount').classList.toggle('near-limit', count >= 1350);
}
function setComposerCollapsed(collapsed) {
  el('questionForm').hidden = collapsed;
  el('questionSummary').hidden = !collapsed;
  el('editQuestionBtn').setAttribute('aria-expanded', String(!collapsed));
  el('backToResults').hidden = !hasCompletedResult;
}
function openQuestionEditor() {
  if (busy) return;
  setComposerCollapsed(false);
  el('q').focus();
}
function focusResults() {
  const target = el('answerTitle');
  // Do not interrupt a guide dialog. Return focus to the answer when it closes.
  if (el('modalOverlay').open) { lastFocus = target; return; }
  target.focus({preventScroll: true});
  el('ansCard').scrollIntoView({block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
}
function returnToResults() {
  if (busy || !hasCompletedResult) return;
  setComposerCollapsed(true); focusResults();
}
function beginResultView(question) {
  hasCompletedResult = false;
  el('summaryQuestion').textContent = question;
  el('summaryQuestion').title = question;
  setComposerCollapsed(true);
}
function completeResultView() {
  hasCompletedResult = true;
  document.body.classList.add('has-results');
  el('summaryQuestion').textContent = el('answerQuestion').textContent;
  setComposerCollapsed(true);
  focusResults();
}
function setBusy(value) {
  busy = value;
  for (const id of ['btn', 'q', 'model']) el(id).disabled = value;
  document.querySelectorAll('#styleToggle button, [data-question]').forEach(b => { b.disabled = value; });
  el('questionForm').setAttribute('aria-busy', String(value));
  el('btn').replaceChildren(document.createTextNode(value ? 'Memproses...' : 'Tanyakan'));
  if (!value) { const arrow = node('span', '\u2197'); arrow.setAttribute('aria-hidden', 'true'); el('btn').appendChild(arrow); }
  el('cancelBtn').hidden = !value; el('cancelBtn').disabled = false;
  el('summaryCancelBtn').hidden = !value; el('summaryCancelBtn').disabled = false;
  el('editQuestionBtn').hidden = value;
  el('backToResults').disabled = value; el('editQuestionBtn').disabled = value;
}
function showWarnings(warnings) {
  el('warnings').replaceChildren();
  if (!warnings || !warnings.length) return;
  const details = node('details', null, 'review-note');
  details.appendChild(node('summary', 'Catatan jawaban dan sumber'));
  for (const text of warnings) details.appendChild(node('p', text));
  el('warnings').appendChild(details);
}
function answerNodes(answer) {
  const fragments = [], pattern = /\[(\d+(?:\s*,\s*\d+)*)\]/g;
  let start = 0, match;
  while ((match = pattern.exec(answer))) {
    fragments.push(document.createTextNode(answer.slice(start, match.index)));
    for (const id of match[1].split(/\s*,\s*/)) {
      const target = el('source-' + id);
      const ref = node(target ? 'a' : 'span', '[' + id + ']', 'citation-ref');
      if (target) { ref.href = '#source-' + id; ref.setAttribute('aria-label', 'Lihat sumber ' + id); }
      fragments.push(ref);
    }
    start = pattern.lastIndex;
  }
  fragments.push(document.createTextNode(answer.slice(start)));
  return fragments;
}

function safeURL(value) {
  try {
    const u = new URL(value);
    return ['https:', 'http:'].includes(u.protocol) ? u.href : '';
  } catch { return ''; }
}
function pages(source) {
  const start = source.page_start, end = source.page_end;
  if (start === null || start === undefined) return 'Halaman belum tersedia';
  return end !== null && end !== undefined && end !== start ? `Hal. ${start}–${end}` : `Hal. ${start}`;
}
function setStyle(style) {
  if (busy) return;
  if (!['ringkas', 'detail'].includes(style)) return;
  responseStyle = style;
  document.querySelectorAll('#styleToggle button').forEach(b => {
    b.classList.toggle('active', b.dataset.style === style);
    b.setAttribute('aria-pressed', String(b.dataset.style === style));
  });
}
function setThink(open) {
  thinkOpen = open;
  el('thinkBody').classList.toggle('open', open);
  el('thinkArrow').textContent = open ? '\u25be' : '\u25b8';
  el('thinkToggle').setAttribute('aria-expanded', String(open));
}
function toggleThink() { thinkTouched = true; setThink(!thinkOpen); }
function finishSteps(failed = false) {
  const prev = el('thinkSteps').querySelector('.active');
  if (prev) {
    prev.classList.remove('active');
    prev.classList.add(failed ? 'failed' : 'done');
    prev.querySelector('.tmark').replaceChildren(node('span', failed ? '!' : '\u2713'));
  }
}
function addStep(label) {
  finishSteps();
  const row = node('div', null, 'tstep active');
  const mark = node('span', null, 'tmark');
  mark.appendChild(node('span', null, 'spinner'));
  row.append(mark, node('span', label));
  el('thinkSteps').appendChild(row);
  el('thinkSummary').textContent = label;
}
function renderRankTable(process) {
  if (!process) return;
  const table = el('rankTable'), wasOpen = table.querySelector('.rank-details')?.open;
  table.style.display = 'block'; table.replaceChildren();
  for (const [label, text] of [
    ['Pertanyaan asli', process.original_query || el('q').value],
    ['Perluasan pencarian', (process.expanded_queries || [])[0] || 'Menggunakan pertanyaan asli']
  ]) {
    const block = node('div', null, 'query-block');
    block.append(node('div', label, 'query-label'), node('div', text)); table.appendChild(block);
  }
  if (process.expansion_note) table.appendChild(node('p', process.expansion_note, 'expansion-note'));
  const details = node('details', null, 'rank-details'); details.open = Boolean(wasOpen);
  details.appendChild(node('summary', 'Lihat rincian kandidat sumber'));
  details.appendChild(node('p', (process.candidates_before_rerank || 0) + ' kandidat diperiksa. Batas skor: ' + (process.rerank_threshold ?? '-') + '. Skor menunjukkan relevansi, bukan persentase kebenaran.', 'rank-meta'));
  for (const r of process.reranked || []) {
    const row = node('div', null, 'rank-item' + (r.passed ? '' : ' rejected'));
    row.append(node('span', r.document_title || 'Publikasi', 'rtitle'),
      node('span', r.selected ? 'Digunakan' : r.passed ? 'Cadangan' : 'Tidak lolos'),
      node('span', Number.isFinite(r.score) ? r.score.toFixed(3) : '-', 'rscore'));
    details.appendChild(row);
  }
  table.appendChild(details);
}
function sourceLink(source, className) {
  const url = safeURL(source.bps_url);
  const link = node(url ? 'a' : 'span', source.document_title || 'Publikasi', className);
  if (url) { link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; }
  return link;
}
function relatedPublication(source) {
  const url = safeURL(source.bps_url);
  const card = node(url ? 'a' : 'article', null, 'other-src-item');
  if (url) {
    card.href = url; card.target = '_blank'; card.rel = 'noopener noreferrer';
  }
  card.append(node('span', 'PUBLIKASI', 'related-label'),
    node('span', source.document_title || 'Publikasi', 'related-title'));
  const meta = node('span', null, 'osmeta');
  meta.appendChild(node('span', pages(source)));
  if (source.document_year) meta.appendChild(node('span', 'Terbit ' + source.document_year));
  card.appendChild(meta);
  if (url) {
    const action = node('span', 'Buka publikasi', 'related-action');
    const arrow = node('span', '\u2197'); arrow.setAttribute('aria-hidden', 'true');
    action.append(arrow, node('span', ' (tab baru)', 'sr-only')); card.appendChild(action);
  } else card.appendChild(node('span', 'Tautan belum tersedia', 'related-unavailable'));
  return card;
}
function renderSources(sources) {
  sources = Array.isArray(sources) ? sources : [];
  const signature = JSON.stringify(sources);
  if (signature === sourceSignature) return;
  sourceSignature = signature;
  const opened = new Set([...el('sources').querySelectorAll('article')].filter(c => c.querySelector('details')?.open).map(c => c.id));
  el('sources').replaceChildren();
  el('sourceCount').textContent = String(sources.length);
  el('srcSection').style.display = sources.length ? 'block' : 'none';
  for (const s of sources) {
    const card = node('article', null, 'src-card'); card.id = 'source-' + s.index;
    const head = node('div', null, 'src-head');
    head.append(node('span', s.index, 'src-num'), sourceLink(s, 'src-title'));
    const meta = node('div', null, 'src-meta');
    meta.append(node('span', pages(s)), node('span', `Skor relevansi: ${Number.isFinite(s.score) ? s.score.toFixed(3) : '-'}`));
    if (s.document_year) meta.appendChild(node('span', 'Tahun terbit: ' + s.document_year));
    card.append(head, meta);
    if (s.quote) {
      const original = node('div', null, 'source-original');
      original.append(node('div', 'CUPLIKAN ASLI YANG RELEVAN', 'source-label'), node('blockquote', s.quote));
      card.appendChild(original);
    }
    if (s.source_text && s.source_text !== s.quote) {
      const details = node('details', null, 'source-full');
      details.open = opened.has(card.id);
      details.append(node('summary', 'Baca teks sumber selengkapnya'), node('blockquote', s.source_text));
      card.appendChild(details);
    }
    el('sources').appendChild(card);
  }
}
function renderAnswer(answer, provisional = false) {
  el('ansCard').style.display = 'block';
  el('answer').replaceChildren(...answerNodes(String(answer || '')));
  el('answerState').textContent = provisional ? 'Sedang menyusun jawaban dan memeriksa sumber...' : '';
}
function flushAnswer() {
  if (answerFrame !== null) cancelAnimationFrame(answerFrame);
  answerFrame = null;
}
function queueAnswer(answer) {
  pendingAnswer = answer;
  if (answerFrame !== null) return;
  answerFrame = requestAnimationFrame(() => { answerFrame = null; renderAnswer(pendingAnswer, true); });
}
function seconds(value) { return Number.isFinite(value) ? value.toLocaleString('id-ID', {maximumFractionDigits: 2}) + ' detik' : '-'; }
function renderFinal(data) {
  if (typeof data.answer !== 'string' || !data.answer.trim()) throw friendlyError(userMessage(503, 'model_empty_response'));
  flushAnswer(); renderSources(data.sources || []); renderAnswer(data.answer);
  renderRankTable(data.process); showWarnings(data.warnings);
  if ((data.warnings || []).length) notifyUser('Jawaban tersedia. Buka catatan jawaban dan sumber untuk rincian yang perlu ditinjau.', 'warning');
  const t = data.latency || {};
  el('meta').replaceChildren(node('span', seconds(t.total_s)), node('span', (data.sources || []).length + ' sumber'), node('span', modelLabel(data.config?.model_key)));
  const requestId = /^[a-f0-9]{32}$/i.test(data.request_id || '') ? data.request_id.slice(0, 8) : '';
  el('processMeta').textContent = 'Antrean ' + seconds(t.queue_s) + ' \u00b7 Perluasan ' + seconds(t.expansion_s) + ' \u00b7 Pencarian ' + seconds(t.search_rerank_s) + ' \u00b7 Generasi ' + seconds(t.generation_s) + (requestId ? ' \u00b7 ID pemeriksaan ' + requestId : '');
  el('otherSrcList').replaceChildren();
  const others = Array.isArray(data.other_sources) ? data.other_sources : [];
  el('otherSrcSection').style.display = others.length ? 'block' : 'none';
  el('otherSrcSection').parentElement.hidden = !others.length;
  for (const s of others) {
    el('otherSrcList').appendChild(relatedPublication(s));
  }
  finishSteps();
  el('thinkSummary').textContent = 'Penelusuran selesai' + (Number.isFinite(t.total_s) ? ' dalam ' + seconds(t.total_s) : '');
  if (!thinkTouched) setThink(false);
  completeResultView();
}
function parseFrame(frame) {
  let event = 'message'; const data = [];
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
  }
  return data.length ? {event, payload: JSON.parse(data.join('\n'))} : null;
}
async function consumeStream(body, onEvent) {
  const reader = body.getReader(), decoder = new TextDecoder();
  let buffer = '', finished = false;
  try {
    while (!finished) {
      const {value, done} = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, {stream: true});
      buffer = buffer.replace(/\r\n/g, '\n');
      const frames = buffer.split('\n\n'); buffer = frames.pop();
      if (done && buffer.trim()) { frames.push(buffer); buffer = ''; }
      for (const frame of frames) {
        const item = parseFrame(frame);
        if (!item) continue;
        onEvent(item.event, item.payload);
        if (item.event === 'done') { finished = true; break; }
      }
      if (done) break;
    }
    if (!finished) throw friendlyError('Koneksi terputus sebelum hasil selesai. Silakan coba lagi.');
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}
function cancelAsk() {
  if (controller) { el('cancelBtn').disabled = true; el('summaryCancelBtn').disabled = true; controller.abort(); }
}
async function ask() {
  const q = el('q').value.trim();
  if (busy) return;
  const issue = questionIssue(q, questionRules);
  if (issue) {
    const message = userMessage(422, issue);
    setFeedback(message, 'warning', true); notifyUser(message, 'warning'); el('q').focus(); return;
  }
  clearNotices(); setFeedback(); controller = new AbortController(); setBusy(true);
  let answer = '', checked = false, started = false, inputRejected = false;
  try {
    const response = await fetch(API + '/api/ask/stream', {
      method: 'POST', signal: controller.signal, headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: q, model_key: el('model').value, use_rag: true, response_style: responseStyle})
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({})); inputRejected = response.status === 422;
      throw serverError(response.status, data);
    }
    if (!response.body) throw friendlyError(userMessage(503, 'model_invalid_response'));
    started = true;
    hasCompletedResult = false; el('backToResults').hidden = true;
    document.body.classList.remove('landing'); clearTimeout(twTimer);
    for (const id of ['ansCard', 'srcSection', 'otherSrcSection', 'rankTable']) el(id).style.display = 'none';
    for (const id of ['sources', 'otherSrcList', 'warnings', 'thinkSteps', 'meta', 'processMeta']) el(id).replaceChildren();
    sourceSignature = ''; el('answer').textContent = ''; el('answerState').textContent = '';
    el('answerQuestion').textContent = q;
    beginResultView(q);
    el('thinkCard').style.display = 'block'; el('thinkCard').setAttribute('aria-busy', 'true');
    thinkTouched = false; setThink(true); el('thinkSummary').textContent = 'Menghubungkan...';
    el('otherSrcSection').parentElement.hidden = true;
    await consumeStream(response.body, (event, data) => {
      if (!data || typeof data !== 'object') throw friendlyError(userMessage(503, 'model_invalid_response'));
      if (event === 'error') throw serverError(503, data);
      if (event === 'queued') {
        clearTimeout(queueTimer);
        queueTimer = setTimeout(() => notifyUser('Server sedang melayani permintaan lain. Pertanyaan Anda menunggu giliran.'), 3000);
      } else if (event !== 'heartbeat') clearTimeout(queueTimer);
      if (event === 'heartbeat') return;
      if (event === 'token') { if (typeof data.text === 'string') { answer += data.text; queueAnswer(answer); } return; }
      if (event === 'answer') {
        flushAnswer(); answer = data.answer; checked = true; renderAnswer(answer); showWarnings(data.warnings); return;
      }
      if (event === 'sources') { renderSources(data.sources || []); return; }
      if (event === 'done') { renderFinal(data); checked = true; return; }
      if (data.label) addStep(data.label);
      if (data.process) renderRankTable(data.process);
    });
  } catch (error) {
    flushAnswer(); if (started) finishSteps(true);
    const cancelled = error.name === 'AbortError';
    const message = cancelled ? 'Permintaan dibatalkan. Proses yang sedang berjalan akan berhenti pada batas proses berikutnya.' : error.userFacing ? error.message : userMessage(0);
    const kind = inputRejected ? 'warning' : cancelled ? 'info' : 'error';
    setFeedback(message, kind, inputRejected); notifyUser(message, kind);
    if (started) el('thinkSummary').textContent = cancelled ? 'Permintaan dibatalkan' : 'Pemrosesan belum selesai';
    if (started && !checked) { el('ansCard').style.display = 'none'; el('answer').textContent = ''; }
  } finally {
    clearTimeout(queueTimer); controller = null; setBusy(false);
    el('thinkCard').setAttribute('aria-busy', 'false');
    if (inputRejected) el('q').focus();
  }
}
function openModal(which) {
  lastFocus = document.activeElement;
  const modal = el('modalContent'); modal.replaceChildren();
  const heading = node('h2', which === 'howto' ? 'Cara memakai layanan' : 'Cara kerja sistem');
  heading.id = 'modalTitle'; modal.appendChild(heading);
  if (which === 'howto') {
    const list = node('ol');
    for (const text of ['Pilih model dan gaya jawaban.', 'Tulis indikator, wilayah, dan periode yang dibutuhkan.',
      'Klik Tanyakan atau tekan Enter. Sumber ditemukan lebih dahulu, kemudian jawaban muncul bertahap.',
      'Buka cuplikan asli dan publikasi untuk memeriksa angka serta periodenya.',
      'Panel proses dapat dibuka kembali setelah selesai.']) list.appendChild(node('li', text));
    modal.appendChild(list);
  } else {
    modal.appendChild(node('p', 'Pertanyaan asli dan satu perluasan dicari melalui pencarian makna dan kata kunci. Kandidat digabung, diurutkan ulang, lalu disaring berdasarkan skor. Model lokal menyusun jawaban dari sumber terpilih.'));
    modal.appendChild(node('p', 'Kartu sumber menampilkan cuplikan asli yang relevan dengan pertanyaan. Klik nomor sitasi untuk menuju sumber. Skor pencarian menunjukkan kecocokan teks, bukan jaminan kebenaran jawaban. Tahun terbit dapat berbeda dari tahun data.'));
  }
  if (!el('modalOverlay').open) el('modalOverlay').showModal();
  document.body.classList.add('modal-open'); el('modalClose').focus();
}
function closeModal() { el('modalOverlay').close(); }
function startTypewriter() {
  const topics = ['Dimensi Kemiskinan di Indonesia', 'Indeks Pembangunan Manusia', 'Tingkat Partisipasi Angkatan Kerja', 'Statistik Kesejahteraan Rakyat'];
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { el('typewriter').textContent = topics[0]; return; }
  let i = 0, chars = 0, deleting = false;
  function tick() {
    if (!document.body.classList.contains('landing')) return;
    chars += deleting ? -1 : 1;
    el('typewriter').textContent = topics[i].slice(0, chars);
    if (chars === topics[i].length) { deleting = true; twTimer = setTimeout(tick, 1600); return; }
    if (chars === 0) { deleting = false; i = (i + 1) % topics.length; }
    twTimer = setTimeout(tick, deleting ? 25 : 55);
  }
  tick();
}
async function timedFetch(url, milliseconds) {
  const abort = new AbortController(), timer = setTimeout(() => abort.abort(), milliseconds);
  try {
    const response = await fetch(url, {signal: abort.signal});
    if (!response.ok) throw new Error('Request unsuccessful');
    return await response.json();
  } finally { clearTimeout(timer); }
}
async function init() {
  // API validation remains authoritative if the optional local rules are unavailable.
  timedFetch('question-rules.json', 3000).then(rules => { if (rules?.version === 1) questionRules = rules; }).catch(() => {});
  el('q').addEventListener('input', () => { updateQuestion(); setFeedback(); });
  el('q').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(); }
  });
  document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => {
    if (busy) return;
    el('q').value = button.dataset.question; updateQuestion(); setFeedback(); el('q').focus();
  }));
  const dialog = el('modalOverlay');
  dialog.addEventListener('close', () => { document.body.classList.remove('modal-open'); lastFocus?.focus(); });
  dialog.addEventListener('click', event => {
    const r = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom)) closeModal();
  });
  updateQuestion(); startTypewriter();
  let modelChanged = false;
  el('model').addEventListener('change', () => { modelChanged = true; });
  try {
    const status = await timedFetch(API + '/api/health', 8000);
    const models = Array.isArray(status.available_models) ? status.available_models : [];
    const ready = status.ready && status.inference_reachable && models.length > 0;
    el('status').textContent = ready ? 'Layanan terhubung' : 'Layanan belum siap';
    el('status').dataset.state = ready ? 'ready' : 'unavailable';
    if (models.length && !busy) {
      const chosenModel = el('model').value;
      const choices = modelChanged && !models.includes(chosenModel) ? [...models, chosenModel] : models;
      el('model').replaceChildren(...choices.map(value => { const option = node('option', modelLabel(value)); option.value = value; return option; }));
      if (modelChanged) el('model').value = chosenModel;
      else if (models.includes(status.default_model)) el('model').value = status.default_model;
      else if (models.includes(chosenModel)) el('model').value = chosenModel;
    }
  } catch {
    el('status').textContent = 'Layanan tidak terjangkau'; el('status').dataset.state = 'unavailable';
  }
}
if (typeof document !== 'undefined') init();
if (typeof module !== 'undefined') module.exports = {parseFrame, consumeStream, safeURL, pages, userMessage, serverError};
