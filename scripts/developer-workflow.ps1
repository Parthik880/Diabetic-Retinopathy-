param(
    [ValidateSet('Run','Deploy')][string]$Mode = 'Run',
    [switch]$NoBuild, [switch]$Clean, [switch]$Validate, [switch]$ModelInfo
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'dependencies.ps1')
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$buildDirectory = Join-Path $projectRoot 'build\ninja'
$configFile = Join-Path $projectRoot 'config\models.json'
if (-not (Test-Path -LiteralPath $configFile -PathType Leaf)) { throw 'Required config/models.json is missing.' }
$config = Get-Content -LiteralPath $configFile -Raw | ConvertFrom-Json
if ($config.version -ne 1 -or $config.checkpoints_directory -ne '../src/checkpoints') { throw 'Expected config version 1 and ../src/checkpoints.' }
foreach ($stage in @('iqa','restoration','grading','lesion')) {
    $name = $config.$stage.model
    if (-not $name -or $name -match '[/\\:]' -or $name -in @('.','..')) { throw "Invalid configured model filename for $stage" }
    $modelPath = Join-Path $projectRoot "src\checkpoints\$name"
    if (-not (Test-Path -LiteralPath $modelPath -PathType Leaf)) { throw "Required $stage model missing: $modelPath" }
}
if ($NoBuild -and ($Clean -or $Mode -eq 'Deploy')) { throw '--no-build cannot combine with --clean or deployment.' }
if ($Validate -and $ModelInfo) { throw 'Select only one of --validate and --model-info.' }
$cache = Read-RetinaGramCache $buildDirectory
$stale = $cache.Count -and -not (Test-RetinaGramSamePath $cache['CMAKE_HOME_DIRECTORY'] $projectRoot)
if ($NoBuild -and $stale) { throw 'Build belongs to another checkout. Run ./run.sh without --no-build.' }
if (($Clean -or $stale) -and (Test-Path -LiteralPath $buildDirectory)) {
    $target = [IO.Path]::GetFullPath($buildDirectory)
    $allowed = [IO.Path]::GetFullPath((Join-Path $projectRoot 'build')) + '\'
    if (-not $target.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase) -or (Split-Path $target -Leaf) -ne 'ninja') { throw 'Unsafe build path.' }
    $running = @(Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -eq 'RetinaGram.exe' -and $_.ExecutablePath -and $_.ExecutablePath.StartsWith($target + '\', [StringComparison]::OrdinalIgnoreCase)) -or
        ($_.Name -in @('cmake.exe','cl.exe','link.exe') -and $_.CommandLine -and $_.CommandLine.Contains($target)) -or $_.Name -eq 'ninja.exe'
    })
    if ($running.Count) { throw 'Close the local app and wait for active build processes before cleaning. No process was terminated.' }
    # Archive bounded compiler data; never clean the sibling toolchain.
    $archive = Join-Path $projectRoot ('build\ninja.previous-' + [guid]::NewGuid().ToString('N'))
    if (-not [IO.Path]::GetFullPath($archive).StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe archive path.' }
    Move-Item -LiteralPath $target -Destination $archive
    Write-Host 'Archived previous compiler tree; configuring fresh build/ninja.'
}
if (-not $NoBuild) {
    $vsRoot = Find-RetinaGramVisualStudio
    $vsDevCmd = Join-Path $vsRoot 'Common7\Tools\VsDevCmd.bat'
    $vsCommand = 'call "' + $vsDevCmd + '" -no_logo -arch=x64 -host_arch=x64 >nul && set'
    $environmentLines = & $env:ComSpec /d /c $vsCommand
    if ($LASTEXITCODE -ne 0) { throw 'VS x64 environment initialization failed.' }
    foreach ($entry in $environmentLines) {
        if ($entry -match '^([^=]+)=(.*)$') {
            $name = $Matches[1]; $value = $Matches[2]
            if ($name -in @('PATH','INCLUDE','LIB','LIBPATH','VisualStudioVersion','Platform','CommandPromptType','UniversalCRTSdkDir','UCRTVersion') -or $name -match '^(VS|VC|WindowsSdk|WindowsSDK)') { [Environment]::SetEnvironmentVariable($name,$value,'Process') }
        }
    }
    $cmake = Get-Command cmake.exe -ErrorAction SilentlyContinue
    $cmakePath = if ($cmake) { $cmake.Source } else { Join-Path $vsRoot 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe' }
    $ninja = Get-Command ninja.exe -ErrorAction SilentlyContinue
    $ninjaPath = if ($ninja) { $ninja.Source } else { Join-Path $vsRoot 'Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe' }
    foreach ($tool in @($cmakePath,$ninjaPath)) { if (-not (Test-Path -LiteralPath $tool)) { throw "Required tool missing: $tool" } }
    $runtime = Get-RetinaGramDependencies $buildDirectory
    New-Item -ItemType Directory -Path $buildDirectory -Force | Out-Null
    # CMake cheaply checks changed inputs and current SDK overrides.
    & $cmakePath -S $projectRoot -B $buildDirectory -G Ninja '-DCMAKE_BUILD_TYPE=Release' '-UONNXRUNTIME_INCLUDE_DIR' '-UONNXRUNTIME_LIBRARY' "-DCMAKE_MAKE_PROGRAM=$ninjaPath" "-DCMAKE_PREFIX_PATH=$($runtime.QtRoot);$($runtime.TorchRoot)" "-DQt6_DIR=$($runtime.QtRoot)\lib\cmake\Qt6" "-DTorch_DIR=$($runtime.TorchRoot)\share\cmake\Torch" "-DONNXRUNTIME_ROOT=$($runtime.OrtRoot)" "-DCUDAToolkit_ROOT=$($runtime.CudaRoot)"
    if ($LASTEXITCODE -ne 0) { throw 'CMake configure failed.' }
    & $cmakePath --build $buildDirectory --parallel 3
    if ($LASTEXITCODE -ne 0) { throw 'Release build failed.' }
}
. (Join-Path $PSScriptRoot 'runtime-environment.ps1')
$null = Set-RetinaGramRuntimeEnvironment $buildDirectory
$executable = Join-Path $buildDirectory 'RetinaGram.exe'
if (-not (Test-Path -LiteralPath $executable)) { throw 'RetinaGram.exe missing; build first.' }
if ($Mode -eq 'Deploy') {
    $packageRoot = Join-Path $projectRoot 'build\package'
    if (Test-Path -LiteralPath $packageRoot) {
        $target = [IO.Path]::GetFullPath($packageRoot)
        $allowed = [IO.Path]::GetFullPath((Join-Path $projectRoot 'build')) + '\'
        if (-not $target.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase) -or (Split-Path $target -Leaf) -ne 'package') { throw 'Unsafe package path.' }
        $running = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($target+'\',[StringComparison]::OrdinalIgnoreCase) })
        if ($running.Count) { throw 'Close the existing packaged app before deploying.' }
        $archive = Join-Path $projectRoot ('build\package.previous-' + [guid]::NewGuid().ToString('N'))
        if (-not [IO.Path]::GetFullPath($archive).StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe package archive path.' }
        Move-Item -LiteralPath $target -Destination $archive
    }
    & (Join-Path $PSScriptRoot 'deploy-windows.ps1') -BuildDirectory $buildDirectory
    $executable = Join-Path $packageRoot 'RetinaGram.exe'
    $requiredFiles = @('RetinaGram.exe','config\models.json') + @('iqa','restoration','grading','lesion' | ForEach-Object { 'src\checkpoints\' + $config.$_.model })
    foreach ($file in $requiredFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $packageRoot $file) -PathType Leaf)) { throw "Package file missing: $file" }
    }
    $savedPath = $env:PATH; $savedRoot = $env:RETINAGRAM_ROOT
    try {
        $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
        Remove-Item Env:RETINAGRAM_ROOT -ErrorAction SilentlyContinue
        & $executable --validate-models | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Packaged validation failed.' }
    } finally {
        $env:PATH = $savedPath
        if ($null -eq $savedRoot) { Remove-Item Env:RETINAGRAM_ROOT -ErrorAction SilentlyContinue } else { $env:RETINAGRAM_ROOT=$savedRoot }
    }
    Write-Host 'Deployment verified: packaged models validated with Windows-only PATH.'
} elseif ($Validate) { & $executable --validate-models | Out-Host; exit $LASTEXITCODE }
elseif ($ModelInfo) { & $executable --model-info | Out-Host; exit $LASTEXITCODE }
else { Start-Process -FilePath $executable -WorkingDirectory $projectRoot }
