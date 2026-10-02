"""
Pixel TrueType writer and reader (SPEC-v3 §8 / §8.1).

``write_ttf(font, ...)`` turns every BDF glyph into a TrueType glyph made of
square dots (merged into one minimal outline when ``dotsize == 1``) or round
dots; ``read_ttf(data, pixelsize=None)`` rasterizes a TrueType font back into
a :class:`~bdfparser.Font`.

Byte-level choices where SPEC-v3 §8 is ambiguous or silent (the TypeScript
port MUST make the same choices so that outputs are byte-identical):

 1. Options are validated: ``ppu`` must be an even ``int`` ≥ 2, ``shape``
    ``'square'``/``'circle'``, ``dotsize`` in ``(0, 1.5]`` (§7.2),
    ``timestamp`` an ``int``; ``upem = em·ppu`` outside 16…16384 raises.
    Every other value that does not fit its TrueType field (e.g. a negative
    advance, coordinates outside int16) raises ``ValueError``; nothing is
    clamped silently.
 2. "int prop" means a property whose value is an ``int`` (not a numeric
    string); "str prop" means a ``str``. ``bold``/``italic``/``SPACING`` only
    look at ``str`` values.
 3. Name-table string properties (``COPYRIGHT``, ``FAMILY_NAME``, ``NOTICE``)
    and the ``fontname`` header count as "present" only if not ``None`` and
    non-empty after ``str()``; otherwise the next fallback is used / the
    record is omitted. ``FONT_VERSION`` is used only if it is a non-empty
    ``str``.
 4. Glyph advance ``dwx0`` (glyph) / ``dwx0`` (headers) are used when not
    ``None``. The ``.notdef`` glyph copies the ``DEFAULT_CHAR`` glyph's
    contours and advance (the glyph also keeps its own gid).
 5. ``OS/2.xAvgCharWidth`` averages over **all** glyphs including gid 0
    (``.notdef``) whose advance is > 0; ``round(sum/count)`` is computed exactly
    as ``(2·sum + count) // (2·count)``. All ``//`` are floor divisions (JS:
    ``Math.floor(a / b)``).
 6. ``head`` bounds, ``hhea`` min/max and ``maxp`` maxima include gid 0.
 7. Unicode mapping: ``font.cp2char(cp)`` (if the Font provides it, else the
    codepoint itself when ``0 <= cp <= 0x10FFFF``) must return exactly one
    Unicode code point (JS: count code points, not UTF-16 units).
    ``usFirstCharIndex``/``usLastCharIndex`` use the mapped code points
    (first-gid-wins dedupe is irrelevant for min/max).
 8. cmap format 4 only contains codes ``0x0000…0xFFFE``: U+FFFF is always the
    terminator segment (``0xFFFF→0xFFFF``, idDelta 1) even if the font maps
    U+FFFF (it is still in format 12). If the format 4 subtable would exceed
    65535 bytes (more than 8188 runs + terminator, possible with non-Unicode
    charsets), whole runs are dropped from the high end until it fits; format
    12 always contains every mapping.
 9. Glyph names: the ``post`` fallback ``glyph{gid}`` is not checked against
    already-used names (literal spec); BDF names are matched with a full-string
    match (no trailing newline allowed). All non-``.notdef`` names are stored
    as custom names (indices ``258 + k``), even standard Mac names.
10. ``BDFP`` table (adopted into SPEC-v3 §8): each ``"glyphs"`` entry is the
    18-element list ``[gid, cp, name, bbw, bbh, bbxoff, bbyoff, swx0, swy0,
    dwx0, dwy0, swx1, swy1, dwx1, dwy1, vvectorx, vvectory, altcode]``
    (``None`` → ``null``; ``cp`` ``-1`` for unencoded glyphs, ``altcode``
    ``null`` for encoded ones), listed in **storage order** (``font.glyphs``
    order, then ``font.unencoded``). The reader also accepts the legacy
    3-element form. ``props`` excludes ``comment``, ``propnames`` is the whole
    ``font._propnames`` dict, ``headers`` is every header in order with
    ``bdfversion`` replaced by ``fmtver`` (``"2.1"``, ``"2.0"``). ``dotsize`` is
    written as a JS ``Number#toString`` literal (``1``, ``0.6``, ``1e-7``;
    integral values below 2**53 as integers). JSON otherwise:
    ``json.dumps(obj, ensure_ascii=False, separators=(',', ':'))`` ⇔
    ``JSON.stringify(obj)``.
11. ``hhea``/``OS/2`` ``usWinAscent = max(hhea.ascender, head.yMax)`` is not
    clamped (raises if negative); ``usWinDescent`` is clamped at 0 per spec.
12. The table checksum of ``head`` (directory) is computed with
    ``checkSumAdjustment = 0``; the whole-file checksum likewise.
13. ``prep`` (adopted into SPEC-v3 §8) = ``B8 01 FF 85 B0 04 8D`` and
    ``maxp.maxStackElements = 1``. Without any instructions FreeType runs its
    auto-hinter, which distorts merged square glyphs at the native size; with
    this table rendering is pixel-exact with hinting on or off. Table order is
    always ``[BDFP] OS/2 cmap glyf head hhea hmtx loca maxp name post prep``.

Reader choices (§8.1): unknown/unsupported cmap formats are skipped in the
preference order (3,10), (0,4), (0,6), (3,1), (0,3), then every other record
in directory order; a glyph mapped by several code points gets the smallest;
glyph name = post name (if non-empty) else ``defaultglyphname(cp)`` else
``glyph{gid}`` (unencoded); ``fontname`` = name ID 6, else 4, else
``"Untitled"``; ``FAMILY_NAME`` = name ID 1 else ``fontname``. Glyph bounds are
recomputed from the (transformed) points incl. off-curve points. Composite
glyphs support offsets, point matching and scale / x-y scale / 2×2 (offsets
are never scaled). With a full ``BDFP`` glyph entry the outline is rasterized
into the stored box without trimming.
"""

from __future__ import annotations

import json
import math
import re
import struct
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from .outline import bitmap_contours, rasterize

if TYPE_CHECKING:  # pragma: no cover
    from .font import Font

__all__ = ['write_ttf', 'read_ttf']

_MAC_EPOCH = 2082844800
_PREP = bytes.fromhex('B801FF85B0048D')
_GLYPHNAME_RE = re.compile(r'[A-Za-z_.][A-Za-z0-9_.]{0,62}')
_PSNAME_STRIP_RE = re.compile(r'[^A-Za-z0-9-]')

