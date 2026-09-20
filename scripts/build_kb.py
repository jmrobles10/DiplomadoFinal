"""
PitWall · Construcción de la base de conocimiento (F1 2026)

Convierte las fuentes crudas en fragmentos (chunks) con metadatos, listos para vectorizar:
  1. Reglamentos FIA 2026 (secciones A, B, C, D)  -> chunking POR ARTÍCULO (no por tamaño fijo)
  2. Temporada 2026 (API Jolpica/Ergast)           -> documentos en español: calendario, resultados, sprints,
                                                      clasificaciones, equipos y pilotos
  3. Narrativa de la temporada (Wikipedia, inglés) -> prosa limpia por sección
  4. Guías propias en español (kb/docs_es/*.md)     -> chunking por encabezado

Salidas en kb/processed/:
  chunks/reglamentos.jsonl, chunks/temporada.jsonl, chunks/narrativa.jsonl, chunks/guias.jsonl
  kb_all.jsonl        (todos los fragmentos: {id, content, metadata})
  kb_manifest.json    (conteos y tamaños por tipo)
  kb_preview.md       (muestra legible para revisión)
"""
import bisect
import glob
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")

ROOT = r"C:\Fuentes_Git\rag-f1-n8n"
TEXT_DIR = os.path.join(ROOT, "kb", "processed", "text")
JOLPICA = os.path.join(ROOT, "kb", "raw", "jolpica")
WIKI = os.path.join(ROOT, "kb", "raw", "wiki_sections.json")
DOCS_ES = os.path.join(ROOT, "kb", "docs_es")
OUT = os.path.join(ROOT, "kb", "processed")
CHUNKS = os.path.join(OUT, "chunks")
os.makedirs(CHUNKS, exist_ok=True)

HOY = date(2026, 9, 20)
MAX_CHARS = 2000   # tamaño objetivo máximo de un fragmento
MIN_CHARS = 250    # fragmentos más cortos se fusionan con el anterior del mismo artículo
# Grupos del reglamento técnico que son listas de materiales/componentes: ruido para un asistente de aficionados
EXCLUDE_GROUPS = {"C7", "C15", "C17", "C18"}
# Palabras con "ff" para reparar la ligadura mal extraída en la Sección C ("eaect" -> "effect")
FF_WORDS = set("""effect effects effective effectively effectiveness ineffective affect affected affects affecting
different differently difference differences differ differs differed differing differential differentials differentiate
differentiates differentiated difficult difficulty difficulties diffuse diffused diffusion diffuser diffusers sufficient
sufficiently insufficient insufficiently sufficiency efficiency efficient efficiently inefficiency inefficient coefficient
coefficients official officially officials office officer officers off offs offset offsets offsetting offside offshore
offload offloaded offline cutoff shutoff liftoff takeoff tradeoff runoff payoff stiff stiffer stiffest stiffness stiffly
staff staffing buffer buffers buffered buffering baffle baffles scaffold scaffolding tariff tariffs traffic effort efforts
affix affixed affirm affirmed affirmative affinity afford affordable offence offences offer offered offering offers suffer
suffered suffering suffix cliff bluff fluff scuff shuffle muffler puff cuff stuff coffee sheriff plaintiff effluent caffeine""".split())
WORD_RE = re.compile(r"[A-Za-z]+")


def build_vocab(texts):
    vocab = set(FF_WORDS)
    for t in texts:
        vocab.update(w.lower() for w in WORD_RE.findall(t))
    return vocab


def repair_ff(text, vocab, _cache={}):
    """Repara palabras desconocidas que, al sustituir una 'a' por 'ff', se vuelven una palabra conocida."""
    def fix(m):
        w = m.group(0); lw = w.lower()
        if lw in vocab or "a" not in lw:
            return w
        if lw not in _cache:
            rep = None
            for i, ch in enumerate(lw):
                if ch == "a":
                    cand = lw[:i] + "ff" + lw[i + 1:]
                    if cand in vocab:
                        rep = cand; break
            _cache[lw] = rep
        rep = _cache[lw]
        if rep is None:
            return w
        return rep.capitalize() if w[0].isupper() else rep
    return WORD_RE.sub(fix, text)

URLS = {
    "A": "https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_a_general_provisions_-_iss_03_-_2026-06-25.pdf",
    "B": "https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_b_sporting_-_iss_08_-_2026-08-05_7.pdf",
    "C": "https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_c_technical_-_iss_20_-_2026-08-05.pdf",
    "D": "https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_d_financial_-_f1_teams_-_iss_07_-_2026-06-25.pdf",
}


