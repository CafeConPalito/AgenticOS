# Runs the local CI gate (lint + all tests) and prints a summary.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

$steps = @(
    @{ Name = 'Lint backend (ruff)';           Cmd = 'npm run lint:backend' },
    @{ Name = 'Lint frontend (eslint+prettier)'; Cmd = 'npm run lint:frontend' },
    @{ Name = 'Tests backend (pytest)';        Cmd = 'npm run test:backend' },
    @{ Name = 'Tests frontend (vitest)';       Cmd = 'npm run test:frontend' }
)

$results = @()
foreach ($step in $steps) {
    Write-Host "`n=== $($step.Name) ===" -ForegroundColor Cyan
    cmd /c $step.Cmd
    $results += [pscustomobject]@{ Paso = $step.Name; Resultado = $(if ($LASTEXITCODE -eq 0) { 'OK' } else { 'FALLO' }) }
}

Write-Host "`n=== Resumen ===" -ForegroundColor Cyan
$results | Format-Table -AutoSize
if ($results.Resultado -contains 'FALLO') { exit 1 }
