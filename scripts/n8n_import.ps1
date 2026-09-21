# =====================================================================
#  PitWall · Importa en n8n las credenciales locales (Ollama y Qdrant) y los tres flujos
#  Uso:  powershell -ExecutionPolicy Bypass -File scripts\n8n_import.ps1
#  Requisito: haber arrancado n8n al menos una vez (para que exista su base de datos). No hace falta tener usuario todavía.
#  Los ids de las credenciales (ollama-local, qdrant-local) son los que traen los flujos, así que
#  después de importar no hay que tocar ningún nodo.
# =====================================================================
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$env:N8N_USER_FOLDER = Join-Path $root ".n8n"      # misma base de datos que usa start_n8n.ps1

if (-not (Test-Path (Join-Path $env:N8N_USER_FOLDER ".n8n\database.sqlite"))) {
  Write-Host "Todavía no existe la base de n8n. Arranca n8n una vez (scripts\start_n8n.ps1) y espera a ver 'Editor is now accessible'." -ForegroundColor Yellow
  exit 1
}

Write-Host "[1/3] Credenciales Ollama local + Qdrant local" -ForegroundColor Cyan
n8n import:credentials --input="$root\workflows\credentials_local.json"

Write-Host "[2/3] Flujos 01, 02, 03 y 04" -ForegroundColor Cyan
foreach ($f in "01_ingesta_kb.json", "02_pitwall_agente_rag.json", "03_pitwall_directo.json", "04_actualizacion_kb.json") {
  n8n import:workflow --input="$root\workflows\$f"
}

Write-Host "[3/3] Activando los flujos 02 (RAG), 03 (directo) y 04 (actualización)" -ForegroundColor Cyan
n8n update:workflow --id=PitWall02AgenteRAG --active=true
n8n update:workflow --id=PitWall03Directo --active=true
n8n update:workflow --id=PitWall04ActualizacionKB --active=true

Write-Host @"

Listo. Si n8n estaba corriendo, reinicialo para que vea los cambios (Ctrl+C en su ventana y start_n8n.ps1 de nuevo).
Los webhooks del front quedan activos. Para ver los flujos en el editor abre http://localhost:5678 (la primera vez pide crear el usuario dueño local).
"@ -ForegroundColor Green
