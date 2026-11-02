﻿# Opens a Windows Sandbox (a clean Windows with no development tools) with the release
# installer mapped read-only, to check that the app installs without admin rights, starts,
# creates its data folder and guides to install the CLIs (CA1 of phase 08, CA7 of phase 25).
#
# Needs Windows 11 Pro with the «Windows Sandbox» optional feature (enable it once, as admin:
#   Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All
# and reboot).
# Usage:
#   scripts/clean-machine.ps1                      # the local build (npm run build:desktop)
#   scripts/clean-machine.ps1 -Url <installer URL> -Sha256 <hash>
#                                                  # downloads it (e.g. from a GitHub release)
#                                                  # and checks its SHA-256 first
param(
    [string]$Url,
    [string]$Sha256
)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
if (-not (Test-Path "$env:SystemRoot\System32\WindowsSandbox.exe")) {
    throw 'Windows Sandbox no está activado (ver la cabecera de este script)'
}

if ($Url) {
    if (-not $Sha256) { throw 'Con -Url hace falta -Sha256 (el valor publicado en la release)' }
    $bundle = Join-Path $env:TEMP 'agentic-os-clean-machine'
    Remove-Item $bundle -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory $bundle | Out-Null
    $name = [Uri]::UnescapeDataString(([Uri]$Url).Segments[-1])
    $target = Join-Path $bundle $name
    Write-Host "Descargando $Url"
    Invoke-WebRequest -Uri $Url -OutFile $target -UseBasicParsing
    $actual = (Get-FileHash $target -Algorithm SHA256).Hash
    if ($actual -ne $Sha256.Trim().ToUpperInvariant()) {
        throw "El SHA-256 no coincide: esperado $Sha256, descargado $actual"
    }
    Write-Host "SHA-256 correcto: $actual"
    $installer = Get-Item $target
}
else {
    $bundle = Join-Path $root 'desktop\src-tauri\target\release\bundle\nsis'
    $installer = Get-ChildItem $bundle -Filter '*-setup.exe' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $installer) { throw "No hay instalador en $bundle (npm run build:desktop)" }
}

$config = @"
<Configuration>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>$bundle</HostFolder>
      <SandboxFolder>C:\Users\WDAGUtilityAccount\Desktop\instalador</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>explorer.exe C:\Users\WDAGUtilityAccount\Desktop\instalador</Command>
  </LogonCommand>
</Configuration>
"@
$file = Join-Path $env:TEMP 'agentic-os-clean-machine.wsb'
Set-Content -Path $file -Value $config -Encoding utf8
Write-Host "Abriendo Windows Sandbox con $($installer.Name)"
Start-Process $file
