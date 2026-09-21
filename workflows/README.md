# Flujos de n8n · PitWall

Tres flujos listos para importar en tu n8n local (`http://localhost:5678`).

| Archivo | Qué hace | Cuándo se usa |
|---|---|---|
| `01_ingesta_kb.json` | Lee `kb/processed/kb_all.jsonl`, genera embeddings con Ollama (`bge-m3`) e inserta en Qdrant | Una vez (o cuando cambie la base); alternativa: `scripts/ingest_ollama.py` |
| `02_pitwall_agente_rag.json` | Reformula la pregunta con el historial, busca en Qdrant, agente con memoria (y la búsqueda como herramienta extra) + evaluador. Es el RAG | Siempre activo: lo usa el chat de n8n y el front |
| `03_pitwall_directo.json` | Mismo modelo sin base de conocimiento | Comparación en la presentación |
| `04_actualizacion_kb.json` | Ejecuta `scripts/actualizar_kb.py --si-hace-falta`: refresca fuentes y sincroniza Qdrant de forma incremental | Cada 6 h y en segundo plano con cada pregunta (lo llama el 02) |

## 1. Credenciales (una sola vez)

Lo más fácil: `powershell -ExecutionPolicy Bypass -File scripts\n8n_import.ps1` importa `credentials_local.json` (Ollama y Qdrant, sin secretos) y los tres flujos con los ids que estos esperan.

A mano, en n8n: menú izquierdo → **Credentials** → **Add credential**.

1. **Ollama**: Base URL `http://127.0.0.1:11434`, sin API key. Nombre sugerido: `Ollama local`.
2. **Qdrant API**: URL `http://127.0.0.1:6333`, API key vacía. Nombre sugerido: `Qdrant local`.

## 2. Importar los flujos

Opción A (recomendada): en el editor, menú `...` (arriba a la derecha) → **Import from URL** → pega
`http://localhost:8766/01_ingesta_kb.json` (requiere el servidor `workflows` del `launch.json`, o `python -m http.server 8766 --directory workflows`).

Opción B: **Import from File** y elige el `.json`.

Si importaste a mano, abre cada nodo de Ollama / Qdrant y selecciona la credencial creada. Modelos: `qwen3:8b` en los nodos de chat (con *Think* desactivado) y `bge-m3` en los de embeddings.

## 3. Cargar la base de conocimiento

Abre `01 Ingesta`, pulsa **Execute workflow**. Tarda unos minutos (1.056 fragmentos, lotes de 40).
Verifica en `http://localhost:6333/dashboard#/collections/pitwall_kb` que hay 1.056 puntos.

Alternativa por consola (más rápida y reanudable):

```powershell
python scripts/ingest_ollama.py
```

## 4. Activar el agente

Abre `02 Agente RAG` y `03 Directo` y pon el interruptor **Active** en verde. Las URL quedan fijas:

- RAG: `http://localhost:5678/webhook/7f3b2c9e-1a5d-4e8f-9b6a-2c4d8e0f1a23/chat`
- Directo: `http://localhost:5678/webhook/c1d2e3f4-5a6b-4c7d-8e9f-0a1b2c3d4e5f/chat`

El chat de n8n del flujo 02 (botón **Open chat** o la URL pública del Chat Trigger) muestra la ejecución nodo por nodo: úsalo para la explicación técnica. El front (`front/index.html`) usa las mismas URL para el público no técnico.

## Flujo 04: actualización incremental

- Dos disparadores: `Schedule Trigger` (cada 6 h) y `Execute Workflow Trigger` (lo llama el nodo `Actualizar la base si hace falta` del flujo 02, con *Wait for sub-workflow* apagado, así la respuesta al usuario no espera).
- Un nodo `Execute Command`: `cd /d "{{ $env.PITWALL_ROOT }}" && python scripts\actualizar_kb.py --si-hace-falta`. n8n 2.x trae ese nodo excluido; `start_n8n.ps1` lo habilita con `NODES_EXCLUDE=[]` y define `PITWALL_ROOT`.
- El script imprime un JSON con `accion` (`omitido`, `sin_cambios`, `actualizado`, `error`), fragmentos nuevos/eliminados y fuentes que cambiaron.

## Detalles del flujo 02 con modelo local

- `Cargar historial` → `Preparar reformulación` → `¿Hay historial?` → `Reformular consulta` (solo si hay turnos previos) → `Armar consulta` → `Buscar en la base` (Qdrant, top 6) → `Armar contexto` → `Agente PitWall`.
- El agente recibe los fragmentos en su system prompt (`{{ $json.contexto_texto }}`) y la pregunta en `text`. Sigue teniendo `buscar_base_conocimiento` como herramienta.
- `¿Escribió la llamada como texto?`: si el modelo imita la traza `Calling buscar_base_conocimiento with input: ...` en vez de invocar la herramienta (n8n guarda ese texto en la memoria y los modelos pequeños lo copian), se reintenta con `Agente PitWall (reintento sin memoria)`.
- `Formatear respuesta` une fuentes y pasos de la búsqueda previa con los de la herramienta; si el modelo no entrega sugerencias, pone tres preguntas de arranque.
- `Respuesta final`: si no se afirmaron cifras y no hubo fragmentos, la evaluación es "Sin afirmaciones que verificar" (saludos y rechazos de temas ajenos).

## Contrato de respuesta (lo que consume el front)

```json
{
  "output": "texto en Markdown",
  "steps": [{ "tipo": "busqueda|herramienta|razonamiento|evaluacion", "titulo": "...", "detalle": "..." }],
  "sources": [{ "documento": "...", "articulo": "...", "titulo": "...", "pagina": "...", "url": "...", "extracto": "..." }],
  "suggestions": ["pregunta corta", "..."],
  "evaluacion": { "fundamentada": true, "confianza": 0.9, "comentario": "..." },
  "mode": "rag|directo",
  "sessionId": "..."
}
```
