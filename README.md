# PitWall · Asistente RAG sobre la Fórmula 1 2026

Proyecto final del **Diplomado en IA Generativa**. Un agente conversacional que responde y guía a aficionados
no técnicos sobre la F1 2026 consultando primero una base de conocimiento propia: los reglamentos oficiales
de la FIA vigentes, los resultados de la temporada 2026 y guías en español. Todo corre en local y con
servicios gratuitos.

## Arquitectura

```
Usuario ──► Front (HTML/JS, blanco y negro) ──► n8n local (Chat Trigger)
                                                   │
                                                   ▼
                                     AI Agent (Llama 4 Scout vía Groq, memoria por sesión)
                                                   │  herramienta: buscar_base_conocimiento
                                                   ▼
                                Qdrant local (1.072 fragmentos, embeddings Gemini 3072d)
                                                   │
                                                   ▼
                          Evaluador (Llama 3.1 8B vía Groq): ¿la respuesta está respaldada por las fuentes?
                                                   │
                                                   ▼
                    Respuesta + pasos ("Pensando") + fuentes + sugerencias ──► Front / chat de n8n
```

| Componente de la consigna | Implementación |
|---|---|
| Interfaz de entrada | `front/index.html` (usuarios no técnicos) y el chat de n8n (explicación técnica) |
| Base de conocimiento | Reglamentos FIA 2026 A/B/C/D, temporada 2026 (API Jolpica), narrativa (Wikipedia), 11 guías propias en español |
| Recuperación | Búsqueda semántica en Qdrant (top 6) como herramienta del agente |
| Modelo de lenguaje | Llama 4 Scout vía Groq (capa gratuita, 1.000 solicitudes/día); embeddings con Gemini |
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

## Estructura del repositorio

```
front/        Página web del asistente (sin frameworks)
workflows/    Flujos de n8n listos para importar (01 ingesta, 02 agente RAG, 03 chat directo) + README
kb/           Base de conocimiento: docs_es/ (guías propias), processed/ (fragmentos listos), raw/ (fuentes, no versionadas)
scripts/      Descarga de fuentes, extracción de PDF, construcción de la base, ingesta a Qdrant, arranque de servicios
docs/         Banco de preguntas de demo, lista de recursos gráficos
sql/          Esquema alternativo para Supabase (no usado en la versión local)
```

## Cómo ejecutarlo en local (Windows)

Requisitos: Node 24, Python 3.12, una API key gratuita de Google AI Studio.

```powershell
npm install -g n8n
python scripts/download_sources.py        # PDFs FIA, Wikipedia, API Jolpica
python scripts/extract_pdf_text.py
python scripts/build_kb.py                # -> kb/processed/kb_all.jsonl
# Qdrant: descargar el binario de Windows en tools/qdrant/qdrant.exe (releases de github.com/qdrant/qdrant)
powershell -ExecutionPolicy Bypass -File scripts/start_qdrant.ps1
python scripts/qdrant_setup.py
powershell -ExecutionPolicy Bypass -File scripts/start_n8n.ps1   # http://localhost:5678
```

En n8n: crear las credenciales `Google Gemini(PaLM) Api` (tu key) y `Qdrant API` (URL `http://127.0.0.1:6333`,
sin key), importar los tres flujos de `workflows/`, ejecutar `01 Ingesta` y publicar `02` y `03`.
Alternativa de ingesta por consola: `$env:GEMINI_API_KEY="..."; python scripts/ingest_qdrant.py`.

Front: `python scripts/serve_cors.py 8765 front` y abrir `http://localhost:8765`.

## Fuentes

- FIA, Reglamentos de Fórmula 1 2026: Sección A (Issue 03), B Deportivo (Issue 08), C Técnico (Issue 20), D Financiero (Issue 07).
- Jolpica F1 API (datos oficiales de resultados, sucesora de Ergast).
- Wikipedia, "2026 Formula One World Championship".
- Formula1.com y FIA: explicadores de los reglamentos 2026.

Autor: Mateo Robles · 2026. Proyecto académico sin fines comerciales; no afiliado a la FIA ni a Formula One.
