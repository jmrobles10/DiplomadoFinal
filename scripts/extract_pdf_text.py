"""Extrae el texto de cada página de los reglamentos FIA a JSONL (una línea por página)."""
import sys, os, json, re, logging
from pypdf import PdfReader
sys.stdout.reconfigure(encoding="utf-8")
logging.getLogger("pypdf").setLevel(logging.ERROR)

RAW = r"C:\Fuentes_Git\rag-f1-n8n\kb\raw"
OUT = r"C:\Fuentes_Git\rag-f1-n8n\kb\processed\text"
DOCS = {
    "fia_2026_A_general_iss03.pdf":  dict(seccion="A", documento="Reglamento General 2026 (Sección A)", edicion="Issue 03", fecha="2026-06-25"),
    "fia_2026_B_sporting_iss08.pdf": dict(seccion="B", documento="Reglamento Deportivo 2026 (Sección B)", edicion="Issue 08", fecha="2026-08-05"),
    "fia_2026_C_technical_iss20.pdf": dict(seccion="C", documento="Reglamento Técnico 2026 (Sección C)", edicion="Issue 20", fecha="2026-08-05"),
    "fia_2026_D_financial_iss07.pdf": dict(seccion="D", documento="Reglamento Financiero 2026 (Sección D)", edicion="Issue 07", fecha="2026-06-25"),
}
ART = re.compile(r"^(?:ARTICLE\s+)?([A-D]\d{1,2}(?:\.\d{1,2}){0,3})\b", re.M)
for fname, meta in DOCS.items():
    r = PdfReader(os.path.join(RAW, fname))
    out = os.path.join(OUT, fname.replace(".pdf", ".pages.jsonl"))
    n_chars = 0; heads = []
    with open(out, "w", encoding="utf-8") as fh:
        for i, p in enumerate(r.pages):
            t = p.extract_text() or ""
            n_chars += len(t)
            heads += [m.group(1) for m in ART.finditer(t)]
            fh.write(json.dumps({"pagina": i + 1, "texto": t, **meta}, ensure_ascii=False) + "\n")
    print(f"{fname}: {len(r.pages)} páginas, {n_chars:,} chars, {len(heads)} encabezados tipo artículo -> {out}")
    print("   ejemplos:", heads[:12], "...", heads[-6:])
