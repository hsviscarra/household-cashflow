"""OCR for statements that arrive as pictures: Pacificard prints its web statement to a PDF that
holds one screenshot per page (grey "COPIA" watermark), and any other bank's PDF without a text
layer (a scan) falls back to it. See ADR-005.

Tesseract runs locally (nothing leaves the server). Two passes: the whole page for words and
lines, then every word that should be a number again with a digits-only alphabet, because the
first pass confuses 5/§, 9/S and 8/B in the statement's thin monospaced font. A misread digit
can't slip through: the parser's tie-out compares every line with the printed subtotals.
"""

import io
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import pairwise

from PIL import Image, ImageOps
from pypdf import PdfReader

WIDE = 3500  # pixels: each page picture is enlarged to about this width before reading
WORKERS = 4  # tesseract processes at once for the re-reads
INK = 165  # darker than the watermark (191) is text
# A word that should be an amount: digit-like characters around a decimal point ("§.03", "a11.a9").
# Signs ("+570.00", "310,00-") are kept from the first reading; either decimal mark is accepted.
NUMBER_LIKE = re.compile(r"^[+-]?[\d§$SOBIZa.,]{1,10}[.,][\d§$SOBIZsa¢]{2,3}-?$")
# The re-read must keep the first reading's decimal mark: US 1,057.81 or Ecuadorian 1.057,78.
# No leading zero unless the whole part is 0: "00,00" is a misread of "50,00", not an amount.
AMOUNT = {
    ".": re.compile(r"(?:0|[1-9]\d{0,2}(?:,?\d{3})*)\.\d{2}"),
    ",": re.compile(r"(?:0|[1-9]\d{0,2}(?:\.?\d{3})*),\d{2}"),
}
DIGIT_LIKE = re.compile(r"^[\d§$SOBIZa.,]{3,10}$")
# A word that should be a date: "SEP/0S", "4GO/28", "2MAY/2026" (a digit next to a slash).
DATE_LIKE = re.compile(r"^(?=.*\d)[\w$§]{1,6}/[\w$§]{1,5}(?:/\w{4})?$")
DATE = re.compile(r"(?:\d{1,2}/)?[A-Z]{3}/\d{1,2}(?:\d{3})?")
DIGITS = "0123456789.,+-"  # signs are allowed so a "+" isn't read as a 4, then set aside
DATE_CHARS = "0123456789/ABCDEFGIJLMNOPRSTUVY"  # digits and the letters of Spanish month names
# Each number is read again from the original picture at several sizes and ink thresholds; the
# answer most of them agree on wins (a single reading can turn a 4 into a 9).
VOTES = ((32, 165), (40, 130), (40, 200), (56, 165), (32, 200))  # (text height px, ink)


class OcrError(Exception):
    """OCR is not available, or the file holds no page images."""


@dataclass(frozen=True)
class Word:
    line: tuple[int, int, int]
    left: int
    top: int
    width: int
    height: int
    text: str


def available() -> bool:
    return shutil.which("tesseract") is not None


def page_images(data: bytes) -> list[Image.Image]:
    """The largest image on each page; a page that repeats the previous image is skipped."""
    reader = PdfReader(io.BytesIO(data))
    out: list[Image.Image] = []
    seen: set[bytes] = set()
    for page in reader.pages:
        images = sorted(page.images, key=lambda i: len(i.data), reverse=True)
        if not images or images[0].data in seen:
            continue
        seen.add(images[0].data)
        out.append(Image.open(io.BytesIO(images[0].data)))
    return out


def _scale(image: Image.Image) -> int:
    """4x for a 880 px screenshot, 2x for a 200 dpi scan, 1x for anything larger."""
    return max(1, round(WIDE / image.width))


def _prepare(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    scale = _scale(image)
    big = gray.resize((gray.width * scale, gray.height * scale), Image.Resampling.BICUBIC)
    return big.point(lambda p: 0 if p < INK else 255)


def _tesseract(image: Image.Image, *args: str) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    try:
        done = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "eng", *args],
            input=buf.getvalue(),
            capture_output=True,
            check=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise OcrError("OCR (tesseract) is not installed on this server.") from exc
    return done.stdout.decode("utf-8", errors="replace")


def _words(image: Image.Image) -> list[Word]:
    tsv = _tesseract(image, "--psm", "6", "tsv")
    words = []
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or not cols[11].strip():
            continue
        block, par, line = (int(c) for c in cols[2:5])
        left, top, width, height = (int(c) for c in cols[6:10])
        words.append(Word((block, par, line), left, top, width, height, cols[11].strip()))
    return words


