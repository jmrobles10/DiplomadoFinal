"""
PitWall · Descarga (y refresca) las fuentes crudas de la base de conocimiento.

Uso: python scripts/download_sources.py            # descarga lo que falte (primera instalación)
     python scripts/download_sources.py --refresh  # vuelve a consultar todo y reemplaza solo lo que cambió

Fuentes, en kb/raw/:
  - Reglamentos FIA 2026 (secciones A, B, C y D). La edición vigente se descubre en la página oficial de
    reglamentos de la FIA (https://www.fia.com/regulation/category/110): si la FIA publica un Issue nuevo, se
    descarga y se anota en kb/raw/fia_sources.json (que leen extract_pdf_text.py y build_kb.py).
  - Wikitext de Wikipedia "2026 Formula One World Championship".
  - Datos de la temporada 2026 desde la API Jolpica (sucesora de Ergast): calendario, pilotos, constructores,
    resultados, sprints y clasificaciones.
Devuelve (y imprime) la lista de archivos que cambiaron, para que scripts/actualizar_kb.py sepa qué reconstruir.
Luego: python scripts/extract_pdf_text.py && python scripts/build_kb.py
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "kb", "raw")
TEXT_DIR = os.path.join(ROOT, "kb", "processed", "text")
FIA_MANIFEST = os.path.join(RAW, "fia_sources.json")
UA = {"User-Agent": "PitWall-RAG-F1/1.0 (proyecto academico; https://github.com)"}

FIA_PAGE = "https://www.fia.com/regulation/category/110"
FIA_BASE = "https://www.fia.com"
# href de cada PDF: .../fia_2026_f1_regulations_-_section_b_sporting_-_iss_08_-_2026-08-05_7.pdf
FIA_HREF = re.compile(r'href="(/system/files/documents/fia_2026_f1_regulations_-_section_([a-d])_[^"]*?iss_(\d+)_-_(\d{4}-\d{2}-\d{2})[^"]*?\.pdf)"')
SECCIONES = {
    "A": dict(slug="general", documento="Reglamento General 2026 (Sección A)"),
    "B": dict(slug="sporting", documento="Reglamento Deportivo 2026 (Sección B)"),
    "C": dict(slug="technical", documento="Reglamento Técnico 2026 (Sección C)"),
    "D": dict(slug="financial", documento="Reglamento Financiero 2026 (Sección D)"),
}
# Ediciones con las que se construyó la base originalmente (respaldo si la página de la FIA no responde)
FIA_DEFAULT = {
    "fia_2026_A_general_iss03.pdf": dict(url="https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_a_general_provisions_-_iss_03_-_2026-06-25.pdf", seccion="A", documento="Reglamento General 2026 (Sección A)", edicion="Issue 03", fecha="2026-06-25"),
    "fia_2026_B_sporting_iss08.pdf": dict(url="https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_b_sporting_-_iss_08_-_2026-08-05_7.pdf", seccion="B", documento="Reglamento Deportivo 2026 (Sección B)", edicion="Issue 08", fecha="2026-08-05"),
    "fia_2026_C_technical_iss20.pdf": dict(url="https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_c_technical_-_iss_20_-_2026-08-05.pdf", seccion="C", documento="Reglamento Técnico 2026 (Sección C)", edicion="Issue 20", fecha="2026-08-05"),
    "fia_2026_D_financial_iss07.pdf": dict(url="https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_d_financial_-_f1_teams_-_iss_07_-_2026-06-25.pdf", seccion="D", documento="Reglamento Financiero 2026 (Sección D)", edicion="Issue 07", fecha="2026-06-25"),
}

WIKI = "https://en.wikipedia.org/w/api.php?action=parse&page=2026_Formula_One_World_Championship&prop=wikitext&format=json&formatversion=2"
JOLPICA = "https://api.jolpi.ca/ergast/f1"
JOLPICA_FILES = {
    "schedule.json": "/2026.json?limit=100",
    "drivers.json": "/2026/drivers.json?limit=100",
    "constructors.json": "/2026/constructors.json?limit=100",
    "driverStandings.json": "/2026/driverStandings.json?limit=100",
    "constructorStandings.json": "/2026/constructorStandings.json?limit=100",
    "results_0.json": "/2026/results.json?limit=100&offset=0",
    "results_100.json": "/2026/results.json?limit=100&offset=100",
    "results_200.json": "/2026/results.json?limit=100&offset=200",
    "results_300.json": "/2026/results.json?limit=100&offset=300",
    "results_400.json": "/2026/results.json?limit=100&offset=400",
    "results_500.json": "/2026/results.json?limit=100&offset=500",
    "sprint.json": "/2026/sprint.json?limit=100",
}


def get(url, timeout=180):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def fetch(url, dest, refresh, cambios):
    """Descarga a dest. Sin refresh: solo si falta. Con refresh: descarga y reemplaza solo si el contenido cambió."""
    name = os.path.relpath(dest, RAW)
    if os.path.exists(dest) and os.path.getsize(dest) > 0 and not refresh:
        print("  ya existe:", name); return False
    try:
        data = get(url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"  {name}: no se pudo descargar ({e}); se conserva la versión local"); return False
    if os.path.exists(dest):
        with open(dest, "rb") as fh:
            if fh.read() == data:
                print("  sin cambios:", name); return False
    with open(dest, "wb") as fh:
        fh.write(data)
    print(f"  {'actualizado' if refresh else 'descargado'}: {name} ({len(data)/1e6:.1f} MB)")
    cambios.append(name)
    return True


def load_manifest():
    try:
        return json.load(open(FIA_MANIFEST, encoding="utf-8"))
    except Exception:
        return dict(FIA_DEFAULT)


def discover_fia():
    """Lee la página oficial y devuelve la edición más reciente de cada sección A-D."""
    html = get(FIA_PAGE, timeout=60).decode("utf-8", "ignore")
    latest = {}
    for href, sec, iss, fecha in FIA_HREF.findall(html):
        sec = sec.upper(); iss = int(iss)
        if sec in SECCIONES and (sec not in latest or iss > latest[sec]["iss"]):
            latest[sec] = dict(iss=iss, url=FIA_BASE + href, fecha=fecha)
    return latest


def refresh_fia(refresh, cambios):
    manifest = load_manifest()
    by_sec = {m["seccion"]: (fname, m) for fname, m in manifest.items()}
    try:
        latest = discover_fia()
        print(f"  página FIA leída: ediciones vigentes " + ", ".join(f"{s} Issue {v['iss']:02d}" for s, v in sorted(latest.items())))
    except Exception as e:
        print(f"  no se pudo leer la página de la FIA ({e}); se usan las ediciones conocidas")
        latest = {}
    nuevo = {}
    for sec, info in SECCIONES.items():
        fname_act, meta_act = by_sec.get(sec, (None, None))
        iss_act = int(meta_act["edicion"].split()[-1]) if meta_act else -1
        cand = latest.get(sec)
        if cand and cand["iss"] > iss_act:
            fname = f"fia_2026_{sec}_{info['slug']}_iss{cand['iss']:02d}.pdf"
            meta = dict(url=cand["url"], seccion=sec, documento=info["documento"], edicion=f"Issue {cand['iss']:02d}", fecha=cand["fecha"])
            print(f"  NUEVA EDICIÓN sección {sec}: Issue {iss_act:02d} -> Issue {cand['iss']:02d} ({cand['fecha']})")
            if fetch(meta["url"], os.path.join(RAW, fname), True, cambios):
                nuevo[fname] = meta
                continue
            # si falló la descarga se conserva la edición anterior
        if fname_act:
            nuevo[fname_act] = meta_act
            pages = os.path.join(TEXT_DIR, fname_act.replace(".pdf", ".pages.jsonl"))
            if not os.path.exists(pages):          # instalación nueva: hace falta el PDF para extraer el texto
                fetch(meta_act["url"], os.path.join(RAW, fname_act), False, cambios)
            else:
                print(f"  sección {sec}: {meta_act['edicion']} vigente, texto ya extraído")
    if nuevo != manifest or not os.path.exists(FIA_MANIFEST):
        json.dump(nuevo, open(FIA_MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return nuevo


def split_wiki(cambios):
    src = os.path.join(RAW, "wiki_2026_season.json")
    dst = os.path.join(RAW, "wiki_sections.json")
    if not os.path.exists(src):
        return
    wt = json.load(open(src, encoding="utf-8"))["parse"]["wikitext"]
    parts = re.split(r"^(==+)\s*(.+?)\s*\1\s*$", wt, flags=re.M)
    sections = {parts[i + 1]: parts[i + 2] for i in range(1, len(parts), 3)}
    data = json.dumps(sections, ensure_ascii=False, indent=1)
    if os.path.exists(dst) and open(dst, encoding="utf-8").read() == data:
        return
    open(dst, "w", encoding="utf-8").write(data)
    if "wiki_sections.json" not in cambios:
        cambios.append("wiki_sections.json")


def main(refresh=False):
    os.makedirs(os.path.join(RAW, "jolpica"), exist_ok=True)
    cambios = []
    print("Reglamentos FIA 2026:")
    refresh_fia(refresh, cambios)
    print("Wikipedia:")
    fetch(WIKI, os.path.join(RAW, "wiki_2026_season.json"), refresh, cambios)
    split_wiki(cambios)
    print("Jolpica (temporada 2026):")
    for name, path in JOLPICA_FILES.items():
        fetch(JOLPICA + path, os.path.join(RAW, "jolpica", name), refresh, cambios); time.sleep(0.5)
    print("Cambios:", cambios if cambios else "ninguno")
    return cambios


if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