# ---------------------------------------------------------------------------
# helpers shared by writer and reader


def _round(v: float) -> int:
    return math.floor(v + 0.5)


def _defaultglyphname(cp: int) -> str:
    if cp <= 0xFFFF:
        return f'uni{cp:04X}'
    return f'u{cp:05X}' if cp <= 0xFFFFF else f'u{cp:06X}'


def _fmtver(v: Any) -> str:
    f = float(v)
    if f.is_integer():
        return f'{int(f)}.0'
    return repr(f)


def _jsnum(v: float) -> str:
    """Text of JS ``String(v)`` (ECMAScript Number::toString) for a finite number."""
    f = float(v)
    if f.is_integer() and abs(f) < 2**53:
        return str(int(f))
    sign, digits, exp = Decimal(repr(f)).as_tuple()
    assert isinstance(exp, int)
    ds = ''.join(map(str, digits))
    n = exp + len(ds)  # value = 0.ds × 10^n
    ds = ds.rstrip('0') or '0'
    k = len(ds)
    neg = '-' if sign else ''
    if k <= n <= 21:
        return neg + ds + '0' * (n - k)
    if 0 < n <= 21:
        return neg + ds[:n] + '.' + ds[n:]
    if -6 < n <= 0:
        return neg + '0.' + '0' * (-n) + ds
    e = n - 1
    es = ('+' if e >= 0 else '-') + str(abs(e))
    if k == 1:
        return neg + ds + 'e' + es
    return neg + ds[0] + '.' + ds[1:] + 'e' + es


def _intprop(props: dict[str, Any], key: str) -> int | None:
    v = props.get(key)
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    return None


def _strprop(props: dict[str, Any], key: str) -> str | None:
    v = props.get(key)
    return v if isinstance(v, str) else None


def _present(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v)
    return s if s != '' else None


def _bindata(meta: Sequence[Any]) -> list[str]:
    """Equivalent of ``Glyph.draw(mode=1).bindata`` (rows padded / cut to the BBX)."""
    bbw = meta[2] or 0
    bbh = meta[3] or 0
    if bbw <= 0 or bbh <= 0:
        return []
    hexdata = meta[16] or []
    rows = []
    for i in range(bbh):
        h = hexdata[i].strip() if i < len(hexdata) else ''
        bits = bin(int(h, 16))[2:].zfill(len(h) * 4) if h else ''
        rows.append(bits[:bbw].ljust(bbw, '0'))
    return rows


def _encode_bitmap(bindata: list[str], bbw: int) -> list[str]:
    """Bitmap rows → BDF hex rows: UPPER-case, ``ceil(bbw/8)*2`` digits, left-aligned."""
    nbytes = (bbw + 7) // 8
    out = []
    for row in bindata:
        if nbytes == 0:
            out.append('')
            continue
        bits = ''.join('0' if ch == '0' else '1' for ch in row[:bbw]).ljust(nbytes * 8, '0')
        out.append(f'{int(bits, 2):0{nbytes * 2}X}')
    return out


def _trim(bindata: list[str], xoff: int, yoff: int) -> tuple[list[str], int, int, int, int]:
    """Drop empty border rows/columns. Returns ``(bindata, w, h, xoff, yoff)``."""
    h = len(bindata)
    w = len(bindata[0]) if h else 0
    inkrows = [i for i, row in enumerate(bindata) if any(ch != '0' for ch in row)]
    if not inkrows:
        return [], 0, 0, 0, 0
    top, bottom = inkrows[0], inkrows[-1]
    cols = [c for c in range(w) if any(row[c] != '0' for row in bindata)]
    left, right = cols[0], cols[-1]
    new = [row[left : right + 1] for row in bindata[top : bottom + 1]]
    return new, right - left + 1, bottom - top + 1, xoff + left, yoff + (h - 1 - bottom)


def _cp2unicode(font: Any) -> Callable[[int], int | None]:
    # resolve the charset converter once (`Font.cp2char` re-detects the charset,
    # incl. the GL form scan over all glyphs, on every call)
    converters = getattr(font, '_converters', None)
    cp2char = converters()[1] if callable(converters) else getattr(font, 'cp2char', None)

    def conv(cp: int) -> int | None:
        if callable(cp2char):
            ch = cp2char(cp)
        else:
            ch = chr(cp) if 0 <= cp <= 0x10FFFF else None
        if isinstance(ch, str) and len(ch) == 1:
            return ord(ch)
        return None

    return conv


def _checksum(data: bytes) -> int:
    if len(data) % 4:
        data = data + b'\0' * (4 - len(data) % 4)
    total = 0
    for (v,) in struct.iter_unpack('>I', data):
        total += v
    return total & 0xFFFFFFFF


def _pad4(data: bytes) -> bytes:
    return data + b'\0' * (-len(data) % 4)


def _pack(fmt: str, *values: Any) -> bytes:
    try:
        return struct.pack(fmt, *values)
    except struct.error as e:
        raise ValueError(f'value out of range for a TrueType field: {values!r} ({e})') from None


# ---------------------------------------------------------------------------
# writer


class _G:
    __slots__ = ('name', 'unicode', 'contours', 'advance', 'bounds', 'npoints')

    def __init__(self, contours: list[list[tuple[int, int, bool]]], advance: int) -> None:
        self.contours = contours
        self.advance = advance
        self.name = ''
        self.unicode: int | None = None
        self.npoints = sum(len(c) for c in contours)
        if self.npoints:
            xs = [p[0] for c in contours for p in c]
            ys = [p[1] for c in contours for p in c]
            self.bounds: tuple[int, int, int, int] | None = (min(xs), min(ys), max(xs), max(ys))
        else:
            self.bounds = None


def _encode_glyf(g: _G) -> bytes:
    if not g.contours:
        return b''
    assert g.bounds is not None
    out = [_pack('>hhhhh', len(g.contours), *g.bounds)]
    end = -1
    ends = []
    for c in g.contours:
        end += len(c)
        ends.append(end)
    out.append(_pack(f'>{len(ends)}H', *ends))
    out.append(b'\0\0')  # instructionLength
    flags = bytearray()
    xb = bytearray()
    yb = bytearray()
    px = py = 0
    for c in g.contours:
        for x, y, on in c:
            dx, dy = x - px, y - py
            px, py = x, y
            f = 1 if on else 0
            if dx == 0:
                f |= 0x10
            elif -255 <= dx <= 255:
                f |= 0x02 | (0x10 if dx > 0 else 0)
                xb.append(abs(dx))
            else:
                xb += _pack('>h', dx)
            if dy == 0:
                f |= 0x20
            elif -255 <= dy <= 255:
                f |= 0x04 | (0x20 if dy > 0 else 0)
                yb.append(abs(dy))
            else:
                yb += _pack('>h', dy)
            flags.append(f)
    out += [bytes(flags), bytes(xb), bytes(yb)]
    return _pad4(b''.join(out))


