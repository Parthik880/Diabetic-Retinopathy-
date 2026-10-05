. (Join-Path $PSScriptRoot 'dependencies.ps1')
function Set-RetinaGramRuntimeEnvironment {
    param([Parameter(Mandatory=$true)][string]$BuildDirectory)
    $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    $cache = Read-RetinaGramCache $BuildDirectory
    if (-not $cache.Count -or -not (Test-RetinaGramSamePath $cache['CMAKE_HOME_DIRECTORY'] $projectRoot)) { throw 'Missing or stale CMake cache. Run ./run.sh to configure this checkout.' }
    $runtime = Get-RetinaGramDependencies $BuildDirectory
    foreach ($directory in @((Join-Path $runtime.QtRoot 'bin'), $runtime.TorchDirectory, $runtime.OrtDirectory, $runtime.CudaDirectory)) {
        if (-not (Test-Path -LiteralPath $directory -PathType Container)) { throw "Missing runtime directory: $directory" }
    }
    Get-ChildItem -LiteralPath $runtime.OrtDirectory -Filter 'onnxruntime*.dll' -File | ForEach-Object {
        $target = Join-Path $BuildDirectory $_.Name
        if (-not (Test-Path -LiteralPath $target) -or (Get-FileHash -LiteralPath $target).Hash -ne (Get-FileHash -LiteralPath $_.FullName).Hash) { Copy-Item -LiteralPath $_.FullName -Destination $target -Force }
    }
    $env:PATH = "$(Join-Path $runtime.QtRoot 'bin');$($runtime.OrtDirectory);$($runtime.TorchDirectory);$($runtime.CudaDirectory);$env:PATH"
    return $runtime
}