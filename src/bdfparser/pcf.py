"""
PCF (Portable Compiled Format) reader and writer.

`write_pcf(font)` reproduces the output of `bdftopcf` (X.Org bdftopcf 1.1, the
version that bundles its own copy of the libXfont bitmap code: bdfread.c,
bdfutils.c, bitmaputil.c, fontaccel.c, fontink.c, pcfwrite.c) **byte for byte**
when run with default options (`bdftopcf -o out.pcf in.bdf`). `read_pcf(data)`
reads any PCF variant back into the bdfparser data model (SPEC-v3 §6).

===========================================================================
bdftopcf 1.1 rules, as derived from its source and verified against its output
===========================================================================

Terminology: "glyph list" = the glyphs in BDF file order; bdfparser stores
encoded glyphs in `font.glyphs` (dict order = file order) and `ENCODING -1`
glyphs in `font.unencoded`; the writer uses `glyphs` then `unencoded`.
All C integer divisions truncate toward zero.

Format word (`format`):
  bits 0-1 glyph pad index (1/2/4/8 bytes -> 0..3), bit 2 byte order
  (1 = MSB first), bit 3 bit order (1 = MSB first), bits 4-5 scan unit index
  (1/2/4 bytes -> 0..2). bdftopcf defaults: MSB byte, MSB bit, pad 4, scan 1
  => 0x0E. Flags -t and -i are accepted but ignored in 1.1.

File layout:
  header: "\\x01fcp" (LSB int32 0x70636601), table count (LSB int32), then per
  table type, format, size, offset (4 LSB int32). Tables are emitted for the
  type bits in ascending order: PROPERTIES(1), ACCELERATORS(2), METRICS(4),
  BITMAPS(8), INK_METRICS(16, optional), BDF_ENCODINGS(32), SWIDTHS(64),
  GLYPH_NAMES(128), BDF_ACCELERATORS(256). First table offset = 8 + 16*n,
  every next offset = previous offset + declared size. Gaps between the end of
  the written data of a table and the next offset are zero bytes. Every table
  starts with its format as LSB int32 (the TOC format and this word are equal);
  all other integers in a table use the table's byte order.
  Declared sizes:
    PROPERTIES   RoundUp4(8 + 9*nprops) + 4 + RoundUp4(stringsize)
    ACCELERATORS 100 (always; data is 48 bytes, or 72 with ink bounds)
    METRICS      compressed: RoundUp4(4 + 2 + 5*n); else 8 + 12*n
    BITMAPS      RoundUp4(8 + 4*n + 16 + bitmapsSizes[padindex])
    INK_METRICS  as METRICS
    BDF_ENCODINGS RoundUp4(4 + 10 + 2*nencodings)
    SWIDTHS      8 + 4*n
    GLYPH_NAMES  8 + 4*n + 4 + RoundUp4(stringsize)
    BDF_ACCELERATORS 100
  The file ends right after the last byte written for BDF_ACCELERATORS, i.e.
  it is 52 (or 28 with ink bounds) bytes SHORTER than the TOC claims.

BDF interpretation (what bdftopcf reads, mapped to the bdfparser model):
  * Properties are written in model order (`props`, `comment` skipped) with
    their original spelling (`font._propnames`, else upper case). Names are
    matched case-sensitively. int value -> integer property (int32), str ->
    string property (UTF-8), None -> property skipped (bdftopcf rejects
    key-only lines), other types -> str(). Names starting with "COMMENT" are
    skipped (bdftopcf's line reader drops every line starting with COMMENT).
  * FONT_ASCENT, FONT_DESCENT, DEFAULT_CHAR are consumed and NOT written as
    properties. FONT_ASCENT/FONT_DESCENT feed the accelerators (bdftopcf
    rejects fonts without them; we fall back to fbby+fbbyoff and -fbbyoff,
    the same values `Font.create` would produce). DEFAULT_CHAR (int) becomes
    the encoding table's defaultCh (as uint16); absent => 0 (not 0xFFFF).
  * Generated properties, appended in this order when not present:
      POINT_SIZE   = trunc(float32(pointsize) * 10)
      FONT         = header fontname (string)
      WEIGHT       = 10 (computed later; bitmapComputeWeight returns 10)
      RESOLUTION   = trunc(xres * 100 / 72.27), only if xres == yres
      RESOLUTION_X = xres, RESOLUTION_Y = yres
      X_HEIGHT     = computed later
      QUAD_WIDTH   = computed later
    "computed later" also applies to an existing integer WEIGHT / X_HEIGHT /
    QUAD_WIDTH whose value is -1:
      X_HEIGHT   = exHeight if non-zero else ink_minbounds.ascent, where
                   exHeight comes from the LAST glyph whose name is exactly
                   "x": (bbh + bbyoff) if > 0 else bbh (pre-padding values)
      QUAD_WIDTH = trunc(sum(dwx) / count) over glyphs named exactly "0".."9"
                   if any, else trunc((ink_minbounds.cw + ink_maxbounds.cw)/2)
      (ink bounds of the ENCODED glyphs, see below).
  * Glyph name = first whitespace-delimited token of the name (C isspace),
    at most 99 bytes (`STARTCHAR %99s`).
  * Glyph encoding: encoded glyphs use their codepoint; an unencoded glyph
    with an altcode (`ENCODING -1 n`) is encoded at n. Codes outside
    0..0xFFFF (incl. -1 and > 0xFFFF, for which bdftopcf only prints an error)
    keep their place in the glyph list (metrics, bitmaps, names, swidths) but
    get no encoding entry. If two glyphs share a code, the later wins in the
    encoding table (both stay in the glyph list).
  * Metrics: lsb = bbxoff, rsb = bbxoff + bbw, ascent = bbh + bbyoff,
    descent = -bbyoff, width = DWIDTH x, attributes = 0. Missing DWIDTH ->
    headers dwx0 -> max(0, bbxoff + bbw); missing SWIDTH -> headers swx0 ->
    computed per spec §2.8. Out-of-int16 metrics raise (bdftopcf rejects).
  * Bitmap rows (bdfReadBitmap): odd hex length gets a '0' appended, at most
    ceil(bbw/8) bytes are taken, a non-hex character contributes nothing to
    its byte, shorter rows are zero-padded, a full row has the bits beyond
    bbw cleared; missing rows are zero (bdftopcf would fail), extra rows are
    ignored. Each row is padded to the glyph pad. Bit order LSB => every byte
    of the glyph buffer is bit-reversed. Terminal padding and ink metrics
    (below) work on this buffer. Finally, if bit order != byte order, the
    bytes of each glyph buffer are swapped within each scan unit (2 or 4).
    DEVIATION (non-default flags only): bdftopcf swaps the bytes while reading
    the BDF, i.e. BEFORE terminal padding and ink metrics, which both index
    the buffer byte by byte; with bit order != byte order and scan unit > 1
    this garbles padded glyphs and ink metrics (and X_HEIGHT / QUAD_WIDTH
    when they are derived from the ink bounds). write_pcf swaps last, so its
    output differs from bdftopcf's exactly in those buggy cases (fonts with
    ink metrics, i.e. constant-metrics fonts) and is identical otherwise.
    scanunit > glyphpad with bit order != byte order raises ValueError
    (bdftopcf swaps across the end of the glyph buffer: undefined behaviour).
    bdftopcf -p8 is broken as well (it writes glyph pad index 0 for pad 8 but
    pads the rows to 8 bytes); write_pcf(glyphpad=8) writes pad index 3.
  * Font bounds (bitmapComputeFontBounds): "all" bounds over every glyph
    (stored in ACCELERATORS, decide METRICS compression) and "encoded" bounds
    over the encoding table in row/col order (stored in BDF_ACCELERATORS).
    Glyphs whose lsb, rsb, width, ascent and descent are all 0 are skipped
    for min/max (initial min = 32767, max = -32768; attributes min = AND,
    max = OR over all glyphs, init 0xFFFF / 0). maxOverlap = max(rsb - width)
    over all (resp. encoded) glyphs, initial -32768. drawDirection = RTL if
    more glyphs have negative width; the counters are NOT reset between the
    "all" and the "encoded" pass, so the encoded info counts all + encoded.
  * Terminal padding: if the ENCODED bounds satisfy FontCouldBeTerminal
    (min lsb >= 0, max rsb <= max width, min width == max width, max ascent
    <= FONT_ASCENT, max descent <= FONT_DESCENT, not already exactly a
    terminal cell, and not (max ascent == 0 and max descent == 0)), EVERY
    glyph (also unencoded ones) is reshaped to lsb 0, rsb = width = encoded
    min width, ascent FONT_ASCENT, descent FONT_DESCENT (bits copied by
    FontCharReshape, clipped) and the bounds are recomputed.
  * Accelerator flags (FontComputeInfoAccelerators, separately for the "all"
    and the "encoded" info): noOverlap = maxOverlap <= min lsb;
    constantMetrics = min == max for lsb, rsb, width, ascent, descent,
    attributes; terminalFont = constantMetrics and max lsb == 0 and max rsb ==
    max width and max ascent == FONT_ASCENT and max descent == FONT_DESCENT;
    constantWidth = min width == max width; inkInside = min lsb >= 0 and
    maxOverlap <= 0 and min ascent >= -FONT_DESCENT and max ascent <=
    FONT_ASCENT and -min descent <= FONT_ASCENT and max descent <=
    FONT_DESCENT.
  * Ink metrics (INK_METRICS table, ink bounds in both accelerators, format
    0x100 on both accelerator tables) exist ONLY if the ENCODED info has
    constantMetrics (after terminal padding). They are computed for every
    glyph by FontCharInkMetrics on the (padded, bit-order transformed) glyph
    buffer: top/bottom-most rows with a non-zero byte, left/right-most set bit
    of the OR of each byte column. Empty glyph => (lsb, lsb, width, 0, 0).
    Ink bounds use the same min/max rule as the normal bounds (all glyphs for
    ACCELERATORS, encoded glyphs for BDF_ACCELERATORS). Without ink metrics
    the ink bounds equal the normal bounds.
  * METRICS / INK_METRICS are compressed (format 0x100, 5 bytes per glyph,
    value + 0x80) iff min and max "all" bounds (resp. ink bounds) have every
    field in -128..127 and attributes == 0.
  * BDF_ENCODINGS: firstCol, lastCol, firstRow, lastRow, defaultCh (int16),
    then (lastCol-firstCol+1)*(lastRow-firstRow+1) glyph indices (0xFFFF =
    none). With no encoded glyph bdftopcf writes 256, 0, 256, 0 and 65025
    entries of 0xFFFF (only a warning); this is reproduced.
  * BITMAPS: count, offsets (for the chosen pad), bitmapsSizes for all four
    pads (sum of BYTES_PER_ROW(bbw, pad) * bbh), then the glyph buffers.
  * Strings (property names/values, glyph names) are NUL-terminated, never
    deduplicated.

Inputs bdftopcf rejects but `write_pcf` accepts (documented deviations): no
FONT_ASCENT / FONT_DESCENT (fallbacks above), missing SWIDTH/DWIDTH,
non-integer unquoted property values (written as strings), key-only
properties (skipped), zero glyphs, STARTFONT other than 2.1, missing SIZE
values (pointsize/xres/yres default to 0 -> POINT_SIZE 0, 75 dpi for
xres/yres < 1), wrong hex row counts, glyph names that are empty (written as
an empty string), BDF syntax bdftopcf cannot read (leading blanks, missing
final newline, ...). Lost by the bdfparser model and therefore not
reproducible: interleaving of encoded/unencoded glyphs, duplicate codepoints
(the model keeps one), ATTRIBUTES lines, and lines longer than 1023 bytes
(bdftopcf splits them).

===========================================================================
Reader (`read_pcf`) reconstruction, SPEC-v3 §6
===========================================================================
* Gzip input (magic 1F 8B) is decompressed first. Any byte/bit order, glyph
  pad, scan unit, compressed or uncompressed metrics. METRICS and BITMAPS are
  required; everything else is optional; INK_METRICS is ignored. Tables may
  declare sizes beyond EOF (bdftopcf does); only bytes actually read must
  exist. Like libXfont's pcfread, the whole bitmap block is byte-swapped (if
  bit order != byte order, per scan unit) and bit-reversed (LSB bit order)
  at once before glyphs are sliced out of it.
* headers: bdfversion 2.1, fontname = string property FONT (else ""),
  pointsize = round(POINT_SIZE / 10), else PIXEL_SIZE, else fbby;
  xres/yres = RESOLUTION_X / RESOLUTION_Y (else 75); FONTBOUNDINGBOX from the
  ACCELERATORS bounds (else BDF_ACCELERATORS, else computed from the glyph
  metrics with the bounds rule above): fbbx = max rsb - min lsb, fbby = max
  ascent + max descent, fbbxoff = min lsb, fbbyoff = -max descent (all 0 when
  no glyph counts); metricsset 0.
* props: ALL PCF properties in table order with their original names
  (string -> str, else signed int32), including FONT (whose first string
  value is also copied to headers['fontname'], SPEC §6). Keeping FONT in
  place makes write_pcf(read_pcf(P)) == P for bdftopcf-written P (and for
  our own output with the same options). Then, if absent:
  FONT_ASCENT / FONT_DESCENT from the accelerators, and DEFAULT_CHAR from the
  encoding table when defaultCh is neither 0 (bdftopcf's value for "no
  DEFAULT_CHAR") nor 0xFFFF.
* glyphs, in PCF glyph index order: each code in the encoding table
  (cp = row << 8 | col) gives an encoded glyph; glyphs referenced by no code
  go to `unencoded` (altcode None). meta: BBX = (rsb - lsb, ascent + descent,
  lsb, -descent), DWIDTH = (width, 0), SWIDTH = (swidths entry, 0) or
  computed per §2.8; name from GLYPH_NAMES, else defaultglyphname(cp, unicode)
  (unicode = encoding.is_unicode_charset(sanitize_charset(CHARSET_REGISTRY,
  CHARSET_ENCODING)), i.e. the "Unicode identity" row of §4), or
  "glyph{index}" for unencoded glyphs; hex rows = MSB-first, ceil(bbw/8)
  bytes per row, upper-case, bits beyond bbw cleared (zero-width or
  zero-height glyphs get no rows, as in BDF). A glyph referenced by several
  codes yields one (copied) entry per code.
* Strings are decoded as UTF-8, falling back to Latin-1 per string.
* PCF -> model -> write_pcf (same format options) is byte-identical for
  bdftopcf-written files. It is not for PCFs whose content bdftopcf would
  never produce (e.g. defaultCh 0xFFFF without DEFAULT_CHAR, other table
  sets, attributes, unsorted/odd layouts).
* Known BDF -> PCF -> BDF losses: the original SIZE point size (only
  POINT_SIZE/10 survives), the original FONTBOUNDINGBOX, terminal padding
  applied by bdftopcf, and the generated properties (POINT_SIZE, FONT,
  WEIGHT, RESOLUTION*, X_HEIGHT, QUAD_WIDTH), which become ordinary props.
"""

