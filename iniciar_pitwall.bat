@echo off
setlocal enabledelayedexpansion
title PitWall - arranque
cd /d "%~dp0"
set "WAIT=%SystemRoot%\System32\timeout.exe"

echo ============================================================
echo  PitWall + Podium  -  arranque completo en local
echo ============================================================
echo.

REM ---------- 1. Ollama, modelos de IA ----------
curl -s -m 5 http://127.0.0.1:11434/api/tags >nul 2>&1
if %errorlevel%==0 (
  echo [1/4] Ollama ya esta corriendo
) else (
  echo [1/4] Arrancando Ollama...
  set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
  if exist "!OLLAMA_EXE!" (
    start "PitWall - Ollama" /min "!OLLAMA_EXE!" serve
  ) else (
    start "PitWall - Ollama" /min ollama serve
  )
)

REM ---------- 2. Qdrant, base vectorial ----------
REM Puede quedar vivo pero sin responder tras un cierre brusco. En ese caso se
REM reinicia, porque si no cada pregunta se queda esperando hasta agotar el tiempo.
curl -s -m 8 http://localhost:6333/ >nul 2>&1
if %errorlevel%==0 (
  echo [2/4] Qdrant ya esta corriendo y responde
) else (
  echo [2/4] Arrancando Qdrant...
  powershell -NoProfile -Command "if (Get-Process qdrant -ErrorAction SilentlyContinue) { Write-Host '      estaba vivo pero sin responder: se reinicia' }"
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_qdrant.ps1" >nul 2>&1
  start "PitWall - Qdrant" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_qdrant.ps1"
)

REM ---------- 3. n8n, agentes ----------
curl -s -m 5 http://localhost:5678/healthz >nul 2>&1
if %errorlevel%==0 (
  echo [3/4] n8n ya esta corriendo
) else (
  echo [3/4] Arrancando n8n, tarda 30-60 s...
  start "PitWall - n8n" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_n8n.ps1"
)

REM ---------- 4. Front, pagina web ----------
curl -s -m 5 http://localhost:8765/ >nul 2>&1
if %errorlevel%==0 (
  echo [4/4] Front ya esta corriendo
) else (
  echo [4/4] Arrancando el front en http://localhost:8765 ...
  start "PitWall - Front" /min python "%~dp0scripts\serve_cors.py" 8765 "%~dp0front"
)

echo.
echo Esperando a que todo responda...
set /a intentos=0
:esperar
set /a intentos+=1
set listo=1
curl -s -m 3 http://127.0.0.1:11434/api/tags >nul 2>&1 || set listo=0
curl -s -m 3 http://localhost:6333/ >nul 2>&1 || set listo=0
curl -s -m 3 http://localhost:5678/healthz >nul 2>&1 || set listo=0
curl -s -m 3 http://localhost:8765/ >nul 2>&1 || set listo=0
if %listo%==1 goto ok
if %intentos% geq 60 goto fallo
<nul set /p "=."
"%WAIT%" /t 2 /nobreak >nul
goto esperar

:ok
echo.
echo.
echo  Todo listo:
echo    PitWall  -^>  http://localhost:8765
echo    Podium   -^>  http://localhost:8765/podium.html
echo    n8n      -^>  http://localhost:5678
echo    Qdrant   -^>  http://localhost:6333/dashboard
echo.
echo  Para que las respuestas salgan rapido, cierra antes las aplicaciones que usan la
echo  tarjeta grafica: fondo de pantalla animado, Teams, Chrome, WhatsApp y PowerPoint.
echo.
echo  Las ventanas minimizadas "PitWall - ..." son los servicios: no las cierres.
echo  Para apagar todo: detener_pitwall.bat
"%WAIT%" /t 4 /nobreak >nul
start "" http://localhost:8765
"%WAIT%" /t 5 /nobreak >nul
exit /b 0

:fallo
echo.
echo  Algo no respondio a tiempo. Revisa las ventanas minimizadas "PitWall - ..." para ver el error.
echo  Ollama: http://127.0.0.1:11434   Qdrant: http://localhost:6333   n8n: http://localhost:5678   Front: http://localhost:8765
pause
exit /b 1
