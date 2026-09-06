# -*- mode: python ; coding: utf-8 -*-
"""CPU-only, onedir PyInstaller build for the RetinaGram backend."""

from pathlib import Path

import torch
import torchvision
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules


root = Path(SPECPATH)

# Packaging from the wrong wheel silently produces a huge and non-portable
# backend. Fail the build before Analysis if this is not the verified CPU venv.
if torch.__version__ != "2.14.0+cpu":
    raise RuntimeError(f"Expected torch 2.14.0+cpu, found {torch.__version__}")
if torchvision.__version__ != "0.29.0+cpu":
    raise RuntimeError(
        f"Expected torchvision 0.29.0+cpu, found {torchvision.__version__}"
    )
if torch.version.cuda is not None or torch.cuda.is_available():
    raise RuntimeError("Refusing to package a CUDA-enabled PyTorch build")

runtime_datas = [
    (str(root / "resources" / "models"), "resources/models"),
    (str(root / "frontend" / "dist"), "frontend/dist"),
    (str(root / "frontend" / "public" / "logo.png.jpeg"), "frontend/public"),
    (str(root / "backend" / "config"), "config"),
]

# torch's official PyInstaller hook already collects its Python modules, data,
# and native libraries. These explicit collections document and protect the
# dynamically imported surface this application actually relies on.
hiddenimports = sorted(
    set(
        collect_submodules("torch.distributed")
        + collect_submodules("torchvision.models")
        + collect_submodules("torchvision.transforms")
    )
)
binaries = collect_dynamic_libs("torch") + collect_dynamic_libs(
    "torchvision", search_patterns=["*.pyd", "*.dll"]
)

# This inference server never compiles graphs. torchvision imports one helper
# from torch._dynamo merely while registering optional ROI operations, so a
# runtime hook supplies that helper without freezing the compiler stack. The
# compiler stack currently reaches torch._numpy, which is not freeze-safe in
# this PyTorch/PyInstaller combination.
excluded_modules = [
    "albumentations",
    "black",
    "IPython",
    "ipykernel",
    "jupyter",
    "notebook",
    "pandas",
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
    runtime_hooks=[str(root / "backend" / "packaging" / "pyi_rth_torch_cpu.py")],
    excludes=excluded_modules,
    noarchive=False,
    optimize=0,
    module_collection_mode={"torch": "pyz+py", "torchvision": "pyz+py"},
)
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