def _runs(mapping: list[tuple[int, int]]) -> list[tuple[int, int, int]]:
    """Maximal runs ``(startcode, endcode, startgid)`` where code and gid both increase by 1."""
    runs: list[tuple[int, int, int]] = []
    for code, gid in mapping:
        if runs:
            s, e, sg = runs[-1]
            if code == e + 1 and gid == sg + (code - s):
                runs[-1] = (s, code, sg)
                continue
        runs.append((code, code, gid))
    return runs


def _cmap(mapping: list[tuple[int, int]]) -> bytes:
    runs4 = _runs([(c, g) for c, g in mapping if c <= 0xFFFE])
    max_runs = (65535 - 16) // 8 - 1
    runs4 = runs4[:max_runs]
    segs = [(s, e, (sg - s) % 65536) for s, e, sg in runs4] + [(0xFFFF, 0xFFFF, 1)]
    n = len(segs)
    lg = n.bit_length() - 1
    sr = 2 * (1 << lg)
    f4 = [_pack('>HHHHHHH', 4, 16 + 8 * n, 0, 2 * n, sr, lg, 2 * n - sr)]
    f4.append(_pack(f'>{n}H', *[s[1] for s in segs]))
    f4.append(b'\0\0')
    f4.append(_pack(f'>{n}H', *[s[0] for s in segs]))
    f4.append(_pack(f'>{n}H', *[s[2] for s in segs]))
    f4.append(b'\0\0' * n)
    sub4 = b''.join(f4)
    runs12 = _runs(mapping)
    sub12 = _pack('>HHIII', 12, 0, 16 + 12 * len(runs12), 0, len(runs12)) + b''.join(
        _pack('>III', *r) for r in runs12
    )
    head = _pack('>HH', 0, 2) + _pack('>HHI', 3, 1, 20) + _pack('>HHI', 3, 10, 20 + len(sub4))
    return head + sub4 + sub12


def _name(records: list[tuple[int, str]]) -> bytes:
    count = len(records)
    strings = [s.encode('utf-16-be') for _, s in records]
    out = [_pack('>HHH', 0, count, 6 + 12 * count)]
    off = 0
    for (nid, _), b in zip(records, strings, strict=True):
        out.append(_pack('>HHHHHH', 3, 1, 0x0409, nid, len(b), off))
        off += len(b)
    return b''.join(out) + b''.join(strings)


