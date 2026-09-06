$ErrorActionPreference = 'Stop'
$appRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $appRoot
& npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
& npm.cmd run desktop
exit $LASTEXITCODE
