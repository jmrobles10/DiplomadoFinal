"""
Palmarés · Base de conocimiento de logros históricos por piloto (separada de la de PitWall).

Uso:
  python scripts/build_kb_pilotos.py              # descarga lo que falte, construye kb/processed/kb_pilotos.jsonl
  python scripts/build_kb_pilotos.py --refresh    # además vuelve a bajar la lista de récords de Wikipedia
Luego:
  python scripts/qdrant_setup.py --collection historia_pilotos
  python scripts/ingest_ollama.py --collection historia_pilotos --kb kb/processed/kb_pilotos.jsonl

Fuentes:
  - Jolpica F1 API (sucesora de Ergast): resultados de toda la carrera de cada piloto de la parrilla 2026 (desde 1950),
    campeón del mundo de cada temporada 1950-2025. Lo histórico (hasta 2025) se descarga una vez y queda en
    kb/raw/pilotos/; la temporada 2026 se toma de kb/raw/jolpica/ (que refresca actualizar_kb.py).
  - Wikipedia "List of Formula One driver records" (inglés): récords de todos los tiempos, por sección.

Documentos generados (en español, con metadatos): perfil de carrera, lista de victorias y resumen temporada a
temporada de cada piloto; campeones del mundo por década; récords históricos por categoría.
El id de cada fragmento es el hash de su contenido (igual que en PitWall), así la sincronización es incremental.
"""
import glob
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
RAW_2026 = os.path.join(ROOT, "kb", "raw", "jolpica")
RAW = os.path.join(ROOT, "kb", "raw", "pilotos")
OUT = os.path.join(ROOT, "kb", "processed", "kb_pilotos.jsonl")
MANIFEST = os.path.join(ROOT, "kb", "processed", "kb_pilotos_manifest.json")
JOLPICA = "https://api.jolpi.ca/ergast/f1"
WIKI_RECORDS = "https://en.wikipedia.org/w/api.php?action=parse&page=List_of_Formula_One_driver_records&prop=wikitext&format=json&formatversion=2"
WIKI_RECORDS_URL = "https://en.wikipedia.org/wiki/List_of_Formula_One_driver_records"
UA = {"User-Agent": "PitWall-RAG-F1/1.0 (proyecto academico; https://github.com)"}
ULTIMA_TEMPORADA_CERRADA = 2025
MAX_CHARS = 1900
os.makedirs(RAW, exist_ok=True)

from build_kb import gp_es, fecha_es  # noqa: E402  (mismos nombres en español que la base de PitWall)


# ------------------------------------------------------------------ descarga
def get_json(url, intentos=6):
    espera = 3
    for _ in range(intentos):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(espera); espera = min(espera * 2, 60); continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(espera); espera = min(espera * 2, 60)
    raise RuntimeError("Jolpica no responde: " + url)


def resultados_2026():
    """Carreras 2026 con resultados, desde los archivos que ya refresca actualizar_kb.py."""
    races = {}
    for f in sorted(glob.glob(os.path.join(RAW_2026, "results_*.json"))):
        for r in json.load(open(f, encoding="utf-8"))["MRData"]["RaceTable"]["Races"]:
            if r.get("Results"):
                races[int(r["round"])] = r
    return [races[k] for k in sorted(races)]


def pilotos_2026(races):
    pilotos = {}
    for r in races:
        for res in r["Results"]:
            d = res["Driver"]
            pilotos[d["driverId"]] = d
    return pilotos


