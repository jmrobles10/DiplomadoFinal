# Instalar PitWall en otro PC (Windows)

Qué viaja en el repositorio y qué no:

| Viaja en git | No viaja (por diseño) | Cómo se repone |
|---|---|---|
| Código, scripts, front, guías, flujos de n8n (`workflows/*.json`) | Instalación de Node, n8n y Python | Instalarlos (paso 0) |
| Base de conocimiento procesada (`kb/processed/kb_all.jsonl`) | PDF y JSON crudos (`kb/raw`) | `python scripts/download_sources.py` (solo si quieres reconstruir) |
| Vectores exportados (`kb/processed/vectors.f32` + índice) | Binario y datos de Qdrant (`tools/`) | `download_qdrant.py` + `qdrant_restore.py` |
| Documentación | Base local de n8n (`.n8n/`): usuario, credenciales, flujos importados | Crear usuario, credenciales e importar los 3 flujos |
| | Fotos y video de Envato (`front/assets/envato/`) | Copiarlos a mano (licencia personal) |

## 0. Requisitos

- Windows 10/11, sin necesidad de administrador.
- Node.js 24 y Python 3.12 en el PATH.
- Una API key de Google AI Studio (Gemini). La capa gratuita de usuarios nuevos solo permite 20 respuestas al día con `gemini-3.6-flash`; con facturación activa el proyecto cuesta centavos.

## 1. Clonar e instalar

```powershell
git clone https://github.com/jmrobles10/DiplomadoFinal.git
cd DiplomadoFinal
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
```

El script instala n8n, descarga Qdrant, lo arranca, crea la colección `pitwall_kb`, restaura los 1.056 vectores
desde `kb/processed/vectors.f32` (sin llamar a Gemini) y arranca n8n.

## 2. Configurar n8n (una sola vez)

1. Abre `http://localhost:5678` y crea el usuario dueño local (correo, nombre y contraseña; queda solo en tu máquina).
2. **Credentials → Add credential**:
   - `Google Gemini(PaLM) Api` → pega tu key → nombre `Gemini PitWall`.
   - `Qdrant API` → URL `http://127.0.0.1:6333`, sin key → nombre `Qdrant local`. Usa `127.0.0.1`, no `localhost`: Node 24 resuelve `localhost` como IPv6 y Qdrant escucha en IPv4.
3. Importa los flujos: en un workflow nuevo, menú `...` → **Import** → **From file** → `workflows/02_pitwall_agente_rag.json`; repite con `03` y `01`.
   Los nodos de Gemini y Qdrant traen el nombre de la credencial pero el id es de la instalación original: abre cada uno y elige la credencial en el desplegable.
4. Pulsa **Publish** en `02` y en `03`. Las URL de los webhooks quedan iguales a las del front porque los ids están fijos en los JSON.

## 3. Front

```powershell
python scripts\serve_cors.py 8765 front
```

Abre `http://localhost:8765`. Copia las fotos y el video de Envato a `front/assets/envato/` con los nombres que indica `front/README.md`.

## 4. Verificar

- `http://localhost:6333/dashboard#/collections/pitwall_kb` debe mostrar 1.056 puntos.
- En el front, pregunta "¿Cuántos puntos da ganar una carrera en 2026?" y abre "¿Cómo llegué a esta respuesta?".
- `python scripts\costo_gemini.py` estima el gasto acumulado de la API.

## Arranque diario

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_qdrant.ps1   # ventana 1
powershell -ExecutionPolicy Bypass -File scripts\start_n8n.ps1     # ventana 2
python scripts\serve_cors.py 8765 front                            # ventana 3
```

## Actualizar la base de conocimiento

- Documentos propios: agrega un `.md` en `kb/docs_es/`, luego `python scripts/build_kb.py` y `python scripts/ingest_qdrant.py` (usa Gemini solo para lo nuevo).
- Reglamento o temporada: `python scripts/download_sources.py`, `extract_pdf_text.py`, `build_kb.py`, `ingest_qdrant.py`.
- Después de ingestar, `python scripts/qdrant_export.py` regenera los vectores exportados para el repositorio.
