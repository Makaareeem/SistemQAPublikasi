"""Copy-only exporter. Refuses to overwrite an existing snapshot."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

PACKAGE = Path(__file__).resolve().parent
SOURCE = PACKAGE.parents[1]
SNAPSHOT = PACKAGE / "snapshot"

def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()

def inside(base, relative):
    path = base / relative
    if not path.resolve().is_relative_to(base.resolve()):
        raise ValueError("Path escapes its intended directory.")
    return path

def verify(compare_source=True):
    manifest = json.loads((SNAPSHOT / "snapshot-manifest.json").read_text(encoding="utf-8"))
    for relative, record in manifest["files"].items():
        copied = inside(SNAPSHOT, relative)
        if not copied.is_file() or digest(copied) != record["sha256"]:
            raise ValueError("Snapshot mismatch: " + relative)
        if compare_source and digest(inside(SOURCE, record["source"])) != record["sha256"]:
            raise ValueError("Local source differs since snapshot: " + record["source"])
    print("Verified snapshot and local originals:", len(manifest["files"]), "files", flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify()
        return
    if SNAPSHOT.exists() or (PACKAGE / "gateway" / "public").exists():
        raise SystemExit("Snapshot already exists. It is intentionally not overwritten. Use --verify.")
    pairs = [(p, Path("app") / p.name) for p in (SOURCE / "app").glob("*.py")]
    pairs += [(SOURCE / "requirements.txt", Path("requirements.txt"))]
    pairs += [(SOURCE / "deploy" / "setup_ollama.py", Path("deploy/setup_ollama.py"))]
    for p in (SOURCE / "web").rglob("*"):
        if p.is_file() and p.suffix.lower() in {".html", ".css", ".js", ".json", ".svg", ".png", ".ico", ".woff", ".woff2"}:
            pairs.append((p, Path("web") / p.relative_to(SOURCE / "web")))
    for filename in ("faiss_index.bin", "chunk_metadata.jsonl"):
        pairs.append((SOURCE / "app" / "kb_cache" / filename, Path("app/kb_cache") / filename))
    tree = ast.parse((SOURCE / "app" / "config.py").read_text(encoding="utf-8-sig"))
    registry = next(ast.literal_eval(node.value) for node in tree.body
                    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MODEL_REGISTRY" for t in node.targets))
    for key, cfg in registry.items():
        filename = cfg["gguf_filename"]
        pairs.append((SOURCE / "deploy" / "ollama_models" / key / filename, Path("assets/gguf") / key / filename))
    for source, relative in pairs:
        if not source.resolve().is_relative_to(SOURCE) or not source.is_file():
            raise SystemExit("Missing or unsafe source: " + str(source))
    total = sum(source.stat().st_size for source, _ in pairs)
    if shutil.disk_usage(PACKAGE).free < total + 512 * 1024 * 1024:
        raise SystemExit("Insufficient free space for a real copy.")
    print("Copying", len(pairs), "files;", round(total / 1024**3, 2), "GiB. Local source is read-only.", flush=True)
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "files": {}, "total_bytes": total}
    for source, relative in pairs:
        destination = inside(SNAPSHOT, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        before = digest(source)
        shutil.copy2(source, destination)
        if digest(destination) != before:
            raise RuntimeError("Copy integrity mismatch: " + relative.as_posix())
        manifest["files"][relative.as_posix()] = {
            "source": source.relative_to(SOURCE).as_posix(), "bytes": source.stat().st_size, "sha256": before
        }
        if source.suffix == ".gguf":
            print("Copied and verified model:", relative.parent.name, flush=True)
    (SNAPSHOT / "snapshot-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # Derive a public frontend from the untouched snapshot, not from the live app.
    public = PACKAGE / "gateway" / "public"
    shutil.copytree(SNAPSHOT / "web", public)
    script = public / "app.js"
    content = script.read_text(encoding="utf-8")
    replacements = {
        "    const response = await fetch(API + '/api/ask/stream', {":
        "    await waitForDemoServer(controller.signal);\n    const response = await fetch(API + '/api/ask/stream', {",
        "el('status').textContent = ready ? 'Layanan terhubung' : 'Layanan belum siap';":
        "el('status').textContent = ready ? 'Layanan terhubung' : status.deployment_mode === 'on_demand' ? 'Siap diaktifkan' : 'Layanan belum siap';",
    }
    replacements["    clearTimeout(queueTimer); controller = null; setBusy(false);"] = "    el('demoConnection').hidden = true;\n    clearTimeout(queueTimer); controller = null; setBusy(false);"
    for old, new in replacements.items():
        if content.count(old) != 1:
            raise RuntimeError("Frontend changed; review the deployment patch before exporting.")
        content = content.replace(old, new)
    script.write_text(content, encoding="utf-8", newline="\n")
    index = public / "index.html"
    html = index.read_text(encoding="utf-8")
    if html.count('<script src="api-config.js"></script>') != 1:
        raise RuntimeError("Cannot locate frontend script entry point.")
    html = html.replace('<script src="api-config.js"></script>',
        '<p id="demoConnection" role="status" aria-live="polite" hidden style="max-width:70rem;margin:1rem auto;padding:1rem;color:#16334a;background:#e7f4fb;border-radius:12px"></p>\n'
        '<script src="api-config.js"></script>\n<script src="demo-connection.js" defer></script>')
    start = html.index('<p id="demoConnection"')
    end = html.index("</p>", start) + 4
    note = html[start:end]
    html = html[:start] + html[end:]
    html = html.replace('  <form id="questionForm"', note + "\n  <form id=\"questionForm\"", 1)
    index.write_text(html, encoding="utf-8", newline="\n")
    shutil.copy2(PACKAGE / "gateway" / "demo-connection.js", public / "demo-connection.js")
    (public / "api-config.js").write_text('window.API_BASE = "";\n', encoding="utf-8")
    (PACKAGE / "gateway" / "public-manifest.json").write_text(json.dumps({
        p.relative_to(public).as_posix(): digest(p) for p in public.rglob("*") if p.is_file()
    }, indent=2), encoding="utf-8")
    print("Snapshot complete. No upload, deployment, purchase, or local configuration change was performed.", flush=True)

if __name__ == "__main__":
    main()
