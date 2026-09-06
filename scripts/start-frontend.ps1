$ErrorActionPreference = 'Stop'
$appRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath (Join-Path $appRoot 'frontend')
& npm.cmd run dev
exit $LASTEXITCODE
