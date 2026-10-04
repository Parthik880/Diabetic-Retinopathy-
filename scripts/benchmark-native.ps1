param(
    [ValidateRange(1,20)][int]$Iterations = 3,
    [Parameter(Mandatory=$true)][string]$GoodImage,
    [Parameter(Mandatory=$true)][string]$UsableImage,
    [string]$BuildDirectory = (Join-Path $PSScriptRoot '..\build\ninja'),
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\build\validation\benchmark_native')
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$output = $OutputDirectory
New-Item -ItemType Directory -Force -Path $output | Out-Null
Set-Content -LiteralPath (Join-Path $output 'summary.jsonl') -Value ''
. (Join-Path $PSScriptRoot 'runtime-environment.ps1')
$null = Set-RetinaGramRuntimeEnvironment -BuildDirectory $BuildDirectory

$cases = @(
    @{ Name = 'good'; Image = (Resolve-Path -LiteralPath $GoodImage).Path },
    @{ Name = 'usable'; Image = (Resolve-Path -LiteralPath $UsableImage).Path }
)
foreach ($case in $cases) {
    $baseline = [int](@(& nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)[0])
    $json = Join-Path $output "$($case.Name).json"
    $errorLog = Join-Path $output "$($case.Name).err"
    $process = Start-Process -FilePath (Join-Path $BuildDirectory 'RetinaGram.exe') `
        -ArgumentList @('--benchmark', ('"'+$case.Image+'"'), "$Iterations") -WorkingDirectory $root `
        -WindowStyle Hidden -RedirectStandardOutput $json -RedirectStandardError $errorLog -PassThru
    $peakGpu = $baseline
    while (-not $process.HasExited) {
        $used = @(& nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
        if ($used -and [int]$used[0] -gt $peakGpu) { $peakGpu = [int]$used[0] }
        Start-Sleep -Milliseconds 200
        $process.Refresh()
    }
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw "Benchmark failed: $errorLog" }
    $result = Get-Content -LiteralPath $json -Raw | ConvertFrom-Json
    [pscustomobject]@{
        case = $case.Name
        exit = $process.ExitCode
        startup_ms = $result.model_initialization_ms
        analysis_ms = @($result.runs | ForEach-Object { $_.analysis_ms })
        idle_ram_mib = [math]::Round($result.idle_memory.working_set_bytes / 1MB, 1)
        peak_ram_mib = [math]::Round(($result.runs | ForEach-Object { $_.memory.peak_working_set_bytes } | Measure-Object -Maximum).Maximum / 1MB, 1)
        total_gpu_memory_delta_mib = $peakGpu - $baseline
    } | ConvertTo-Json -Compress | Add-Content -LiteralPath (Join-Path $output 'summary.jsonl')
}
