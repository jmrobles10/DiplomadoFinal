# =====================================================================
#  PitWall · Arranca n8n en local (sin Docker, sin cuenta en la nube)
#  Uso:  powershell -ExecutionPolicy Bypass -File scripts\start_n8n.ps1
#  Editor: http://localhost:5678
# =====================================================================
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

$env:N8N_PORT = "5678"
$env:N8N_HOST = "localhost"
$env:N8N_PROTOCOL = "http"
$env:N8N_WEBHOOK_URL = "http://localhost:5678/"       # base de las URL de webhook (test y producción)
$env:N8N_SECURE_COOKIE = "false"                      # necesario al usar http en localhost
$env:GENERIC_TIMEZONE = "America/Bogota"
$env:TZ = "America/Bogota"
$env:N8N_DIAGNOSTICS_ENABLED = "false"                # sin telemetría
$env:N8N_VERSION_NOTIFICATIONS_ENABLED = "false"
$env:N8N_RUNNERS_TASK_TIMEOUT = "300"                 # 5 min por nodo Code (la ingesta usa lotes largos)
$env:N8N_DEFAULT_BINARY_DATA_MODE = "filesystem"
# n8n crea dentro de esta carpeta su propia subcarpeta ".n8n" (base SQLite, credenciales cifradas, logs).
# Queda en el proyecto: <repo>\.n8n\.n8n
$env:N8N_USER_FOLDER = Join-Path $root ".n8n"
$env:PITWALL_ROOT = $root                          # lo usa el flujo 04 para ejecutar scripts\actualizar_kb.py
$env:N8N_RESTRICT_FILE_ACCESS_TO = $root              # permite al nodo de archivos leer la base de conocimiento del proyecto
$env:N8N_COMMUNITY_PACKAGES_ENABLED = "true"
$env:N8N_BLOCK_ENV_ACCESS_IN_NODE = "false"          # permite usar {{ $env.PITWALL_ROOT }} en el flujo 04
$env:NODES_EXCLUDE = "[]"                            # n8n 2.x excluye Execute Command por defecto; el flujo 04 lo necesita para correr actualizar_kb.py
$env:N8N_LOG_LEVEL = "info"

New-Item -ItemType Directory -Force $env:N8N_USER_FOLDER | Out-Null
Write-Host "PitWall :: n8n en http://localhost:5678  (datos en $($env:N8N_USER_FOLDER))"
Write-Host "La primera vez tarda 2-3 minutos creando la base de datos; espera a ver 'Editor is now accessible'."
n8n start
if ($LASTEXITCODE -ne 0) {
  Write-Host "`nEl servicio termino con error (codigo $LASTEXITCODE). Revisa el mensaje de arriba." -ForegroundColor Red
  Read-Host "Pulsa Enter para cerrar"
}
