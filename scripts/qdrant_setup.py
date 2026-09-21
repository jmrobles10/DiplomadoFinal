"""
PitWall · Crea (o verifica) la colección de Qdrant para la base de conocimiento.

Uso:  python scripts/qdrant_setup.py            (Qdrant debe estar corriendo en http://localhost:6333)
      python scripts/qdrant_setup.py --recreate  (borra y vuelve a crear la colección)
      python scripts/qdrant_setup.py --recreate --dims 3072   (otro tamaño de vector, p. ej. Gemini)

La colección guarda un vector por fragmento (embeddings de bge-m3 vía Ollama, 1024 dimensiones, distancia coseno)
y el texto + metadatos como "payload". Los vectores quedan en disco: no se pierden al reiniciar.
"""
import json
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")

QDRANT = "http://localhost:6333"
COLLECTION = "pitwall_kb"
VECTOR_SIZE = 1024          # bge-m3 (Ollama, local). Con --dims N se puede cambiar (3072 para gemini-embedding-2)
DISTANCE = "Cosine"
PAYLOAD_INDEXES = {         # filtros rápidos por metadatos (n8n guarda los metadatos bajo "metadata.*")
    "metadata.tipo": "keyword",
    "metadata.seccion": "keyword",
    "metadata.articulo_grupo": "keyword",
    "metadata.subtipo": "keyword",
}


def call(method, path, body=None):
    req = urllib.request.Request(QDRANT + path, method=method, headers={"Content-Type": "application/json"},
                                 data=json.dumps(body).encode("utf-8") if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def main():
    global VECTOR_SIZE
    recreate = "--recreate" in sys.argv
    if "--dims" in sys.argv:
        VECTOR_SIZE = int(sys.argv[sys.argv.index("--dims") + 1])
    status, info = call("GET", "/")
    if status != 200:
        print(f"Qdrant no responde en {QDRANT} (status {status}). Arráncalo con scripts/start_qdrant.ps1"); sys.exit(1)
    print("Qdrant", info.get("version"), "OK")

    status, _ = call("GET", f"/collections/{COLLECTION}")
    exists = status == 200
    if exists and recreate:
        print("Borrando colección existente...")
        call("DELETE", f"/collections/{COLLECTION}")
        exists = False
    if not exists:
        status, res = call("PUT", f"/collections/{COLLECTION}", {
            "vectors": {"size": VECTOR_SIZE, "distance": DISTANCE, "on_disk": True},
            "optimizers_config": {"default_segment_number": 2},
        })
        print("Crear colección:", status, res.get("result", res.get("status")))
    else:
        print("La colección ya existe; no se toca.")

    for field, schema in PAYLOAD_INDEXES.items():
        status, res = call("PUT", f"/collections/{COLLECTION}/index", {"field_name": field, "field_schema": schema})
        print(f"Índice {field}: {status}")

    status, res = call("GET", f"/collections/{COLLECTION}")
    r = res.get("result", {})
    print(json.dumps({"status": r.get("status"), "puntos": r.get("points_count"), "vector_size": r.get("config", {}).get("params", {}).get("vectors", {}).get("size")}, ensure_ascii=False))
    print(f"Panel: {QDRANT}/dashboard#/collections/{COLLECTION}")


if __name__ == "__main__":
    main()
