# Build a Docker image used solely to transport the Windows application.

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path -LiteralPath 'dist\CiteFjord\CiteFjord.exe')) {
    throw 'Build the native app first with build-windows.ps1.'
}
if (-not (Test-Path -LiteralPath 'dist\CiteFjord\_internal\pymupdf\layout\resources\onnx\layout_rf2.4.1+imf1.yaml')) {
    throw 'PyMuPDF PDF resources are missing. Rebuild the native app first.'
}
if (-not (Test-Path -LiteralPath 'dist\CiteFjord\tessdata\eng.traineddata')) {
    throw 'English OCR data is missing. Rebuild the native app first.'
}
docker build -f Dockerfile.delivery -t citefjord-delivery:windows .
if ($LASTEXITCODE -ne 0) { throw 'Docker image build failed. Start Docker Desktop and retry.' }
docker save -o citefjord-delivery.tar citefjord-delivery:windows
if ($LASTEXITCODE -ne 0) { throw 'Docker image export failed.' }
Write-Host "Ready to send: $(Join-Path $PSScriptRoot 'citefjord-delivery.tar')"
