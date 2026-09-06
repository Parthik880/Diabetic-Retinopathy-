$ErrorActionPreference = 'Stop'
$appRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $appRoot
if (!(Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
  & py -3.12 -m venv .venv
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required.' }
}
& $PSScriptRoot\install_windows_gpu.ps1 -PythonPath '.venv\Scripts\python.exe'
if ($LASTEXITCODE -ne 0) { throw 'GPU Python dependency installation failed.' }
& .\.venv\Scripts\python.exe scripts\prepare-resources.py
if ($LASTEXITCODE -ne 0) { throw 'Model resource preparation failed.' }
& npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw 'Desktop dependency installation failed.' }
& node node_modules\electron\install.js
if ($LASTEXITCODE -ne 0) { throw 'Electron runtime download failed.' }
& npm.cmd --prefix frontend ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
& npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
Write-Host 'Setup complete. Run .\scripts\start-desktop.ps1'