def write_ttf(
    font: Font,
    *,
    shape: str = 'square',
    dotsize: float = 1.0,
    ppu: int = 64,
    metadata: bool = True,
    timestamp: int = 0,
) -> bytes:
    """
    Convert a bitmap font to a TrueType font (SPEC-v3 §8). Deterministic.

    :param shape: ``'square'`` or ``'circle'`` dots.
    :param dotsize: dot size relative to a pixel, ``(0, 1.5]``; square dots of
        size 1 are merged into one minimal outline per glyph.
    :param ppu: font units per pixel (even integer ≥ 2).
    :param metadata: embed the private ``BDFP`` table (lossless round trip
        through :func:`read_ttf`).
    :param timestamp: Unix seconds for ``head.created`` / ``head.modified``.
    :returns: the TTF file as ``bytes``.
    """
    if isinstance(ppu, bool) or not isinstance(ppu, int) or ppu < 2 or ppu % 2:
        raise ValueError(f'ppu must be an even integer >= 2, not {ppu!r}')
    if isinstance(timestamp, bool) or not isinstance(timestamp, int):
        raise ValueError(f'timestamp must be an int, not {timestamp!r}')
    # validates shape and dotsize
    bitmap_contours([], shape, dotsize, ppu)

    headers: dict[str, Any] = font.headers
    props: dict[str, Any] = font.props
    fbbx = headers.get('fbbx') or 0
    fbby = headers.get('fbby') or 0
    fbbyoff = headers.get('fbbyoff') or 0

    fa = _intprop(props, 'font_ascent')
    fd = _intprop(props, 'font_descent')
    ascent = fa if fa is not None else fbby + fbbyoff
    descent = fd if fd is not None else -fbbyoff
    ps = _intprop(props, 'pixel_size')
    if ps is not None and ps > 0:
        em = ps
    elif ascent + descent > 0:
        em = ascent + descent
    else:
        em = fbby
    upem = em * ppu
    if not (16 <= upem <= 16384):
        raise ValueError(f'unitsPerEm = em * ppu = {em} * {ppu} = {upem} is outside 16..16384')
    wn = _strprop(props, 'weight_name')
    bold = wn is not None and 'bold' in wn.lower()
    sl = _strprop(props, 'slant')
    italic = sl is not None and sl.upper() in ('I', 'O')

    to_uni = _cp2unicode(font)
    hdwx0 = headers.get('dwx0')

    def advance_of(meta: Sequence[Any]) -> int:
        if meta[8] is not None:
            adv = meta[8]
        elif hdwx0 is not None:
            adv = hdwx0
        else:
            adv = max(0, (meta[4] or 0) + (meta[2] or 0))
        return adv * ppu

    def make(meta: Sequence[Any]) -> _G:
        cs = bitmap_contours(_bindata(meta), shape, dotsize, ppu, meta[4] or 0, meta[5] or 0)
        return _G(cs, advance_of(meta))

    # glyph order
    glyphs: list[_G] = []
    defchar = _intprop(props, 'default_char')
    if defchar is not None and defchar in font.glyphs:
        notdef = make(font.glyphs[defchar])
    else:
        notdef = _G([], fbbx * ppu)
    notdef.name = '.notdef'
    glyphs.append(notdef)
    order: list[tuple[int, Sequence[Any], Any]] = []  # (cp, meta, altcode)
    for cp in font.itercps(1):
        order.append((cp, font.glyphs[cp], None))
    unencoded: list[dict[str, Any]] = list(getattr(font, 'unencoded', None) or [])
    for u in unencoded:
        order.append((-1, u['meta'], u.get('altcode')))
    gid_of_encoded: dict[int, int] = {}
    gid_of_unencoded: list[int] = []
    nencoded = len(order) - len(unencoded)
    for i, (cp, meta, _alt) in enumerate(order):
        g = make(meta)
        glyphs.append(g)
        if i < nencoded:
            gid_of_encoded[cp] = i + 1
            g.unicode = to_uni(cp)
        else:
            gid_of_unencoded.append(i + 1)
    numglyphs = len(glyphs)
    if numglyphs > 65535:
        raise ValueError(f'too many glyphs for TrueType: {numglyphs}')

    # names
    used = {'.notdef'}
    for i, (_cp, meta, _alt) in enumerate(order):
        gid = i + 1
        g = glyphs[gid]
        bname = meta[0]
        if (
            isinstance(bname, str)
            and _GLYPHNAME_RE.fullmatch(bname)
            and bname != '.notdef'
            and bname not in used
        ):
            name = bname
        elif g.unicode is not None and _defaultglyphname(g.unicode) not in used:
            name = _defaultglyphname(g.unicode)
        else:
            name = f'glyph{gid}'
        used.add(name)
        g.name = name

    # cmap mapping (first gid wins)
    umap: dict[int, int] = {}
    for gid, g in enumerate(glyphs):
        if g.unicode is not None and g.unicode not in umap:
            umap[g.unicode] = gid
    mapping = sorted(umap.items())

    # metrics
    inked = [g for g in glyphs if g.bounds is not None]
    if inked:
        xmin = min(g.bounds[0] for g in inked)  # type: ignore[index]
        ymin = min(g.bounds[1] for g in inked)  # type: ignore[index]
        xmax = max(g.bounds[2] for g in inked)  # type: ignore[index]
        ymax = max(g.bounds[3] for g in inked)  # type: ignore[index]
        min_lsb = min(g.bounds[0] for g in inked)  # type: ignore[index]
        min_rsb = min(g.advance - g.bounds[2] for g in inked)  # type: ignore[index]
        xmax_extent = max(g.bounds[2] for g in inked)  # type: ignore[index]
    else:
        xmin = ymin = xmax = ymax = min_lsb = min_rsb = xmax_extent = 0
    adv_max = max(g.advance for g in glyphs)
    max_points = max(g.npoints for g in glyphs)
    max_contours = max(len(g.contours) for g in glyphs)
    hasc = ascent * ppu
    hdesc = -descent * ppu

    tables: dict[bytes, bytes] = {}

    # head (checkSumAdjustment patched later)
    mac_style = (1 if bold else 0) | (2 if italic else 0)
    ts = timestamp + _MAC_EPOCH
    tables[b'head'] = _pack(
        '>IIIIHHqqhhhhHHhhh',
        0x00010000,
        0x00010000,
        0,
        0x5F0F3CF5,
        0x000B,
        upem,
        ts,
        ts,
        xmin,
        ymin,
        xmax,
        ymax,
        mac_style,
        em,
        2,
        1,
        0,
    )

    tables[b'hhea'] = _pack(
        '>IhhhHhhhhhhhhhhhH',
        0x00010000,
        hasc,
        hdesc,
        0,
        adv_max,
        min_lsb,
        min_rsb,
        xmax_extent,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        numglyphs,
    )

    tables[b'maxp'] = _pack(
        '>IHHH' + 'H' * 11,
        0x00010000,
        numglyphs,
        max_points,
        max_contours,
        *(0, 0, 2, 0, 0, 0, 0, 1, 0, 0, 0),  # maxStackElements = 1 (prep)
    )

    # OS/2
    advs = [g.advance for g in glyphs if g.advance > 0]
    avg = (2 * sum(advs) + len(advs)) // (2 * len(advs)) if advs else 0
    xh = _intprop(props, 'x_height')
    xh = xh if xh is not None and xh > 0 else None
    cap = _intprop(props, 'cap_height')
    fs_sel = (
        (1 if italic else 0) | (0x20 if bold else 0) | (0x40 if not (bold or italic) else 0) | 0x80
    )
    codes = [c for c, _ in mapping]
    first_ci = min(codes[0], 0xFFFF) if codes else 0
    last_ci = min(codes[-1], 0xFFFF) if codes else 0
    sub = upem * 65 // 100
    tables[b'OS/2'] = b''.join(
        [
            _pack(
                '>HhHHHhhhhhhhhhhh',
                4,
                avg,
                700 if bold else 400,
                5,
                0,
                sub,
                sub,
                0,
                upem * 14 // 100,
                sub,
                sub,
                0,
                upem * 48 // 100,
                ppu,
                xh * ppu // 2 if xh else ascent * ppu // 3,
                0,
            ),
            b'\0' * 10,
            b'\0' * 16,
            b'BDFP',
            _pack(
                '>HHHhhhHHIIhhHHH',
                fs_sel,
                first_ci,
                last_ci,
                hasc,
                hdesc,
                0,
                max(hasc, ymax),
                max(-hdesc, -ymin, 0),
                1,
                0,
                xh * ppu if xh else 0,
                cap * ppu if cap is not None else ascent * ppu,
                0,
                32,
                0,
            ),
        ]
    )

    tables[b'cmap'] = _cmap(mapping)

    # glyf / loca / hmtx
    glyf_parts = []
    loca = [0]
    hmtx = []
    for g in glyphs:
        b = _encode_glyf(g)
        glyf_parts.append(b)
        loca.append(loca[-1] + len(b))
        hmtx.append(_pack('>Hh', g.advance, g.bounds[0] if g.bounds else 0))
    tables[b'glyf'] = b''.join(glyf_parts)
    tables[b'loca'] = _pack(f'>{len(loca)}I', *loca)
    tables[b'hmtx'] = b''.join(hmtx)

    # name
    family = _present(props.get('family_name')) or _present(headers.get('fontname')) or 'Untitled'
    subfamily = {
        (False, False): 'Regular',
        (True, False): 'Bold',
        (False, True): 'Italic',
        (True, True): 'Bold Italic',
    }[(bold, italic)]
    full = family if subfamily == 'Regular' else family + ' ' + subfamily
    psname = _PSNAME_STRIP_RE.sub('', full)[:63] or 'Untitled'
    fv = _strprop(props, 'font_version')
    version = 'Version ' + fv if fv else 'Version 1.000'
    records: list[tuple[int, str]] = []
    copyright_ = _present(props.get('copyright'))
    if copyright_ is not None:
        records.append((0, copyright_))
    records += [(1, family), (2, subfamily), (3, psname), (4, full), (5, version), (6, psname)]
    notice = _present(props.get('notice'))
    if notice is not None:
        records.append((10, notice))
    tables[b'name'] = _name(records)

    # post
    up = _intprop(props, 'underline_position')
    ut = _intprop(props, 'underline_thickness')
    sp = _strprop(props, 'spacing')
    fixed = 1 if sp is not None and sp.upper() in ('M', 'C') else 0
    post = [
        _pack(
            '>IIhhIIIIIH',
            0x00020000,
            0,
            -up * ppu if up is not None else -ppu,
            ut * ppu if ut is not None else ppu,
            fixed,
            0,
            0,
            0,
            0,
            numglyphs,
        ),
        _pack(f'>{numglyphs}H', 0, *range(258, 258 + numglyphs - 1)),
    ]
    for g in glyphs[1:]:
        nb = g.name.encode('ascii')
        post.append(bytes([len(nb)]) + nb)
    tables[b'post'] = b''.join(post)

    # prep: PUSHW 0x01FF, SCANCTRL, PUSHB 4, SCANTYPE (dropout control on). Its
    # presence also stops FreeType from auto-hinting the unhinted glyphs.
    tables[b'prep'] = _PREP

    # BDFP
    if metadata:
        tables[b'BDFP'] = _bdfp(font, ppu, shape, dotsize, gid_of_encoded, gid_of_unencoded)

    return _assemble(tables)


