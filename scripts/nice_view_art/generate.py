"""Generate the nice!view dog art (LVGL C image + optional 4x preview).

Usage (local only, never run in CI):

    python3 scripts/nice_view_art/generate.py \
        scripts/nice_view_art/dog_cutout.png \
        boards/shields/nice_view_custom/widgets/dog.c \
        [preview-4x.png]

Requires Python 3 and Pillow (`pip install Pillow`).
"""

import sys

from PIL import Image, ImageChops, ImageFilter, ImageOps

ART_SIZE = (68, 140)  # portrait, as seen on the keyboard
ALPHA_THRESHOLD = 100
CONTRAST_LO = 60
CONTRAST_HI = 200
# Cap keeps the light fur at the ear base from going white (detached ear).
BRIGHTNESS_CAP = 170
PREVIEW_SCALE = 4
PALETTE_BYTES = 8
COMMAND = "python3 scripts/nice_view_art/generate.py <cutout.png> <dog.c> [preview.png]"

HEADER = f"""/*
 * GENERATED FILE - do not edit by hand.
 * Regenerate with: {COMMAND}
 */

#include <lvgl.h>

#ifndef LV_ATTRIBUTE_MEM_ALIGN
#define LV_ATTRIBUTE_MEM_ALIGN
#endif

#ifndef LV_ATTRIBUTE_IMG_DOG
#define LV_ATTRIBUTE_IMG_DOG
#endif

const LV_ATTRIBUTE_MEM_ALIGN LV_ATTRIBUTE_LARGE_CONST LV_ATTRIBUTE_IMG_DOG uint8_t
    dog_map[] = {{
#if CONFIG_NICE_VIEW_CUSTOM_WIDGET_INVERTED
        0xff, 0xff, 0xff, 0xff, /*Color of index 0*/
        0x00, 0x00, 0x00, 0xff, /*Color of index 1*/
#else
        0x00, 0x00, 0x00, 0xff, /*Color of index 0*/
        0xff, 0xff, 0xff, 0xff, /*Color of index 1*/
#endif

"""

FOOTER = """};

const lv_img_dsc_t dog = {
    .header.cf = LV_IMG_CF_INDEXED_1BIT,
    .header.always_zero = 0,
    .header.reserved = 0,
    .header.w = 140,
    .header.h = 68,
    .data_size = 1232,
    .data = dog_map,
};
"""


def render_portrait(source_path):
    cutout = Image.open(source_path).convert("RGBA")
    background = Image.new("RGBA", cutout.size, (255, 255, 255, 255))
    background.alpha_composite(cutout)
    gray = ImageOps.grayscale(background)
    gray.thumbnail(ART_SIZE, Image.LANCZOS)

    # Centered horizontally, anchored to the bottom.
    offset = ((ART_SIZE[0] - gray.width) // 2, ART_SIZE[1] - gray.height)
    canvas = Image.new("L", ART_SIZE, 255)
    canvas.paste(gray, offset)

    alpha = cutout.getchannel("A")
    alpha.thumbnail(ART_SIZE, Image.LANCZOS)
    mask = Image.new("L", ART_SIZE, 0)
    mask.paste(alpha, offset)
    mask = mask.point(lambda p: 255 if p > ALPHA_THRESHOLD else 0)

    stretched = canvas.point(
        lambda p: min(
            BRIGHTNESS_CAP,
            max(0, min(255, int((p - CONTRAST_LO) * 255 / (CONTRAST_HI - CONTRAST_LO)))),
        )
    )
    toned = Image.composite(stretched, Image.new("L", ART_SIZE, 255), mask)
    dithered = toned.convert("1")  # Floyd-Steinberg

    edge = ImageChops.subtract(mask, mask.filter(ImageFilter.MinFilter(3)))
    outlined = ImageChops.darker(dithered.convert("L"), ImageOps.invert(edge))
    return outlined.convert("1")


def pack_rows(portrait):
    # Rotate 90 degrees clockwise: 68x140 -> 140x68.
    rotated = portrait.transpose(Image.ROTATE_270)
    width, height = rotated.size
    row_bytes = (width + 7) // 8
    pixels = rotated.load()
    data = bytearray()
    for y in range(height):
        row = bytearray(row_bytes)
        for x in range(width):
            if pixels[x, y]:  # white = palette index 1; MSB first
                row[x // 8] |= 0x80 >> (x % 8)
        data.extend(row)
    return bytes(data)


def format_c(data):
    lines = []
    for start in range(0, len(data), 15):
        chunk = data[start : start + 15]
        lines.append("        " + ", ".join(f"0x{b:02x}" for b in chunk) + ",")
    return HEADER + "\n".join(lines) + "\n" + FOOTER


def main(argv):
    if len(argv) not in (3, 4):
        print(f"usage: {COMMAND}", file=sys.stderr)
        return 2

    portrait = render_portrait(argv[1])
    data = pack_rows(portrait)
    assert len(data) == 1224, len(data)
    with open(argv[2], "w", newline="\n") as out:
        out.write(format_c(data))

    if len(argv) == 4:
        size = (ART_SIZE[0] * PREVIEW_SCALE, ART_SIZE[1] * PREVIEW_SCALE)
        portrait.convert("L").resize(size, Image.NEAREST).save(argv[3])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