from __future__ import annotations

import gzip
import math
import struct
import zlib
from collections.abc import Iterable
from typing import Any

from .encoding import is_unicode_charset, sanitize_charset
from .errors import BDFParseError
from .glyph import defaultglyphname

__all__ = ['PCFError', 'read_pcf', 'write_pcf']


class PCFError(BDFParseError):
    """
    Raised for malformed PCF data or fonts that cannot be written as PCF.
    Subclass of `BDFParseError` (itself a `ValueError`).
    """


# --------------------------------------------------------------------------
# constants

PCF_MAGIC = b'\x01fcp'

PCF_PROPERTIES = 1 << 0
PCF_ACCELERATORS = 1 << 1
PCF_METRICS = 1 << 2
PCF_BITMAPS = 1 << 3
PCF_INK_METRICS = 1 << 4
PCF_BDF_ENCODINGS = 1 << 5
PCF_SWIDTHS = 1 << 6
PCF_GLYPH_NAMES = 1 << 7
PCF_BDF_ACCELERATORS = 1 << 8

PCF_DEFAULT_FORMAT = 0x00000000
PCF_ACCEL_W_INKBOUNDS = 0x00000100
PCF_COMPRESSED_METRICS = 0x00000100
PCF_FORMAT_MASK = 0xFFFFFF00