def _bdfp(
    font: Any,
    ppu: int,
    shape: str,
    dotsize: float,
    gid_of_encoded: dict[int, int],
    gid_of_unencoded: list[int],
) -> bytes:
    hdrs: dict[str, Any] = {}
    for k, v in font.headers.items():
        hdrs[k] = _fmtver(v) if k == 'bdfversion' else v
    props = {k: v for k, v in font.props.items() if k != 'comment'}
    entries: list[list[Any]] = []
    for cp, meta in font.glyphs.items():
        entries.append([gid_of_encoded[cp], cp, meta[0], *meta[2:16], None])
    for gid, u in zip(gid_of_unencoded, getattr(font, 'unencoded', None) or [], strict=True):
        meta = u['meta']
        entries.append([gid, -1, meta[0], *meta[2:16], u.get('altcode')])

    def dumps(o: Any) -> str:
        return json.dumps(o, ensure_ascii=False, separators=(',', ':'))

    text = (
        '{"version":1,"ppu":'
        + dumps(ppu)
        + ',"shape":'
        + dumps(shape)
        + ',"dotsize":'
        + _jsnum(dotsize)
        + ',"headers":'
        + dumps(hdrs)
        + ',"props":'
        + dumps(props)
        + ',"propnames":'
        + dumps(dict(getattr(font, '_propnames', None) or {}))
        + ',"glyphs":'
        + dumps(entries)
        + '}'
    )
    return text.encode('utf-8')


def _assemble(tables: dict[bytes, bytes]) -> bytes:
    tags = sorted(tables)
    n = len(tags)
    lg = n.bit_length() - 1
    sr = 16 * (1 << lg)
    header = _pack('>IHHHH', 0x00010000, n, sr, lg, 16 * n - sr)
    offset = 12 + 16 * n
    directory = []
    body = []
    head_offset = 0
    for tag in tags:
        data = tables[tag]
        if tag == b'head':
            head_offset = offset
        directory.append(struct.pack('>4sIII', tag, _checksum(data), offset, len(data)))
        padded = _pad4(data)
        body.append(padded)
        offset += len(padded)
    font = bytearray(header + b''.join(directory) + b''.join(body))
    adj = (0xB1B0AFBA - _checksum(bytes(font))) & 0xFFFFFFFF
    font[head_offset + 8 : head_offset + 12] = struct.pack('>I', adj)
    return bytes(font)


# ---------------------------------------------------------------------------
# reader

_MAC_NAMES = (
    '.notdef .null nonmarkingreturn space exclam quotedbl numbersign dollar percent ampersand '
    'quotesingle parenleft parenright asterisk plus comma hyphen period slash zero one two three '
    'four five six seven eight nine colon semicolon less equal greater question at A B C D E F G H '
    'I J K L M N O P Q R S T U V W X Y Z bracketleft backslash bracketright asciicircum underscore '
    'grave a b c d e f g h i j k l m n o p q r s t u v w x y z braceleft bar braceright asciitilde '
    'Adieresis Aring Ccedilla Eacute Ntilde Odieresis Udieresis aacute agrave acircumflex '
    'adieresis atilde aring ccedilla eacute egrave ecircumflex edieresis iacute igrave icircumflex '
    'idieresis ntilde oacute ograve ocircumflex odieresis otilde uacute ugrave ucircumflex '
    'udieresis dagger degree cent sterling section bullet paragraph germandbls registered '
    'copyright trademark acute dieresis notequal AE Oslash infinity plusminus lessequal '
    'greaterequal yen mu partialdiff summation product pi integral ordfeminine ordmasculine Omega '
    'ae oslash questiondown exclamdown logicalnot radical florin approxequal Delta guillemotleft '
    'guillemotright ellipsis nonbreakingspace Agrave Atilde Otilde OE oe endash emdash quotedblleft '
    'quotedblright quoteleft quoteright divide lozenge ydieresis Ydieresis fraction currency '
    'guilsinglleft guilsinglright fi fl daggerdbl periodcentered quotesinglbase quotedblbase '
    'perthousand Acircumflex Ecircumflex Aacute Edieresis Egrave Iacute Icircumflex Idieresis '
    'Igrave Oacute Ocircumflex apple Ograve Uacute Ucircumflex Ugrave dotlessi circumflex tilde '
    'macron breve dotaccent ring cedilla hungarumlaut ogonek caron Lslash lslash Scaron scaron '
    'Zcaron zcaron brokenbar Eth eth Yacute yacute Thorn thorn minus multiply onesuperior '
    'twosuperior threesuperior onehalf onequarter threequarters franc Gbreve gbreve Idotaccent '
    'Scedilla scedilla Cacute cacute Ccaron ccaron dcroat'
).split()


class _Reader:
    def __init__(self, data: bytes, name: str) -> None:
        self.data = data
        self.name = name

    def need(self, off: int, size: int) -> None:
        if off < 0 or off + size > len(self.data):
            raise ValueError(f'Malformed TrueType font: {self.name} table is truncated')

    def unpack(self, fmt: str, off: int) -> tuple[Any, ...]:
        size = struct.calcsize(fmt)
        self.need(off, size)
        return struct.unpack_from(fmt, self.data, off)


