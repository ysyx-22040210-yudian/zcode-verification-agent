"""Read retained PDF pages with native Poppler tools for Agent reference."""
import base64
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time


INLINE_IMAGE_BYTES = 144 * 1024
MAX_IMAGE_PARTS = 8
MAX_TEXT_CHARACTERS = 64000


def command(arguments, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError("Original document reading timed out")
    try:
        result = subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, timeout=remaining)
    except subprocess.TimeoutExpired:
        raise ValueError("Original document reading timed out")
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[:600]
        raise ValueError("Original PDF could not be read: " + detail)
    return result.stdout


def render_images(renderer, pdf, page, directory, deadline):
    base = [renderer, "-f", str(page), "-l", str(page), "-singlefile", "-scale-to", "2000", "-png"]
    prefix = directory / "page"
    command(base + [str(pdf), str(prefix)], deadline)
    image = prefix.with_suffix(".png").read_bytes()
    if len(image) < 24 or not image.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("The PDF renderer did not return a PNG page")
    width, height = struct.unpack(">II", image[16:24])
    pending = [(0, 0, width, height, image)]
    images = []
    while pending:
        x, y, part_width, part_height, data = pending.pop(0)
        if data is None:
            crop = ["-x", str(x), "-y", str(y), "-W", str(part_width), "-H", str(part_height)]
            command(base + crop + [str(pdf), str(prefix)], deadline)
            data = prefix.with_suffix(".png").read_bytes()
            if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("The PDF renderer did not return a PNG region")
        if len(data) <= INLINE_IMAGE_BYTES:
            images.append({"mimeType": "image/png", "data": base64.b64encode(data).decode("ascii"),
                           "region": {"x": x, "y": y, "width": part_width, "height": part_height}})
            continue
        if len(images) + len(pending) + 2 > MAX_IMAGE_PARTS or min(part_width, part_height) < 2:
            raise ValueError("This page exceeds the Agent image limit. Read fewer pages or use the original PDF file")
        if part_height >= part_width:
            first = part_height // 2
            pending.extend([(x, y, part_width, first, None),
                            (x, y + first, part_width, part_height - first, None)])
        else:
            first = part_width // 2
            pending.extend([(x, y, first, part_height, None),
                            (x + first, y, part_width - first, part_height, None)])
    images.sort(key=lambda part: (part["region"]["y"], part["region"]["x"]))
    return {"width": width, "height": height, "images": images}


def read_pages(pdf, first, last, *, include_images=True):
    renderer = shutil.which("pdftoppm") if include_images else None
    extractor = shutil.which("pdftotext")
    if (include_images and not renderer) or not extractor:
        tools = "pdftoppm and pdftotext" if include_images else "pdftotext"
        raise ValueError("Original PDF reading requires " + tools + " on the native host")
    deadline = time.monotonic() + 12
    pages = []
    with tempfile.TemporaryDirectory(prefix="zcode-original-") as temporary:
        directory = Path(temporary)
        for number in range(first, last + 1):
            output = command([extractor, "-f", str(number), "-l", str(number), "-layout", "-enc", "UTF-8",
                              str(pdf), "-"], deadline)
            text = output.decode("utf-8", errors="replace").strip("\f\n ")
            rendered = render_images(renderer, pdf, number, directory, deadline) if include_images else {"images": []}
            pages.append(dict(rendered, page=number, text=text[:MAX_TEXT_CHARACTERS],
                              textTruncated=len(text) > MAX_TEXT_CHARACTERS))
    return pages