PCF_GLYPH_PAD_MASK = 3
PCF_BYTE_MASK = 1 << 2
PCF_BIT_MASK = 1 << 3
PCF_SCAN_UNIT_MASK = 3 << 4

MINSHORT = -32768
MAXSHORT = 32767

_PAD_INDEX = {1: 0, 2: 1, 4: 2, 8: 3}
_SCAN_INDEX = {1: 0, 2: 1, 4: 2}

_REVERSE = bytes(int(f'{i:08b}'[::-1], 2) for i in range(256))
_HEXVAL = {c: int(chr(c), 16) for c in b'0123456789abcdefABCDEF'}
_HEXCHARS = frozenset('0123456789abcdefABCDEF')
_C_SPACE = b' \t\n\v\f\r'

_INK_MASK_MSB = (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01)
_INK_MASK_LSB = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80)


def _bytes_per_row(bits: int, nbytes: int) -> int:
    """BYTES_PER_ROW from libXfont: row length in bytes padded to `nbytes`."""
    if nbytes == 1:
        return (bits + 7) >> 3
    if nbytes == 2:
        return ((bits + 15) >> 4) << 1
    if nbytes == 4:
        return ((bits + 31) >> 5) << 2
    return ((bits + 63) >> 6) << 3


def _round_up(n: int) -> int:
    return (n + 3) & ~3


def _cdiv(a: int, b: int) -> int:
    """C integer division (truncation toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _round(v: float) -> int:
    return math.floor(v + 0.5)


def _swidth(headers: dict, dwx: int) -> int:
    """SPEC §2.8 swidth(dwx), computed from the headers only."""
    pointsize = headers.get('pointsize')
    xres = headers.get('xres')
    if pointsize and xres:
        return _round(dwx * 72000 / (pointsize * xres))
    return _round(dwx * 1000 / max(headers.get('fbbx') or 1, 1))


def _charset_is_unicode(props: dict) -> bool:
    key = sanitize_charset(props.get('charset_registry'), props.get('charset_encoding'))
    return is_unicode_charset(key)


# --------------------------------------------------------------------------
# metrics helpers (xCharInfo = [lsb, rsb, width, ascent, descent, attributes])

_LSB, _RSB, _CW, _ASC, _DESC, _ATTR = range(6)


def _init_bounds() -> tuple[list[int], list[int]]:
    return (
        [MAXSHORT, MAXSHORT, MAXSHORT, MAXSHORT, MAXSHORT, 0xFFFF],
        [MINSHORT, MINSHORT, MINSHORT, MINSHORT, MINSHORT, 0x0000],
    )


def _minmax(mn: list[int], mx: list[int], m: list[int]) -> None:
    """COMPUTE_MINMAX + attribute AND/OR."""
    if m[_ASC] or m[_DESC] or m[_LSB] or m[_RSB] or m[_CW]:
        for f in (_ASC, _DESC, _LSB, _RSB, _CW):
            v = m[f]
            if mn[f] > v:
                mn[f] = v
            if mx[f] < v:
                mx[f] = v
    mn[_ATTR] &= m[_ATTR]
    mx[_ATTR] |= m[_ATTR]


class _Info:
    """The subset of libXfont's FontInfoRec that ends up in a PCF file."""

    def __init__(self) -> None:
        self.minbounds, self.maxbounds = _init_bounds()
        self.ink_minbounds, self.ink_maxbounds = _init_bounds()
        self.max_overlap = MINSHORT
        self.draw_direction = 0
        self.font_ascent = 0
        self.font_descent = 0
        self.no_overlap = 0
        self.constant_metrics = 0
        self.terminal_font = 0
        self.constant_width = 0
        self.ink_inside = 0
        self.ink_metrics = 0

    def compute_accelerators(self) -> None:
        """FontComputeInfoAccelerators."""
        mn, mx = self.minbounds, self.maxbounds
        self.no_overlap = 1 if self.max_overlap <= mn[_LSB] else 0
        if mn == mx:
            self.constant_metrics = 1
            self.terminal_font = (
                1
                if (
                    mx[_LSB] == 0
                    and mx[_RSB] == mx[_CW]
                    and mx[_ASC] == self.font_ascent
                    and mx[_DESC] == self.font_descent
                )
                else 0
            )
        else:
            self.constant_metrics = 0
            self.terminal_font = 0
        self.constant_width = 1 if mn[_CW] == mx[_CW] else 0
        self.ink_inside = (
            1
            if (
                mn[_LSB] >= 0
                and self.max_overlap <= 0
                and mn[_ASC] >= -self.font_descent
                and mx[_ASC] <= self.font_ascent
                and -mn[_DESC] <= self.font_ascent
                and mx[_DESC] <= self.font_descent
            )
            else 0
        )

    def could_be_terminal(self) -> bool:
        """FontCouldBeTerminal."""
        mn, mx = self.minbounds, self.maxbounds
        if (
            mn[_LSB] >= 0
            and mx[_RSB] <= mx[_CW]
            and mn[_CW] == mx[_CW]
            and mx[_ASC] <= self.font_ascent
            and mx[_DESC] <= self.font_descent
            and (
                mx[_LSB] != 0
                or mn[_RSB] != mn[_CW]
                or mn[_ASC] != self.font_ascent
                or mn[_DESC] != self.font_descent
            )
        ):
            return not (mx[_ASC] == 0 and mx[_DESC] == 0)
        return False


class _Glyph:
    __slots__ = ('metrics', 'bits', 'name', 'swidth', 'ink')

    def __init__(self, metrics: list[int], bits: bytes, name: bytes, swidth: int) -> None:
        self.metrics = metrics
        self.bits = bits
        self.name = name
        self.swidth = swidth
        self.ink: list[int] | None = None


# --------------------------------------------------------------------------
# writer


def _swap_units(buf: bytearray, unit: int) -> bytearray:
    """TwoByteSwap / FourByteSwap on the whole buffer (partial unit: zeros)."""
    n = len(buf)
    rem = n % unit
    if rem:
        buf = buf + bytes(unit - rem)
    out = bytearray(len(buf))
    for k in range(unit):
        out[k::unit] = buf[unit - 1 - k :: unit]
    return out[:n]


