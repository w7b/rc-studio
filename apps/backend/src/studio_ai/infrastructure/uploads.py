import base64
import binascii
import io
import warnings

from PIL import Image


def decode_upload(value):
    if not value:
        return None
    try:
        content = base64.b64decode(value, validate=True)
        if len(content) > 8 * 1024 * 1024:
            raise ValueError()
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in ('PNG', 'JPEG') or image.width * image.height > 25000000:
                    raise ValueError()
                image.verify()
        return content
    except (ValueError, OSError, SyntaxError, binascii.Error, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('Envie PNG ou JPEG válido, de até 8 MB e 25 megapixels') from None
