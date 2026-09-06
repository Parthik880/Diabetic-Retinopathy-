# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


root = Path(SPECPATH)
runtime_datas = [
    (str(root / 'resources' / 'models'), 'resources/models'),
    (str(root / 'frontend' / 'dist'), 'frontend/dist'),
    (str(root / 'frontend' / 'public' / 'logo.png.jpeg'), 'frontend/public'),
    (str(root / 'backend' / 'config'), 'config'),
]


a = Analysis(
    ['backend/run_server.py'],
    pathex=[str(root / 'backend')],
    binaries=[],
    datas=runtime_datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'albumentations', 'black', 'IPython', 'ipykernel', 'jupyter',
        'notebook', 'pandas', 'pytest', 'ruff', 'seaborn', 'sklearn',
        'tensorboard',
        # CPU inference does not compile, export, train, benchmark, or use
        # distributed execution. PyInstaller's torch hook otherwise collects
        # these sizeable optional Python subsystems.
        'torch._dynamo', 'torch._inductor', 'torch.distributed', 'torch.onnx',
        'torch.profiler', 'torch.testing', 'torch.utils.benchmark',
        'torch.utils.tensorboard',
        # The desktop uses scipy.ndimage only; model-training/evaluation code is
        # intentionally outside this runtime bundle.
        'scipy.cluster', 'scipy.constants', 'scipy.datasets', 'scipy.fft',
        'scipy.integrate', 'scipy.interpolate', 'scipy.io', 'scipy.linalg',
        'scipy.odr', 'scipy.optimize', 'scipy.signal', 'scipy.sparse',
        'scipy.spatial', 'scipy.stats',
        # Only classification backbones/transforms are used from torchvision.
        'torchvision.datasets', 'torchvision.io',
        'torchvision.models.detection', 'torchvision.models.optical_flow',
        'torchvision.models.quantization', 'torchvision.models.segmentation',
        'torchvision.models.video',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RetinaGramBackend',
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
    name='RetinaGramBackend',
)