def _hex_row(row: str, nbytes: int) -> bytes:
    """bdfReadBitmap's decoding of one hex row into at most `nbytes` bytes."""
    if len(row) == nbytes * 2 and _HEXCHARS.issuperset(row):
        return bytes.fromhex(row)
    raw = row.encode('utf-8', 'replace')
    if len(raw) & 1:
        raw += b'0'
    out = bytearray()
    for i in range(min(len(raw) >> 1, nbytes)):
        b = 0
        for c in raw[2 * i : 2 * i + 2]:
            v = _HEXVAL.get(c)
            if v is not None:
                b = ((b << 4) + v) & 0xFF
        out.append(b)
    return bytes(out)


def _read_bitmap(hexdata: list[str] | None, bw: int, bh: int, pad: int, bitlsb: bool) -> bytes:
    width_bytes = _bytes_per_row(bw, pad)
    if bw == 0 or bh == 0:
        return b''
    hex_bytes = (bw + 7) >> 3
    mask = (0xFF << (8 - (bw & 7))) & 0xFF
    rows = hexdata or []
    fill = bytes(width_bytes - hex_bytes)
    pic = bytearray()
    for r in range(bh):
        line = _hex_row(rows[r].strip(), hex_bytes) if r < len(rows) else b''
        if len(line) < hex_bytes:
            pic += line
            pic += bytes(hex_bytes - len(line))
        else:
            pic += line
            if mask and pic[-1] & ~mask & 0xFF:
                pic[-1] &= mask
        pic += fill
    if bitlsb:
        pic = bytearray(pic.translate(_REVERSE))
    return bytes(pic)


def _reshape(g: _Glyph, new: list[int], pad: int, bitlsb: bool) -> bytes:
    """FontCharReshape: copy the bits of `g` into a glyph with metrics `new`."""
    src = g.metrics
    outwidth = new[_RSB] - new[_LSB]
    outheight = new[_DESC] + new[_ASC]
    out_bytes = _bytes_per_row(outwidth, pad)
    in_bytes = _bytes_per_row(src[_RSB] - src[_LSB], pad)
    out = bytearray(out_bytes * outheight)
    old = g.bits
    y_min = max(-src[_ASC], -new[_ASC])
    y_max = min(src[_DESC], new[_DESC])
    x_min = max(src[_LSB], new[_LSB])
    x_max = min(src[_RSB], new[_RSB])
    in_off = (y_min + src[_ASC]) * in_bytes
    out_off = (y_min + new[_ASC]) * out_bytes
    for _y in range(y_min, y_max):
        for x in range(x_min, x_max):
            xs = x - src[_LSB]
            xd = x - new[_LSB]
            if bitlsb:
                if old[in_off + (xs >> 3)] & (1 << (xs & 7)):
                    out[out_off + (xd >> 3)] |= 1 << (xd & 7)
            else:
                if old[in_off + (xs >> 3)] & (1 << (7 - (xs & 7))):
                    out[out_off + (xd >> 3)] |= 1 << (7 - (xd & 7))
        in_off += in_bytes
        out_off += out_bytes
    return bytes(out)


def _ink_metrics(g: _Glyph, pad: int, bitlsb: bool) -> list[int]:
    """FontCharInkMetrics, emulated on the final byte buffer."""
    m = g.metrics
    lsb, asc, desc = m[_LSB], m[_ASC], m[_DESC]
    ink = [0, 0, m[_CW], 0, 0, m[_ATTR]]
    bitw = m[_RSB] - m[_LSB]
    bytew = (bitw + 7) >> 3
    bytewp = _bytes_per_row(bitw, pad)
    height = asc + desc
    bits = g.bits
    first = -1
    for r in range(height):
        o = r * bytewp
        if any(bits[o : o + bytew]):
            first = r
            break
    if first < 0:
        ink[_LSB] = lsb
        ink[_RSB] = lsb
        return ink
    ink[_ASC] = asc - first
    last = first
    for r in range(height - 1, -1, -1):
        o = r * bytewp
        if any(bits[o : o + bytew]):
            last = r
            break
    ink[_DESC] = last - asc + 1
    masks = _INK_MASK_LSB if bitlsb else _INK_MASK_MSB
    colbits = []
    for hpos in range(bytew):
        c = 0
        for r in range(height):
            c |= bits[r * bytewp + hpos]
        colbits.append(c)
    # left
    bmax = 8
    bpos = 0
    hpos = 0
    found = False
    while hpos < bytew:
        charbits = colbits[hpos]
        if charbits:
            if hpos == bytew - 1:
                bmax = bitw - (hpos << 3)
            bpos = bmax
            k = 0
            while True:
                bpos -= 1
                if bpos < 0:  # pragma: no cover - bits beyond the width are always cleared
                    break
                if charbits & masks[k]:
                    found = True
                    break
                k += 1
            if found:
                break
        hpos += 1
    ink[_LSB] = lsb + (hpos << 3) + bmax - bpos - 1
    # right
    bmax = bitw - ((bytew - 1) << 3)
    hpos = bytew - 1
    found = False
    while hpos >= 0:
        charbits = colbits[hpos]
        if charbits:
            bpos = bmax
            while True:
                bpos -= 1
                if bpos < 0:  # pragma: no cover - bits beyond the width are always cleared
                    break
                if charbits & masks[bpos]:
                    found = True
                    break
            if found:
                break
        bmax = 8
        hpos -= 1
    ink[_RSB] = lsb + (hpos << 3) + bpos + 1
    return ink


class _Out:
    """Byte sink tracking the current position (pcfWrite & friends)."""

    def __init__(self) -> None:
        self.buf = bytearray()

    def lsb32(self, v: int) -> None:
        self.buf += struct.pack('<I', v & 0xFFFFFFFF)

    def int32(self, msb: bool, v: int) -> None:
        self.buf += struct.pack('>I' if msb else '<I', v & 0xFFFFFFFF)

    def int16(self, msb: bool, v: int) -> None:
        self.buf += struct.pack('>H' if msb else '<H', v & 0xFFFF)

    def int8(self, v: int) -> None:
        self.buf.append(v & 0xFF)


def _check16(name: str, v: int) -> None:
    if not MINSHORT <= v <= MAXSHORT:
        raise PCFError(f'Glyph "{name}": metric value {v} does not fit in 16 bits')


# integer property values are written as 32-bit words (signed or unsigned)
_PROP_MIN = -(2**31)
_PROP_MAX = 2**32 - 1


def _check_prop(name: str, v: int) -> None:
    if not _PROP_MIN <= v <= _PROP_MAX:
        raise PCFError(f'PCF: property {name} value {v} does not fit in 32 bits')


def _as_int(v: Any) -> int | None:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    return None


def _glyph_token(name: Any) -> bytes:
    raw = ('' if name is None else str(name)).encode('utf-8', 'replace')
    for i, c in enumerate(raw):
        if c not in _C_SPACE:
            raw = raw[i:]
            break
    else:
        return b''
    for i, c in enumerate(raw):
        if c in _C_SPACE:
            raw = raw[:i]
            break
    return raw[:99]


def _norm_order(value: str, what: str) -> bool:
    v = str(value).lower()
    if v in ('msb', 'big', 'm'):
        return True
    if v in ('lsb', 'little', 'l'):
        return False
    raise ValueError(f"{what} must be 'msb' or 'lsb', got {value!r}")


def _iter_glyph_metas(font: Any) -> Iterable[tuple[list, int]]:
    for cp, meta in font.glyphs.items():
        yield meta, cp
    for entry in getattr(font, 'unencoded', None) or []:
        if isinstance(entry, dict):
            meta = entry.get('meta')
            alt = entry.get('altcode')
        else:  # tolerate a bare meta list
            meta, alt = entry, None
        yield meta, (alt if isinstance(alt, int) and alt >= 0 else -1)


