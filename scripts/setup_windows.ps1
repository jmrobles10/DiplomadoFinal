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

Write-Host "`n[1/6] Dependencias de Python (solo pypdf, para reconstruir la base si hace falta)"
python -m pip install --quiet --user pypdf

Write-Host "`n[2/6] n8n (instalación global con npm, sin permisos de administrador)"
if (-not (Get-Command n8n -ErrorAction SilentlyContinue)) { npm install -g n8n --no-fund --no-audit } else { Write-Host "n8n ya está instalado: $(n8n --version)" }

Write-Host "`n[3/6] Qdrant (binario oficial para Windows)"
python scripts\download_qdrant.py

Write-Host "`n[4/6] Arrancando Qdrant en segundo plano"
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","$root\scripts\start_qdrant.ps1" -WindowStyle Minimized
Start-Sleep -Seconds 6
python scripts\qdrant_setup.py

Write-Host "`n[5/6] Restaurando los vectores ya calculados (sin gastar API)"
if (Test-Path "kb\processed\vectors.f32") { python scripts\qdrant_restore.py } else { Write-Host "No hay vectores exportados; usa  python scripts\ingest_qdrant.py  con GEMINI_API_KEY" -ForegroundColor Yellow }

Write-Host "`n[6/6] Arrancando n8n en segundo plano (la primera vez tarda 2-3 minutos)"
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","$root\scripts\start_n8n.ps1" -WindowStyle Minimized

Write-Host @"

Listo. Pasos manuales que quedan (una sola vez, ver docs/INSTALACION.md):
  1. Abre http://localhost:5678 y crea el usuario dueño local.
  2. Credentials: 'Google Gemini(PaLM) Api' con tu key (nombre: Gemini PitWall) y 'Qdrant API' con URL http://127.0.0.1:6333 (nombre: Qdrant local).
  3. Importa workflows/01, 02 y 03 (menú ... > Import > From file), abre los nodos de Gemini y Qdrant y elige las credenciales, y publica 02 y 03.
  4. Front: python scripts\serve_cors.py 8765 front  ->  http://localhost:8765
"@ -ForegroundColor Green
