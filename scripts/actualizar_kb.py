"""
PitWall · Actualización incremental de la base de conocimiento (fuentes -> fragmentos -> Qdrant), todo en local.

Uso:
  python scripts/actualizar_kb.py                    # revisa las fuentes y aplica solo lo que cambió
  python scripts/actualizar_kb.py --si-hace-falta    # igual, pero sale enseguida si ya se revisó hace menos de --horas (6)
  python scripts/actualizar_kb.py --forzar           # reconstruye y sincroniza aunque las fuentes no hayan cambiado
  python scripts/actualizar_kb.py --conservar-obsoletos   # no borra de Qdrant los fragmentos que ya no existen
  python scripts/actualizar_kb.py --estado           # muestra la última revisión/actualización

Qué hace:
  1. download_sources.py --refresh: vuelve a consultar la API de la temporada (Jolpica), Wikipedia y la página oficial
     de reglamentos de la FIA; reemplaza solo los archivos cuyo contenido cambió (nueva carrera, nuevo Issue...).
  2. Si cambió algún PDF, extract_pdf_text.py extrae su texto (y retira el de la edición anterior).
  3. build_kb.py regenera los fragmentos. Cada fragmento tiene un id que es el hash de su contenido, así que:
       - lo que no cambió conserva su id  -> no se toca ni se duplica en Qdrant
       - lo nuevo o modificado tiene id nuevo -> se vectoriza con Ollama (bge-m3) y se inserta
       - lo que desapareció (p. ej. la clasificación "tras 14 rondas" cuando ya hay 15) -> se elimina de Qdrant
  4. Exporta los vectores (kb/processed/vectors.f32) para que el repositorio quede sincronizado.
Estado en kb/processed/update_state.json; bitácora en kb/processed/update_log.jsonl.
Lo invoca el flujo 04 de n8n (cada 6 h y, en segundo plano, cuando alguien pregunta), pero se puede correr a mano.
"""
import argparse
import json
import os
import sys
import time
import traceback
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
PROCESSED = os.path.join(ROOT, "kb", "processed")
KB = os.path.join(PROCESSED, "kb_all.jsonl")
STATE = os.path.join(PROCESSED, "update_state.json")
LOG = os.path.join(PROCESSED, "update_log.jsonl")
LOCK = os.path.join(PROCESSED, ".update.lock")
QDRANT = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = "pitwall_kb"
NAMESPACE = uuid.UUID("6f1c2a9e-0d3b-4f7a-9c1e-5b2d8e4a7c10")   # mismo espacio de ids que ingest_ollama.py / qdrant_restore.py