def write_pcf(
    font: Any,
    *,
    byteorder: str = 'msb',
    bitorder: str = 'msb',
    glyphpad: int = 4,
    scanunit: int = 1,
) -> bytes:
    """
    Convert a `Font` to PCF bytes. With the default options the result is
    byte-identical to `bdftopcf` (1.1) run with default flags on the same BDF.
    `byteorder`/`bitorder`: 'msb' or 'lsb' (bdftopcf -M/-L, -m/-l);
    `glyphpad`: 1, 2, 4 or 8 (-p); `scanunit`: 1, 2 or 4 (-u).
    """
    msb = _norm_order(byteorder, 'byteorder')
    bitmsb = _norm_order(bitorder, 'bitorder')
    if glyphpad not in _PAD_INDEX:
        raise ValueError(f'glyphpad must be 1, 2, 4 or 8, got {glyphpad!r}')
    if scanunit not in _SCAN_INDEX:
        raise ValueError(f'scanunit must be 1, 2 or 4, got {scanunit!r}')
    bitlsb = not bitmsb
    swap = scanunit if bitmsb != msb else 1
    if swap > glyphpad:
        raise ValueError(
            'scanunit must not exceed glyphpad when bitorder != byteorder '
            '(bdftopcf output is undefined for that combination)'
        )
    fmt = (
        (_SCAN_INDEX[scanunit] << 4)
        | ((1 if bitmsb else 0) << 3)
        | ((1 if msb else 0) << 2)
        | _PAD_INDEX[glyphpad]
    )

    headers = font.headers
    props = font.props
    propnames = getattr(font, '_propnames', {}) or {}

    def hget(key: str, default: int = 0) -> int:
        v = headers.get(key)
        return v if isinstance(v, int) and not isinstance(v, bool) else default

    # ---- properties (bdfReadProperties) ----
    plist: list[list[Any]] = []  # [name bytes, is_string, value(int|bytes)]
    font_ascent: int | None = None
    font_descent: int | None = None
    default_ch = 0
    special: dict[str, list[Any]] = {}
    for key, value in props.items():
        if key == 'comment':
            continue
        name = str(propnames.get(key, key.upper()))
        if name.startswith('COMMENT') or value is None:
            continue
        iv = _as_int(value)
        is_string = iv is None
        if iv is not None:
            _check_prop(name, iv)
        if name in ('FONT_ASCENT', 'FONT_DESCENT', 'DEFAULT_CHAR'):
            if not is_string:
                if name == 'FONT_ASCENT':
                    font_ascent = iv
                elif name == 'FONT_DESCENT':
                    font_descent = iv
                else:
                    default_ch = iv & 0xFFFF  # type: ignore[operator]
            continue
        entry = [
            name.encode('utf-8', 'replace'),
            is_string,
            str(value).encode('utf-8', 'replace') if is_string else iv,
        ]
        plist.append(entry)
        if name in (
            'POINT_SIZE',
            'RESOLUTION',
            'X_HEIGHT',
            'WEIGHT',
            'QUAD_WIDTH',
            'FONT',
            'RESOLUTION_X',
            'RESOLUTION_Y',
        ):
            special[name] = entry
    fbby = hget('fbby')
    fbbyoff = hget('fbbyoff')
    if font_ascent is None:
        font_ascent = fbby + fbbyoff
    if font_descent is None:
        font_descent = -fbbyoff
    pointsize = headers.get('pointsize') or 0
    xres = hget('xres', 75)
    yres = hget('yres', 75)
    if xres < 1:
        xres = 75
    if yres < 1:
        yres = 75
    fontname = str(headers.get('fontname') or '')

    def add(name: str, is_string: bool, value: Any) -> list[Any]:
        entry = [name.encode(), is_string, value]
        plist.append(entry)
        special[name] = entry
        return entry

    if 'POINT_SIZE' not in special:
        ps32 = struct.unpack('<f', struct.pack('<f', float(pointsize)))[0]
        add('POINT_SIZE', False, int(ps32 * 10.0))
    if 'FONT' not in special:
        add('FONT', True, fontname.encode('utf-8', 'replace'))
    if 'WEIGHT' not in special:
        add('WEIGHT', False, -1)
    if 'RESOLUTION' not in special and xres == yres:
        add('RESOLUTION', False, int((xres * 100.0) / 72.27))
    if 'RESOLUTION_X' not in special:
        add('RESOLUTION_X', False, xres)
    if 'RESOLUTION_Y' not in special:
        add('RESOLUTION_Y', False, yres)
    if 'X_HEIGHT' not in special:
        add('X_HEIGHT', False, -1)
    if 'QUAD_WIDTH' not in special:
        add('QUAD_WIDTH', False, -1)

    # range guards before any bitmap is built (SPEC-v3 §11.2): generated property
    # values must fit their 32-bit words; the font ascent / descent (16-bit in
    # the X font info and in the metrics of a terminal font's character cell)
    # and the cell height must fit 16 bits
    for pname, is_string, pvalue in plist:
        if not is_string:
            _check_prop(pname.decode('utf-8', 'replace'), pvalue)
    for v in (font_ascent, font_descent, font_ascent + font_descent):
        if not MINSHORT <= v <= MAXSHORT:
            raise PCFError(
                f'PCF: FONT_ASCENT {font_ascent} / FONT_DESCENT {font_descent} '
                'do not fit in 16 bits'
            )

    # ---- glyphs (bdfReadCharacters) ----
    glyphs: list[_Glyph] = []
    encoding: dict[int, int] = {}
    bitmaps_sizes = [0, 0, 0, 0]
    digit_widths = 0
    digit_count = 0
    ex_height = 0
    hdwx = headers.get('dwx0')
    hswx = headers.get('swx0')
    for meta, enc in _iter_glyph_metas(font):
        if meta is None or len(meta) < 17:
            raise PCFError('glyph meta must be a 17-slot list')
        name = _glyph_token(meta[0])
        bw = meta[2] or 0
        bh = meta[3] or 0
        bl = meta[4] or 0
        bb = meta[5] or 0
        label = name.decode('utf-8', 'replace')
        if bw < 0 or bh < 0:
            raise PCFError(f'Glyph "{label}" has a negative sized bitmap, {bw}x{bh}')
        wx = meta[8]
        if wx is None:
            wx = hdwx if isinstance(hdwx, int) else max(0, bl + bw)
        sw = meta[6]
        if sw is None:
            sw = hswx if isinstance(hswx, int) else _swidth(headers, wx)
        for v in (wx, bl, bb, bl + bw, bh + bb, -bb):
            _check16(label, v)
        if len(name) == 1:
            if 0x30 <= name[0] <= 0x39:
                digit_widths += wx
                digit_count += 1
            elif name == b'x':
                ex_height = bh if (bh + bb) <= 0 else bh + bb
        if 0 <= enc <= 0xFFFF:
            encoding[enc] = len(glyphs)
        for i in range(4):
            bitmaps_sizes[i] += _bytes_per_row(bw, 1 << i) * bh
        bits = _read_bitmap(meta[16], bw, bh, glyphpad, bitlsb)
        glyphs.append(_Glyph([bl, bl + bw, wx, bh + bb, -bb, 0], bits, name, sw))

    if encoding:
        rows = [c >> 8 for c in encoding]
        cols = [c & 0xFF for c in encoding]
        first_row, last_row = min(rows), max(rows)
        first_col, last_col = min(cols), max(cols)
    else:
        first_row, last_row, first_col, last_col = 256, 0, 256, 0

    def encoded_glyphs() -> list[_Glyph]:
        out = []
        for r in range(first_row, last_row + 1):
            for c in range(first_col, last_col + 1):
                idx = encoding.get((r << 8) | c)
                if idx is not None:
                    out.append(glyphs[idx])
        return out

    enc_list = encoded_glyphs()

    info = _Info()  # pFont->info (encoded glyphs)
    extra = _Info()  # bitmapExtra->info (all glyphs)
    info.font_ascent = extra.font_ascent = font_ascent
    info.font_descent = extra.font_descent = font_descent

    def compute_bounds() -> None:
        """bitmapComputeFontBounds."""
        numneg = numpos = 0
        for target, gl in ((extra, glyphs), (info, enc_list)):
            target.minbounds, target.maxbounds = _init_bounds()
            max_overlap = MINSHORT
            for g in gl:
                m = g.metrics
                _minmax(target.minbounds, target.maxbounds, m)
                if m[_CW] < 0:
                    numneg += 1
                else:
                    numpos += 1
                overlap = m[_RSB] - m[_CW]
                if max_overlap < overlap:
                    max_overlap = overlap
            target.draw_direction = 1 if numneg > numpos else 0
            target.max_overlap = max_overlap

    compute_bounds()
    if info.could_be_terminal():
        new = [0, info.minbounds[_CW], info.minbounds[_CW], font_ascent, font_descent, 0]
        for g in glyphs:
            g.bits = _reshape(g, new, glyphpad, bitlsb)
            g.metrics = [new[0], new[1], new[2], new[3], new[4], g.metrics[_ATTR]]
        w = new[_RSB] - new[_LSB]
        h = new[_ASC] + new[_DESC]
        for i in range(4):
            bitmaps_sizes[i] = len(glyphs) * (_bytes_per_row(w, 1 << i) * h)
        compute_bounds()
    info.compute_accelerators()
    extra.compute_accelerators()
    if info.constant_metrics:
        for g in glyphs:
            g.ink = _ink_metrics(g, glyphpad, bitlsb)
        info.ink_metrics = 1
    extra.ink_metrics = info.ink_metrics
    if swap > 1:
        for g in glyphs:
            g.bits = bytes(_swap_units(bytearray(g.bits), swap))

    # bitmapComputeFontInkBounds
    if not info.ink_metrics:
        extra.ink_minbounds, extra.ink_maxbounds = list(extra.minbounds), list(extra.maxbounds)
        info.ink_minbounds, info.ink_maxbounds = list(info.minbounds), list(info.maxbounds)
    else:
        for target, gl in ((extra, glyphs), (info, enc_list)):
            target.ink_minbounds, target.ink_maxbounds = _init_bounds()
            for g in gl:
                _minmax(target.ink_minbounds, target.ink_maxbounds, g.ink)  # type: ignore[arg-type]

    # generated property values
    xh = special.get('X_HEIGHT')
    if xh is not None and not xh[1] and xh[2] == -1:
        xh[2] = ex_height if ex_height else info.ink_minbounds[_ASC]
    qw = special.get('QUAD_WIDTH')
    if qw is not None and not qw[1] and qw[2] == -1:
        qw[2] = (
            _cdiv(digit_widths, digit_count)
            if digit_count
            else _cdiv(info.ink_minbounds[_CW] + info.ink_maxbounds[_CW], 2)
        )
    wt = special.get('WEIGHT')
    if wt is not None and not wt[1] and wt[2] == -1:
        wt[2] = 10

    return _emit(
        fmt,
        msb,
        glyphpad,
        plist,
        glyphs,
        info,
        extra,
        bitmaps_sizes,
        (first_col, last_col, first_row, last_row, default_ch),
        encoding,
    )