def make_id(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------------------
# 1. REGLAMENTOS FIA: limpieza y chunking por artículo
# --------------------------------------------------------------------------------------
LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl"}
HEADER_LINE_PATTERNS = [re.compile(p) for p in [
    r"^SECTION [A-D]:.*$",
    r"^[A-D]\d{1,3}\s*$",                                   # etiqueta de página sola (ej. B12)
    r"^[A-D]\d{1,3} 2026 Formula 1.*?Issue \d+\s*$",         # encabezado en una sola línea
    r"^2026 Formula 1.*$",
    r"^\u00a92026 F.d.ration.*$",
    r"^\d{1,2} (January|February|March|April|May|June|July|August|September|October|November|December) 2026\s*$",
    r"^Issue \d+\s*$",
    r"^0\s*$",
    r"^[A-D]\s*$",
    r"^Advisory Committee:.*$",
    r"^Governance:.*$",
]]
TOC_LINE = re.compile(r"\s\d{1,3}\s*$")


def clean_page(text: str) -> str:
    for k, v in LIGATURES.items():
        text = text.replace(k, v)
    text = re.sub(r"(?<=[A-Za-z])\u2018(?=[a-z])", "ff", text)      # ligadura "ff" mal decodificada
    text = text.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    # l\u00edneas de puntos de formularios ("Nombre: \u2026\u2026\u2026\u2026\u2026\u2026") y casillas: Gemini devuelve vectores vac\u00edos con ellas
    text = re.sub(r"[\u2026]{2,}|\.{4,}|_{4,}", " ___ ", text)
    text = re.sub(r"[\u2610\u2611\u2612\u25a1\u25a0]", " ", text)
    lines = []
    for line in text.split("\n"):
        line = line.rstrip()
        if not line.strip():
            continue
        if any(p.match(line.strip()) for p in HEADER_LINE_PATTERNS):
            continue
        # letra de sección pegada al inicio del cuerpo ("C ii. at Y = 50 ...")
        line = re.sub(r"^\s*([A-D]) (?=[a-z0-9(\"'])", "", line)
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def is_toc_page(text: str) -> bool:
    lines = [l for l in text.split("\n") if l.strip()]
    if len(lines) < 12:
        return False
    hits = sum(1 for l in lines if TOC_LINE.search(l))
    return hits / len(lines) > 0.35


def is_successor(prev, cand):
    """¿Es `cand` el siguiente número de artículo esperado tras `prev`? (numeración secuencial)"""
    if prev is None:
        return cand[0] == 1 and all(x == 1 for x in cand[1:])
    if cand[:-1] == prev and cand[-1] == 1:            # primer hijo: (1,8) -> (1,8,1)
        return True
    for depth in range(1, len(prev) + 1):               # hermano en cualquier nivel: (1,8,3) -> (1,9)
        if len(cand) == depth and cand[:depth - 1] == prev[:depth - 1] and cand[depth - 1] == prev[depth - 1] + 1:
            return True
    if cand[0] == prev[0] + 1 and all(x == 1 for x in cand[1:]):   # nuevo artículo nivel 1: (1,9,3) -> (2,1)
        return True
    return False


def chunk_regulation(pages_file: str, vocab):
    rows = [json.loads(l) for l in open(pages_file, encoding="utf-8")]
    meta0 = {k: rows[0][k] for k in ("seccion", "documento", "edicion", "fecha")}
    S = meta0["seccion"]
    cleaned = [(r["pagina"], repair_ff(clean_page(r["texto"]), vocab)) for r in rows]

    # saltar portada e índice: el cuerpo empieza en la primera página (no índice) con "ARTICLE S1:"
    first_art = re.compile(rf"ARTICLE {S}1:")
    start = None
    for i, (_, t) in enumerate(cleaned[:25]):
        if first_art.search(t) and not is_toc_page(t):
            start = i; break
    if start is None:
        toc_idx = [i for i, (_, t) in enumerate(cleaned[:20]) if is_toc_page(t)]
        start = (max(toc_idx) + 1) if toc_idx else 0
    body = cleaned[start:]

    # texto unido con offsets por página
    offsets, pages, buf = [], [], []
    pos = 0
    for pg, t in body:
        offsets.append(pos); pages.append(pg)
        buf.append(t); pos += len(t) + 1
    full = "\n".join(buf)

    def page_at(i):
        return pages[max(0, bisect.bisect_right(offsets, i) - 1)]

    token_re = re.compile(rf"(?<![A-Za-z0-9.]){S}(\d{{1,2}})(?:\.(\d{{1,2}}))?(?:\.(\d{{1,2}}))?(?:\.(\d{{1,2}}))?(?![\d.])(?=[\s:])")
    art_re = re.compile(rf"ARTICLE {S}(\d{{1,2}}):\s*([^\n]{{0,160}})")

    def art_title(raw):
        t = re.split(r"Advisory Committee|Governance:|\.\./\.\.|…/…|\s[A-D]\d{1,2}\.\d", raw)[0]
        m = re.match(r"[A-Z0-9 ,&'\-/()]+", t)
        return (m.group(0) if m else t).strip(" ,-")[:90]

    # candidatos: encabezados ARTICLE (anclas) y tokens numerados
    events = []
    for m in art_re.finditer(full):
        events.append((m.start(), "ART", (int(m.group(1)),), art_title(m.group(2)), m.end()))
    for m in token_re.finditer(full):
        tup = tuple(int(g) for g in m.groups() if g is not None)
        events.append((m.start(), "TOK", tup, None, m.end()))
    events.sort(key=lambda e: (e[0], 0 if e[1] == "ART" else 1))

    segments = []   # (tupla, titulo_nivel1, inicio, fin)
    prev = None
    art_titles = {}
    for pos_, kind, tup, title, end in events:
        if kind == "ART":
            art_titles[tup[0]] = title
            prev = tup
            segments.append((tup, pos_))
            continue
        if is_successor(prev, tup):
            prev = tup
            segments.append((tup, pos_))
    # cerrar segmentos
    segs = []
    for i, (tup, st) in enumerate(segments):
        en = segments[i + 1][1] if i + 1 < len(segments) else len(full)
        txt = full[st:en].strip()
        if txt:
            segs.append((tup, st, txt))

    # agrupar por artículo de nivel 2 (ej. B1.8) y cortar por tamaño en fronteras de sub-artículo
    chunks = []
    current = None   # dict con group, parts, start, page
    def flush():
        nonlocal current
        if not current or not current["parts"]:
            current = None; return
        parts = current["parts"]
        text = "\n".join(p[1] for p in parts)
        g = current["group"]
        art_label = f"{S}{'.'.join(map(str, g))}"
        art1 = art_titles.get(g[0], "")
        title = current["title"] or ""
        header = f"{meta0['documento']} · Artículo {art_label}"
        if title:
            header += f" {title}"
        if art1:
            header += f" (ARTICLE {S}{g[0]}: {art1})"
        subs = [f"{S}{'.'.join(map(str, p[0]))}" for p in parts]
        content = header + "\n" + text
        chunks.append({
            "id": make_id("reg", S, art_label, current["idx"]),
            "content": content,
            "metadata": {
                "tipo": "reglamento",
                "seccion": S,
                "documento": meta0["documento"],
                "edicion": meta0["edicion"],
                "fecha": meta0["fecha"],
                "url": URLS[S],
                "articulo_grupo": f"{S}{g[0]}",
                "titulo_grupo": art1,
                "articulo": art_label,
                "titulo_articulo": title,
                "sub_articulos": f"{subs[0]}–{subs[-1]}" if len(subs) > 1 else subs[0],
                "pagina": current["page"],
                "parte": current["idx"],
                "idioma": "en",
                "fuente": "FIA",
            },
        })
        current = None

    def title_of(tup, txt):
        # texto tras el número hasta el fin de la primera "frase" corta
        t = re.sub(rf"^{S}[\d.]+\s*", "", txt)
        t = t.split("\n")[0]
        t = re.split(r"(?<=[a-z\)])\.\s|:\s", t)[0]
        return t[:90].strip()

    for tup, st, txt in segs:
        if f"{S}{tup[0]}" in EXCLUDE_GROUPS:
            continue
        group = tup[:2] if len(tup) >= 2 else tup
        if current is None or current["group"] != group:
            flush()
            current = {"group": group, "parts": [], "page": page_at(st), "idx": 1,
                       "title": title_of(tup, txt) if len(tup) <= 2 else ""}
        elif len(tup) == 2 and not current["title"]:
            current["title"] = title_of(tup, txt)
        # cortar si excede el tamaño
        size = sum(len(p[1]) for p in current["parts"])
        if current["parts"] and size + len(txt) > MAX_CHARS:
            keep = dict(current)
            flush()
            current = {"group": group, "parts": [], "page": page_at(st), "idx": keep["idx"] + 1, "title": keep["title"]}
        # sub-artículo más largo que el tamaño objetivo: dividir por frases
        if len(txt) > MAX_CHARS:
            sentences = re.split(r"(?<=[.;])\s+(?=[A-Z(a-z])", txt)
            piece = ""
            for s_ in sentences:
                if piece and len(piece) + len(s_) > MAX_CHARS:
                    current["parts"].append((tup, piece.strip()))
                    keep = dict(current); flush()
                    current = {"group": group, "parts": [], "page": page_at(st), "idx": keep["idx"] + 1, "title": keep["title"]}
                    piece = ""
                piece += (" " if piece else "") + s_
            if piece:
                current["parts"].append((tup, piece.strip()))
        else:
            current["parts"].append((tup, txt))
    flush()

    # descartar fragmentos que son formularios (casi sin texto real: menos del 55 % de letras)
    def letters_ratio(t):
        body = t.split("\n", 1)[1] if "\n" in t else t
        return sum(ch.isalpha() for ch in body) / max(1, len(body))
    chunks = [c for c in chunks if letters_ratio(c["content"]) >= 0.55]

    # fusionar fragmentos muy cortos con el anterior del mismo artículo
    merged = []
    for c in chunks:
        if merged and len(c["content"]) < MIN_CHARS and merged[-1]["metadata"]["articulo"] == c["metadata"]["articulo"]:
            merged[-1]["content"] += "\n" + c["content"].split("\n", 1)[1]
            merged[-1]["metadata"]["sub_articulos"] = merged[-1]["metadata"]["sub_articulos"].split("–")[0] + "–" + c["metadata"]["sub_articulos"].split("–")[-1]
        else:
            merged.append(c)
    return merged, {"paginas_total": len(rows), "paginas_cuerpo": len(body), "segmentos": len(segs)}


# --------------------------------------------------------------------------------------
# 2. TEMPORADA 2026 (Jolpica / Ergast)
# --------------------------------------------------------------------------------------
GP_ES = {
    "Australian Grand Prix": "Gran Premio de Australia", "Chinese Grand Prix": "Gran Premio de China",
    "Japanese Grand Prix": "Gran Premio de Japón", "Miami Grand Prix": "Gran Premio de Miami",
    "Canadian Grand Prix": "Gran Premio de Canadá", "Monaco Grand Prix": "Gran Premio de Mónaco",
    "Barcelona Grand Prix": "Gran Premio de Barcelona-Cataluña", "Austrian Grand Prix": "Gran Premio de Austria",
    "British Grand Prix": "Gran Premio de Gran Bretaña", "Belgian Grand Prix": "Gran Premio de Bélgica",
    "Hungarian Grand Prix": "Gran Premio de Hungría", "Dutch Grand Prix": "Gran Premio de los Países Bajos",
    "Italian Grand Prix": "Gran Premio de Italia", "Spanish Grand Prix": "Gran Premio de España",
    "Azerbaijan Grand Prix": "Gran Premio de Azerbaiyán", "Bahrain Grand Prix in Malaysia": "Gran Premio de Baréin (disputado en Malasia)",
    "Singapore Grand Prix": "Gran Premio de Singapur", "United States Grand Prix": "Gran Premio de Estados Unidos",
    "Mexico City Grand Prix": "Gran Premio de la Ciudad de México", "Brazilian Grand Prix": "Gran Premio de Brasil",
    "Las Vegas Grand Prix": "Gran Premio de Las Vegas", "Qatar Grand Prix": "Gran Premio de Catar",
    "Abu Dhabi Grand Prix": "Gran Premio de Abu Dabi", "Saudi Arabian Grand Prix": "Gran Premio de Arabia Saudita",
}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_es(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} de {MESES[m-1]} de {y}"


def gp_es(name):
    return GP_ES.get(name, name)


def load_mr(name):
    return json.load(open(os.path.join(JOLPICA, name), encoding="utf-8"))["MRData"]


def season_docs():
    docs = []
    src = "Jolpica F1 API (datos oficiales de resultados, sucesora de Ergast)"
    base_meta = {"tipo": "temporada", "temporada": 2026, "idioma": "es", "fuente": src,
                 "url": "https://api.jolpi.ca/ergast/f1/2026.json", "fecha_consulta": HOY.isoformat()}

    # Calendario
    races = load_mr("schedule.json")["RaceTable"]["Races"]
    done = [r for r in races if r["date"] <= HOY.isoformat()]
    nxt = [r for r in races if r["date"] > HOY.isoformat()]
    lines = [f"Calendario del Campeonato Mundial de Fórmula 1 2026 ({len(races)} Grandes Premios). "
             f"Estado al {fecha_es(HOY.isoformat())}: {len(done)} rondas disputadas; "
             f"próxima carrera: {gp_es(nxt[0]['raceName'])} el {fecha_es(nxt[0]['date'])}." if nxt else ""]
    for r in races:
        c = r["Circuit"]; loc = c["Location"]
        sprint = " · fin de semana con Sprint" if "Sprint" in r else ""
        lines.append(f"Ronda {r['round']}: {gp_es(r['raceName'])} ({r['raceName']}), {fecha_es(r['date'])}, "
                     f"circuito {c['circuitName']}, {loc['locality']}, {loc['country']}{sprint}.")
    lines.append("Nota: el Gran Premio de Arabia Saudita fue cancelado y el Gran Premio de Baréin se disputa en Malasia (Sepang) en 2026.")
    docs.append({"id": make_id("cal", 2026), "content": "\n".join(lines),
                 "metadata": {**base_meta, "subtipo": "calendario", "titulo": "Calendario F1 2026"}})

    # Resultados por carrera
    results_races = []
    for f in sorted(glob.glob(os.path.join(JOLPICA, "results_*.json"))):
        results_races += load_mr(os.path.basename(f))["RaceTable"]["Races"]
    by_round = defaultdict(list)
    race_info = {}
    for r in results_races:
        by_round[int(r["round"])] += r["Results"]; race_info[int(r["round"])] = r
    sprints = {int(r["round"]): r for r in load_mr("sprint.json")["RaceTable"]["Races"]}

    lineups = defaultdict(lambda: defaultdict(set))   # constructor -> driver -> rounds
    wins = Counter(); podiums = Counter(); poles = Counter()
    for rnd in sorted(by_round):
        r = race_info[rnd]; res = sorted(by_round[rnd], key=lambda x: int(x["position"]))
        c = r["Circuit"]; loc = c["Location"]
        head = (f"Resultados del {gp_es(r['raceName'])} 2026 (ronda {rnd} de {len(races)}), disputado el {fecha_es(r['date'])} "
                f"en {c['circuitName']} ({loc['locality']}, {loc['country']}).")
        body = []
        for x in res:
            d = x["Driver"]; name = f"{d['givenName']} {d['familyName']}"; team = x["Constructor"]["name"]
            lineups[team][name].add(rnd)
            pos = int(x["position"]); status = x["status"]
            finished = status == "Finished" or status.startswith("+")
            t = x.get("Time", {}).get("time")
            extra = f", tiempo {t}" if t else (f", {status}" if not finished else "")
            fl = x.get("FastestLap", {})
            flt = f", vuelta rápida de la carrera ({fl['Time']['time']})" if fl.get("rank") == "1" and fl.get("Time") else ""
            grid = x.get("grid", "?")
            pts = x.get("points", "0")
            body.append(f"{pos}. {name} ({team}) — salió {('desde la pole' if grid == '1' else 'en la posición ' + grid + ' de la parrilla')}, "
                        f"{x.get('laps', '?')} vueltas{extra}, {pts} puntos{flt}.")
            if pos == 1: wins[name] += 1
            if pos <= 3: podiums[name] += 1
            if grid == "1": poles[name] += 1
        retired = [f"{x['Driver']['givenName']} {x['Driver']['familyName']} ({x['status']})" for x in res
                   if not (x["status"] == "Finished" or x["status"].startswith("+"))]
        if retired:
            body.append("No clasificados o retirados: " + "; ".join(retired) + ".")
        content = head + "\n" + "\n".join(body)
        docs.append({"id": make_id("res", rnd), "content": content,
                     "metadata": {**base_meta, "subtipo": "resultado_carrera", "ronda": rnd, "gran_premio": gp_es(r["raceName"]),
                                  "titulo": f"Resultados {gp_es(r['raceName'])} 2026", "fecha_evento": r["date"]}})
        # Sprint
        if rnd in sprints:
            sr = sorted(sprints[rnd]["SprintResults"], key=lambda x: int(x["position"]))
            sl = [f"Resultados de la carrera Sprint del {gp_es(r['raceName'])} 2026 (ronda {rnd}), fin de semana del {fecha_es(r['date'])}:"]
            for x in sr[:12]:
                d = x["Driver"]
                sl.append(f"{x['position']}. {d['givenName']} {d['familyName']} ({x['Constructor']['name']}), {x.get('points', '0')} puntos"
                          + (f", {x['status']}" if x["status"] not in ("Finished",) and not x["status"].startswith("+") else "") + ".")
            docs.append({"id": make_id("sprint", rnd), "content": "\n".join(sl),
                         "metadata": {**base_meta, "subtipo": "resultado_sprint", "ronda": rnd, "gran_premio": gp_es(r["raceName"]),
                                      "titulo": f"Sprint {gp_es(r['raceName'])} 2026", "fecha_evento": r["date"]}})

    # Clasificaciones
    ds = load_mr("driverStandings.json")["StandingsTable"]["StandingsLists"][0]
    cs = load_mr("constructorStandings.json")["StandingsTable"]["StandingsLists"][0]
    last_round = int(ds["round"])
    last_gp = gp_es(race_info[last_round]["raceName"]) if last_round in race_info else f"ronda {last_round}"
    dl = [f"Clasificación del Campeonato Mundial de Pilotos de Fórmula 1 2026 tras {last_round} rondas "
          f"(última: {last_gp}, {fecha_es(race_info[last_round]['date'])}). Quedan {len(races) - last_round} carreras."]
    for d in ds["DriverStandings"]:
        dr = d["Driver"]; name = f"{dr['givenName']} {dr['familyName']}"
        dl.append(f"{d['position']}. {name} ({', '.join(c_['name'] for c_ in d['Constructors'])}) — {d['points']} puntos, "
                  f"{d['wins']} victorias, {podiums.get(name, 0)} podios, {poles.get(name, 0)} poles.")
    leader = ds["DriverStandings"][0]; second = ds["DriverStandings"][1]
    dl.append(f"Líder del campeonato: {leader['Driver']['givenName']} {leader['Driver']['familyName']} con {leader['points']} puntos, "
              f"{float(leader['points']) - float(second['points']):g} puntos de ventaja sobre {second['Driver']['givenName']} {second['Driver']['familyName']}.")
    docs.append({"id": make_id("wdc", last_round), "content": "\n".join(dl),
                 "metadata": {**base_meta, "subtipo": "clasificacion_pilotos", "ronda": last_round, "titulo": f"Clasificación de pilotos tras ronda {last_round}"}})
    cl = [f"Clasificación del Campeonato Mundial de Constructores de Fórmula 1 2026 tras {last_round} rondas (última: {last_gp}):"]
    for c_ in cs["ConstructorStandings"]:
        cl.append(f"{c_['position']}. {c_['Constructor']['name']} ({c_['Constructor']['nationality']}) — {c_['points']} puntos, {c_['wins']} victorias.")
    docs.append({"id": make_id("wcc", last_round), "content": "\n".join(cl),
                 "metadata": {**base_meta, "subtipo": "clasificacion_constructores", "ronda": last_round, "titulo": f"Clasificación de constructores tras ronda {last_round}"}})

    # Equipos y pilotos (derivado de participaciones reales)
    drivers = {f"{d['givenName']} {d['familyName']}": d for d in load_mr("drivers.json")["DriverTable"]["Drivers"]}
    el = [f"Equipos y pilotos de la temporada 2026 de Fórmula 1 (11 equipos, 22 autos). Alineaciones según participación real en las {last_round} rondas disputadas hasta el {fecha_es(HOY.isoformat())}:"]
    for team in sorted(lineups):
        parts = []
        for name, rounds in sorted(lineups[team].items(), key=lambda kv: -len(kv[1])):
            d = drivers.get(name, {})
            extra = f"{d.get('nationality', '')}, dorsal {d.get('permanentNumber', '?')}, nacido el {fecha_es(d['dateOfBirth']) if d.get('dateOfBirth') else '?'}"
            rr = f"rondas {min(rounds)}–{max(rounds)}" if len(rounds) == last_round else f"{len(rounds)} rondas: {', '.join(map(str, sorted(rounds)))}"
            parts.append(f"{name} ({extra}; {rr})")
        el.append(f"{team}: " + "; ".join(parts) + ".")
    el.append("Cadillac F1 Team es el equipo debutante de 2026 (undécimo equipo). Audi compite como equipo de fábrica tras absorber a Sauber.")
    docs.append({"id": make_id("teams", 2026), "content": "\n".join(el),
                 "metadata": {**base_meta, "subtipo": "equipos_pilotos", "titulo": "Equipos y pilotos F1 2026"}})

    # Ganadores resumen
    wl = [f"Resumen de ganadores de Grandes Premios de la temporada 2026 tras {last_round} rondas:"]
    for rnd in sorted(by_round):
        r = race_info[rnd]; win = [x for x in by_round[rnd] if x["position"] == "1"][0]
        wl.append(f"Ronda {rnd}, {gp_es(r['raceName'])} ({fecha_es(r['date'])}): ganó {win['Driver']['givenName']} {win['Driver']['familyName']} ({win['Constructor']['name']}).")
    wl.append("Victorias por piloto: " + "; ".join(f"{n}: {w}" for n, w in wins.most_common()) + ".")
    docs.append({"id": make_id("winners", last_round), "content": "\n".join(wl),
                 "metadata": {**base_meta, "subtipo": "ganadores", "ronda": last_round, "titulo": "Ganadores 2026"}})
    return docs


# --------------------------------------------------------------------------------------
# 3. NARRATIVA (Wikipedia)
# --------------------------------------------------------------------------------------
def strip_templates(s):
    out = []; depth = 0; i = 0
    while i < len(s):
        if s.startswith("{{", i):
            depth += 1; i += 2; continue
        if s.startswith("}}", i) and depth > 0:
            depth -= 1; i += 2; continue
        if depth == 0:
            out.append(s[i])
        i += 1
    return "".join(out)


def clean_wiki(s):
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = strip_templates(s)
    s = re.sub(r"\{\|.*?\|\}", "", s, flags=re.S)
    s = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", s)
    s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", s)
    s = re.sub(r"'{2,}", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"^\s*[*#:;]+\s*", "- ", s, flags=re.M)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


WIKI_SECTIONS_ES = {
    "Team changes": "Cambios de equipos", "Driver changes": "Cambios de pilotos", "Mid-season changes": "Cambios a mitad de temporada",
    "Calendar changes": "Cambios en el calendario", "Postponed and cancelled Grands Prix": "Grandes Premios aplazados y cancelados",
    "Pre-season": "Pretemporada", "Opening rounds": "Primeras rondas", "Mid-season rounds": "Rondas de mitad de temporada",
    "Power units": "Unidades de potencia 2026", "Car size and aerodynamics": "Tamaño del auto y aerodinámica 2026",
    "Safety features": "Seguridad 2026", "Sporting regulations": "Cambios deportivos 2026", "Financial regulation": "Reglamento financiero 2026",
    "Scoring system": "Sistema de puntuación 2026", "Free practice drivers": "Pilotos de prácticas libres",
}


def wiki_docs():
    if not os.path.exists(WIKI):
        return []
    sections = json.load(open(WIKI, encoding="utf-8"))
    docs = []
    for name, es in WIKI_SECTIONS_ES.items():
        raw = sections.get(name, "")
        txt = clean_wiki(raw)
        if len(txt) < 80:
            continue
        paras = [p.strip() for p in re.split(r"\n\s*\n", txt) if p.strip()]
        piece, idx = "", 1
        def emit(piece, idx):
            docs.append({"id": make_id("wiki", name, idx),
                         "content": f"Temporada 2026 de Fórmula 1 — {es} ({name}), fuente Wikipedia en inglés:\n{piece}",
                         "metadata": {"tipo": "temporada_narrativa", "temporada": 2026, "idioma": "en", "seccion_wiki": name,
                                      "titulo": es, "parte": idx, "fuente": "Wikipedia: 2026 Formula One World Championship",
                                      "url": "https://en.wikipedia.org/wiki/2026_Formula_One_World_Championship",
                                      "fecha_consulta": HOY.isoformat()}})
        for p in paras:
            if piece and len(piece) + len(p) > 1800:
                emit(piece, idx); idx += 1; piece = ""
            piece += ("\n\n" if piece else "") + p
        if piece:
            emit(piece, idx)
    return docs


# --------------------------------------------------------------------------------------
# 4. GUÍAS PROPIAS EN ESPAÑOL (kb/docs_es/*.md)
# --------------------------------------------------------------------------------------
def guide_docs():
    docs = []
    for path in sorted(glob.glob(os.path.join(DOCS_ES, "*.md"))):
        md = open(path, encoding="utf-8").read()
        title = re.search(r"^#\s+(.+)$", md, re.M)
        title = title.group(1).strip() if title else os.path.basename(path)
        meta_src = re.search(r"^>\s*Fuentes?:\s*(.+)$", md, re.M)
        parts = re.split(r"^##\s+", md, flags=re.M)
        intro = parts[0]
        sections = [("Introducción", intro)] + [(p.split("\n", 1)[0].strip(), p.split("\n", 1)[1] if "\n" in p else "") for p in parts[1:]]
        idx = 0
        for sec_title, body in sections:
            body = re.sub(r"^#\s+.+$", "", body, flags=re.M).strip()
            if len(body) < 60:
                continue
            paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
            piece = ""
            def emit(piece):
                nonlocal idx
                idx += 1
                docs.append({"id": make_id("guia", os.path.basename(path), idx),
                             "content": f"{title} — {sec_title}\n{piece}",
                             "metadata": {"tipo": "guia", "idioma": "es", "titulo": title, "seccion": sec_title, "parte": idx,
                                          "archivo": os.path.basename(path),
                                          "fuente": (meta_src.group(1).strip() if meta_src else "Guía propia redactada para PitWall")}})
            for p in paras:
                if piece and len(piece) + len(p) > 1600:
                    emit(piece); piece = ""
                piece += ("\n\n" if piece else "") + p
            if piece:
                emit(piece)
    return docs


# --------------------------------------------------------------------------------------
def write_jsonl(path, docs):
    with open(path, "w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")


def main():
    manifest = {"generado": HOY.isoformat(), "tipos": {}}
    all_docs = []

    # vocabulario de referencia (secciones A, B y D, que extraen bien) para reparar la ligadura "ff" de la C
    ref_texts = []
    for f in sorted(glob.glob(os.path.join(TEXT_DIR, "*.pages.jsonl"))):
        if "_C_" in os.path.basename(f):
            continue
        ref_texts += [clean_page(json.loads(l)["texto"]) for l in open(f, encoding="utf-8")]
    vocab = build_vocab(ref_texts)

    reg_docs = []
    for f in sorted(glob.glob(os.path.join(TEXT_DIR, "*.pages.jsonl"))):
        docs, info = chunk_regulation(f, vocab)
        reg_docs += docs
        sizes = [len(d["content"]) for d in docs]
        print(f"[reglamento] {os.path.basename(f)}: {len(docs)} fragmentos | páginas cuerpo {info['paginas_cuerpo']}/{info['paginas_total']} | "
              f"segmentos {info['segmentos']} | chars prom {sum(sizes)//max(1,len(sizes))} máx {max(sizes) if sizes else 0}")
    write_jsonl(os.path.join(CHUNKS, "reglamentos.jsonl"), reg_docs); all_docs += reg_docs

    t_docs = season_docs()
    write_jsonl(os.path.join(CHUNKS, "temporada.jsonl"), t_docs); all_docs += t_docs
    print(f"[temporada] {len(t_docs)} documentos")

    w_docs = wiki_docs()
    write_jsonl(os.path.join(CHUNKS, "narrativa.jsonl"), w_docs); all_docs += w_docs
    print(f"[narrativa] {len(w_docs)} fragmentos")

    g_docs = guide_docs()
    write_jsonl(os.path.join(CHUNKS, "guias.jsonl"), g_docs); all_docs += g_docs
    print(f"[guias] {len(g_docs)} fragmentos")

    write_jsonl(os.path.join(OUT, "kb_all.jsonl"), all_docs)
    for tipo, group in defaultdict(list, {t: [d for d in all_docs if d["metadata"]["tipo"] == t] for t in {d["metadata"]["tipo"] for d in all_docs}}).items():
        sizes = [len(d["content"]) for d in group]
        manifest["tipos"][tipo] = {"fragmentos": len(group), "chars_total": sum(sizes), "chars_promedio": sum(sizes) // max(1, len(sizes)), "chars_max": max(sizes)}
    manifest["total_fragmentos"] = len(all_docs)
    manifest["chars_total"] = sum(len(d["content"]) for d in all_docs)
    json.dump(manifest, open(os.path.join(OUT, "kb_manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # vista previa legible
    with open(os.path.join(OUT, "kb_preview.md"), "w", encoding="utf-8") as fh:
        fh.write("# Vista previa de la base de conocimiento PitWall\n\n")
        fh.write("```json\n" + json.dumps(manifest, ensure_ascii=False, indent=2) + "\n```\n\n")
        shown = Counter()
        for d in all_docs:
            key = d["metadata"]["tipo"] + ":" + d["metadata"].get("seccion", d["metadata"].get("subtipo", ""))
            if shown[key] >= 2:
                continue
            shown[key] += 1
            fh.write(f"## {key} · {d['id']}\n\n```json\n{json.dumps(d['metadata'], ensure_ascii=False, indent=1)}\n```\n\n{d['content'][:1500]}\n\n---\n\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
