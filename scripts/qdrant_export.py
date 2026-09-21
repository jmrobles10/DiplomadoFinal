"""
PitWall · Exporta los vectores de Qdrant a archivos versionables, para restaurarlos en otro PC sin recalcular embeddings.

Salida:
  kb/processed/vectors.f32         vectores float32 concatenados (n × 3072)
  kb/processed/vectors_index.json  lista de ids de fragmento en el mismo orden + dimensión

Uso: python scripts/qdrant_export.py     (Qdrant corriendo en http://localhost:6333)
Luego: git add kb/processed/vectors.*  → en el otro PC: python scripts/qdrant_restore.py
"""
import hashlib
import json
import os
import sys
import urllib.request
from array import array

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QDRANT = "http://localhost:6333"
COLLECTION = "pitwall_kb"
OUT_VEC = os.path.join(ROOT, "kb", "processed", "vectors.f32")
OUT_IDX = os.path.join(ROOT, "kb", "processed", "vectors_index.json")


def post(path, body):
    req = urllib.request.Request(QDRANT + path, method="POST", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ids, vec = [], array("f")
    offset, dims = None, None
    while True:
        body = {"limit": 200, "with_payload": {"include": ["content", "metadata.tipo"]}, "with_vector": True}
        if offset is not None:
            body["offset"] = offset
        res = post(f"/collections/{COLLECTION}/points/scroll", body)["result"]
        for p in res["points"]:
            payload = p.get("payload") or {}
            content = payload.get("content")
            if not content:
                continue
            # mismo esquema de id que build_kb.py: sha1(tipo|contenido)[:16]
            cid = hashlib.sha1((payload.get("metadata", {}).get("tipo", "") + "|" + content).encode("utf-8")).hexdigest()[:16]
            if cid in ids:
                continue
            v = p["vector"]
            dims = dims or len(v)
            ids.append(cid); vec.extend(v)
        offset = res.get("next_page_offset")
        print(f"  exportados {len(ids)} ...", end="\r")
        if offset is None:
            break
    with open(OUT_VEC, "wb") as fh:
        vec.tofile(fh)
    json.dump({"collection": COLLECTION, "dims": dims, "model": "gemini-embedding-2", "ids": ids},
              open(OUT_IDX, "w", encoding="utf-8"))
    print(f"\n{len(ids)} vectores de {dims} dimensiones -> {OUT_VEC} ({os.path.getsize(OUT_VEC)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
