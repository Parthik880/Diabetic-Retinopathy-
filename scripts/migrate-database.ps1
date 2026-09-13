$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
$pythonExecutable = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    throw 'Install the project Python environment first. See CLOUD_SYNC_STORAGE.md.'
}
& $pythonExecutable -m alembic -c (Join-Path $projectRoot 'alembic.ini') upgrade head
exit $LASTEXITCODE
