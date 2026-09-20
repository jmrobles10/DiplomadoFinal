"""
PitWall · Ingesta directa a Qdrant con embeddings de Gemini (alternativa al flujo 01 de n8n).

Requisitos:
  - Qdrant corriendo en http://localhost:6333 (scripts/start_qdrant.ps1) y la colección creada (scripts/qdrant_setup.py)
  - Variable de entorno GEMINI_API_KEY con tu key de Google AI Studio (la key NUNCA se escribe en archivos):
        PowerShell:  $env:GEMINI_API_KEY = "pega-aquí-tu-key"
Uso:
  python scripts/ingest_qdrant.py                 # ingesta completa (reanudable: salta lo ya insertado)
  python scripts/ingest_qdrant.py --limit 50      # prueba con 50 fragmentos
  python scripts/ingest_qdrant.py --only temporada,guia
  python scripts/ingest_qdrant.py --query "cuántos puntos da ganar una carrera sprint"   # prueba de búsqueda
  python scripts/ingest_qdrant.py --count

Modelo: gemini-embedding-2, 3072 dimensiones (la misma configuración que usa el nodo de n8n para las consultas).
Cuota gratuita: lotes de 20 textos por solicitud con 20 s de pausa (~1.072 fragmentos ≈ 18-20 minutos).
Si Gemini devuelve vectores vacíos (señal de cuota superada) el script espera 60 s y reintenta; es reanudable.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

sys.stdout.reconfigure(encoding="utf-8")

ROOT = r"C:\Fuentes_Git\rag-f1-n8n"
KB = os.path.join(ROOT, "kb", "processed", "kb_all.jsonl")
PROGRESS = os.path.join(ROOT, "kb", "processed", "ingest_progress.json")
QDRANT = "http://localhost:6333"
COLLECTION = "pitwall_kb"
MODEL = "gemini-embedding-2"
DIMS = 3072
BATCH = 40          # textos por solicitud (key de pago: sin problema de tokens por minuto)
PAUSE = 2           # segundos entre solicitudes
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:batchEmbedContents"
GEMINI_ONE = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:embedContent"
NAMESPACE = uuid.UUID("6f1c2a9e-0d3b-4f7a-9c1e-5b2d8e4a7c10")


def http(method, url, body=None, headers=None, timeout=120):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, method=method, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            return e.code, {}


def api_key():
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if not k:
        print("Falta la variable de entorno GEMINI_API_KEY. En PowerShell:  $env:GEMINI_API_KEY = \"tu-key\"")
        sys.exit(1)
    return k


def embed_batch(texts, key, task="RETRIEVAL_DOCUMENT"):
    body = {"requests": [{"model": f"models/{MODEL}", "content": {"parts": [{"text": t}]}, "taskType": task, "outputDimensionality": DIMS} for t in texts]}
    delay = 5
    for attempt in range(8):
        status, res = http("POST", GEMINI_URL, body, {"x-goog-api-key": key})
        if status == 200:
            vectors = [e.get("values", []) for e in res.get("embeddings", [])]
            if len(vectors) != len(texts) or any(len(v) != DIMS for v in vectors):
                # Gemini a veces responde 200 con vectores vacíos al superar la cuota: esperar y reintentar
                print(f"   respuesta incompleta ({sum(1 for v in vectors if len(v) != DIMS)} vectores vacíos): espero 60s")
                time.sleep(60); continue
            return vectors
        if status in (429, 500, 502, 503, 504):
            msg = (res.get("error") or {}).get("message", "")[:160]
            print(f"   cuota/servidor ({status}): espero {delay}s. {msg}")
            time.sleep(delay); delay = min(delay * 2, 90)
            continue
        raise RuntimeError(f"Gemini error {status}: {json.dumps(res)[:400]}")
    raise RuntimeError("Gemini: demasiados reintentos")


def embed_query(text, key):
    body = {"model": f"models/{MODEL}", "content": {"parts": [{"text": text}]}, "taskType": "RETRIEVAL_QUERY", "outputDimensionality": DIMS}
    status, res = http("POST", GEMINI_ONE, body, {"x-goog-api-key": key})
    if status != 200:
        raise RuntimeError(f"Gemini error {status}: {json.dumps(res)[:400]}")
    return res["embedding"]["values"]


def point_id(chunk_id):
    return str(uuid.uuid5(NAMESPACE, chunk_id))


def load_progress():
    try:
        return set(json.load(open(PROGRESS, encoding="utf-8")))
    except Exception:
        return set()


def save_progress(done):
    json.dump(sorted(done), open(PROGRESS, "w", encoding="utf-8"))


def count():
    status, res = http("GET", f"{QDRANT}/collections/{COLLECTION}")
    if status != 200:
        print("Qdrant no responde o la colección no existe:", status, res); return None
    r = res["result"]
    print(f"Colección {COLLECTION}: {r.get('points_count')} puntos, estado {r.get('status')}, dims {r['config']['params']['vectors']['size']}")
    return r.get("points_count")


def ingest(limit=None, only=None):
    key = api_key()
    docs = [json.loads(l) for l in open(KB, encoding="utf-8")]
    if only:
        docs = [d for d in docs if d["metadata"].get("tipo") in only]
    done = load_progress()
    pending = [d for d in docs if d["id"] not in done]
    if limit:
        pending = pending[:limit]
    print(f"Fragmentos: {len(docs)} | ya insertados: {len(done)} | por insertar ahora: {len(pending)}")
    total_chars = sum(len(d["content"]) for d in pending)
    print(f"Caracteres a vectorizar: {total_chars:,} (~{total_chars // 4:,} tokens) en {(len(pending) + BATCH - 1) // BATCH} lotes")
    t0 = time.time()
    for i in range(0, len(pending), BATCH):
        batch = pending[i:i + BATCH]
        vectors = embed_batch([d["content"] for d in batch], key)
        points = [{"id": point_id(d["id"]), "vector": v, "payload": {"content": d["content"], "metadata": {**d["metadata"], "id": d["id"]}}}
                  for d, v in zip(batch, vectors)]
        status, res = http("PUT", f"{QDRANT}/collections/{COLLECTION}/points?wait=true", {"points": points})
        if status != 200:
            raise RuntimeError(f"Qdrant error {status}: {json.dumps(res)[:400]}")
        done.update(d["id"] for d in batch)
        save_progress(done)
        hecho = i + len(batch)
        print(f"  {hecho}/{len(pending)} insertados · {time.time() - t0:5.0f}s")
        time.sleep(PAUSE)
    count()


def query(text, k=5):
    key = api_key()
    vec = embed_query(text, key)
    status, res = http("POST", f"{QDRANT}/collections/{COLLECTION}/points/search", {"vector": vec, "limit": k, "with_payload": True})
    if status != 200:
        raise RuntimeError(f"Qdrant error {status}: {res}")
    print(f"\nConsulta: {text}\n")
    for r in res["result"]:
        md = r["payload"].get("metadata", {})
        print(f"[{r['score']:.3f}] {md.get('documento') or md.get('titulo')} · {md.get('articulo') or md.get('subtipo', '')} (p. {md.get('pagina', '-')})")
        print("   ", r["payload"]["content"][:260].replace("\n", " "), "...\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", help="tipos separados por coma: reglamento,temporada,temporada_narrativa,guia")
    ap.add_argument("--query")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--reset-progress", action="store_true")
    a = ap.parse_args()
    if a.reset_progress and os.path.exists(PROGRESS):
        os.remove(PROGRESS); print("progreso reiniciado")
    if a.count:
        count()
    elif a.query:
        query(a.query)
    else:
        ingest(a.limit, set(a.only.split(",")) if a.only else None)
