"""Pixel-aligned browser artifacts; never draw on the source image."""
from pathlib import Path
import numpy as np
from PIL import Image
import matplotlib


def save_attention(values, destination: Path, values_path: str | Path | None = None):
    values = np.asarray(values, dtype=np.float32)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise ValueError('Attention map must be a finite H x W array')
    destination.parent.mkdir(parents=True, exist_ok=True)
    values = np.clip(values, 0, 1)
    retained_values = Path(values_path).resolve() if values_path is not None else destination.with_suffix('.npy').resolve()
    if values_path is None:
        np.save(retained_values, values, allow_pickle=False)
    # A raw full-canvas RGB map, without axes, padding, or a baked fundus image.
    rgb = np.rint(matplotlib.colormaps['jet'](values)[..., :3] * 255).astype(np.uint8)
    Image.fromarray(rgb).save(destination, compress_level=1)
    return {'heatmap_path': str(destination), 'values_path': str(retained_values),
            'width': values.shape[1], 'height': values.shape[0],
            'minimum': float(values.min()), 'maximum': float(values.max()),
            'colormap': 'jet', 'normalization': '0 to 1', 'pixel_aligned': True}


def save_mask_layers(mask_path, color, destination: Path):
    with Image.open(mask_path) as image:
        mask = np.asarray(image).astype(bool)
    destination.parent.mkdir(parents=True, exist_ok=True)
    binary = destination.with_name(destination.stem + '_binary.png')
    Image.fromarray(mask.astype(np.uint8) * 255).save(binary, compress_level=1)
    rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
    rgba[..., :3] = color
    rgba[..., 3] = mask.astype(np.uint8) * 255
    Image.fromarray(rgba).save(destination, compress_level=1)
    return {'mask_png_path': str(binary), 'mask_layer_path': str(destination),
            'color': '#%02x%02x%02x' % tuple(color)}
