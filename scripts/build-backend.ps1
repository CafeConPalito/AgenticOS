# Builds the backend sidecar with PyInstaller and copies it where Tauri expects it:
# desktop/src-tauri/binaries/agentic-os-backend-<target-triple>.exe
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$backend = Join-Path $root 'backend'
$binaries = Join-Path $root 'desktop\src-tauri\binaries'

Push-Location $backend
try {
    # Alembic loads env.py and the revisions from files at runtime: ship them as data.
    # Paths are absolute because --specpath changes the base for relative --add-data paths.
    $migrations = Join-Path $backend 'src\agentic_os\db\migrations'
    # pywinpty's conpty.dll starts OpenConsole.exe from its own folder, and PyInstaller only
    # picks up the DLLs: without these executables every run dies as soon as it starts.
    $winpty = Join-Path $backend '.venv\Lib\site-packages\winpty'
    # The models that ship inside the app (the OCR, ~18 MB): downloaded and checked here, with the
    # same pinned hashes the app uses, and added to the executable as `bundled_models`.
    $bundled = Join-Path $backend 'build\bundled'
    uv run python -m agentic_os.services.localmodels.stage $bundled
    if ($LASTEXITCODE -ne 0) { throw "No se pudieron preparar los modelos incluidos ($LASTEXITCODE)" }
    # RapidOCR's own settings files (its models are not taken: ours are the bundled_models).
    $rapidocr = Join-Path $backend '.venv\Lib\site-packages\rapidocr'
    uv run pyinstaller --noconfirm --clean --onefile --console `
        --add-binary "$winpty\OpenConsole.exe;winpty" `
        --add-binary "$winpty\winpty-agent.exe;winpty" `
        --name agentic-os-backend `
        --paths src `
        --collect-submodules uvicorn `
        --collect-submodules websockets `
        --collect-submodules mcp.server `
        --collect-submodules mcp.shared `
        --collect-submodules mcp.client `
        --collect-submodules keyring `
        --copy-metadata keyring `
        --collect-submodules agentic_os `
        --collect-submodules markitdown `
        --collect-data markitdown `
        --collect-all magika `
        --collect-all pypdfium2 `
        --collect-all pypdfium2_raw `
        --collect-data pptx `
        --collect-all trafilatura `
        --collect-all justext `
        --collect-all courlan `
        --collect-all htmldate `
        --collect-submodules rapidocr `
        --collect-submodules networkx `
        --add-data "$rapidocr\config.yaml;rapidocr" `
        --add-data "$rapidocr\default_models.yaml;rapidocr" `
        --exclude-module pandas `
        --exclude-module pdfminer `
        --add-data "$migrations;agentic_os\db\migrations" `
        --add-data "$bundled\models;bundled_models" `
        --distpath build\dist --workpath build\work --specpath build `
        packaging\entry.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }
}
finally {
    Pop-Location
}

$triple = 'x86_64-pc-windows-msvc'
if (Get-Command rustc -ErrorAction SilentlyContinue) {
    $triple = ((rustc -vV | Select-String '^host:').ToString() -split '\s+')[1]
}

New-Item -ItemType Directory -Force $binaries | Out-Null
$target = Join-Path $binaries "agentic-os-backend-$triple.exe"
Copy-Item (Join-Path $backend 'build\dist\agentic-os-backend.exe') $target -Force
# Code signing when a certificate is configured (a no-op otherwise, ADR 0012).
& (Join-Path $PSScriptRoot 'sign.ps1') $target
Write-Host "Sidecar listo: $target"
