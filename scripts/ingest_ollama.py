"""
PitWall · Ingesta directa a Qdrant con embeddings LOCALES de Ollama (gratis, sin API keys).

Requisitos:
  - Ollama corriendo en http://127.0.0.1:11434 con el modelo de embeddings:  ollama pull bge-m3
  - Qdrant corriendo en http://localhost:6333 y la colección creada:  python scripts/qdrant_setup.py
Uso:
  python scripts/ingest_ollama.py                 # ingesta completa (reanudable: salta lo ya insertado)
  python scripts/ingest_ollama.py --limit 50      # prueba con 50 fragmentos
  python scripts/ingest_ollama.py --only temporada,guia
  python scripts/ingest_ollama.py --query "cuántos puntos da ganar una carrera sprint"   # prueba de búsqueda
  python scripts/ingest_ollama.py --count
  python scripts/ingest_ollama.py --reset-progress

Modelo: bge-m3 (1024 dimensiones, multilingüe: el usuario pregunta en español y el reglamento está en inglés).
Es la misma configuración que usa el nodo "Embeddings Ollama" de n8n para vectorizar las consultas.
Tiempo aproximado: 1.056 fragmentos en 2-4 minutos con GPU (más en CPU).
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB = os.path.join(ROOT, "kb", "processed", "kb_all.jsonl")
PROGRESS = os.path.join(ROOT, "kb", "processed", "ingest_progress.json")
QDRANT = os.environ.get("QDRANT_URL", "http://localhost:6333")
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
COLLECTION = "pitwall_kb"
MODEL = os.environ.get("EMBED_MODEL", "bge-m3")
DIMS = int(os.environ.get("EMBED_DIMS", "1024"))
BATCH = 16          # textos por solicitud a Ollama
NAMESPACE = uuid.UUID("6f1c2a9e-0d3b-4f7a-9c1e-5b2d8e4a7c10")   # mismo espacio de ids que qdrant_restore.py


def http(method, url, body=None, timeout=600):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, method=method, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            return e.code, {}
    except urllib.error.URLError as e:
        return 0, {"error": str(e.reason)}


def check_ollama():
    status, res = http("GET", f"{OLLAMA}/api/tags", timeout=10)
    if status != 200:
        print(f"Ollama no responde en {OLLAMA}. Arráncalo (ollama serve) o abre la app de Ollama."); sys.exit(1)
    names = [m["name"] for m in res.get("models", [])]
    if not any(n == MODEL or n.startswith(MODEL + ":") for n in names):
        print(f"El modelo {MODEL} no está descargado. Ejecuta:  ollama pull {MODEL}"); sys.exit(1)


def embed_batch(texts):
    for attempt in range(5):
        status, res = http("POST", f"{OLLAMA}/api/embed", {"model": MODEL, "input": texts, "truncate": True, "keep_alive": "30m"})
        if status == 200 and len(res.get("embeddings", [])) == len(texts):
            vectors = res["embeddings"]
            if any(len(v) != DIMS for v in vectors):
                raise RuntimeError(f"El modelo devolvió {len(vectors[0])} dimensiones y la colección espera {DIMS}. Recrea la colección: python scripts/qdrant_setup.py --recreate --dims {len(vectors[0])}")
            return vectors
        print(f"   Ollama respondió {status}: {json.dumps(res)[:200]}; reintento en {5 * (attempt + 1)}s")
        time.sleep(5 * (attempt + 1))
    raise RuntimeError("Ollama: demasiados reintentos")


def embed_query(text):
    return embed_batch([text])[0]


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
    status, res = http("GET", f"{QDRANT}/collections/{COLLECTION}", timeout=15)
    if status != 200:
        print("Qdrant no responde o la colección no existe:", status, res); return None
    r = res["result"]
    print(f"Colección {COLLECTION}: {r.get('points_count')} puntos, estado {r.get('status')}, dims {r['config']['params']['vectors']['size']}")
    return r.get("points_count")


def ingest(limit=None, only=None):
    check_ollama()
    status, res = http("GET", f"{QDRANT}/collections/{COLLECTION}", timeout=15)
    if status != 200:
        print("La colección no existe o Qdrant no responde. Ejecuta:  python scripts/qdrant_setup.py"); sys.exit(1)
    size = res["result"]["config"]["params"]["vectors"]["size"]
    if size != DIMS:
        print(f"La colección tiene {size} dimensiones y {MODEL} produce {DIMS}. Recréala:  python scripts/qdrant_setup.py --recreate --dims {DIMS}"); sys.exit(1)
    docs = [json.loads(l) for l in open(KB, encoding="utf-8")]
    if only:
        docs = [d for d in docs if d["metadata"].get("tipo") in only]
    done = load_progress()
    pending = [d for d in docs if d["id"] not in done]
    if limit:
        pending = pending[:limit]
    print(f"Fragmentos: {len(docs)} | ya insertados: {len(done)} | por insertar ahora: {len(pending)}")
    t0 = time.time()
    for i in range(0, len(pending), BATCH):
        batch = pending[i:i + BATCH]
        vectors = embed_batch([d["content"] for d in batch])
        points = [{"id": point_id(d["id"]), "vector": v, "payload": {"content": d["content"], "metadata": {**d["metadata"], "id": d["id"]}}}
                  for d, v in zip(batch, vectors)]
        status, res = http("PUT", f"{QDRANT}/collections/{COLLECTION}/points?wait=true", {"points": points})
        if status != 200:
            raise RuntimeError(f"Qdrant error {status}: {json.dumps(res)[:400]}")
        done.update(d["id"] for d in batch)
        save_progress(done)
        hecho = i + len(batch)
        print(f"  {hecho}/{len(pending)} insertados · {time.time() - t0:5.0f}s", end="\r", flush=True)
    print()
    count()


def query(text, k=5):
    check_ollama()
    vec = embed_query(text)
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
