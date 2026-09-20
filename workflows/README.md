# Flujos de n8n · PitWall

Tres flujos listos para importar en tu n8n local (`http://localhost:5678`).

| Archivo | Qué hace | Cuándo se usa |
|---|---|---|
| `01_ingesta_kb.json` | Lee `kb/processed/kb_all.jsonl`, genera embeddings con Gemini e inserta en Qdrant | Una vez (o cuando cambie la base) |
| `02_pitwall_agente_rag.json` | Agente con memoria + herramienta de búsqueda en Qdrant + evaluador. Es el RAG | Siempre activo: lo usa el chat de n8n y el front |
| `03_pitwall_directo.json` | Mismo modelo sin base de conocimiento | Comparación en la presentación |

## 1. Credenciales (una sola vez)

En n8n: menú izquierdo → **Credentials** → **Add credential**.

1. **Google Gemini(PaLM) Api**: pega tu API key de Google AI Studio. Nombre sugerido: `Gemini PitWall`.
2. **Qdrant API**: URL `http://localhost:6333`, API key vacía. Nombre sugerido: `Qdrant local`.

## 2. Importar los flujos

Opción A (recomendada): en el editor, menú `...` (arriba a la derecha) → **Import from URL** → pega
`http://localhost:8766/01_ingesta_kb.json` (requiere el servidor `workflows` del `launch.json`, o `python -m http.server 8766 --directory workflows`).

Opción B: **Import from File** y elige el `.json`.

Después de importar, abre cada nodo de Gemini / Qdrant y selecciona la credencial creada.

## 3. Cargar la base de conocimiento

Abre `01 Ingesta`, pulsa **Execute workflow**. Tarda unos minutos (992 fragmentos, lotes de 40 con pausa).
Verifica en `http://localhost:6333/dashboard#/collections/pitwall_kb` que hay ~992 puntos.

Alternativa por consola (más rápida y reanudable):

```powershell
$env:GEMINI_API_KEY = "tu-key"
python scripts/ingest_qdrant.py
```

## 4. Activar el agente

Abre `02 Agente RAG` y `03 Directo` y pon el interruptor **Active** en verde. Las URL quedan fijas:

- RAG: `http://localhost:5678/webhook/7f3b2c9e-1a5d-4e8f-9b6a-2c4d8e0f1a23/chat`
- Directo: `http://localhost:5678/webhook/c1d2e3f4-5a6b-4c7d-8e9f-0a1b2c3d4e5f/chat`

El chat de n8n del flujo 02 (botón **Open chat** o la URL pública del Chat Trigger) muestra la ejecución nodo por nodo: úsalo para la explicación técnica. El front (`front/index.html`) usa las mismas URL para el público no técnico.

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
