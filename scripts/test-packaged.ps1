# End-to-end tests against the packaged backend (phase 08): the PyInstaller sidecar built by
# build-backend.ps1, launched like the desktop app does, with the fake CLI. It catches modules
# or data files missing from the build. Usage: npm run test:packaged (builds the sidecar first).
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$binary = Get-ChildItem (Join-Path $root 'desktop\src-tauri\binaries') -Filter 'agentic-os-backend-*.exe' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $binary) { throw 'No hay sidecar: ejecuta npm run build:backend' }

$env:AGENTIC_OS_E2E_BINARY = $binary.FullName
Write-Host "Backend empaquetado: $($binary.FullName)"
Push-Location $root
try {
    uv run --project backend pytest -p no:cacheprovider `
        backend/tests/test_scheduler_e2e.py `
        backend/tests/test_hitl_e2e.py `
        backend/tests/test_usage_e2e.py `
        backend/tests/test_resume_e2e.py
    if ($LASTEXITCODE -ne 0) { throw "los e2e empaquetados fallaron ($LASTEXITCODE)" }
}
finally {
    Pop-Location
    Remove-Item Env:AGENTIC_OS_E2E_BINARY
}
