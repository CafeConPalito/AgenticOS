# Builds the release app and its NSIS installer (the sidecar must be built first:
# npm run build:desktop does both). With AGENTIC_OS_SIGN_CERT set, the app and the installer
# are signed too (tauri.sign.conf.json → sign.ps1); without it nothing is signed, because
# Tauri's bundler requires signtool as soon as a sign command is configured.
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$configs = @('--config', 'src-tauri/tauri.release.conf.json')
if ($env:AGENTIC_OS_SIGN_CERT) {
    $configs += @('--config', 'src-tauri/tauri.sign.conf.json')
    Write-Host 'Firmando con el certificado de AGENTIC_OS_SIGN_CERT'
}
Push-Location (Join-Path $root 'desktop')
try {
    npx tauri build @configs
    if ($LASTEXITCODE -ne 0) { throw "tauri build falló ($LASTEXITCODE)" }
}
finally {
    Pop-Location
}