def now():
    # UTC con zona explícita: n8n arranca con TZ=America/Bogota y el runtime de Windows no entiende ese nombre,
    # así que la hora local de Python cambia según quién lance el script. En UTC la comparación es estable.
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_ts(v):
    d = datetime.fromisoformat(v)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def save_state(st):
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def log(entry):
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def qdrant(method, path, body=None, timeout=300):
    req = urllib.request.Request(QDRANT + path, method=method, data=json.dumps(body).encode("utf-8") if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def qdrant_ids():
    """Ids de fragmento (metadata.id) presentes en la colección."""
    ids, offset = set(), None
    while True:
        body = {"limit": 500, "with_payload": {"include": ["metadata.id"]}, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        res = qdrant("POST", f"/collections/{COLLECTION}/points/scroll", body)["result"]
        for p in res["points"]:
            cid = ((p.get("payload") or {}).get("metadata") or {}).get("id")
            if cid:
                ids.add(cid)
        offset = res.get("next_page_offset")
        if offset is None:
            return ids


def sync_qdrant(conservar_obsoletos):
    import ingest_ollama as ing
    ing.check_ollama()
    docs = {}
    for l in open(KB, encoding="utf-8"):
        d = json.loads(l); docs[d["id"]] = d
    existentes = qdrant_ids()
    nuevos = [docs[i] for i in docs if i not in existentes]
    obsoletos = sorted(existentes - set(docs))
    print(f"Qdrant: {len(existentes)} fragmentos | base: {len(docs)} | nuevos: {len(nuevos)} | obsoletos: {len(obsoletos)}")
    t0 = time.time()
    for i in range(0, len(nuevos), ing.BATCH):
        batch = nuevos[i:i + ing.BATCH]
        vectors = ing.embed_batch([d["content"] for d in batch])
        points = [{"id": str(uuid.uuid5(NAMESPACE, d["id"])), "vector": v, "payload": {"content": d["content"], "metadata": {**d["metadata"], "id": d["id"]}}}
                  for d, v in zip(batch, vectors)]
        qdrant("PUT", f"/collections/{COLLECTION}/points?wait=true", {"points": points})
        print(f"  insertados {min(i + ing.BATCH, len(nuevos))}/{len(nuevos)} · {time.time() - t0:4.0f}s", end="\r", flush=True)
    if nuevos:
        print()
    if obsoletos and not conservar_obsoletos:
        qdrant("POST", f"/collections/{COLLECTION}/points/delete?wait=true", {"points": [str(uuid.uuid5(NAMESPACE, cid)) for cid in obsoletos]})
        print(f"  eliminados {len(obsoletos)} fragmentos obsoletos")
    elif obsoletos:
        print(f"  {len(obsoletos)} fragmentos obsoletos conservados (--conservar-obsoletos)")
    resumen = {"nuevos": len(nuevos), "eliminados": 0 if conservar_obsoletos else len(obsoletos), "total": len(docs)}
    resumen["ejemplos_nuevos"] = [ (d["metadata"].get("titulo") or d["metadata"].get("documento", "")) + (" · " + d["metadata"]["articulo"] if d["metadata"].get("articulo") else "") for d in nuevos[:5]]
    return resumen


def run(args):
    st = load_state()
    if args.si_hace_falta and st.get("ultima_revision") and not args.forzar:
        ultima = parse_ts(st["ultima_revision"])
        transcurrido = now() - ultima
        if timedelta(0) <= transcurrido < timedelta(hours=args.horas):
            print(json.dumps({"accion": "omitido", "motivo": f"revisado hace {int(transcurrido.total_seconds() // 60)} min (< {args.horas:g} h)", "ultima_revision": st["ultima_revision"]}, ensure_ascii=False))
            return
    if os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) < 2 * 3600:
        print(json.dumps({"accion": "omitido", "motivo": "hay otra actualización en curso"}, ensure_ascii=False)); return
    open(LOCK, "w").write(str(os.getpid()))
    inicio = now()
    entrada = {"inicio": inicio.isoformat(), "forzado": args.forzar}
    try:
        import download_sources, extract_pdf_text, build_kb, qdrant_export
        print("== 1/4 Fuentes")
        cambios = download_sources.main(refresh=True)
        entrada["fuentes_cambiadas"] = cambios
        if any(c.endswith(".pdf") for c in cambios) or args.forzar:
            print("== 2/4 Texto de los reglamentos")
            entrada["textos"] = extract_pdf_text.main(force=False)
        if cambios or args.forzar or not os.path.exists(KB):
            print("== 3/4 Fragmentos")
            build_kb.main()
        else:
            print("== 3/4 Fragmentos: las fuentes no cambiaron, no se reconstruye")
        print("== 4/4 Sincronización con Qdrant")
        resumen = sync_qdrant(args.conservar_obsoletos)
        entrada.update(resumen)
        if resumen["nuevos"] or resumen["eliminados"]:
            qdrant_export.main()
            st["ultima_actualizacion"] = now().isoformat()
        st["ultima_revision"] = now().isoformat()
        st["ultimo_resultado"] = resumen
        st["fuentes_cambiadas"] = cambios
        save_state(st)
        entrada["fin"] = now().isoformat(); entrada["estado"] = "ok"
        log(entrada)
        print(json.dumps({"accion": "actualizado" if (resumen["nuevos"] or resumen["eliminados"]) else "sin_cambios", **resumen, "fuentes_cambiadas": cambios, "duracion_s": (now() - inicio).seconds}, ensure_ascii=False))
    except Exception as e:
        entrada["fin"] = now().isoformat(); entrada["estado"] = "error"; entrada["error"] = repr(e)
        log(entrada)
        st["ultima_revision"] = now().isoformat(); st["ultimo_error"] = repr(e); save_state(st)
        traceback.print_exc()
        print(json.dumps({"accion": "error", "error": repr(e)}, ensure_ascii=False))
        sys.exit(1)
    finally:
        if os.path.exists(LOCK):
            os.remove(LOCK)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--si-hace-falta", action="store_true", help="salir si ya se revisó hace menos de --horas")
    ap.add_argument("--horas", type=float, default=6)
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--conservar-obsoletos", action="store_true")
    ap.add_argument("--estado", action="store_true")
    a = ap.parse_args()
    if a.estado:
        print(json.dumps(load_state(), ensure_ascii=False, indent=2))
    else:
        run(a)
