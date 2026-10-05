// Only the deployment copy uses this helper. No provider key is present.
window.QA_DEMO_MODE = true;
function demoPause(ms, signal) {
  return new Promise((resolve, reject) => {
    const aborted = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', aborted); resolve(); }, ms);
    if (signal.aborted) aborted();
    else signal.addEventListener('abort', aborted, {once: true});
  });
}
async function waitForDemoServer(signal) {
  const started = Date.now();
  const status = document.getElementById('status');
  const info = document.getElementById('demoConnection');
  info.hidden = false;
  info.textContent = 'Mengaktifkan server demo dan memuat model. Akses pertama dapat memerlukan beberapa menit. Anda dapat membatalkan.';
  status.textContent = 'Menyiapkan layanan';
  status.dataset.state = 'unavailable';
  try {
    while (Date.now() - started < 300000) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      let response;
      const attempt = new AbortController();
      const cancelAttempt = () => attempt.abort();
      signal.addEventListener('abort', cancelAttempt, {once: true});
      const attemptTimer = setTimeout(cancelAttempt, 25000);
      try { response = await fetch('/api/wake', {signal: attempt.signal, cache: 'no-store'}); }
      catch (error) {
        if (signal.aborted) throw error;
        throw friendlyError('Koneksi terputus saat menyiapkan server. Periksa koneksi lalu coba kembali.');
      }
      finally {
        clearTimeout(attemptTimer);
        signal.removeEventListener('abort', cancelAttempt);
      }
      if (response.status === 401) throw friendlyError('Sesi demo berakhir. Muat ulang halaman dan masuk kembali.');
      const data = await response.json().catch(() => ({}));
      if (data.code === 'demo_not_configured') throw friendlyError('Konfigurasi demo belum siap. Hubungi pengelola demo.');
      if (response.ok && data.ready && data.inference_reachable) {
        const selected = document.getElementById('model').value;
        if (!(data.available_models || []).includes(selected)) throw friendlyError('Model pilihan belum tersedia di server demo. Pilih model lain.');
        info.textContent = 'Server siap. Pertanyaan sedang diproses.';
        status.textContent = 'Layanan terhubung'; status.dataset.state = 'ready';
        return;
      }
      info.textContent = 'Server sedang disiapkan (' + Math.floor((Date.now() - started) / 1000) + ' detik). Menunggu kesiapan sebelum mengirim pertanyaan.';
      await demoPause(5000, signal);
    }
    throw friendlyError('Server belum siap setelah beberapa menit. Coba kembali atau hubungi pengelola demo.');
  } finally {
    if (signal.aborted) {
      info.textContent = 'Permintaan dibatalkan sebelum pertanyaan dikirim.';
      status.textContent = 'Siap diaktifkan';
    }
  }
}