def carrera_historica(driver_id):
    """Todas las carreras (hasta ULTIMA_TEMPORADA_CERRADA) del piloto; se descargan una vez."""
    dest = os.path.join(RAW, f"{driver_id}_results.json")
    if os.path.exists(dest):
        return json.load(open(dest, encoding="utf-8"))
    races, offset, total = [], 0, None
    while total is None or offset < total:
        data = get_json(f"{JOLPICA}/drivers/{driver_id}/results.json?limit=100&offset={offset}")["MRData"]
        total = int(data["total"])
        races += data["RaceTable"]["Races"]
        offset += 100
        time.sleep(0.4)
    races = [r for r in races if int(r["season"]) <= ULTIMA_TEMPORADA_CERRADA]
    json.dump(races, open(dest, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"  {driver_id}: {len(races)} carreras históricas descargadas")
    return races


def campeones():
    dest = os.path.join(RAW, "campeones.json")
    camp = json.load(open(dest, encoding="utf-8")) if os.path.exists(dest) else {}
    faltan = [y for y in range(1950, ULTIMA_TEMPORADA_CERRADA + 1) if str(y) not in camp]
    for y in faltan:
        lst = get_json(f"{JOLPICA}/{y}/driverStandings/1.json")["MRData"]["StandingsTable"]["StandingsLists"]
        if lst:
            s = lst[0]["DriverStandings"][0]
            camp[str(y)] = {"driverId": s["Driver"]["driverId"], "nombre": s["Driver"]["givenName"] + " " + s["Driver"]["familyName"],
                            "nacionalidad": s["Driver"].get("nationality", ""), "puntos": s["points"], "victorias": s["wins"],
                            "equipo": s["Constructors"][0]["name"] if s.get("Constructors") else ""}
        time.sleep(0.4)
    if faltan:
        json.dump(camp, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  campeones: {len(faltan)} temporadas descargadas")
    return camp


def wiki_records(refresh):
    dest = os.path.join(RAW, "wiki_records.json")
    if os.path.exists(dest) and not refresh:
        return json.load(open(dest, encoding="utf-8"))["parse"]["wikitext"]
    data = get_json(WIKI_RECORDS)
    if os.path.exists(dest) and json.load(open(dest, encoding="utf-8")) == data:
        return data["parse"]["wikitext"]
    json.dump(data, open(dest, "w", encoding="utf-8"), ensure_ascii=False)
    print("  Wikipedia (récords): descargado")
    return data["parse"]["wikitext"]


# ------------------------------------------------------------------ estadísticas por piloto
def stats(races, driver_id):
    """Resumen de una lista de carreras (cada una con el Result del piloto)."""
    s = {"gp": 0, "victorias": 0, "podios": 0, "poles": 0, "vr": 0, "puntos": 0.0, "wins": [], "equipos": defaultdict(set), "por_temporada": defaultdict(lambda: {"gp": 0, "victorias": 0, "podios": 0, "poles": 0, "puntos": 0.0, "equipos": []})}
    for r in races:
        res = next((x for x in r["Results"] if x["Driver"]["driverId"] == driver_id), None)
        if not res:
            continue
        y = r["season"]
        t = s["por_temporada"][y]
        s["gp"] += 1; t["gp"] += 1
        pos = res.get("position")
        pts = float(res.get("points") or 0)
        s["puntos"] += pts; t["puntos"] += pts
        equipo = res["Constructor"]["name"]
        s["equipos"][equipo].add(int(y))
        if equipo not in t["equipos"]:
            t["equipos"].append(equipo)
        if res.get("grid") == "1":
            s["poles"] += 1; t["poles"] += 1
        if pos == "1":
            s["victorias"] += 1; t["victorias"] += 1
            s["wins"].append({"season": y, "round": r["round"], "gp": gp_es(r["raceName"]), "circuito": r["Circuit"]["circuitName"], "fecha": r["date"], "equipo": equipo, "grid": res.get("grid", "?")})
        if pos in ("1", "2", "3"):
            s["podios"] += 1; t["podios"] += 1
        if (res.get("FastestLap") or {}).get("rank") == "1":
            s["vr"] += 1
    return s


def fmt_pts(p):
    return str(int(p)) if float(p).is_integer() else f"{p:.1f}"


def rango(anios):
    a = sorted(anios)
    grupos, ini, prev = [], a[0], a[0]
    for y in a[1:]:
        if y != prev + 1:
            grupos.append((ini, prev)); ini = y
        prev = y
    grupos.append((ini, prev))
    return ", ".join(f"{i}" if i == f else f"{i}-{f}" for i, f in grupos)


def docs_piloto(d, hist, r2026, camp, ronda_2026):
    driver_id = d["driverId"]
    nombre = d["givenName"] + " " + d["familyName"]
    todas = hist + r2026
    s = stats(todas, driver_id)
    h = stats(hist, driver_id)
    t26 = stats(r2026, driver_id)
    titulos = [y for y, c in camp.items() if c["driverId"] == driver_id]
    doc_name = f"Palmarés de {nombre}"
    base_md = {"tipo": "perfil", "documento": doc_name, "piloto": driver_id, "nombre": nombre, "fuente": "Jolpica F1 API (datos oficiales desde 1950)",
               "url": f"https://api.jolpi.ca/ergast/f1/drivers/{driver_id}/results.json", "idioma": "es", "actualizado_hasta": f"2026 ronda {ronda_2026}"}
    docs = []

    # 1) perfil
    primeras = sorted(todas, key=lambda r: (int(r["season"]), int(r["round"])))
    primera = primeras[0] if primeras else None
    equipos_txt = "; ".join(f"{e} ({rango(y)})" for e, y in sorted(s["equipos"].items(), key=lambda kv: min(kv[1])))
    lineas = [f"{doc_name}: logros históricos de {nombre} en la Fórmula 1 ({d.get('nationality', '')}, nacido el {fecha_es(d['dateOfBirth']) if d.get('dateOfBirth') else '?'}, dorsal {d.get('permanentNumber', '?')})."]
    if primera:
        lineas.append(f"Debut: {gp_es(primera['raceName'])} de {primera['season']} con {primera['Results'][0]['Constructor']['name']}.")
    lineas.append(f"Grandes Premios disputados: {s['gp']} (hasta la ronda {ronda_2026} de 2026). Victorias: {s['victorias']}. Podios: {s['podios']}. Pole positions: {s['poles']}. Vueltas rápidas: {s['vr']}. Puntos totales: {fmt_pts(s['puntos'])}.")
    if titulos:
        lineas.append(f"Títulos mundiales de pilotos: {len(titulos)} ({', '.join(titulos)}).")
    else:
        lineas.append("Títulos mundiales de pilotos: ninguno hasta 2025.")
    lineas.append(f"Equipos: {equipos_txt}.")
    if s["wins"]:
        w0, w1 = s["wins"][0], s["wins"][-1]
        lineas.append(f"Primera victoria: {w0['gp']} de {w0['season']} ({w0['equipo']}). Última victoria: {w1['gp']} de {w1['season']} ({w1['equipo']}).")
        mejor = max(s["por_temporada"].items(), key=lambda kv: (kv[1]["victorias"], kv[1]["puntos"]))
        lineas.append(f"Mejor temporada por victorias: {mejor[0]} con {mejor[1]['victorias']} victorias, {mejor[1]['podios']} podios y {fmt_pts(mejor[1]['puntos'])} puntos.")
    else:
        lineas.append("Todavía no ha ganado un Gran Premio.")
    if t26["gp"]:
        lineas.append(f"Temporada 2026 hasta la ronda {ronda_2026}: {t26['gp']} carreras, {t26['victorias']} victorias, {t26['podios']} podios, {t26['poles']} poles, {fmt_pts(t26['puntos'])} puntos con {', '.join(t26['por_temporada']['2026']['equipos'])}.")
    lineas.append(f"Antes de 2026 (carrera completa 1950-2025): {h['gp']} GP, {h['victorias']} victorias, {h['podios']} podios, {h['poles']} poles, {fmt_pts(h['puntos'])} puntos.")
    docs.append({"content": "\n".join(lineas), "metadata": {**base_md, "tipo": "perfil", "titulo": f"Perfil histórico de {nombre}"}})

    # 2) victorias (en bloques)
    if s["wins"]:
        lst = [f"{w['season']} · {w['gp']} ({w['circuito']}, {fecha_es(w['fecha'])}) · {w['equipo']} · salió {w['grid']}º" for w in s["wins"]]
        bloque, n_ini = [], 1
        def cerrar(bloque, n_ini):
            n_fin = n_ini + len(bloque) - 1
            head = f"Victorias de {nombre} en Grandes Premios de Fórmula 1 ({s['victorias']} en total hasta la ronda {ronda_2026} de 2026, {len(titulos)} títulos mundiales): victorias {n_ini} a {n_fin}, de {bloque[0][:4]} a {bloque[-1][:4]}."
            docs.append({"content": head + "\n" + "\n".join(f"{n_ini + i}. {l}" for i, l in enumerate(bloque)), "metadata": {**base_md, "tipo": "victorias", "titulo": f"Victorias de {nombre} ({n_ini}-{n_fin})"}})
        for l in lst:
            if bloque and sum(len(x) + 4 for x in bloque) + len(l) > MAX_CHARS:
                cerrar(bloque, n_ini); n_ini += len(bloque); bloque = []
            bloque.append(l)
        if bloque:
            cerrar(bloque, n_ini)

    # 3) temporada a temporada
    filas = []
    for y in sorted(s["por_temporada"]):
        t = s["por_temporada"][y]
        extra = " · CAMPEÓN DEL MUNDO" if y in titulos else ""
        filas.append(f"{y} · {', '.join(t['equipos'])} · {t['gp']} GP, {t['victorias']} victorias, {t['podios']} podios, {t['poles']} poles, {fmt_pts(t['puntos'])} puntos{extra}")
    bloque = []
    def cerrar_t(bloque):
        head = (f"Trayectoria de {nombre} temporada a temporada en la Fórmula 1 ({bloque[0][:4]}-{bloque[-1][:4]}): equipo, carreras, victorias, podios, poles y puntos por año. "
                f"Totales de toda su carrera hasta la ronda {ronda_2026} de 2026: {s['gp']} GP, {s['victorias']} victorias, {s['podios']} podios, {s['poles']} poles, {fmt_pts(s['puntos'])} puntos, {len(titulos)} títulos mundiales.")
        docs.append({"content": head + "\n" + "\n".join(bloque), "metadata": {**base_md, "tipo": "temporadas", "titulo": f"Trayectoria de {nombre} {bloque[0][:4]}-{bloque[-1][:4]}"}})
    for f in filas:
        if bloque and sum(len(x) + 1 for x in bloque) + len(f) > MAX_CHARS:
            cerrar_t(bloque); bloque = []
        bloque.append(f)
    if bloque:
        cerrar_t(bloque)
    return docs, s


def docs_campeones(camp):
    docs = []
    por_decada = defaultdict(list)
    for y in sorted(camp):
        c = camp[y]
        por_decada[y[:3] + "0"].append(f"{y}: {c['nombre']} ({c['nacionalidad']}) con {c['equipo']} · {c['puntos']} puntos, {c['victorias']} victorias")
    for dec, lineas in por_decada.items():
        content = f"Campeones del mundo de pilotos de Fórmula 1, década {dec}-{int(dec) + 9}:\n" + "\n".join(lineas)
        docs.append({"content": content, "metadata": {"tipo": "campeones", "documento": "Campeones del mundo de Fórmula 1 (1950-2025)", "titulo": f"Campeones {dec}-{int(dec) + 9}",
                                                       "fuente": "Jolpica F1 API (datos oficiales desde 1950)", "url": "https://api.jolpi.ca/ergast/f1/2025/driverStandings/1.json", "idioma": "es"}})
    # conteo de títulos por piloto
    cuenta = defaultdict(list)
    for y, c in camp.items():
        cuenta[c["nombre"]].append(y)
    ranking = sorted(cuenta.items(), key=lambda kv: (-len(kv[1]), kv[1][0]))
    lineas = [f"{i + 1}. {n}: {len(ys)} título{'s' if len(ys) > 1 else ''} ({', '.join(ys)})" for i, (n, ys) in enumerate(ranking) if len(ys) >= 2]
    docs.append({"content": "Pilotos con más títulos mundiales de Fórmula 1 (campeonatos de pilotos 1950-2025, solo quienes tienen dos o más):\n" + "\n".join(lineas),
                 "metadata": {"tipo": "campeones", "documento": "Campeones del mundo de Fórmula 1 (1950-2025)", "titulo": "Pilotos con más títulos mundiales", "fuente": "Jolpica F1 API (datos oficiales desde 1950)",
                              "url": "https://api.jolpi.ca/ergast/f1/2025/driverStandings/1.json", "idioma": "es"}})
    return docs


def docs_ranking_2026(perfiles):
    """Comparativa entre los pilotos de la parrilla 2026."""
    docs = []
    for clave, nombre in [("victorias", "victorias"), ("podios", "podios"), ("poles", "pole positions"), ("gp", "Grandes Premios disputados"), ("puntos", "puntos")]:
        orden = sorted(perfiles, key=lambda p: -p[1][clave])
        lineas = [f"{i + 1}. {p[0]}: {fmt_pts(p[1][clave]) if clave == 'puntos' else p[1][clave]}" for i, p in enumerate(orden)]
        docs.append({"content": f"Ranking histórico de {nombre} entre los pilotos de la parrilla de Fórmula 1 2026 (toda su carrera, 1950-2026 ronda actual):\n" + "\n".join(lineas),
                     "metadata": {"tipo": "ranking", "documento": "Comparativa histórica de los pilotos de 2026", "titulo": f"Ranking de {nombre} (parrilla 2026)", "fuente": "Jolpica F1 API (datos oficiales desde 1950)",
                                  "url": "https://api.jolpi.ca/ergast/f1/2026/drivers.json", "idioma": "es"}})
    return docs


# ------------------------------------------------------------------ Wikipedia: récords
F1STAT = {}   # código de piloto (HAM) -> estadísticas calculadas; lo llena main()
F1STAT_CAMPOS = {"entries": "gp", "starts": "gp", "races": "gp", "wins": "victorias", "poles": "poles", "podiums": "podios", "fastestlaps": "vr", "fastest laps": "vr", "points": "puntos", "championships": "titulos", "titles": "titulos"}


def f1stat(m):
    code, campo = m.group(1).upper(), m.group(2).strip().lower()
    st = F1STAT.get(code)
    if not st or campo not in F1STAT_CAMPOS:
        return "?"
    v = st.get(F1STAT_CAMPOS[campo], "?")
    return fmt_pts(v) if isinstance(v, float) else str(v)


def limpiar_wikitext(s):
    s = re.sub(r"\{\{\s*F1stat\s*\|\s*([A-Za-z]{3})\s*\|\s*([^{}|]+?)\s*\}\}", f1stat, s)
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    for _ in range(6):   # plantillas anidadas
        s2 = re.sub(r"\{\{(?:flagicon|flag|flagu|flagcountry|nowrap|small|efn|refn|abbr|dts|sort|sortname|nts|ntsh|n/a|center|age|birth date and age|Birth date and age|F1|F1stat|fb|flagathlete|Flagicon|Nowrap)\|([^{}]*)\}\}",
                    lambda m: " ".join(p for p in m.group(1).split("|") if "=" not in p and p.strip()), s)
        s2 = re.sub(r"\{\{[^{}]*\}\}", "", s2)
        if s2 == s:
            break
        s = s2
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[https?://[^\s\]]+\s*([^\]]*)\]", r"\1", s)
    s = re.sub(r"'{2,}", "", s)
    s = re.sub(r"<br\s*/?>", ", ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ")
    return s


def tabla_a_lineas(t):
    filas, celdas = [], []
    for linea in t.split("\n"):
        l = linea.strip()
        if l.startswith("{|") or l.startswith("|+") or l == "|}":
            continue
        if l.startswith("|-"):
            if celdas:
                filas.append(celdas); celdas = []
            continue
        if l.startswith("!") or l.startswith("|"):
            partes = re.split(r"\s*(?:\|\||!!)\s*", l[1:])
            for p in partes:
                if "|" in p and "=" in p.split("|")[0]:   # atributos de estilo antes del contenido
                    p = p.split("|", 1)[1]
                p = re.sub(r"\s+", " ", p).strip()
                if p and p not in ("—", "-"):
                    celdas.append(p)
        elif celdas and l:
            celdas[-1] += " " + l
    if celdas:
        filas.append(celdas)
    return [" · ".join(f) for f in filas if f]


def docs_records(wt):
    wt = limpiar_wikitext(wt)
    partes = re.split(r"^(==+)\s*(.+?)\s*\1\s*$", wt, flags=re.M)
    docs, h2 = [], ""
    for i in range(1, len(partes), 3):
        nivel, titulo, cuerpo = len(partes[i]), partes[i + 1].strip(), partes[i + 2]
        if nivel == 2:
            h2 = titulo
        if titulo.lower() in ("see also", "notes", "references", "footnotes", "external links"):
            continue
        # tablas -> líneas; prosa -> párrafos
        lineas = []
        def repl(m):
            lineas.extend(tabla_a_lineas(m.group(0))); return "\n"
        prosa = re.sub(r"\{\|.*?\n\|\}", repl, cuerpo, flags=re.S)
        prosa = [p.strip() for p in prosa.split("\n") if p.strip() and not p.strip().startswith(("|", "!", "{"))]
        texto = "\n".join(prosa + lineas).strip()
        if len(texto) < 60:
            continue
        ruta = f"{h2} · {titulo}" if nivel > 2 and h2 != titulo else titulo
        head = f"Récords históricos de pilotos de Fórmula 1 (Wikipedia, en inglés) · {ruta}:"
        # trocear en bloques
        bloque, n = [], 1
        def cerrar(bloque, n):
            docs.append({"content": head + (f" (parte {n})" if n > 1 or len(texto) > MAX_CHARS else "") + "\n" + "\n".join(bloque),
                         "metadata": {"tipo": "record", "documento": "Récords históricos de la Fórmula 1 (Wikipedia)", "titulo": ruta, "parte": n,
                                      "fuente": "Wikipedia", "url": WIKI_RECORDS_URL + "#" + titulo.replace(" ", "_"), "idioma": "en"}})
        for l in texto.split("\n"):
            if bloque and sum(len(x) + 1 for x in bloque) + len(l) > MAX_CHARS:
                cerrar(bloque, n); n += 1; bloque = []
            bloque.append(l[:600])
        if bloque:
            cerrar(bloque, n)
    return docs


# ------------------------------------------------------------------ principal
def main(refresh=False):
    r26 = resultados_2026()
    ronda = max((int(r["round"]) for r in r26), default=0)
    pilotos = pilotos_2026(r26)
    print(f"Temporada 2026: {len(r26)} carreras con resultados (hasta la ronda {ronda}); {len(pilotos)} pilotos con al menos una salida")
    print("Descargando historial (solo la primera vez)...")
    camp = campeones()
    docs, perfiles = [], []
    for did in sorted(pilotos):
        hist = carrera_historica(did)
        dd, s = docs_piloto(pilotos[did], hist, r26, camp, ronda)
        docs += dd
        perfiles.append((pilotos[did]["givenName"] + " " + pilotos[did]["familyName"], s))
        if pilotos[did].get("code"):
            F1STAT[pilotos[did]["code"].upper()] = {**{k: s[k] for k in ("gp", "victorias", "poles", "podios", "vr", "puntos")}, "titulos": sum(1 for c in camp.values() if c["driverId"] == did)}
    docs += docs_ranking_2026(perfiles)
    docs += docs_campeones(camp)
    wt = wiki_records(refresh)
    rec = docs_records(wt)
    docs += rec
    # ids por contenido
    vistos = {}
    for d in docs:
        base = hashlib.sha1((d["metadata"]["tipo"] + "|" + d["content"]).encode("utf-8")).hexdigest()[:16]
        n = vistos.get(base, 0); vistos[base] = n + 1
        d["id"] = base if n == 0 else f"{base}-{n}"
    with open(OUT, "w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(json.dumps({"id": d["id"], "content": d["content"], "metadata": d["metadata"]}, ensure_ascii=False) + "\n")
    conteo = defaultdict(int)
    for d in docs:
        conteo[d["metadata"]["tipo"]] += 1
    manifest = {"total_fragmentos": len(docs), "pilotos": len(pilotos), "ronda_2026": ronda, "tipos": dict(conteo), "chars_total": sum(len(d["content"]) for d in docs)}
    json.dump(manifest, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(manifest, ensure_ascii=False))
    return manifest


if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
