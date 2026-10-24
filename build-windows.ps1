param(
    [switch]$SkipModelCache
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv and install requirements first.' }
if (-not $SkipModelCache) {
    & $python -c 'from src.config import make_embeddings; make_embeddings(offline=False)'
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the embedding model for the Windows release.' }
}
& $python -m PyInstaller --noconfirm --onedir --windowed --name CiteFjord `
    --additional-hooks-dir build_hooks `
    --collect-all chromadb `
    --collect-all sentence_transformers `
    --collect-all langchain_huggingface `
    --collect-all langchain_chroma `
    --collect-data pymupdf `
    desktop_app.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
$release = Join-Path $PSScriptRoot 'dist\CiteFjord'
$layoutSource = Join-Path $PSScriptRoot '.venv\Lib\site-packages\pymupdf\layout'
$layoutTarget = Join-Path $release '_internal\pymupdf\layout'
if (-not (Test-Path -LiteralPath (Join-Path $layoutSource 'resources\onnx\layout_rf2.4.1+imf1.yaml'))) {
    throw 'PyMuPDF layout resources are missing from the build environment.'
}
New-Item -ItemType Directory -Path $layoutTarget -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $layoutSource 'resources') -Destination $layoutTarget -Recurse -Force
New-Item -ItemType Directory -Path (Join-Path $layoutTarget 'onnx') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $layoutSource 'onnx\global_config.yaml') -Destination (Join-Path $layoutTarget 'onnx\global_config.yaml') -Force
if (-not (Test-Path -LiteralPath (Join-Path $layoutTarget 'resources\onnx\layout_rf2.4.1+imf1.yaml'))) {
    throw 'PyMuPDF layout resources were not copied into the Windows release.'
}
if (-not $SkipModelCache -and (Test-Path -LiteralPath 'model_cache')) {
    Copy-Item -LiteralPath 'model_cache' -Destination (Join-Path $release 'model_cache') -Recurse -Force
}
Copy-Item -LiteralPath 'README.md' -Destination (Join-Path $release 'README.md') -Force
$tessdata = Join-Path $PSScriptRoot 'tessdata'
if (-not (Test-Path -LiteralPath (Join-Path $tessdata 'eng.traineddata'))) {
    throw 'English OCR data is missing from the source package.'
}
Copy-Item -LiteralPath $tessdata -Destination (Join-Path $release 'tessdata') -Recurse -Force
Write-Host "Native app ready in $release"
