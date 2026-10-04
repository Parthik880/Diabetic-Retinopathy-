param(
    [string]$BuildDirectory = (Join-Path $PSScriptRoot '..\build\ninja'),
    [string]$Destination = (Join-Path $PSScriptRoot '..\build\package')
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$executable = Join-Path $BuildDirectory 'RetinaGram.exe'
if (-not (Test-Path -LiteralPath $executable)) { throw "Build RetinaGram.exe first: $executable" }
$builtAt = (Get-Item -LiteralPath $executable).LastWriteTimeUtc
$nativeSources = @(Get-ChildItem -LiteralPath (Join-Path $project 'src'), (Join-Path $project 'include') -File -Recurse) +
    @(Get-Item -LiteralPath (Join-Path $project 'CMakeLists.txt'))
if ($nativeSources | Where-Object { $_.LastWriteTimeUtc -gt $builtAt }) {
    throw 'Native source is newer than RetinaGram.exe. Rebuild in the VS x64 environment before deploying.'
}

. (Join-Path $PSScriptRoot 'runtime-environment.ps1')
$runtime = Set-RetinaGramRuntimeEnvironment -BuildDirectory $BuildDirectory
$qt = $runtime.QtRoot
$torch = $runtime.TorchDirectory
$ort = $runtime.OrtDirectory
$cuda = $runtime.CudaDirectory
$command = Get-Command dumpbin.exe -ErrorAction SilentlyContinue
$dumpbin = if ($command) { $command.Source } else { $null }
if (-not $dumpbin) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path -LiteralPath $vswhere) {
        $installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($installation) {
            $dumpbin = Get-ChildItem -LiteralPath (Join-Path $installation 'VC\Tools\MSVC') -Filter dumpbin.exe -Recurse |
                Where-Object { $_.FullName -match 'Hostx64\\x64' } |
                Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
        }
    }
}
if (-not $dumpbin) { throw 'dumpbin.exe is required to collect native DLL dependencies.' }
foreach ($directory in @($qt, $torch, $ort, $cuda)) {
    if (-not (Test-Path -LiteralPath $directory)) { throw "Missing runtime dependency directory: $directory" }
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
Copy-Item -LiteralPath $executable -Destination $Destination -Force
if ((Get-FileHash -LiteralPath $executable).Hash -ne
    (Get-FileHash -LiteralPath (Join-Path $Destination 'RetinaGram.exe')).Hash) {
    throw 'Packaged executable does not match the development build.'
}
Copy-Item -LiteralPath (Join-Path $project 'assets') -Destination $Destination -Recurse -Force
$models = Join-Path $Destination 'checkpoints'
New-Item -ItemType Directory -Force -Path $models | Out-Null
$configFile = Join-Path $project 'config\models.json'
$modelConfig = Get-Content -LiteralPath $configFile -Raw | ConvertFrom-Json
if ($modelConfig.version -ne 1 -or $modelConfig.checkpoints_directory -ne '../checkpoints') {
    throw 'Deployment requires model config version 1 with checkpoints_directory ../checkpoints.'
}
$configDestination = Join-Path $Destination 'config'
New-Item -ItemType Directory -Force -Path $configDestination | Out-Null
Copy-Item -LiteralPath $configFile -Destination (Join-Path $configDestination 'models.json') -Force
$modelNames = foreach ($stage in @('iqa', 'restoration', 'grading', 'lesion')) {
    $name = $modelConfig.$stage.model
    if (-not $modelConfig.$stage.enabled -or -not $name -or $name -match '[/\\:]' -or $name -in @('.', '..')) {
        throw "Invalid configured deployment model for $stage."
    }
    $name
}
foreach ($name in ($modelNames | Select-Object -Unique)) {
    Copy-Item -LiteralPath (Join-Path $project "checkpoints\$name") -Destination $models -Force
}

$env:PATH = "$($qt)\bin;$ort;$torch;$cuda;$env:PATH"
& (Join-Path $qt 'bin\windeployqt.exe') --release --no-translations --no-compiler-runtime `
    --no-opengl-sw --no-system-d3d-compiler --dir $Destination (Join-Path $Destination 'RetinaGram.exe')
if ($LASTEXITCODE -ne 0) { throw "windeployqt failed with exit code $LASTEXITCODE" }

$available = @{}
foreach ($directory in @($ort, $torch, $cuda, (Join-Path $qt 'bin'))) {
    Get-ChildItem -LiteralPath $directory -Filter '*.dll' -File | ForEach-Object {
        if (-not $available.ContainsKey($_.Name.ToLowerInvariant())) {
            $available[$_.Name.ToLowerInvariant()] = $_.FullName
        }
    }
}

$queue = [System.Collections.Generic.Queue[string]]::new()
$queue.Enqueue((Join-Path $Destination 'RetinaGram.exe'))
# ONNX Runtime loads CUDA providers dynamically, so seed their dependency closure.
foreach ($name in @('onnxruntime_providers_cuda.dll', 'onnxruntime_providers_shared.dll')) {
    $path = $available[$name]
    if (-not $path) { throw "Missing ONNX Runtime provider: $name" }
    Copy-Item -LiteralPath $path -Destination $Destination -Force
    $queue.Enqueue((Join-Path $Destination $name))
}
# cuDNN loads its component engines with LoadLibrary, so they are absent from
# the static import table scanned below. Keep all components from one build.
Get-ChildItem -LiteralPath $torch -Filter 'cudnn*.dll' -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $Destination -Force
    $queue.Enqueue((Join-Path $Destination $_.Name))
}
Get-ChildItem -LiteralPath $torch -Filter 'nvrtc*.dll' -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $Destination -Force
    $queue.Enqueue((Join-Path $Destination $_.Name))
}

$visited = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
while ($queue.Count -gt 0) {
    $file = $queue.Dequeue()
    if (-not $visited.Add($file)) { continue }
    $dependencies = & $dumpbin /dependents $file 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect DLL dependencies: $file" }
    foreach ($line in $dependencies) {
        if ($line -notmatch '^\s+([a-zA-Z0-9_.-]+\.dll)\s*$') { continue }
        $name = $Matches[1]
        $target = Join-Path $Destination $name
        if (-not (Test-Path -LiteralPath $target)) {
            $source = $available[$name.ToLowerInvariant()]
            if (-not $source) { continue } # Windows and MSVC redistributable DLLs remain system prerequisites.
            Copy-Item -LiteralPath $source -Destination $target -Force
        }
        $queue.Enqueue($target)
    }
}

$files = Get-ChildItem -LiteralPath $Destination -File -Recurse
$bytes = ($files | Measure-Object -Property Length -Sum).Sum
Write-Host "Packaged $($files.Count) files ($([math]::Round($bytes / 1GB, 2)) GiB) at $Destination"
Write-Host 'Production model files are only under checkpoints/; no Python or Node runtime is included.'
