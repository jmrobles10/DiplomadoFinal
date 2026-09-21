"""
PitWall · Extrae el texto de cada página de los reglamentos FIA a JSONL (una línea por página).

Uso: python scripts/extract_pdf_text.py           # solo los PDF nuevos o cambiados
     python scripts/extract_pdf_text.py --force   # todos

Lee la lista de ediciones vigentes de kb/raw/fia_sources.json (la escribe download_sources.py). Los textos de
ediciones que ya no están vigentes se eliminan de kb/processed/text para que build_kb.py no mezcle versiones.
"""
import glob
import json
import logging
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
logging.getLogger("pypdf").setLevel(logging.ERROR)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "kb", "raw")
OUT = os.path.join(ROOT, "kb", "processed", "text")
ART = re.compile(r"^(?:ARTICLE\s+)?([A-D]\d{1,2}(?:\.\d{1,2}){0,3})\b", re.M)


def load_docs():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from download_sources import load_manifest
    return load_manifest()


def main(force=False):
    from pypdf import PdfReader
    os.makedirs(OUT, exist_ok=True)
    docs = load_docs()
    vigentes = {fname.replace(".pdf", ".pages.jsonl") for fname in docs}
    cambios = []
    for old in glob.glob(os.path.join(OUT, "*.pages.jsonl")):
        if os.path.basename(old) not in vigentes:
            os.remove(old); cambios.append("eliminado " + os.path.basename(old))
            print("edición reemplazada, texto eliminado:", os.path.basename(old))
    for fname, meta in docs.items():
        pdf = os.path.join(RAW, fname)
        out = os.path.join(OUT, fname.replace(".pdf", ".pages.jsonl"))
        if os.path.exists(out) and not force and (not os.path.exists(pdf) or os.path.getmtime(out) >= os.path.getmtime(pdf)):
            print(f"{fname}: texto ya extraído"); continue
        if not os.path.exists(pdf):
            print(f"{fname}: falta el PDF y no hay texto extraído; ejecuta download_sources.py"); continue
        r = PdfReader(pdf)
        n_chars = 0; heads = []
        meta_pages = {k: meta[k] for k in ("seccion", "documento", "edicion", "fecha")}
        with open(out, "w", encoding="utf-8") as fh:
            for i, p in enumerate(r.pages):
                t = p.extract_text() or ""
                n_chars += len(t)
                heads += [m.group(1) for m in ART.finditer(t)]
                fh.write(json.dumps({"pagina": i + 1, "texto": t, **meta_pages}, ensure_ascii=False) + "\n")
        cambios.append(os.path.basename(out))
        print(f"{fname}: {len(r.pages)} páginas, {n_chars:,} chars, {len(heads)} encabezados tipo artículo -> {out}")
    return cambios


if __name__ == "__main__":
    main(force="--force" in sys.argv)