def _can_compress(mn: list[int], mx: list[int]) -> bool:
    for m in (mn, mx):
        for f in (_LSB, _RSB, _CW, _ASC, _DESC):
            if not -128 <= m[f] <= 127:
                return False
        if m[_ATTR] != 0:  # pragma: no cover - attributes are always 0 (no ATTRIBUTES)
            return False
    return True


def _emit(
    fmt: int,
    msb: bool,
    glyphpad: int,
    plist: list[list[Any]],
    glyphs: list[_Glyph],
    info: _Info,
    extra: _Info,
    bitmaps_sizes: list[int],
    enc_header: tuple[int, int, int, int, int],
    encoding: dict[int, int],
) -> bytes:
    n = len(glyphs)
    first_col, last_col, first_row, last_row, default_ch = enc_header
    nencodings = (last_row - first_row + 1) * (last_col - first_col + 1)

    prop_string_size = 0
    offsets: list[tuple[int, int]] = []
    for name, is_string, value in plist:
        name_off = prop_string_size
        prop_string_size += len(name) + 1
        if is_string:
            offsets.append((name_off, prop_string_size))
            prop_string_size += len(value) + 1
        else:
            offsets.append((name_off, value))
    glyph_string_size = sum(len(g.name) + 1 for g in glyphs)

    has_ink = bool(info.ink_metrics)
    metrics_compressed = _can_compress(extra.minbounds, extra.maxbounds)
    ink_compressed = _can_compress(extra.ink_minbounds, extra.ink_maxbounds)
    pad_index = _PAD_INDEX[glyphpad]
    prop_size = 8 + 9 * len(plist)

    tables: list[tuple[int, int, int]] = []  # type, format, size
    tables.append((PCF_PROPERTIES, fmt, _round_up(prop_size) + 4 + _round_up(prop_string_size)))
    tables.append((PCF_ACCELERATORS, (PCF_ACCEL_W_INKBOUNDS if has_ink else 0) | fmt, 100))
    if metrics_compressed:
        tables.append((PCF_METRICS, PCF_COMPRESSED_METRICS | fmt, _round_up(6 + 5 * n)))
    else:
        tables.append((PCF_METRICS, fmt, 8 + 12 * n))
    tables.append(
        (PCF_BITMAPS, fmt, _round_up(8 + 4 * n + 16 + bitmaps_sizes[pad_index])),
    )
    if has_ink:
        if ink_compressed:
            tables.append((PCF_INK_METRICS, PCF_COMPRESSED_METRICS | fmt, _round_up(6 + 5 * n)))
        else:
            tables.append((PCF_INK_METRICS, fmt, 8 + 12 * n))
    tables.append((PCF_BDF_ENCODINGS, fmt, _round_up(14 + 2 * nencodings)))
    tables.append((PCF_SWIDTHS, fmt, 8 + 4 * n))
    tables.append((PCF_GLYPH_NAMES, fmt, 12 + 4 * n + _round_up(glyph_string_size)))
    tables.append((PCF_BDF_ACCELERATORS, (PCF_ACCEL_W_INKBOUNDS if has_ink else 0) | fmt, 100))

    out = _Out()
    out.buf += PCF_MAGIC
    out.lsb32(len(tables))
    offset = 8 + 16 * len(tables)
    table_offsets = []
    for ttype, tfmt, tsize in tables:
        out.lsb32(ttype)
        out.lsb32(tfmt)
        out.lsb32(tsize)
        out.lsb32(offset)
        table_offsets.append(offset)
        offset += tsize

    def put_metric(m: list[int], compressed: bool) -> None:
        if compressed:
            out.buf += bytes(((v + 0x80) & 0xFF) for v in m[:5])
        else:
            out.buf += struct.pack('>6H' if msb else '<6H', *[v & 0xFFFF for v in m])

    def put_accel(i: _Info, with_ink: bool) -> None:
        for v in (
            i.no_overlap,
            i.constant_metrics,
            i.terminal_font,
            i.constant_width,
            i.ink_inside,
            i.ink_metrics,
            i.draw_direction,
            0,
        ):
            out.int8(v)
        out.int32(msb, i.font_ascent)
        out.int32(msb, i.font_descent)
        out.int32(msb, i.max_overlap)
        put_metric(i.minbounds, False)
        put_metric(i.maxbounds, False)
        if with_ink:
            put_metric(i.ink_minbounds, False)
            put_metric(i.ink_maxbounds, False)

    for (ttype, tfmt, _tsize), toff in zip(tables, table_offsets, strict=True):
        if len(out.buf) < toff:
            out.buf += bytes(toff - len(out.buf))
        out.lsb32(tfmt)
        if ttype == PCF_PROPERTIES:
            out.int32(msb, len(plist))
            for (_name, is_string, _v), (name_off, value) in zip(plist, offsets, strict=True):
                out.int32(msb, name_off)
                out.int8(1 if is_string else 0)
                out.int32(msb, value)
            out.buf += bytes(_round_up(prop_size) - prop_size)
            out.int32(msb, prop_string_size)
            for name, is_string, value in plist:
                out.buf += name + b'\0'
                if is_string:
                    out.buf += value + b'\0'
        elif ttype in (PCF_ACCELERATORS, PCF_BDF_ACCELERATORS):
            put_accel(extra if ttype == PCF_ACCELERATORS else info, has_ink)
        elif ttype in (PCF_METRICS, PCF_INK_METRICS):
            compressed = bool(tfmt & PCF_COMPRESSED_METRICS)
            if compressed:
                out.int16(msb, n)
            else:
                out.int32(msb, n)
            for g in glyphs:
                put_metric(g.metrics if ttype == PCF_METRICS else g.ink, compressed)  # type: ignore[arg-type]
        elif ttype == PCF_BITMAPS:
            out.int32(msb, n)
            off = 0
            for g in glyphs:
                out.int32(msb, off)
                off += len(g.bits)
            for s in bitmaps_sizes:
                out.int32(msb, s)
            for g in glyphs:
                out.buf += g.bits
        elif ttype == PCF_BDF_ENCODINGS:
            for v in (first_col, last_col, first_row, last_row, default_ch):
                out.int16(msb, v)
            if encoding:
                vals = [
                    encoding.get((r << 8) | c, 0xFFFF)
                    for r in range(first_row, last_row + 1)
                    for c in range(first_col, last_col + 1)
                ]
            else:
                vals = [0xFFFF] * nencodings
            out.buf += struct.pack(('>' if msb else '<') + f'{len(vals)}H', *vals)
        elif ttype == PCF_SWIDTHS:
            out.int32(msb, n)
            for g in glyphs:
                out.int32(msb, g.swidth)
        elif ttype == PCF_GLYPH_NAMES:
            out.int32(msb, n)
            off = 0
            for g in glyphs:
                out.int32(msb, off)
                off += len(g.name) + 1
            out.int32(msb, off)
            for g in glyphs:
                out.buf += g.name + b'\0'
    return bytes(out.buf)


