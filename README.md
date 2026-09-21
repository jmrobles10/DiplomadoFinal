# PitWall · Asistente RAG sobre la Fórmula 1 2026

Proyecto final del **Diplomado en IA Generativa**. Un agente conversacional que responde y guía a aficionados
no técnicos sobre la F1 2026 consultando primero una base de conocimiento propia: los reglamentos oficiales
de la FIA vigentes, los resultados de la temporada 2026 y guías en español. Todo corre en local, sin API keys
y sin costo: los modelos de IA son locales (Ollama).

## Arquitectura

```
Usuario ──► Front (HTML/JS, blanco y negro) ──► n8n local (Chat Trigger)
                                                   │
                                                   ▼
                    Reformulador (qwen3:8b): pregunta + historial ──► consulta de búsqueda autónoma
                                                   │
                                                   ▼
                Qdrant local (1.056 fragmentos, embeddings bge-m3 1024d vía Ollama) ──► top 6 fragmentos
                                                   │
                                                   ▼
               AI Agent (qwen3:8b, memoria por sesión) responde con esos fragmentos en el prompt;
               conserva la herramienta buscar_base_conocimiento para búsquedas adicionales
                                                   │
                                                   ▼
                          Evaluador (qwen3:8b): ¿la respuesta está respaldada por las fuentes?
                                                   │
                                                   ▼
                    Respuesta + pasos ("Pensando") + fuentes + sugerencias ──► Front / chat de n8n
```

| Componente de la consigna | Implementación |
|---|---|
| Interfaz de entrada | `front/index.html` (PitWall) y `front/podium.html` (Podium), más el chat de n8n (explicación técnica) |
| Base de conocimiento | Reglamentos FIA 2026 A/B/C/D, temporada 2026 (API Jolpica), narrativa (Wikipedia), 11 guías propias en español. Se actualiza sola de forma incremental (flujo 04) |
| Recuperación | Búsqueda semántica en Qdrant (top 6) en cada turno, con la pregunta reformulada según el historial; el agente además tiene la búsqueda como herramienta |
| Modelo de lenguaje | `qwen3:8b` en Ollama (local, gratis, tool calling). Embeddings `bge-m3` (multilingüe) también en Ollama |
| Respuesta con contexto | El agente responde solo con lo recuperado y cita documento y artículo |
| Módulo evaluador | Segunda llamada que verifica la fundamentación de cada respuesta |
| Comparación RAG vs directo | Flujo 03 con el mismo modelo sin base de conocimiento; interruptor en el front |

## Decisiones de diseño

- **Chunking por artículo**, no por tamaño fijo: cada fragmento del reglamento es un artículo o sub-artículo
  con su número, título y página. Así cada cita apunta a un artículo real.
- **Consulta multilingüe**: los reglamentos están en inglés y el usuario pregunta en español; el agente
  formula las búsquedas en el idioma de cada fuente y responde en español.
- **Persistencia**: la base vectorial vive en disco (Qdrant) y no se pierde entre chats ni reinicios.
- **Thinking visible**: el agente devuelve sus pasos intermedios reales (qué buscó, qué encontró, cómo lo
  verificó) y el front los muestra en un panel "Pensando".
- **Honestidad**: si la información no está en la base, el agente lo dice en vez de inventar.
- **Recuperación determinista**: con un modelo local de 8B no se puede confiar en que el agente llame la herramienta en cada
  turno (tras el primero tendía a responder de memoria). Por eso el flujo reformula la pregunta con el historial, busca en
  Qdrant y le entrega los fragmentos al agente antes de que responda. La herramienta queda para búsquedas extra.

## Estructura del repositorio

```
front/        Páginas web de PitWall (index.html) y Podium (podium.html), sin frameworks
workflows/    Flujos de n8n listos para importar (01 ingesta, 02 agente RAG, 03 chat directo, 04 actualización, 05 Podium) + README
kb/           Base de conocimiento: docs_es/ (guías propias), processed/ (fragmentos listos), raw/ (fuentes, no versionadas)
scripts/      Descarga de fuentes, extracción de PDF, construcción de la base, ingesta a Qdrant, arranque de servicios
docs/         Banco de preguntas de demo, lista de recursos gráficos
sql/          Esquema alternativo para Supabase (no usado en la versión local)
```

## Instalar en otro PC

Guía completa en [docs/INSTALACION.md](docs/INSTALACION.md). Resumen: clonar, ejecutar
`scripts\setup_windows.ps1` (instala n8n, descarga Qdrant y restaura los vectores exportados sin gastar API),
crear el usuario y las dos credenciales en n8n, importar los tres flujos y publicar 02 y 03.

## Cómo ejecutarlo en local (Windows)