def _reread(
    gray: Image.Image,
    w: Word,
    first: str,
    chars: str,
    valid: re.Pattern[str],
    clean: Callable[[str], str] = str.strip,
) -> str | None:
    """Majority of several readings of the word's box with a restricted alphabet; stops once three
    readings agree. Word coordinates are on the enlarged picture, `gray` is the original; each
    reading enlarges the word to a given text height (Tesseract reads best at 30-60 px)."""
    k = _scale(gray)
    pad = 8
    left, top = (w.left - pad) // k, (w.top - pad) // k
    right, bottom = (w.left + w.width + pad) // k, (w.top + w.height + pad) // k
    crop = gray.crop((left, top, right, bottom))
    height = max(1.0, w.height / k)
    votes: Counter[str] = Counter()
    if valid.fullmatch(clean(first)):
        votes[clean(first)] += 1
    for target, ink in VOTES:
        f = max(1.0, target / height)
        size = (round(crop.width * f), round(crop.height * f))
        big = crop.resize(size, Image.Resampling.BICUBIC)
        big = ImageOps.expand(big.point(lambda p, ink=ink: 0 if p < ink else 255), 20, 255)
        text = clean(_tesseract(big, "--psm", "7", "-c", f"tessedit_char_whitelist={chars}"))
        if valid.fullmatch(text):
            votes[text] += 1
            if votes.most_common(1)[0][1] >= 3:
                break
    if not votes:
        return None
    (best, n), *rest = votes.most_common()
    return best if not rest or rest[0][1] < n else None  # a tie is not an answer


def _amount(gray: Image.Image, w: Word) -> str:
    """An amount re-read digits-only, keeping the first reading's sign and decimal mark."""
    lead = w.text[0] if w.text[0] in "+-" else ""
    trail = "-" if w.text.endswith("-") else ""
    core = w.text.strip("+-")
    mark = "," if re.search(r",\S{2,3}$", core) and "." not in core[-3:] else "."
    # A leading "$" may be a currency sign or a misread 5: only the re-readings decide then.
    seed = "" if core.startswith("$") else core
    best = _reread(gray, w, seed, DIGITS, AMOUNT[mark], lambda t: t.strip().strip("+-"))
    if not best:
        return w.text
    # "$500.00": a dollar sign when the digits-only reading has no extra digit in its place;
    # "$12.34" read again as "512.34" means the "$" was a 5.
    dollar = "$" if core.startswith("$") and _digits(best) == _digits(core[1:]) else ""
    return f"{lead}{dollar}{best}{trail}"


def _digits(text: str) -> int:
    return sum(c.isdigit() or c in "§SOBIZa" for c in text)


def first_page(image: Image.Image) -> Image.Image:
    """The part of a printed web page above its second page banner (a dark bar across the page,
    "Pag. 2 Estado de cuenta"): the fine print below it isn't needed and is slow to read."""
    gray = ImageOps.grayscale(image)
    width, height = gray.size
    raw = gray.tobytes()  # one byte per pixel, row by row
    in_band, bands = False, 0
    for y in range(height):
        row = raw[y * width : (y + 1) * width : 4]
        dark = sum(1 for p in row if p < 100) / len(row) > 0.6
        if dark and not in_band:
            bands += 1
            if bands == 2:
                return image.crop((0, 0, width, max(1, y - 30)))
        in_band = dark
    return image


def header_text(data: bytes, whole: bool = False) -> str:
    """A quick read of the first page image to recognize the bank: the top (a screenshot's header),
    or with `whole` the full page at its own size (a scan, whose bank name may be in the footer)."""
    images = page_images(data)
    if not images:
        return ""
    first = images[0]
    if whole:
        return _tesseract(
            ImageOps.grayscale(first).point(lambda p: 0 if p < INK else 255), "--psm", "3"
        )
    top = first.crop((0, 0, first.width, min(first.height, 450)))
    return _tesseract(_prepare(top), "--psm", "6")


def ocr_pages(data: bytes, crop: Callable[[Image.Image], Image.Image] | None = None) -> list[str]:
    """Text of each page image, one statement line per text line, numbers re-read in parallel.

    `crop`: keeps the part of each image worth reading (e.g. `first_page`)."""
    images = page_images(data)
    if not images:
        raise OcrError("This PDF has no page images to read.")
    pages = []
    for img in images:
        part = crop(img) if crop else img
        gray = ImageOps.grayscale(part)
        words = _words(_prepare(part))

        # The word before a closing "+"/"-" is an amount even when its decimal point was lost.
        before_sign = {
            id(a)
            for a, b in pairwise(words)
            if a.line == b.line and b.text in ("+", "-") and DIGIT_LIKE.match(a.text)
        }

        def better(w: Word, gray: Image.Image = gray, before_sign: set[int] = before_sign) -> str:
            if NUMBER_LIKE.match(w.text) or id(w) in before_sign:
                return _amount(gray, w)
            if DATE_LIKE.match(w.text):
                return _reread(gray, w, w.text, DATE_CHARS, DATE) or w.text
            return w.text

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            texts = list(pool.map(better, words))
        lines: dict[tuple[int, int, int], list[str]] = defaultdict(list)
        for w, text in zip(words, texts, strict=True):
            lines[w.line].append(text)  # dicts keep the reading order
        pages.append("\n".join(" ".join(line) for line in lines.values()))
    return pages
