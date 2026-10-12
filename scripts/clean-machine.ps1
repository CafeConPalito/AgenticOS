# Opens a Windows Sandbox (a clean Windows with no development tools) with the release
# installer mapped read-only, to check CA1 of phase 08: the app installs without admin rights,
# starts, creates its data folder and guides to install the CLIs.
#
# Needs Windows 11 Pro with the «Windows Sandbox» optional feature (enable it once, as admin:
#   Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All
# and reboot). Usage: npm run build:desktop, then scripts/clean-machine.ps1
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$bundle = Join-Path $root 'desktop\src-tauri\target\release\bundle\nsis'
$installer = Get-ChildItem $bundle -Filter '*-setup.exe' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $installer) { throw "No hay instalador en $bundle (npm run build:desktop)" }
if (-not (Test-Path "$env:SystemRoot\System32\WindowsSandbox.exe")) {
    throw 'Windows Sandbox no está activado (ver la cabecera de este script)'
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
