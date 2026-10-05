"""Bounded inline raster inputs. This validates transport, not image aesthetics."""
import base64
import binascii


def validated_image_inputs(values):
    if values is None:
        return ()
    if not isinstance(values, (tuple, list)) or len(values) > 3:
        raise ValueError('image inputs must contain at most three inline rasters')
    images = []
    for value in values:
        if not isinstance(value, str) or len(value) > 4 * 1024 * 1024 * 4 // 3 + 100:
            raise ValueError('image input exceeds 4 MiB or is not an inline raster')
        prefix, separator, encoded = value.partition(',')
        if not separator or prefix not in {
            'data:image/png;base64', 'data:image/jpeg;base64', 'data:image/webp;base64',
        }:
            raise ValueError('only inline PNG, JPEG and WebP images are supported')
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('invalid inline image encoding') from None
        valid = (
            prefix == 'data:image/png;base64' and data.startswith(b'\x89PNG\r\n\x1a\n')
            or prefix == 'data:image/jpeg;base64' and data.startswith(b'\xff\xd8\xff')
            or prefix == 'data:image/webp;base64' and data.startswith(b'RIFF') and data[8:12] == b'WEBP'
        )
        if not valid or len(data) > 4 * 1024 * 1024:
            raise ValueError('invalid raster signature or image size')
        images.append(value)
    return tuple(images)


def image_message(prompt, images, responses=False):
    if not images:
        return prompt
    content = [{'type':'input_text' if responses else 'text', 'text':str(prompt)}]
    for image in images:
        content.append({'type':'input_image' if responses else 'image_url',
                        'image_url':image if responses else {'url':image, 'detail':'high'}})
    return [{'role':'user', 'content':content}] if responses else content