# --------------------------------------------------------------------------
# reader


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def need(self, off: int, n: int, what: str) -> None:
        if off < 0 or off + n > len(self.data):
            raise PCFError(f'PCF data truncated while reading {what}')

    def u32le(self, off: int, what: str) -> int:
        self.need(off, 4, what)
        return struct.unpack_from('<I', self.data, off)[0]

    def unpack(self, fmt: str, off: int, what: str) -> tuple:
        self.need(off, struct.calcsize(fmt), what)
        return struct.unpack_from(fmt, self.data, off)


def _decode(raw: bytes) -> str:
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('latin-1')


def _cstring(data: bytes, start: int, end: int, what: str) -> str:
    if start < 0 or start >= end:
        raise PCFError(f'PCF string offset out of range in {what}')
    nul = data.find(b'\0', start, end)
    if nul < 0:
        nul = end
    return _decode(data[start:nul])


def read_pcf(data: bytes | bytearray | memoryview) -> Any:
    """
    Parse PCF (optionally gzip-compressed) bytes into a `Font` (SPEC-v3 §6).
    Raises `PCFError` (a `ValueError`) on malformed input.
    """
    from .font import Font

    data = bytes(data)
    if data[:2] == b'\x1f\x8b':
        try:
            data = gzip.decompress(data)
        except (OSError, EOFError, zlib.error) as e:
            raise PCFError(f'invalid gzip data: {e}') from e
    if data[:4] != PCF_MAGIC:
        raise PCFError('not a PCF file (bad magic)')
    rd = _Reader(data)
    ntables = rd.u32le(4, 'table count')
    if ntables > 1024:
        raise PCFError(f'implausible PCF table count {ntables}')
    toc: dict[int, tuple[int, int]] = {}
    for i in range(ntables):
        ttype, _tfmt, tsize, toff = rd.unpack('<4I', 8 + 16 * i, 'table of contents')
        if ttype not in toc:
            toc[ttype] = (toff, tsize)

    def table(ttype: int) -> tuple[int, int, str] | None:
        """-> (offset after format word, format, struct byte-order prefix)"""
        if ttype not in toc:
            return None
        off = toc[ttype][0]
        tfmt = rd.u32le(off, 'table format')
        return off + 4, tfmt, ('>' if tfmt & PCF_BYTE_MASK else '<')

    # ---- metrics ----
    def read_metrics(ttype: int, what: str) -> list[list[int]] | None:
        t = table(ttype)
        if t is None:
            return None
        off, tfmt, e = t
        out = []
        if (tfmt & PCF_FORMAT_MASK) == PCF_COMPRESSED_METRICS:
            (cnt,) = rd.unpack(e + 'H', off, what)
            off += 2
            rd.need(off, 5 * cnt, what)
            raw = data[off : off + 5 * cnt]
            for i in range(cnt):
                b = raw[5 * i : 5 * i + 5]
                out.append([b[0] - 0x80, b[1] - 0x80, b[2] - 0x80, b[3] - 0x80, b[4] - 0x80, 0])
        elif (tfmt & PCF_FORMAT_MASK) == PCF_DEFAULT_FORMAT:
            (cnt,) = rd.unpack(e + 'I', off, what)
            off += 4
            rd.need(off, 12 * cnt, what)
            vals = struct.unpack_from(f'{e}{6 * cnt}h', data, off)
            out = [list(vals[6 * i : 6 * i + 6]) for i in range(cnt)]
        else:
            raise PCFError(f'unsupported {what} format {tfmt:#x}')
        return out

    metrics = read_metrics(PCF_METRICS, 'metrics')
    if metrics is None:
        raise PCFError('PCF file has no METRICS table')
    n = len(metrics)
    for m in metrics:
        if m[_RSB] < m[_LSB] or m[_ASC] + m[_DESC] < 0:
            raise PCFError('PCF glyph metrics describe a negative sized bitmap')

    # ---- bitmaps ----
    t = table(PCF_BITMAPS)
    if t is None:
        raise PCFError('PCF file has no BITMAPS table')
    off, bfmt, e = t
    (cnt,) = rd.unpack(e + 'I', off, 'bitmaps')
    if cnt != n:
        raise PCFError(f'PCF bitmap count {cnt} != metrics count {n}')
    boffsets = rd.unpack(f'{e}{n}I', off + 4, 'bitmap offsets') if n else ()
    sizes = rd.unpack(e + '4I', off + 4 + 4 * n, 'bitmap sizes')
    pad = 1 << (bfmt & PCF_GLYPH_PAD_MASK)
    bit_msb = bool(bfmt & PCF_BIT_MASK)
    byte_msb = bool(bfmt & PCF_BYTE_MASK)
    scan = 1 << ((bfmt & PCF_SCAN_UNIT_MASK) >> 4)
    if scan > 4:
        raise PCFError(f'invalid PCF scan unit in format {bfmt:#x}')
    bdata_off = off + 4 + 4 * n + 16
    bdata_size = sizes[bfmt & PCF_GLYPH_PAD_MASK]
    rd.need(bdata_off, bdata_size, 'bitmap data')
    # like libXfont's pcfread: transform the whole bitmap block at once
    block = bytearray(data[bdata_off : bdata_off + bdata_size])
    if bit_msb != byte_msb and scan > 1:
        block = _swap_units(block, scan)
    if not bit_msb:
        block = bytearray(block.translate(_REVERSE))
    hexrows: list[list[str]] = []
    for i, m in enumerate(metrics):
        w = m[_RSB] - m[_LSB]
        h = m[_ASC] + m[_DESC]
        if w == 0 or h == 0:
            hexrows.append([])  # what a BDF file can express (no empty rows)
            continue
        rowlen = _bytes_per_row(w, pad)
        start = boffsets[i]
        if start + rowlen * h > bdata_size:
            raise PCFError(f'PCF bitmap of glyph {i} exceeds the bitmap data')
        nb = (w + 7) >> 3
        mask = (0xFF << (8 - (w & 7))) & 0xFF if w & 7 else 0xFF
        rows = []
        for r in range(h):
            row = block[start + r * rowlen : start + r * rowlen + nb]
            row[-1] &= mask
            rows.append(row.hex().upper())
        hexrows.append(rows)

    # ---- properties ----
    plist: list[tuple[str, Any]] = []
    t = table(PCF_PROPERTIES)
    if t is not None:
        off, _pfmt, e = t
        (nprops,) = rd.unpack(e + 'I', off, 'properties')
        rd.need(off + 4, 9 * nprops, 'properties')
        entries = []
        p = off + 4
        for _ in range(nprops):
            name_off, is_string, value = struct.unpack_from(e + 'IBi', data, p)
            entries.append((name_off, is_string, value))
            p += 9
        p += (4 - (nprops & 3)) & 3
        (ssize,) = rd.unpack(e + 'I', p, 'property strings')
        sstart = p + 4
        rd.need(sstart, ssize, 'property strings')
        send = sstart + ssize
        for name_off, is_string, value in entries:
            name = _cstring(data, sstart + name_off, send, 'properties')
            if is_string:
                plist.append((name, _cstring(data, sstart + value, send, 'properties')))
            else:
                plist.append((name, value))

    # ---- accelerators ----
    def read_accel(ttype: int) -> dict | None:
        t = table(ttype)
        if t is None:
            return None
        off, _afmt, e = t
        vals = rd.unpack(e + '8B3i12h', off, 'accelerators')
        return {
            'ascent': vals[8],
            'descent': vals[9],
            'minbounds': list(vals[11:17]),
            'maxbounds': list(vals[17:23]),
        }

    accel = read_accel(PCF_ACCELERATORS) or read_accel(PCF_BDF_ACCELERATORS)

    # ---- encodings ----
    codes: list[list[int]] = [[] for _ in range(n)]
    default_ch = 0xFFFF
    t = table(PCF_BDF_ENCODINGS)
    if t is not None:
        off, _efmt, e = t
        first_col, last_col, first_row, last_row, default_ch = rd.unpack(e + '5H', off, 'encodings')
        if first_col <= last_col and first_row <= last_row:
            ncols = last_col - first_col + 1
            total = ncols * (last_row - first_row + 1)
            idx = rd.unpack(f'{e}{total}H', off + 10, 'encodings')
            for k, gi in enumerate(idx):
                if gi != 0xFFFF:
                    if gi >= n:
                        raise PCFError(f'PCF encoding refers to missing glyph {gi}')
                    row = first_row + k // ncols
                    col = first_col + k % ncols
                    codes[gi].append((row << 8) | col)

    # ---- swidths ----
    swidths: tuple | None = None
    t = table(PCF_SWIDTHS)
    if t is not None:
        off, _sfmt, e = t
        (cnt,) = rd.unpack(e + 'I', off, 'swidths')
        if cnt != n:
            raise PCFError(f'PCF swidth count {cnt} != metrics count {n}')
        swidths = rd.unpack(f'{e}{n}i', off + 4, 'swidths')

    # ---- glyph names ----
    names: list[str] | None = None
    t = table(PCF_GLYPH_NAMES)
    if t is not None:
        off, _gfmt, e = t
        (cnt,) = rd.unpack(e + 'I', off, 'glyph names')
        if cnt != n:
            raise PCFError(f'PCF glyph name count {cnt} != metrics count {n}')
        noffs = rd.unpack(f'{e}{n}I', off + 4, 'glyph names')
        (ssize,) = rd.unpack(e + 'I', off + 4 + 4 * n, 'glyph names')
        sstart = off + 8 + 4 * n
        rd.need(sstart, ssize, 'glyph names')
        names = [_cstring(data, sstart + o, sstart + ssize, 'glyph names') for o in noffs]

    # ---- build the font ----
    font = Font()
    pdict = {name.lower(): value for name, value in plist}
    fontname = ''
    for name, value in plist:
        if name == 'FONT' and isinstance(value, str):
            fontname = value
            break

    if accel is not None:
        mn, mx = accel['minbounds'], accel['maxbounds']
    else:
        mn, mx = _init_bounds()
        for m in metrics:
            _minmax(mn, mx, m)
    if mx[_RSB] >= mn[_LSB] and mx[_ASC] + mx[_DESC] >= 0 and mn[_LSB] != MAXSHORT:
        fbb = (mx[_RSB] - mn[_LSB], mx[_ASC] + mx[_DESC], mn[_LSB], -mx[_DESC])
    else:
        fbb = (0, 0, 0, 0)

    ps = pdict.get('point_size')
    if isinstance(ps, int):
        pointsize = _round(ps / 10)
    elif isinstance(pdict.get('pixel_size'), int):
        pointsize = pdict['pixel_size']
    else:
        pointsize = fbb[1]
    xres = pdict.get('resolution_x')
    yres = pdict.get('resolution_y')
    h = font.headers
    h['bdfversion'] = 2.1
    h['fontname'] = fontname
    h['pointsize'] = pointsize
    h['xres'] = xres if isinstance(xres, int) else 75
    h['yres'] = yres if isinstance(yres, int) else 75
    h['fbbx'], h['fbby'], h['fbbxoff'], h['fbbyoff'] = fbb
    h['metricsset'] = 0

    for name, value in plist:
        font.setprop(name, value)
    if accel is not None:
        if 'font_ascent' not in font.props:
            font.setprop('FONT_ASCENT', accel['ascent'])
        if 'font_descent' not in font.props:
            font.setprop('FONT_DESCENT', accel['descent'])
    if 'default_char' not in font.props and default_ch not in (0, 0xFFFF):
        font.setprop('DEFAULT_CHAR', default_ch)

    unicode = _charset_is_unicode(font.props)
    for i, m in enumerate(metrics):
        w = m[_RSB] - m[_LSB]
        hh = m[_ASC] + m[_DESC]
        sw = swidths[i] if swidths is not None else _swidth(h, m[_CW])
        base = [
            None,
            -1,
            w,
            hh,
            m[_LSB],
            -m[_DESC],
            sw,
            0,
            m[_CW],
            0,
            None,
            None,
            None,
            None,
            None,
            None,
            hexrows[i],
        ]
        if not codes[i]:
            meta = list(base)
            meta[0] = names[i] if names is not None else f'glyph{i}'
            font.unencoded.append({'altcode': None, 'meta': meta})
            continue
        for cp in codes[i]:
            meta = list(base)
            meta[16] = list(hexrows[i])
            meta[0] = names[i] if names is not None else defaultglyphname(cp, unicode)
            meta[1] = cp
            font.glyphs[cp] = meta
    return font
