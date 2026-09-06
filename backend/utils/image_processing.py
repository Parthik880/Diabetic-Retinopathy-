from io import BytesIO
from PIL import Image, UnidentifiedImageError

MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 16_000_000
FORMATS = {'JPEG', 'PNG', 'BMP', 'TIFF'}


def decode_upload(data: bytes):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Image must contain data and be no larger than 20 MB.')
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in FORMATS:
                raise TypeError('Unsupported format. Use JPEG, PNG, BMP, or single-page TIFF.')
            if getattr(source, 'n_frames', 1) != 1:
                raise TypeError('Multi-page images are unsupported.')
            if source.width * source.height > MAX_PIXELS:
                raise ValueError('Image exceeds the 16 megapixel limit.')
            source.verify()
        with Image.open(BytesIO(data)) as source:
            return source.convert('RGB')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Invalid or unreadable image.') from exc
