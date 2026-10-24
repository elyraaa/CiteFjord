param(
    [Parameter(Mandatory = $true)]
    [string]$ImageTar
)

$ErrorActionPreference = 'Stop'
$archive = (Resolve-Path -LiteralPath $ImageTar -ErrorAction Stop).Path
$tar = (Get-Command tar.exe -ErrorAction Stop).Source
$destination = Join-Path (Get-Location).Path 'CiteFjord'
if (Test-Path -LiteralPath $destination) { throw "Destination already exists: $destination" }

$scratch = Join-Path ([IO.Path]::GetTempPath()) ("CiteFjord-delivery-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch -ErrorAction Stop | Out-Null
try {
    & $tar -xf $archive -C $scratch manifest.json
    if ($LASTEXITCODE -ne 0) { throw 'Could not read Docker archive manifest.' }
    $manifest = Get-Content -LiteralPath (Join-Path $scratch 'manifest.json') -Raw | ConvertFrom-Json
    if ($manifest.Count -ne 1 -or $manifest[0].RepoTags -notcontains 'citefjord-delivery:windows') {
        throw 'This is not the CiteFjord delivery archive.'
    }

    $appLayer = $null
    foreach ($layer in $manifest[0].Layers) {
        if ($layer -notmatch '^blobs/sha256/[0-9a-f]{64}$') { throw 'Unexpected Docker layer path.' }
        & $tar -xf $archive -C $scratch $layer
        if ($LASTEXITCODE -ne 0) { throw "Could not read Docker layer: $layer" }
        $layerFile = Join-Path $scratch ($layer -replace '/', [IO.Path]::DirectorySeparatorChar)
        $contents = & $tar -tf $layerFile
        if ($LASTEXITCODE -ne 0) { throw "Could not inspect Docker layer: $layer" }
        if ($contents -contains 'delivery/CiteFjord/CiteFjord.exe') {
            $appLayer = $layerFile
            break
        }
    }
    if (-not $appLayer) { throw 'The archive does not contain CiteFjord.exe.' }

    $stage = Join-Path $scratch 'stage'
    New-Item -ItemType Directory -Path $stage -ErrorAction Stop | Out-Null
    & $tar -xf $appLayer -C $stage delivery/CiteFjord
    if ($LASTEXITCODE -ne 0) { throw 'Could not extract the Windows application.' }
    $extracted = Join-Path $stage 'delivery\CiteFjord'
    if (-not (Test-Path -LiteralPath (Join-Path $extracted 'CiteFjord.exe'))) {
        throw 'The extracted application is incomplete.'
    }
    Move-Item -LiteralPath $extracted -Destination $destination -ErrorAction Stop
    Write-Host "Application extracted to $destination"
    Write-Host 'Run CiteFjord.exe after installing Ollama and qwen2.5-coder:7b.'
}
finally {
    $resolvedScratch = [IO.Path]::GetFullPath($scratch)
    $resolvedTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (-not $resolvedScratch.StartsWith($resolvedTemp, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing to remove a temporary folder outside the system temp directory.'
    }
    Remove-Item -LiteralPath $resolvedScratch -Recurse -Force -ErrorAction SilentlyContinue
}
