# Signs a binary with the code-signing certificate named by AGENTIC_OS_SIGN_CERT (the SHA-1
# thumbprint of a certificate in the user's store). Without it nothing is signed: v1.0 ships
# unsigned (ADR 0012) and this step is ready for when there is a certificate.
#
# Called by Tauri for the app and the installer (bundle.windows.signCommand in
# tauri.release.conf.json) and by build-backend.ps1 for the sidecar.
param([Parameter(Mandatory = $true)][string]$Path)
$ErrorActionPreference = 'Stop'

if (-not $env:AGENTIC_OS_SIGN_CERT) {
    Write-Host "Sin certificado (AGENTIC_OS_SIGN_CERT): no se firma $Path"
    exit 0
}

$signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue
if (-not $signtool) {
    $kits = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
    $signtool = Get-ChildItem $kits -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\x64\\' } |
        Sort-Object FullName -Descending |
        Select-Object -First 1
}
if (-not $signtool) { throw 'signtool.exe no encontrado (instala el Windows SDK)' }

$timestamp = if ($env:AGENTIC_OS_SIGN_TIMESTAMP) { $env:AGENTIC_OS_SIGN_TIMESTAMP } else { 'http://timestamp.digicert.com' }
& $signtool.Source sign /fd SHA256 /sha1 $env:AGENTIC_OS_SIGN_CERT /tr $timestamp /td SHA256 $Path
if ($LASTEXITCODE -ne 0) { throw "signtool falló ($LASTEXITCODE) al firmar $Path" }
Write-Host "Firmado: $Path"