def _parse_tables(data: bytes) -> dict[str, bytes]:
    if len(data) < 12:
        raise ValueError('Malformed TrueType font: file too short')
    tag = data[:4]
    if tag == b'OTTO':
        raise ValueError('CFF-based OpenType is not supported')
    if tag not in (b'\x00\x01\x00\x00', b'true'):
        raise ValueError(f'Not a TrueType font (sfnt version {tag!r})')
    (num,) = struct.unpack_from('>H', data, 4)
    if 12 + 16 * num > len(data):
        raise ValueError('Malformed TrueType font: table directory is truncated')
    tables: dict[str, bytes] = {}
    for i in range(num):
        t, _cs, off, ln = struct.unpack_from('>4sIII', data, 12 + 16 * i)
        if off + ln > len(data):
            raise ValueError(
                f'Malformed TrueType font: table {t.decode("latin-1")!r} exceeds the file'
            )
        tables[t.decode('latin-1')] = data[off : off + ln]
    for req in ('head', 'maxp', 'hhea', 'hmtx', 'loca', 'glyf'):
        if req not in tables:
            raise ValueError(f'Malformed TrueType font: missing required table {req!r}')
    return tables


def _parse_cmap(data: bytes) -> dict[int, int]:
    r = _Reader(data, 'cmap')
    _ver, n = r.unpack('>HH', 0)
    recs = []
    for i in range(n):
        pid, eid, off = r.unpack('>HHI', 4 + 8 * i)
        recs.append((pid, eid, off))
    order: list[tuple[int, int, int]] = []
    for pref in ((3, 10), (0, 4), (0, 6), (3, 1), (0, 3)):
        order += [x for x in recs if (x[0], x[1]) == pref]
    order += [x for x in recs if x not in order]
    for _pid, _eid, off in order:
        (fmt,) = r.unpack('>H', off)
        if fmt in (0, 4, 6, 12):
            return _parse_cmap_sub(r, off, fmt)
    return {}


def _parse_cmap_sub(r: _Reader, off: int, fmt: int) -> dict[int, int]:
    m: dict[int, int] = {}
    if fmt == 0:
        r.need(off + 6, 256)
        for c in range(256):
            g = r.data[off + 6 + c]
            if g:
                m[c] = g
    elif fmt == 6:
        first, count = r.unpack('>HH', off + 6)
        gids = r.unpack(f'>{count}H', off + 10)
        for i, g in enumerate(gids):
            if g:
                m[first + i] = g
    elif fmt == 4:
        (segx2,) = r.unpack('>H', off + 6)
        n = segx2 // 2
        ends = r.unpack(f'>{n}H', off + 14)
        starts = r.unpack(f'>{n}H', off + 16 + segx2)
        deltas = r.unpack(f'>{n}H', off + 16 + 2 * segx2)
        roff_base = off + 16 + 3 * segx2
        roffs = r.unpack(f'>{n}H', roff_base)
        for i in range(n):
            s, e, d, ro = starts[i], ends[i], deltas[i], roffs[i]
            if s > e:
                continue
            for c in range(s, e + 1):
                if c == 0xFFFF:
                    continue
                if ro == 0:
                    g = (c + d) & 0xFFFF
                else:
                    (g,) = r.unpack('>H', roff_base + 2 * i + ro + 2 * (c - s))
                    if g:
                        g = (g + d) & 0xFFFF
                if g:
                    m[c] = g
    else:  # 12
        (ngroups,) = r.unpack('>I', off + 12)
        r.need(off + 16, 12 * ngroups)
        for i in range(ngroups):
            s, e, sg = r.unpack('>III', off + 16 + 12 * i)
            if e < s or e > 0x10FFFF:
                raise ValueError('Malformed TrueType font: bad cmap format 12 group')
            for c in range(s, e + 1):
                g = sg + c - s
                if g:
                    m[c] = g
    return m


def _parse_post(data: bytes, numglyphs: int) -> list[str] | None:
    r = _Reader(data, 'post')
    (ver,) = r.unpack('>I', 0)
    if ver == 0x00010000:
        return list(_MAC_NAMES[:numglyphs]) + [''] * max(0, numglyphs - 258)
    if ver != 0x00020000:
        return None
    (n,) = r.unpack('>H', 32)
    idx = r.unpack(f'>{n}H', 34)
    pos = 34 + 2 * n
    custom: list[str] = []
    while pos < len(data):
        ln = data[pos]
        custom.append(data[pos + 1 : pos + 1 + ln].decode('latin-1'))
        pos += 1 + ln
    names = []
    for i in range(min(n, numglyphs)):
        k = idx[i]
        if k < 258:
            names.append(_MAC_NAMES[k])
        elif k - 258 < len(custom):
            names.append(custom[k - 258])
        else:
            names.append('')
    return names + [''] * (numglyphs - len(names))


def _parse_name(data: bytes) -> dict[int, str]:
    r = _Reader(data, 'name')
    _fmt, count, soff = r.unpack('>HHH', 0)
    found: dict[int, tuple[int, str]] = {}
    for i in range(count):
        pid, eid, lid, nid, ln, off = r.unpack('>HHHHHH', 6 + 12 * i)
        if pid == 3 and eid in (0, 1, 10):
            prio = 0 if lid == 0x0409 else 1
            codec = 'utf-16-be'
        elif pid == 0:
            prio, codec = 2, 'utf-16-be'
        elif pid == 1 and eid == 0:
            prio, codec = 3, 'mac-roman'
        else:
            continue
        r.need(soff + off, ln)
        raw = data[soff + off : soff + off + ln]
        try:
            s = raw.decode(codec)
        except UnicodeDecodeError:
            continue
        if nid not in found or prio < found[nid][0]:
            found[nid] = (prio, s)
    return {k: v[1] for k, v in found.items()}


