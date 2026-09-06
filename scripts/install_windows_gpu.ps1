param(
  [string]$PythonPath = ".venv\Scripts\python.exe"
)

$ErrorActionPreference = 'Stop'
$appRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $appRoot

if (!(Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue)) {
  throw 'No NVIDIA driver was detected. Install a supported NVIDIA driver before installing RetinaGram GPU dependencies.'
}

Write-Host 'Detected NVIDIA driver:'
& nvidia-smi.exe
if ($LASTEXITCODE -ne 0) { throw 'nvidia-smi failed; CUDA-capable NVIDIA driver verification did not complete.' }

if (!(Test-Path -LiteralPath $PythonPath)) {
  & py -3.12 -m venv .venv
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required.' }
}

& $PythonPath -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& $PythonPath -m pip install -r requirements-runtime.txt
if ($LASTEXITCODE -ne 0) { throw 'Runtime dependency installation failed.' }

# The 591.86 driver reports CUDA 13.1 capability. PyTorch 2.14.0 publishes
# official Windows wheels for CUDA 13.0, so cu130 is the compatible supported
# runtime selected here. PyTorch wheels provide their own CUDA runtime libraries.
& $PythonPath -m pip install --upgrade --force-reinstall torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cu130
if ($LASTEXITCODE -ne 0) { throw 'CUDA-enabled PyTorch installation failed.' }

& $PythonPath scripts\verify_gpu.py
if ($LASTEXITCODE -ne 0) { throw 'CUDA verification failed.' }
