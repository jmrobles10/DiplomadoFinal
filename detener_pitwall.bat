@echo off
title PitWall - apagado
echo Deteniendo PitWall: Qdrant, n8n y el front. Ollama se deja corriendo.
powershell -NoProfile -Command ^
  "Get-Process qdrant -ErrorAction SilentlyContinue | Stop-Process -Force;" ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'n8n' -and $_.Name -match 'node' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue };" ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'serve_cors.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue };" ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'powershell.exe' -and ($_.CommandLine -match 'start_qdrant.ps1' -or $_.CommandLine -match 'start_n8n.ps1') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Listo.
"%SystemRoot%\System32\timeout.exe" /t 3 /nobreak >nul
