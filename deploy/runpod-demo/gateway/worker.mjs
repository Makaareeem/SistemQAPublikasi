// Runpod's key stays in Worker secrets. Browser clients only use demo credentials.
const json = (status, code) => new Response(JSON.stringify({code}), {
  status, headers: {"Content-Type": "application/json", "Cache-Control": "no-store"}
});
async function equalSecret(left, right) {
  const encode = new TextEncoder();
  const [a, b] = await Promise.all([left, right].map(s => crypto.subtle.digest("SHA-256", encode.encode(s))));
  const aa = new Uint8Array(a), bb = new Uint8Array(b);
  let difference = 0;
  for (let i = 0; i < aa.length; i++) difference |= aa[i] ^ bb[i];
  return difference === 0;
}
async function authorized(request, env) {
  try {
    const auth = request.headers.get("Authorization") || "";
    if (!auth.startsWith("Basic ")) return false;
    return await equalSecret(atob(auth.slice(6)), (env.DEMO_USER || "demo") + ":" + env.DEMO_PASSWORD);
  } catch { return false; }
}
async function readBody(request) {
  const reader = request.body?.getReader();
  if (!reader) return "";
  const decoder = new TextDecoder();
  let size = 0, body = "";
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 16384) throw new Error("body_limit");
      body += decoder.decode(value, {stream: true});
    }
    return body + decoder.decode();
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
function originFor(env) {
  const origin = new URL(env.RUNPOD_ORIGIN);
  if (origin.protocol !== "https:" || !/^[a-z0-9-]+\.api\.runpod\.ai$/.test(origin.hostname) ||
      origin.port || origin.username || origin.password || origin.pathname !== "/" || origin.search || origin.hash ||
      origin.hostname.includes("replace")) throw new Error("configuration");
  return origin.origin;
}
export default {
  async fetch(request, env) {
    if (typeof env.DEMO_PASSWORD !== "string" || env.DEMO_PASSWORD.length < 12) return json(503, "demo_not_configured");
    if (!await authorized(request, env)) return new Response("Masuk untuk membuka demo.", {
      status: 401, headers: {"WWW-Authenticate": 'Basic realm="Demo QA Publikasi", charset="UTF-8"', "Cache-Control": "no-store"}
    });
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/api/")) {
      if (!["GET", "HEAD"].includes(request.method)) return json(405, "method_not_allowed");
      return env.ASSETS.fetch(request);
    }
    // A page view does not wake the GPU. This is not a real readiness result.
    if (url.pathname === "/api/health" && request.method === "GET") return new Response(JSON.stringify({
      ready: false, inference_reachable: false, available_models: [], deployment_mode: "on_demand"
    }), {headers: {"Content-Type": "application/json", "Cache-Control": "no-store"}});
    const waking = url.pathname === "/api/wake" && request.method === "GET";
    const asking = ["/api/ask", "/api/ask/stream"].includes(url.pathname) && request.method === "POST";
    if (!waking && !asking) return json(404, "not_found");
    if (request.headers.get("Origin") && request.headers.get("Origin") !== url.origin) return json(403, "origin_not_allowed");
    if (!env.RUNPOD_API_KEY) return json(503, "demo_not_configured");
    let origin, body;
    try { origin = originFor(env); } catch { return json(503, "demo_not_configured"); }
    if (asking) {
      if (!(request.headers.get("Content-Type") || "").startsWith("application/json")) return json(415, "invalid_request");
      try { body = await readBody(request); JSON.parse(body); }
      catch { return json(400, "invalid_request"); }
    }
    const abort = new AbortController();
    const onAbort = () => abort.abort();
    request.signal.addEventListener("abort", onAbort, {once: true});
    if (request.signal.aborted) abort.abort();
    const timer = setTimeout(() => abort.abort(), waking ? 20000 : 315000);
    const cleanup = () => {
      clearTimeout(timer);
      request.signal.removeEventListener("abort", onAbort);
    };
    let upstream;
    try {
      upstream = await fetch(origin + (waking ? "/api/health" : url.pathname), {
        method: waking ? "GET" : "POST", body,
        headers: {"Authorization": "Bearer " + env.RUNPOD_API_KEY, "Content-Type": "application/json"},
        signal: abort.signal, redirect: "manual"
      });
      if ([401, 403].includes(upstream.status)) {
        await upstream.body?.cancel(); cleanup(); return json(503, "demo_not_configured");
      }
      if (upstream.status >= 500 || upstream.status === 204 || upstream.status >= 300 && upstream.status < 400) {
        await upstream.body?.cancel(); cleanup(); return json(503, waking ? "server_warming" : "model_unavailable");
      }
      if (!upstream.ok) {
        const status = upstream.status;
        await upstream.body?.cancel(); cleanup();
        return json(status === 429 ? 429 : 400, status === 429 ? "model_busy" : "invalid_request");
      }
      if (waking) {
        const data = await upstream.json();
        cleanup();
        return new Response(JSON.stringify({
          ready: data.ready === true, inference_reachable: data.inference_reachable === true,
          available_models: Array.isArray(data.available_models) ? data.available_models : [],
          default_model: data.default_model
        }), {headers: {"Content-Type": "application/json", "Cache-Control": "no-store"}});
      }
      const reader = upstream.body.getReader();
      const stream = new ReadableStream({
        async pull(controller) {
          try {
            const {done, value} = await reader.read();
            if (done) { cleanup(); controller.close(); }
            else controller.enqueue(value);
          } catch { cleanup(); controller.error(new Error("Upstream connection closed")); }
        },
        async cancel(reason) {
          abort.abort(); cleanup(); await reader.cancel(reason).catch(() => {});
        }
      });
      return new Response(stream, {headers: {
        "Content-Type": url.pathname.endsWith("/stream") ? "text/event-stream" : "application/json",
        "Cache-Control": "no-store, no-transform", "X-Content-Type-Options": "nosniff"
      }});
    } catch {
      abort.abort(); cleanup();
      return json(503, waking ? "server_warming" : "model_unavailable");
    }
  }
};
