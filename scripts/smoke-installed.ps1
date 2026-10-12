# Smoke test of the installed app (phase 08): it starts, its backend answers, the data folder
# and the database are where they should be, and closing the window leaves no backend process,
# no CLI it launched and no PyInstaller _MEI folder behind. Prints the startup time.
#
# Usage: npm run smoke:installed  (or: scripts/smoke-installed.ps1 -App "C:\…\Agentic OS.exe")
param([string]$App)
$ErrorActionPreference = 'Stop'

function Find-App {
    $folder = Join-Path $env:LOCALAPPDATA 'Agentic OS'
    $exe = Get-ChildItem $folder -Filter '*.exe' -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch 'uninstall' -and $_.Name -notmatch 'agentic-os-backend' } |
        Select-Object -First 1
    if (-not $exe) { throw "No encuentro la app instalada en $folder (usa -App)" }
    return $exe.FullName
}

function Backend-Processes { @(Get-Process -Name 'agentic-os-backend*' -ErrorAction SilentlyContinue) }
function Cli-Count { @(Get-Process -Name 'claude', 'agy' -ErrorAction SilentlyContinue).Count }
function Mei-Folders { @(Get-ChildItem $env:TEMP -Directory -Filter '_MEI*' -ErrorAction SilentlyContinue).Count }

function Data-Dir {
    $home_ = Join-Path $env:APPDATA 'AgenticOS'
    $pointer = Join-Path $home_ 'location.json'
    if (Test-Path $pointer) {
        $moved = (Get-Content $pointer -Raw | ConvertFrom-Json).data_dir
        if ($moved) { return $moved }
    }
    return $home_
}

$results = New-Object System.Collections.Generic.List[object]
function Check([string]$Name, [bool]$Ok, [string]$Detail = '') {
    $results.Add([pscustomobject]@{ Comprobacion = $Name; Ok = $(if ($Ok) { 'OK' } else { 'FALLO' }); Detalle = $Detail })
}

if (-not $App) { $App = Find-App }
if (Backend-Processes) { throw 'Ya hay un backend de Agentic OS en marcha: cierra la app antes de la prueba' }
$clisBefore = Cli-Count
$meiBefore = Mei-Folders

Write-Host "Arrancando $App"
$clock = [System.Diagnostics.Stopwatch]::StartNew()
$process = Start-Process -FilePath $App -PassThru

# The backend listens on a free port: find it through the backend processes' sockets.
$url = $null
$version = $null
while ($clock.Elapsed.TotalSeconds -lt 60 -and -not $url) {
    Start-Sleep -Milliseconds 250
    $pids = (Backend-Processes).Id
    if (-not $pids) { continue }
    $ports = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $pids -contains $_.OwningProcess -and $_.LocalAddress -eq '127.0.0.1' } |
        Select-Object -ExpandProperty LocalPort -Unique
    foreach ($port in $ports) {
        try {
            $health = Invoke-RestMethod "http://127.0.0.1:$port/api/health" -TimeoutSec 2
            $url = "http://127.0.0.1:$port"
            $version = $health.version
        } catch { }
    }
}
$startup = $clock.Elapsed.TotalSeconds
Check 'El backend responde' ([bool]$url) $(if ($url) { "$url · v$version" } else { 'sin respuesta en 60 s' })
Check 'Arranque (< 5 s hasta /api/health)' ($url -and $startup -lt 5) ('{0:N1} s' -f $startup)

$data = Data-Dir
Check 'Carpeta de datos' (Test-Path $data) $data
Check 'Base de datos' (Test-Path (Join-Path $data 'agentic-os.db')) (Join-Path $data 'agentic-os.db')
Check 'Log del backend' (Test-Path (Join-Path $data 'logs\backend.log')) (Join-Path $data 'logs\backend.log')

Write-Host 'Cerrando la ventana'
$null = $process.CloseMainWindow()
$process.WaitForExit(15000) | Out-Null
$closed = [System.Diagnostics.Stopwatch]::StartNew()
while ((Backend-Processes) -and $closed.Elapsed.TotalSeconds -lt 15) { Start-Sleep -Milliseconds 250 }
Check 'La app se cierra' $process.HasExited
Check 'Sin procesos del backend' (-not (Backend-Processes)) ('{0:N1} s tras cerrar' -f $closed.Elapsed.TotalSeconds)
Check 'Sin CLIs nuevos' ((Cli-Count) -le $clisBefore) ("antes $clisBefore, después $(Cli-Count)")
Start-Sleep -Seconds 1
Check 'Sin carpetas _MEI nuevas' ((Mei-Folders) -le $meiBefore) ("antes $meiBefore, después $(Mei-Folders)")

$results | Format-Table -AutoSize | Out-String | Write-Host
if ($results | Where-Object { $_.Ok -ne 'OK' }) { exit 1 }
