# =====================================================================
#  PitWall · Arranca Qdrant (base vectorial persistente) en local
#  Uso:  powershell -ExecutionPolicy Bypass -File scripts\start_qdrant.ps1
#  API:   http://localhost:6333      Panel: http://localhost:6333/dashboard
# =====================================================================
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$exe = Join-Path $root "tools\qdrant\qdrant.exe"
$storage = Join-Path $root "tools\qdrant\storage"
$snapshots = Join-Path $root "tools\qdrant\snapshots"

if (-not (Test-Path $exe)) { Write-Error "No existe $exe. Descarga Qdrant para Windows en tools\qdrant\"; exit 1 }
New-Item -ItemType Directory -Force $storage | Out-Null
New-Item -ItemType Directory -Force $snapshots | Out-Null

$env:QDRANT__STORAGE__STORAGE_PATH = $storage      # los vectores quedan en disco: no se pierden al reiniciar
$env:QDRANT__STORAGE__SNAPSHOTS_PATH = $snapshots
$env:QDRANT__SERVICE__HTTP_PORT = "6333"
$env:QDRANT__SERVICE__GRPC_PORT = "6334"
$env:QDRANT__TELEMETRY_DISABLED = "true"

Write-Host "PitWall :: Qdrant en http://localhost:6333  (datos en $storage)"
Set-Location (Split-Path $exe)
& $exe
if ($LASTEXITCODE -ne 0) {
  Write-Host "`nEl servicio termino con error (codigo $LASTEXITCODE). Revisa el mensaje de arriba." -ForegroundColor Red
  Read-Host "Pulsa Enter para cerrar"
}
