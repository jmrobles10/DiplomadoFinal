"""
PitWall · Descarga las fuentes crudas de la base de conocimiento (no se versionan en git por tamaño).

Uso: python scripts/download_sources.py
Descarga a kb/raw/:
  - Reglamentos FIA 2026 vigentes (secciones A, B, C y D) en PDF
  - Wikitext de Wikipedia "2026 Formula One World Championship"
  - Datos de la temporada 2026 desde la API Jolpica (sucesora de Ergast): calendario, pilotos, constructores,
    resultados, sprints y clasificaciones
Luego ejecuta:  python scripts/extract_pdf_text.py  y  python scripts/build_kb.py
"""
import json
import os
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kb", "raw")
UA = {"User-Agent": "PitWall-RAG-F1/1.0 (proyecto academico; https://github.com)"}

PDFS = {
    "fia_2026_A_general_iss03.pdf": "https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_a_general_provisions_-_iss_03_-_2026-06-25.pdf",
    "fia_2026_B_sporting_iss08.pdf": "https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_b_sporting_-_iss_08_-_2026-08-05_7.pdf",
    "fia_2026_C_technical_iss20.pdf": "https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_c_technical_-_iss_20_-_2026-08-05.pdf",
    "fia_2026_D_financial_iss07.pdf": "https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_d_financial_-_f1_teams_-_iss_07_-_2026-06-25.pdf",
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


def fetch(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print("  ya existe:", os.path.basename(dest)); return
    data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180).read()
    with open(dest, "wb") as fh:
        fh.write(data)
    print(f"  {os.path.basename(dest)}: {len(data)/1e6:.1f} MB")


def main():
    os.makedirs(os.path.join(RAW, "jolpica"), exist_ok=True)
    print("Reglamentos FIA 2026:")
    for name, url in PDFS.items():
        fetch(url, os.path.join(RAW, name))
    print("Wikipedia:")
    fetch(WIKI, os.path.join(RAW, "wiki_2026_season.json"))
    print("Jolpica (temporada 2026):")
    for name, path in JOLPICA_FILES.items():
        fetch(JOLPICA + path, os.path.join(RAW, "jolpica", name)); time.sleep(1)
    # separar secciones del wikitext (lo usa build_kb.py)
    import re
    wt = json.load(open(os.path.join(RAW, "wiki_2026_season.json"), encoding="utf-8"))["parse"]["wikitext"]
    parts = re.split(r"^(==+)\s*(.+?)\s*\1\s*$", wt, flags=re.M)
    sections = {parts[i + 1]: parts[i + 2] for i in range(1, len(parts), 3)}
    json.dump(sections, open(os.path.join(RAW, "wiki_sections.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("Listo. Ahora: python scripts/extract_pdf_text.py && python scripts/build_kb.py")


if __name__ == "__main__":
    main()
