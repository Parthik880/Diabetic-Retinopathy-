param(
  [string]$PythonPath = ".venv\Scripts\python.exe"
)

$ErrorActionPreference = 'Stop'
$appRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $appRoot

if (!(Test-Path -LiteralPath $PythonPath)) {
  & py -3.12 -m venv .venv
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required.' }
}

& $PythonPath -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& $PythonPath -m pip install -r requirements-runtime.txt
if ($LASTEXITCODE -ne 0) { throw 'Runtime dependency installation failed.' }

# Force replacement so an environment previously containing a same-version
# CUDA wheel cannot satisfy the version pins and remain installed.
& $PythonPath -m pip install --upgrade --force-reinstall torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { throw 'CPU-only PyTorch installation failed.' }

$installed = & $PythonPath -m pip list --format=json | ConvertFrom-Json
$nvidiaPackages = @($installed | Where-Object { $_.name -match '^(nvidia-|cuda-python$|nvidia-pyindex$)' } | ForEach-Object { $_.name })
if ($nvidiaPackages.Count -gt 0) {
  & $PythonPath -m pip uninstall --yes @nvidiaPackages
  if ($LASTEXITCODE -ne 0) { throw 'NVIDIA-only package cleanup failed.' }
}

& $PythonPath scripts\verify_cpu.py
if ($LASTEXITCODE -ne 0) { throw 'CPU-only PyTorch verification failed.' }
