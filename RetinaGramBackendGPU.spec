# -*- mode: python ; coding: utf-8 -*-
"""CUDA-enabled, onedir PyInstaller build for the RetinaGram GPU backend."""

from pathlib import Path

import torch
import torchvision
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules


root = Path(SPECPATH)

# Freeze only from the already-verified GPU environment. These checks run at
# build time; the resulting application still retains its runtime CPU fallback.
if torch.__version__ != "2.14.0+cu130":
    raise RuntimeError(f"Expected torch 2.14.0+cu130, found {torch.__version__}")
if torchvision.__version__ != "0.29.0+cu130":
    raise RuntimeError(
        f"Expected torchvision 0.29.0+cu130, found {torchvision.__version__}"
    )
if torch.version.cuda != "13.0":
    raise RuntimeError(f"Expected CUDA 13.0 wheel, found {torch.version.cuda}")

runtime_datas = [
    (str(root / "resources" / "models"), "resources/models"),
    (str(root / "frontend" / "dist"), "frontend/dist"),
    (str(root / "frontend" / "public" / "logo.png.jpeg"), "frontend/public"),
    (str(root / "backend" / "config"), "config"),
]

hiddenimports = sorted(
    set(
        collect_submodules("torch.distributed")
        + collect_submodules("torchvision.models")
        + collect_submodules("torchvision.transforms")
    )
)

# The cu130 Torch wheel carries its CUDA/cuDNN/cuBLAS runtime in torch/lib.
# collect_dynamic_libs preserves that complete native dependency set.
binaries = collect_dynamic_libs("torch") + collect_dynamic_libs(
    "torchvision", search_patterns=["*.pyd", "*.dll"]
)

# These are optional developer/multi-GPU alternatives and are not imported by
# any bundled Torch DLL. Keeping the core NVRTC, cuSOLVER, cuPTI, cuDNN, cuBLAS,
# cuFFT, cuSPARSE, cuRAND, and CUDA runtime libraries preserves inference while
# keeping the NSIS payload below its 2 GiB embedded-file limit.
optional_native_dlls = {
    "cusolvermg64_12.dll",
    "nvperf_host.dll",
    "nvrtc64_130_0.alt.dll",
}
binaries = [
    binary
    for binary in binaries
    if Path(binary[0]).name.lower() not in optional_native_dlls
]

excluded_modules = [
    "albumentations",
    "black",
    "IPython",
    "ipykernel",
    "jupyter",
    "notebook",
    "pytest",
    "ruff",
    "seaborn",
    "sklearn",
    "tensorboard",
    "torch._dynamo",
    "torch._inductor",
    "torch._numpy",
    "torch.utils.benchmark",
    "torch.utils.tensorboard",
]


a = Analysis(
    ["backend/run_server.py"],
    pathex=[str(root / "backend")],
    binaries=binaries,
    datas=runtime_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(root / "backend" / "packaging" / "pyi_rth_torch_gpu.py")],
    excludes=excluded_modules,
    noarchive=False,
    optimize=0,
    module_collection_mode={"torch": "pyz+py", "torchvision": "pyz+py"},
)
a.binaries = [
    binary
    for binary in a.binaries
    if Path(binary[0]).name.lower() not in optional_native_dlls
]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RetinaGramBackend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="RetinaGramBackend",
)
