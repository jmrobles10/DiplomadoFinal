# =====================================================================
#  PitWall · Detiene Qdrant de forma ordenada
#  Uso:  powershell -ExecutionPolicy Bypass -File scripts\stop_qdrant.ps1
#
#  Qdrant es una base de datos: si se termina a la fuerza no vacia sus registros
#  pendientes al disco y en el siguiente arranque puede quedarse bloqueada
#  intentando recuperarse. Aqui se le envia Ctrl+C, que es la forma en que espera
#  que se le pida cerrar, y solo se fuerza si no responde en 20 segundos.
# =====================================================================
$ErrorActionPreference = "SilentlyContinue"

$proc = Get-Process qdrant -ErrorAction SilentlyContinue
if (-not $proc) { Write-Host "Qdrant no estaba corriendo."; exit 0 }

# API de consola de Windows: adjuntarse a la consola del proceso y mandarle Ctrl+C
if (-not ("ConsolaWin32" -as [type])) {
  Add-Type -Namespace "" -Name ConsolaWin32 -MemberDefinition @"
[DllImport("kernel32.dll", SetLastError = true)] public static extern bool AttachConsole(uint dwProcessId);
[DllImport("kernel32.dll", SetLastError = true)] public static extern bool FreeConsole();
[DllImport("kernel32.dll", SetLastError = true)] public static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);
[DllImport("kernel32.dll", SetLastError = true)] public static extern bool GenerateConsoleCtrlEvent(uint dwCtrlEvent, uint dwProcessGroupId);
"@
}

foreach ($p in $proc) {
  Write-Host "Pidiendo a Qdrant (PID $($p.Id)) que cierre..."
  [ConsolaWin32]::FreeConsole() | Out-Null
  if ([ConsolaWin32]::AttachConsole([uint32]$p.Id)) {
    [ConsolaWin32]::SetConsoleCtrlHandler([IntPtr]::Zero, $true) | Out-Null
    [ConsolaWin32]::GenerateConsoleCtrlEvent(0, 0) | Out-Null   # 0 = CTRL_C_EVENT
    Start-Sleep -Milliseconds 400
    [ConsolaWin32]::FreeConsole() | Out-Null
    [ConsolaWin32]::SetConsoleCtrlHandler([IntPtr]::Zero, $false) | Out-Null
  }
}

# esperar hasta 20 s a que termine solo
for ($i = 0; $i -lt 20; $i++) {
  if (-not (Get-Process qdrant -ErrorAction SilentlyContinue)) {
    Write-Host "Qdrant cerro ordenadamente."
    exit 0
  }
  Start-Sleep -Seconds 1
}

Write-Host "Qdrant no cerro solo; se fuerza." -ForegroundColor Yellow
Get-Process qdrant -ErrorAction SilentlyContinue | Stop-Process -Force
exit 0