class _GlyfReader:
    def __init__(self, glyf: bytes, loca: list[int]) -> None:
        self.glyf = glyf
        self.loca = loca
        self.r = _Reader(glyf, 'glyf')

    def contours(self, gid: int, depth: int = 0) -> list[list[tuple[float, float, bool]]]:
        if depth > 32:
            raise ValueError('Malformed TrueType font: composite glyph nesting too deep')
        if gid + 1 >= len(self.loca):
            raise ValueError(f'Malformed TrueType font: glyph index {gid} out of range')
        start, end = self.loca[gid], self.loca[gid + 1]
        if end <= start:
            return []
        if end > len(self.glyf):
            raise ValueError('Malformed TrueType font: loca points beyond glyf')
        r = self.r
        (nc,) = r.unpack('>h', start)
        if nc >= 0:
            return self._simple(start, nc)
        return self._composite(start, depth)

    def _simple(self, off: int, nc: int) -> list[list[tuple[float, float, bool]]]:
        try:
            return self._simple_unchecked(off, nc)
        except (IndexError, struct.error):
            raise ValueError('Malformed TrueType font: glyf table is truncated') from None

    def _simple_unchecked(self, off: int, nc: int) -> list[list[tuple[float, float, bool]]]:
        data = self.glyf
        p = off + 10
        ends = struct.unpack_from(f'>{nc}H', data, p)
        p += 2 * nc
        npts = ends[-1] + 1 if nc else 0
        (ilen,) = struct.unpack_from('>H', data, p)
        p += 2 + ilen
        flags: list[int] = []
        while len(flags) < npts:
            f = data[p]
            p += 1
            flags.append(f)
            if f & 0x08:
                flags += [f] * data[p]
                p += 1
        flags = flags[:npts]
        xs = []
        v = 0
        for f in flags:
            if f & 0x02:
                v += data[p] if f & 0x10 else -data[p]
                p += 1
            elif not f & 0x10:
                v += (data[p] << 8 | data[p + 1]) - ((data[p] & 0x80) << 9)
                p += 2
            xs.append(v)
        ys = []
        v = 0
        for f in flags:
            if f & 0x04:
                v += data[p] if f & 0x20 else -data[p]
                p += 1
            elif not f & 0x20:
                v += (data[p] << 8 | data[p + 1]) - ((data[p] & 0x80) << 9)
                p += 2
            ys.append(v)
        if p > len(data):
            raise IndexError
        out = []
        s = 0
        for e in ends:
            if e < s - 1 or e >= npts:
                raise ValueError('Malformed TrueType font: bad endPtsOfContours')
            out.append([(xs[i], ys[i], bool(flags[i] & 1)) for i in range(s, e + 1)])
            s = e + 1
        return out

    def _composite(self, off: int, depth: int) -> list[list[tuple[float, float, bool]]]:
        r = self.r
        p = off + 10
        result: list[list[tuple[float, float, bool]]] = []
        while True:
            flags, gi = r.unpack('>HH', p)
            p += 4
            if flags & 0x0001:
                a1, a2 = r.unpack('>hh' if flags & 0x0002 else '>HH', p)
                p += 4
            else:
                a1, a2 = r.unpack('>bb' if flags & 0x0002 else '>BB', p)
                p += 2
            xx, xy, yx, yy = 1.0, 0.0, 0.0, 1.0
            if flags & 0x0008:
                (sc,) = r.unpack('>h', p)
                p += 2
                xx = yy = sc / 16384
            elif flags & 0x0040:
                sx, sy = r.unpack('>hh', p)
                p += 4
                xx, yy = sx / 16384, sy / 16384
            elif flags & 0x0080:
                a, b, c, d = r.unpack('>hhhh', p)
                p += 8
                xx, xy, yx, yy = a / 16384, b / 16384, c / 16384, d / 16384
            comp = self.contours(gi, depth + 1)
            tr = [[(x * xx + y * yx, x * xy + y * yy, on) for x, y, on in c] for c in comp]
            if flags & 0x0002:
                dx, dy = a1, a2
            else:  # point matching
                parent = [pt for c in result for pt in c]
                child = [pt for c in tr for pt in c]
                if a1 >= len(parent) or a2 >= len(child):
                    raise ValueError('Malformed TrueType font: bad composite point index')
                dx, dy = parent[a1][0] - child[a2][0], parent[a1][1] - child[a2][1]
            result += [[(x + dx, y + dy, on) for x, y, on in c] for c in tr]
            if not flags & 0x0020:
                break
        return result


def _floordiv(a: float, ppu: float) -> int:
    if isinstance(a, int) and isinstance(ppu, int):
        return a // ppu
    return math.floor(a / ppu)


