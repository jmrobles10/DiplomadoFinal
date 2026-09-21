# =====================================================================
#  PitWall · Instalación en un PC nuevo (Windows 10/11)
#  Uso: clonar el repo y ejecutar desde su raíz:
#       powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
#  Requisitos previos: Node.js 24 (https://nodejs.org) y Python 3.12 (https://python.org) en el PATH.
# =====================================================================
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
Write-Host "== PitWall · setup en $root" -ForegroundColor Cyan

function Need($cmd, $hint) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { Write-Host "Falta '$cmd'. $hint" -ForegroundColor Red; exit 1 }
}
Need node "Instala Node.js 24 desde https://nodejs.org"
Need npm "Viene con Node.js"
Need python "Instala Python 3.12 desde https://python.org (marca 'Add to PATH')"

Write-Host "`n[1/7] Dependencias de Python (solo pypdf, para reconstruir la base si hace falta)"
python -m pip install --quiet --user pypdf

Write-Host "`n[2/7] Ollama (modelos de IA locales y gratuitos)"
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
  winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements --silent
  $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
$ollamaExe = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $ollamaExe) { $ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" }
try { Invoke-RestMethod http://127.0.0.1:11434/api/tags | Out-Null } catch { Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden; Start-Sleep -Seconds 5 }
& $ollamaExe pull bge-m3        # embeddings multilingües (1,2 GB)
& $ollamaExe pull qwen3:8b      # generador y evaluador (5,2 GB; cabe en una GPU de 8 GB)

Write-Host "`n[3/7] n8n (instalación global con npm, sin permisos de administrador)"
if (-not (Get-Command n8n -ErrorAction SilentlyContinue)) { npm install -g n8n --no-fund --no-audit } else { Write-Host "n8n ya está instalado: $(n8n --version)" }

Write-Host "`n[4/7] Qdrant (binario oficial para Windows)"
python scripts\download_qdrant.py

Write-Host "`n[5/7] Arrancando Qdrant en segundo plano"
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","$root\scripts\start_qdrant.ps1" -WindowStyle Minimized
Start-Sleep -Seconds 6
python scripts\qdrant_setup.py

Write-Host "`n[6/7] Vectorizando la base de conocimiento con Ollama (bge-m3, local; 2-5 minutos)"
$idx = "kb\processed\vectors_index.json"
$restaurable = (Test-Path $idx) -and ((Get-Content $idx -Raw | ConvertFrom-Json).model -eq "bge-m3")
if ($restaurable) { python scripts\qdrant_restore.py } else { python scripts\ingest_ollama.py }

Write-Host "`n[7/7] Arrancando n8n en segundo plano (la primera vez tarda 2-3 minutos)"
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","$root\scripts\start_n8n.ps1" -WindowStyle Minimized

Write-Host @"

Listo. Pasos manuales que quedan (una sola vez, ver docs/INSTALACION.md):
  1. Abre http://localhost:5678 y crea el usuario dueño local.
  2. Ejecuta  powershell -ExecutionPolicy Bypass -File scripts\n8n_import.ps1  (importa credenciales Ollama/Qdrant y los 3 flujos).
  3. Reinicia n8n, abre los flujos 02 y 03 y pulsa Publish.
  4. Front: python scripts\serve_cors.py 8765 front  ->  http://localhost:8765
  Sin API keys ni costos: todo corre en este PC.
"@ -ForegroundColor Green
