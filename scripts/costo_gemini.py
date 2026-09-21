"""
PitWall · Estima el gasto de Gemini a partir de los tokens registrados en las ejecuciones locales de n8n.

Uso: python scripts/costo_gemini.py            (lee la base SQLite de n8n en modo solo lectura)
     python scripts/costo_gemini.py --hoy      (solo ejecuciones de hoy)

Precios de referencia (USD por millón de tokens) — ajústalos si Google los cambia:
  gemini-3.6-flash: entrada 0.50, salida 3.00 (los tokens de razonamiento cuentan como salida)
  gemini-embedding-2: 0.15 por millón de tokens de entrada
"""
import json
import os
import re
import sqlite3
import sys
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".n8n", ".n8n", "database.sqlite")
PRECIO_IN, PRECIO_OUT, PRECIO_EMB = 0.50, 3.00, 0.15
TOKEN_RE = re.compile(r'"completionTokens":(\d+),"promptTokens":(\d+),"totalTokens":(\d+)')


def main():
    solo_hoy = "--hoy" in sys.argv
    con = sqlite3.connect(f"file:{DB.replace(chr(92), '/')}?mode=ro", uri=True)
    rows = con.execute("select e.id, e.status, e.startedAt, e.workflowId, d.data from execution_entity e join execution_data d on d.executionId = e.id order by e.id").fetchall()
    names = dict(con.execute("select id, name from workflow_entity").fetchall())
    tot_in = tot_out = 0; por_flujo = {}
    hoy = date.today().isoformat()
    for eid, status, started, wf, data in rows:
        if solo_hoy and not str(started).startswith(hoy):
            continue
        c_in = c_out = 0
        for m in TOKEN_RE.finditer(data or ""):
            c_out += int(m.group(1)); c_in += int(m.group(2))
        if c_in or c_out:
            k = names.get(wf, wf)
            f = por_flujo.setdefault(k, {"ejecuciones": 0, "entrada": 0, "salida": 0})
            f["ejecuciones"] += 1; f["entrada"] += c_in; f["salida"] += c_out
            tot_in += c_in; tot_out += c_out
    costo = tot_in / 1e6 * PRECIO_IN + tot_out / 1e6 * PRECIO_OUT
    print(f"Tokens de chat registrados en n8n{' (hoy)' if solo_hoy else ''}: entrada {tot_in:,} · salida {tot_out:,}")
    for k, f in por_flujo.items():
        c = f["entrada"] / 1e6 * PRECIO_IN + f["salida"] / 1e6 * PRECIO_OUT
        print(f"  - {k}: {f['ejecuciones']} ejecuciones · {f['entrada']:,} in · {f['salida']:,} out · ~${c:.4f}")
    print(f"Costo estimado de generación: ~${costo:.4f} USD")
    print("Embeddings: la ingesta completa (1.056 fragmentos, ~330k tokens) cuesta ~$0.05; cada pregunta consume ~1 embedding (despreciable).")
    print("Nota: las ejecuciones del flujo 01 (ingesta) no registran tokens; las consultas de prueba desde el chat del editor tampoco si no se guardan.")


if __name__ == "__main__":
    main()
