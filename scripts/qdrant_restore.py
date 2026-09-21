"""
PitWall · Restaura la base vectorial en Qdrant a partir de los vectores exportados (sin llamar a Gemini).

Requiere: Qdrant corriendo, la colección creada (scripts/qdrant_setup.py), y los archivos
kb/processed/kb_all.jsonl, kb/processed/vectors.f32 y kb/processed/vectors_index.json del repositorio.

Uso: python scripts/qdrant_restore.py
Los fragmentos que no tengan vector exportado (por ejemplo documentos nuevos) se listan al final:
esos se cargan con  python scripts/ingest_qdrant.py  (que sí usa la API de Gemini).
"""
import json
import os
import sys
import urllib.request
import uuid
from array import array

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QDRANT = "http://localhost:6333"
COLLECTION = "pitwall_kb"
if "--collection" in sys.argv:
    COLLECTION = sys.argv[sys.argv.index("--collection") + 1]
SUFIJO = "" if COLLECTION == "pitwall_kb" else "_" + COLLECTION
KB = os.path.join(ROOT, "kb", "processed", "kb_all.jsonl" if not SUFIJO else "kb_pilotos.jsonl")
if "--kb" in sys.argv:
    KB = sys.argv[sys.argv.index("--kb") + 1]
VEC = os.path.join(ROOT, "kb", "processed", f"vectors{SUFIJO}.f32")
IDX = os.path.join(ROOT, "kb", "processed", f"vectors_index{SUFIJO}.json")
NAMESPACE = uuid.UUID("6f1c2a9e-0d3b-4f7a-9c1e-5b2d8e4a7c10")   # mismo espacio de ids que ingest_qdrant.py


def put(path, body):
    req = urllib.request.Request(QDRANT + path, method="PUT", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    idx = json.load(open(IDX, encoding="utf-8"))
    dims, ids = idx["dims"], idx["ids"]
    vec = array("f")
    with open(VEC, "rb") as fh:
        vec.frombytes(fh.read())
    assert len(vec) == dims * len(ids), "vectors.f32 no coincide con vectors_index.json"
    docs = {json.loads(l)["id"]: json.loads(l) for l in open(KB, encoding="utf-8")}
    pos = {cid: i for i, cid in enumerate(ids)}
    batch, total = [], 0
    for cid, d in docs.items():
        i = pos.get(cid)
        if i is None:
            continue
        batch.append({"id": str(uuid.uuid5(NAMESPACE, cid)), "vector": vec[i * dims:(i + 1) * dims].tolist(),
                      "payload": {"content": d["content"], "metadata": {**d["metadata"], "id": cid}}})
        if len(batch) == 100:
            put(f"/collections/{COLLECTION}/points?wait=true", {"points": batch}); total += len(batch); batch = []
            print(f"  restaurados {total} ...", end="\r")
    if batch:
        put(f"/collections/{COLLECTION}/points?wait=true", {"points": batch}); total += len(batch)
    faltan = [cid for cid in docs if cid not in pos]
    print(f"\n{total} fragmentos restaurados en '{COLLECTION}'.")
    if faltan:
        print(f"{len(faltan)} fragmentos sin vector exportado (nuevos): cárgalos con  python scripts/ingest_qdrant.py")
    else:
        print("La base quedó completa; no hace falta llamar a Gemini.")


if __name__ == "__main__":
    main()