Requisitos: Node 22 o 24, Python 3.12 y [Ollama](https://ollama.com) (`winget install Ollama.Ollama`). No hace falta ninguna API key.
Recomendado: GPU con 8 GB de VRAM (probado en una RTX 4060); en CPU funciona pero cada respuesta tarda más.

```powershell
ollama pull qwen3:8b                      # generador y evaluador (5,2 GB)
ollama pull bge-m3                        # embeddings (1,2 GB)
npm install -g n8n
python scripts/download_sources.py        # PDFs FIA, Wikipedia, API Jolpica
python scripts/extract_pdf_text.py
python scripts/build_kb.py                # -> kb/processed/kb_all.jsonl
# Qdrant: descargar el binario de Windows en tools/qdrant/qdrant.exe (releases de github.com/qdrant/qdrant)
powershell -ExecutionPolicy Bypass -File scripts/start_qdrant.ps1
python scripts/qdrant_setup.py            # colección de 1024 dimensiones
python scripts/ingest_ollama.py           # vectoriza los 1.056 fragmentos con bge-m3 (2-5 min con GPU)
powershell -ExecutionPolicy Bypass -File scripts/start_n8n.ps1   # http://localhost:5678
```

En n8n: crear el usuario dueño en `http://localhost:5678` y luego ejecutar `scripts\n8n_import.ps1`, que importa las
credenciales `Ollama local` (`http://127.0.0.1:11434`) y `Qdrant local` (`http://127.0.0.1:6333`) con los ids que ya traen
los flujos, más los tres flujos de `workflows/`. Reiniciar n8n y publicar `02` y `03`.
Si prefieres vectorizar desde n8n en vez de la consola, ejecuta el flujo `01 Ingesta` (usa el mismo modelo `bge-m3`).

Front: `python scripts/serve_cors.py 8765 front` y abrir `http://localhost:8765`.

## Actualización automática de la base de conocimiento

La base se mantiene sola, en local y sin costo, con `scripts/actualizar_kb.py` (lo ejecuta el flujo `04` de n8n):

- **Cuándo**: cada 6 horas por horario y, además, en segundo plano cada vez que alguien pregunta (el flujo `02`
  llama al `04` sin esperar; con `--si-hace-falta` sale de inmediato si ya se revisó en las últimas 6 h, así una
  consulta nunca se demora por esto).
- **Qué revisa**: la API de la temporada (Jolpica: resultados, sprints, clasificaciones), Wikipedia y la página oficial
  de reglamentos de la FIA, donde detecta si salió un Issue nuevo de las secciones A a D y lo descarga.
- **Cómo evita duplicar o sobrescribir**: el id de cada fragmento es el hash de su contenido. Lo que no cambió
  conserva su id y no se toca; lo nuevo (una carrera más, un artículo modificado) tiene id nuevo y se vectoriza con
  Ollama e inserta; lo que dejó de existir (por ejemplo la clasificación "tras 14 rondas" cuando ya hay 15, o el texto
  de un artículo reemplazado) se elimina para que no contradiga a la versión vigente. Una actualización típica toca
  unas decenas de fragmentos y tarda menos de un minuto.
- **Trazabilidad**: `kb/processed/update_state.json` (última revisión y resultado) y `kb/processed/update_log.jsonl`.
  `python scripts/actualizar_kb.py --estado` los muestra; `--forzar` reconstruye todo; `--conservar-obsoletos` no borra.
- **Límite**: las guías propias de `kb/docs_es/` son texto escrito a mano y no se regeneran solas (la 08, "la temporada
  hasta hoy", envejece); los datos de resultados y clasificaciones sí se actualizan porque salen de la API.

## Podium: logros históricos por piloto (RAG separado)

Segunda sección del front (`front/podium.html`) con su propio asistente, **Podium**, para la historia de los pilotos:
palmarés (debut, victorias, podios, poles, títulos, equipos), lista de victorias y trayectoria año a año de los 23
pilotos que han corrido en 2026, campeón del mundo de cada temporada desde 1950, rankings entre los pilotos actuales y
más de sesenta categorías de récords de todos los tiempos.

Está completamente separado de PitWall: colección de Qdrant propia (`historia_pilotos`, construida por
`scripts/build_kb_pilotos.py` con la API Jolpica desde 1950 y la lista de récords de Wikipedia), flujo de n8n propio
(`05`, mismo diseño que el `02`) con su webhook, su memoria y su personalidad, y sesión e historial de chat propios en
el navegador. Si le preguntan por el reglamento o la temporada 2026, remite a PitWall. El flujo `04` también mantiene
esta base al día tras cada carrera.

## Fuentes

- FIA, Reglamentos de Fórmula 1 2026: Sección A (Issue 03), B Deportivo (Issue 08), C Técnico (Issue 20), D Financiero (Issue 07).
- Jolpica F1 API (datos oficiales de resultados, sucesora de Ergast).
- Wikipedia, "2026 Formula One World Championship".
- Formula1.com y FIA: explicadores de los reglamentos 2026.

Autor: Mateo Robles · 2026. Proyecto académico sin fines comerciales; no afiliado a la FIA ni a Formula One.
