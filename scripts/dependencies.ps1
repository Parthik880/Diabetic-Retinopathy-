# Git Bash can inherit another PowerShell version's module path. Prefer the
# modules shipped with the PowerShell process actually executing this script.
$env:PSModulePath = (Join-Path $PSHOME 'Modules') + [IO.Path]::PathSeparator + $env:PSModulePath
function Read-RetinaGramCache {
    param([string]$BuildDirectory)
    $values = @{}
    $file = Join-Path $BuildDirectory 'CMakeCache.txt'
    if (Test-Path -LiteralPath $file) {
        foreach ($line in Get-Content -LiteralPath $file) {
            if ($line -match '^([^/#][^:]*):[^=]+=(.*)$') { $values[$Matches[1]] = $Matches[2] }
        }
    }
    return $values
}
function Test-RetinaGramSamePath {
    param([string]$Left, [string]$Right)
    if (-not $Left -or -not $Right) { return $false }
    return [IO.Path]::GetFullPath($Left).TrimEnd('\','/') -ieq [IO.Path]::GetFullPath($Right).TrimEnd('\','/')
}
function Find-RetinaGramVisualStudio {
    $vswhere = Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path -LiteralPath $vswhere) {
        $installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($installation) { return $installation }
    }
    if ($env:VSINSTALLDIR -and (Test-Path -LiteralPath (Join-Path $env:VSINSTALLDIR 'Common7\Tools\VsDevCmd.bat'))) { return $env:VSINSTALLDIR }
    throw 'Visual Studio x64 tools missing. Install VS2022 C++ Build Tools.'
}
function Get-RetinaGramDependencies {
    param([Parameter(Mandatory=$true)][string]$BuildDirectory)
    $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    $cache = Read-RetinaGramCache $BuildDirectory
    if ($cache.Count -and -not (Test-RetinaGramSamePath $cache['CMAKE_HOME_DIRECTORY'] $projectRoot)) { $cache = @{} }
    $qtRoot = $env:QT_ROOT
    if (-not $qtRoot -and $cache['Qt6_DIR']) { $qtRoot = [IO.Path]::GetFullPath((Join-Path $cache['Qt6_DIR'] '..\..\..')) }
    if (-not $qtRoot -or (-not $env:QT_ROOT -and -not (Test-Path -LiteralPath (Join-Path $qtRoot 'lib\cmake\Qt6\Qt6Config.cmake')))) {
        $qtRoot = $null
        $qtpaths = Get-Command qtpaths6.exe -ErrorAction SilentlyContinue
        if ($qtpaths) { $qtRoot = (& $qtpaths.Source --query QT_INSTALL_PREFIX | Select-Object -First 1) }
        $qtBase = Join-Path $env:SystemDrive 'Qt'
        if (-not $qtRoot -and (Test-Path -LiteralPath $qtBase)) {
            $qtRoot = Get-ChildItem -Path (Join-Path $qtBase '*\msvc*_64') -Directory -ErrorAction SilentlyContinue |
                Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'lib\cmake\Qt6\Qt6Config.cmake') } |
                Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
        }
    }
    if (-not $qtRoot -or -not (Test-Path -LiteralPath (Join-Path $qtRoot 'lib\cmake\Qt6\Qt6Config.cmake'))) { throw 'Qt MSVC x64 SDK missing. Set QT_ROOT.' }
    $torchRoot = $env:TORCH_ROOT
    if (-not $torchRoot) {
        $python = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($python) {
            try {
                $candidate = & $python.Source -c 'import pathlib, torch; print(pathlib.Path(torch.__file__).parent if torch.version.cuda else "")' 2>$null | Select-Object -Last 1
                if ($LASTEXITCODE -eq 0 -and $candidate -and (Test-Path -LiteralPath (Join-Path $candidate 'lib\torch_cuda.dll'))) { $torchRoot = $candidate }
            } catch { }
        }
        if (-not $torchRoot -and $cache['Torch_DIR']) { $torchRoot = [IO.Path]::GetFullPath((Join-Path $cache['Torch_DIR'] '..\..\..')) }
    }
    if (-not $torchRoot -or -not (Test-Path -LiteralPath (Join-Path $torchRoot 'share\cmake\Torch\TorchConfig.cmake')) -or -not (Test-Path -LiteralPath (Join-Path $torchRoot 'lib\torch_cuda.dll'))) { throw 'CUDA LibTorch SDK missing. Set TORCH_ROOT or activate CUDA-enabled PyTorch.' }
    $ortRoot = $env:ONNXRUNTIME_ROOT
    if (-not $ortRoot) {
        $localOrt = Join-Path $projectRoot 'build\toolchain\onnxruntime-gpu-windows-1.26.0'
        if (Test-Path -LiteralPath $localOrt) { $ortRoot = $localOrt } else { $ortRoot = $cache['ONNXRUNTIME_ROOT'] }
    }
    $ortNative = $null
    if ($ortRoot) {
        $ortNative = @((Join-Path $ortRoot 'runtimes\win-x64\native'), (Join-Path $ortRoot 'lib')) |
            Where-Object { Test-Path -LiteralPath (Join-Path $_ 'onnxruntime.dll') } | Select-Object -First 1
    }
    if (-not $ortNative) { throw 'ONNX Runtime GPU SDK missing. Set ONNXRUNTIME_ROOT or extract official Windows GPU NuGet to build/toolchain/onnxruntime-gpu-windows-1.26.0. See README Dependency setup.' }
    $cudaRoot = $env:CUDA_PATH
    if (-not $cudaRoot) {
        $nvcc = Get-Command nvcc.exe -ErrorAction SilentlyContinue
        $nvccFile = if ($nvcc) { $nvcc.Source } elseif ($cache['CUDA_NVCC_EXECUTABLE']) { $cache['CUDA_NVCC_EXECUTABLE'] } else { $cache['CMAKE_CUDA_COMPILER'] }
        if ($nvccFile -and (Test-Path -LiteralPath $nvccFile)) { $cudaRoot = Split-Path (Split-Path $nvccFile -Parent) -Parent }
        $cudaBase = Join-Path $env:ProgramFiles 'NVIDIA GPU Computing Toolkit\CUDA'
        if (-not $cudaRoot -and (Test-Path -LiteralPath $cudaBase)) {
            $cudaRoot = Get-ChildItem -LiteralPath $cudaBase -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin\nvcc.exe') } | Sort-Object Name -Descending | Select-Object -First 1 -ExpandProperty FullName
        }
    }
    if (-not $cudaRoot -or -not (Test-Path -LiteralPath (Join-Path $cudaRoot 'bin\nvcc.exe'))) { throw 'CUDA Toolkit missing. Set CUDA_PATH.' }
    [pscustomobject]@{ QtRoot=$qtRoot; TorchRoot=$torchRoot; TorchDirectory=(Join-Path $torchRoot 'lib'); OrtRoot=$ortRoot; OrtDirectory=$ortNative; CudaRoot=$cudaRoot; CudaDirectory=(Join-Path $cudaRoot 'bin') }
}
