# Instalar PitWall en otro PC (Windows)

Qué viaja en el repositorio y qué no:

| Viaja en git | No viaja (por diseño) | Cómo se repone |
|---|---|---|
| Código, scripts, front, guías, flujos de n8n (`workflows/*.json`) | Instalación de Node, n8n y Python | Instalarlos (paso 0) |
| Base de conocimiento procesada (`kb/processed/kb_all.jsonl`) | PDF y JSON crudos (`kb/raw`) | `python scripts/download_sources.py` (solo si quieres reconstruir) |
| Vectores exportados (`kb/processed/vectors.f32` + índice) | Binario y datos de Qdrant (`tools/`) | `download_qdrant.py` + `qdrant_restore.py` (o `ingest_ollama.py`, que los recalcula en local en pocos minutos) |
| | Ollama y sus modelos (`qwen3:8b`, `bge-m3`) | `winget install Ollama.Ollama` + `ollama pull` (lo hace `setup_windows.ps1`) |
| Documentación | Base local de n8n (`.n8n/`): usuario, credenciales, flujos importados | Crear usuario, credenciales e importar los 3 flujos |
| | Fotos y video de Envato (`front/assets/envato/`) | Copiarlos a mano (licencia personal) |

## 0. Requisitos

- Windows 10/11, sin necesidad de administrador.
- Node.js 22 o 24 y Python 3.12 en el PATH.
- Ollama (`winget install Ollama.Ollama`; el instalador lo hace si falta). **No hace falta ninguna API key: todo es local y gratis.**
- Recomendado una GPU con 8 GB de VRAM (probado con RTX 4060 y 32 GB de RAM). Sin GPU funciona, pero cada respuesta tarda bastante más.

## 1. Clonar e instalar

```powershell
git clone https://github.com/jmrobles10/DiplomadoFinal.git
cd DiplomadoFinal
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
```

El script instala Ollama y descarga los modelos `bge-m3` (embeddings) y `qwen3:8b` (generador/evaluador), instala n8n,
descarga Qdrant, lo arranca, crea la colección `pitwall_kb` (1024 dimensiones) y vectoriza los 1.056 fragmentos con
`bge-m3` en local (o restaura `kb/processed/vectors.f32` si ya fue exportado con ese modelo). Por último arranca n8n.

## 2. Configurar n8n (una sola vez)

1. Abre `http://localhost:5678` y crea el usuario dueño local (correo, nombre y contraseña; queda solo en tu máquina).
2. Ejecuta:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\n8n_import.ps1
   ```

   Importa las credenciales `Ollama local` (`http://127.0.0.1:11434`) y `Qdrant local` (`http://127.0.0.1:6333`) desde
   `workflows/credentials_local.json` (no contienen secretos) y los tres flujos. Los flujos ya referencian esas credenciales
   por id (`ollama-local`, `qdrant-local`), así que no hay que tocar ningún nodo. Se usa `127.0.0.1` y no `localhost`
   porque Node resuelve `localhost` como IPv6 y Ollama/Qdrant escuchan en IPv4.

   Alternativa manual: **Credentials → Add credential** (`Ollama` y `Qdrant API`) y menú `...` → **Import from file** con cada JSON, eligiendo la credencial en cada nodo.
3. Reinicia n8n (Ctrl+C y `start_n8n.ps1`). El importador deja activos `02`, `03` y `04`; si importaste a mano, publica esos tres. Las URL de los webhooks quedan iguales a las del front porque los ids están fijos en los JSON.

## 3. Front

```powershell
python scripts\serve_cors.py 8765 front
```

Abre `http://localhost:8765`. Copia las fotos y el video de Envato a `front/assets/envato/` con los nombres que indica `front/README.md`.

## 4. Verificar

- `http://localhost:6333/dashboard#/collections/pitwall_kb` debe mostrar 1.056 puntos de 1024 dimensiones.
- `python scripts\ingest_ollama.py --query "puntos por ganar una carrera"` debe devolver la guía de puntos y el artículo A2.2 del reglamento.
- En el front, pregunta "¿Cuántos puntos da ganar una carrera en 2026?" y abre "¿Cómo llegué a esta respuesta?".
- La primera respuesta tarda más (Ollama carga el modelo en la GPU); las siguientes salen en 10-30 s con una RTX 4060.

## Arranque diario

Ollama arranca solo con Windows (icono en la bandeja). Si no, `ollama serve`.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_qdrant.ps1   # ventana 1
powershell -ExecutionPolicy Bypass -File scripts\start_n8n.ps1     # ventana 2
python scripts\serve_cors.py 8765 front                            # ventana 3
```

## Actualizar la base de conocimiento

- **Automático**: el flujo `04` ejecuta `python scripts\actualizar_kb.py --si-hace-falta` cada 6 h y en segundo plano con cada pregunta. Revisa la API de la temporada, Wikipedia y la página de reglamentos de la FIA, y sincroniza Qdrant de forma incremental (inserta lo nuevo, elimina lo obsoleto, no toca lo demás). Requiere que n8n arranque con `scripts\start_n8n.ps1` (define `PITWALL_ROOT` y habilita el nodo Execute Command). Estado: `python scripts\actualizar_kb.py --estado`.
- **A mano**: `python scripts\actualizar_kb.py` (o `--forzar` para reconstruir todo).
- Documentos propios: agrega un `.md` en `kb/docs_es/` y ejecuta `python scripts\actualizar_kb.py --forzar` (o `build_kb.py` + `ingest_ollama.py`).
- `scripts/ingest_qdrant.py` es la versión anterior con Gemini (3072 dimensiones); solo sirve si recreas la colección con `qdrant_setup.py --recreate --dims 3072`.
- Después de ingestar, `python scripts/qdrant_export.py` regenera los vectores exportados para el repositorio.