def _ceildiv(a: float, ppu: float) -> int:
    if isinstance(a, int) and isinstance(ppu, int):
        return -((-a) // ppu)
    return math.ceil(a / ppu)


def read_ttf(data: bytes | bytearray | memoryview, pixelsize: int | None = None) -> Font:
    """
    Read a TrueType (``glyf``) font into a :class:`~bdfparser.Font` (SPEC-v3 §8.1).

    Fonts written by :func:`write_ttf` with ``metadata=True`` are restored
    losslessly from their ``BDFP`` table. Other fonts are rasterized at
    ``pixelsize`` pixels per em (required then).
    """
    from .font import Font

    data = bytes(data)
    tables = _parse_tables(data)
    hr = _Reader(tables['head'], 'head')
    (upem,) = hr.unpack('>H', 18)
    (locfmt,) = hr.unpack('>h', 50)
    (numglyphs,) = _Reader(tables['maxp'], 'maxp').unpack('>H', 4)
    hh = _Reader(tables['hhea'], 'hhea')
    asc, desc = hh.unpack('>hh', 4)
    (nhm,) = hh.unpack('>H', 34)
    if nhm == 0 or nhm > numglyphs:
        raise ValueError('Malformed TrueType font: bad hhea.numberOfHMetrics')
    hm = _Reader(tables['hmtx'], 'hmtx')
    advances = [hm.unpack('>H', 4 * i)[0] for i in range(nhm)]
    advances += [advances[-1]] * (numglyphs - nhm)
    lr = _Reader(tables['loca'], 'loca')
    if locfmt == 0:
        loca = [v * 2 for v in lr.unpack(f'>{numglyphs + 1}H', 0)]
    elif locfmt == 1:
        loca = list(lr.unpack(f'>{numglyphs + 1}I', 0))
    else:
        raise ValueError('Malformed TrueType font: bad head.indexToLocFormat')
    gr = _GlyfReader(tables['glyf'], loca)

    font = Font()
    if 'BDFP' in tables:
        _read_with_bdfp(font, tables['BDFP'], gr, advances, numglyphs)
        return font

    if pixelsize is None:
        raise ValueError('pixelsize is required to read a TrueType font without BDFP metadata')
    if isinstance(pixelsize, bool) or not isinstance(pixelsize, int) or pixelsize <= 0:
        raise ValueError(f'pixelsize must be a positive integer, not {pixelsize!r}')
    ppu: float = upem // pixelsize if upem % pixelsize == 0 else upem / pixelsize
    names = _parse_name(tables['name']) if 'name' in tables else {}
    cmap = _parse_cmap(tables['cmap']) if 'cmap' in tables else {}
    post = _parse_post(tables['post'], numglyphs) if 'post' in tables else None
    cps: dict[int, int] = {}
    for c in sorted(cmap):
        g = cmap[c]
        if 0 < g < numglyphs and g not in cps:
            cps[g] = c

    fontname = _present(names.get(6)) or _present(names.get(4)) or 'Untitled'
    ascent = _round(asc / ppu)
    descent = _round(-desc / ppu)
    font.headers.update(
        {
            'bdfversion': 2.1,
            'fontname': fontname,
            'pointsize': pixelsize,
            'xres': 75,
            'yres': 75,
            'fbbx': pixelsize,
            'fbby': ascent + descent,
            'fbbxoff': 0,
            'fbbyoff': -descent,
            'metricsset': 0,
        }
    )
    _setprop(font, 'FAMILY_NAME', _present(names.get(1)) or fontname)
    if _present(names.get(0)) is not None:
        _setprop(font, 'COPYRIGHT', names[0])
    _setprop(font, 'PIXEL_SIZE', pixelsize)
    _setprop(font, 'FONT_ASCENT', ascent)
    _setprop(font, 'FONT_DESCENT', descent)
    _setprop(font, 'CHARSET_REGISTRY', 'ISO10646')
    _setprop(font, 'CHARSET_ENCODING', '1')

    for gid in range(1, numglyphs):
        cp = cps.get(gid)
        pname = post[gid] if post is not None else ''
        if pname:
            name = pname
        elif cp is not None:
            name = _defaultglyphname(cp)
        else:
            name = f'glyph{gid}'
        meta = _raster_meta(gr.contours(gid), ppu, None)
        dwx = _round(advances[gid] / ppu)
        meta[0] = name
        meta[1] = cp if cp is not None else -1
        meta[8], meta[9] = dwx, 0
        meta[6], meta[7] = _swidth(font, dwx), 0
        if cp is not None:
            font.glyphs[cp] = meta
        else:
            font.unencoded.append({'altcode': None, 'meta': meta})
    _updatebbox(font, pixelsize, ascent, descent)
    return font


def _setprop(font: Any, key: str, value: Any) -> None:
    font.props[key.lower()] = value
    font._propnames[key.lower()] = key


def _swidth(font: Any, dwx: int) -> int:
    f = getattr(font, 'swidth', None)
    if callable(f):
        return f(dwx)
    h = font.headers
    if h.get('pointsize') and h.get('xres'):
        return _round(dwx * 72000 / (h['pointsize'] * h['xres']))
    return _round(dwx * 1000 / max(h.get('fbbx') or 1, 1))


def _raster_meta(
    contours: list[list[tuple[float, float, bool]]],
    ppu: float,
    box: tuple[int, int, int, int] | None,
) -> list[Any]:
    """17-slot meta with BBX and hexdata filled from the rasterized outline."""
    meta: list[Any] = [None] * 17
    if box is not None:
        w, h, xo, yo = box
        if w > 0 and h > 0:
            bm = rasterize(contours, ppu, xo, yo, w, h)
        else:
            bm = ['' for _ in range(max(h, 0))]
        meta[2:6] = [w, h, xo, yo]
        meta[16] = _encode_bitmap(bm, w) if w > 0 else ['' for _ in range(max(h, 0))]
        return meta
    pts = [p for c in contours for p in c]
    if not pts:
        meta[2:6] = [0, 0, 0, 0]
        meta[16] = []
        return meta
    x0 = _floordiv(min(p[0] for p in pts), ppu)
    y0 = _floordiv(min(p[1] for p in pts), ppu)
    w = _ceildiv(max(p[0] for p in pts), ppu) - x0
    h = _ceildiv(max(p[1] for p in pts), ppu) - y0
    bm = rasterize(contours, ppu, x0, y0, w, h) if w > 0 and h > 0 else []
    bm, w, h, xo, yo = _trim(bm, x0, y0)
    meta[2:6] = [w, h, xo, yo]
    meta[16] = _encode_bitmap(bm, w)
    return meta


def _updatebbox(font: Any, em: int, ascent: int, descent: int) -> None:
    metas = list(font.glyphs.values()) + [u['meta'] for u in font.unencoded]
    boxes = [(m[4], m[5], m[4] + m[2], m[5] + m[3]) for m in metas if m[2] > 0 and m[3] > 0]
    h = font.headers
    if boxes:
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes)
        y1 = max(b[3] for b in boxes)
        h['fbbx'], h['fbby'], h['fbbxoff'], h['fbbyoff'] = x1 - x0, y1 - y0, x0, y0
    else:
        h['fbbx'], h['fbby'], h['fbbxoff'], h['fbbyoff'] = em, ascent + descent, 0, -descent


def _read_with_bdfp(
    font: Any, raw: bytes, gr: _GlyfReader, advances: list[int], numglyphs: int
) -> None:
    try:
        obj = json.loads(raw.decode('utf-8'))
        ppu = obj['ppu']
        headers = obj['headers']
        props = obj['props']
        propnames = obj['propnames']
        entries = obj['glyphs']
    except (UnicodeDecodeError, ValueError, KeyError, TypeError) as e:
        raise ValueError(f'Malformed BDFP table: {e}') from None
    if not isinstance(ppu, (int, float)) or isinstance(ppu, bool) or ppu <= 0:
        raise ValueError('Malformed BDFP table: bad ppu')
    if not (isinstance(headers, dict) and isinstance(props, dict) and isinstance(entries, list)):
        raise ValueError('Malformed BDFP table: bad structure')
    for k, v in headers.items():
        font.headers[k] = float(v) if k == 'bdfversion' else v
    for k, v in props.items():
        font.props[k] = v
    font._propnames.update(propnames)
    for e in entries:
        if not isinstance(e, list) or len(e) not in (3, 18):
            raise ValueError('Malformed BDFP table: bad glyph entry')
        gid, cp, name = e[0], e[1], e[2]
        if not isinstance(gid, int) or not 0 < gid < numglyphs or not isinstance(cp, int):
            raise ValueError('Malformed BDFP table: bad glyph entry')
        contours = gr.contours(gid)
        if len(e) == 18:
            meta = _raster_meta(contours, ppu, (e[3], e[4], e[5], e[6]))
            meta[6:16] = e[7:17]
            altcode = e[17]
        else:
            meta = _raster_meta(contours, ppu, None)
            dwx = _round(advances[gid] / ppu)
            meta[8], meta[9] = dwx, 0
            meta[6], meta[7] = _swidth(font, dwx), 0
            altcode = None
        meta[0] = name
        meta[1] = cp
        if cp == -1:
            font.unencoded.append({'altcode': altcode, 'meta': meta})
        else:
            font.glyphs[cp] = meta
