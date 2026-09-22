@echo off
setlocal
title PitWall - apagado
set "WAIT=%SystemRoot%\System32\timeout.exe"
echo Deteniendo PitWall. Ollama se deja corriendo.
echo.

REM Qdrant es una base de datos: si se termina a la fuerza no vacia sus registros
REM pendientes al disco y en el siguiente arranque puede quedarse bloqueada.
echo [1/3] Qdrant, cierre ordenado...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_qdrant.ps1"

echo [2/3] n8n y front...
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -match 'n8n' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue };" ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'serve_cors' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo [3/3] Ventanas de servicio...
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'powershell.exe' -and ($_.CommandLine -match 'start_qdrant' -or $_.CommandLine -match 'start_n8n') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo.
echo Listo.
"%WAIT%" /t 3 /nobreak >nul
