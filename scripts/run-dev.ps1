param(
    [string]$BuildDirectory = (Join-Path $PSScriptRoot '..\build\ninja'),
    [string[]]$Arguments = @()
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$exe = Join-Path $BuildDirectory 'RetinaGram.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw "Build RetinaGram.exe first: $exe" }
. (Join-Path $PSScriptRoot 'runtime-environment.ps1')
$null = Set-RetinaGramRuntimeEnvironment -BuildDirectory $BuildDirectory
if ($Arguments.Count) { & $exe @Arguments; exit $LASTEXITCODE }
Start-Process -FilePath $exe -WorkingDirectory $root
