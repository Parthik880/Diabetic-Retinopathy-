# Shared by local launch, benchmark and deployment scripts. No machine paths.
function Set-RetinaGramRuntimeEnvironment {
    param([Parameter(Mandatory=$true)][string]$BuildDirectory)
    $cacheFile = Join-Path $BuildDirectory 'CMakeCache.txt'
    if (-not (Test-Path -LiteralPath $cacheFile)) { throw "Configure CMake first: $cacheFile" }
    $cache = @{}
    foreach ($line in Get-Content -LiteralPath $cacheFile) {
        if ($line -match '^([^/#][^:]*):[^=]+=(.*)$') { $cache[$Matches[1]] = $Matches[2] }
    }
    $qt = $env:QT_ROOT
    if (-not $qt -and $cache['Qt6_DIR']) { $qt = [IO.Path]::GetFullPath((Join-Path $cache['Qt6_DIR'] '..\..\..')) }
    $torchRoot = $env:TORCH_ROOT
    if (-not $torchRoot -and $cache['Torch_DIR']) { $torchRoot = [IO.Path]::GetFullPath((Join-Path $cache['Torch_DIR'] '..\..\..')) }
    $ortRoot = $env:ONNXRUNTIME_ROOT
    if (-not $ortRoot) { $ortRoot = $cache['ONNXRUNTIME_ROOT'] }
    $cuda = $env:CUDA_PATH
    if ($cuda) { $cuda = Join-Path $cuda 'bin' }
    elseif ($cache['CUDAToolkit_NVCC_EXECUTABLE']) { $cuda = Split-Path $cache['CUDAToolkit_NVCC_EXECUTABLE'] -Parent }
    elseif ($cache['CUDA_NVCC_EXECUTABLE']) { $cuda = Split-Path $cache['CUDA_NVCC_EXECUTABLE'] -Parent }
    elseif ($cache['CMAKE_CUDA_COMPILER']) { $cuda = Split-Path $cache['CMAKE_CUDA_COMPILER'] -Parent }
    elseif ($cache['CUDAToolkit_BIN_DIR']) { $cuda = $cache['CUDAToolkit_BIN_DIR'] }
    if (-not $qt -or -not $torchRoot -or -not $ortRoot -or -not $cuda) {
        throw 'Missing dependencies. Configure CMake or set QT_ROOT, TORCH_ROOT, ONNXRUNTIME_ROOT and CUDA_PATH.'
    }
    $torch = Join-Path $torchRoot 'lib'
    $ort = @((Join-Path $ortRoot 'runtimes\win-x64\native'), (Join-Path $ortRoot 'lib')) |
        Where-Object { Test-Path -LiteralPath (Join-Path $_ 'onnxruntime.dll') } | Select-Object -First 1
    if (-not $ort) { throw "Cannot find onnxruntime.dll under $ortRoot" }
    foreach ($directory in @((Join-Path $qt 'bin'), $torch, $ort, $cuda)) {
        if (-not (Test-Path -LiteralPath $directory -PathType Container)) { throw "Missing runtime directory: $directory" }
    }
    # Windows can resolve another imported ORT before consulting PATH. Keep the
    # selected SDK's complete ORT provider set beside the development executable.
    Get-ChildItem -LiteralPath $ort -Filter 'onnxruntime*.dll' -File | ForEach-Object {
        $target = Join-Path $BuildDirectory $_.Name
        if (-not (Test-Path -LiteralPath $target) -or
            (Get-FileHash -LiteralPath $target).Hash -ne (Get-FileHash -LiteralPath $_.FullName).Hash) {
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
    }
    # Prefer the selected SDK's DLLs over older ORT copies on the ambient PATH.
    $env:PATH = "$(Join-Path $qt 'bin');$ort;$torch;$cuda;$env:PATH"
    [pscustomobject]@{ QtRoot=$qt; TorchDirectory=$torch; OrtDirectory=$ort; CudaDirectory=$cuda }
}
