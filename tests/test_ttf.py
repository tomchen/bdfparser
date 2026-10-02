"""Tests for bdfparser.ttf (SPEC-v3 §8 / §8.1), validated with fontTools and FreeType (Pillow)."""

from __future__ import annotations

import io
import json
import math
import os
import re
import struct
import warnings
from functools import cache
from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.pointInsidePen import PointInsidePen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import _g_l_y_f
from fontTools.ttLib.tables.DefaultTable import DefaultTable

from bdfparser import Font
from bdfparser.outline import bitmap_contours
from bdfparser.ttf import _bindata, _jsnum, read_ttf, write_ttf

FONTDIR = Path(__file__).parent / 'fonts'
FULL_UNIFONT = 'unifont-13.0.04.bdf'
FONT_NAMES = sorted(p.name for p in FONTDIR.glob('*.bdf') if p.name != FULL_UNIFONT)
SMALL_FONTS = [n for n in FONT_NAMES if n not in ('HanWangYanKai-26.bdf',)]
SHAPES = ['square', 'circle']
SLOW = os.environ.get('BDFPARSER_SLOW') == '1'
#: heavy tests: run with BDFPARSER_SLOW=1 (``-m slow`` selects them)
slow = [
    pytest.mark.slow,
    pytest.mark.skipif(not SLOW, reason='slow test: set BDFPARSER_SLOW=1 to run'),
]


def font_shape_params(slow_hanwang_square: bool = False):
    """Every test font × both shapes; HanWang circle (68 MB TTF) is always slow."""
    return [
        pytest.param(
            n,
            sh,
            marks=slow
            if n == 'HanWangYanKai-26.bdf' and (sh == 'circle' or slow_hanwang_square)
            else [],
        )
        for n in FONT_NAMES
        for sh in SHAPES
    ]


@cache
def load(name: str) -> Font:
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return Font(str(FONTDIR / name))


@cache
def ttf_bytes(
    name: str, shape: str, dotsize: float = 1.0, ppu: int = 64, metadata: bool = True
) -> bytes:
    return write_ttf(load(name), shape=shape, dotsize=dotsize, ppu=ppu, metadata=metadata)


@cache
def tt_of(name: str, shape: str) -> TTFont:
    tt = TTFont(io.BytesIO(ttf_bytes(name, shape)), lazy=False, checkChecksums=2)
    for tag in tt.keys():
        tt[tag]  # decompile everything
    return tt


# ---------------------------------------------------------------------------
# independent re-derivation of the spec'd values (§8)


def iprop(font, key):
    v = font.props.get(key)
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def sprop(font, key):
    v = font.props.get(key)
    return v if isinstance(v, str) else None


def r(v):
    return math.floor(v + 0.5)


class Expected:
    def __init__(self, font: Font, shape='square', dotsize=1.0, ppu=64):
        h = font.headers
        self.ppu = ppu
        fa, fd = iprop(font, 'font_ascent'), iprop(font, 'font_descent')
        self.ascent = fa if fa is not None else h['fbby'] + h['fbbyoff']
        self.descent = fd if fd is not None else -h['fbbyoff']
        ps = iprop(font, 'pixel_size')
        self.em = ps if ps and ps > 0 else (self.ascent + self.descent or h['fbby'])
        self.upem = self.em * ppu
        wn = sprop(font, 'weight_name')
        sl = sprop(font, 'slant')
        self.bold = bool(wn and 'bold' in wn.lower())
        self.italic = bool(sl and sl.lower() in ('i', 'o'))

        def adv(m):
            if m[8] is not None:
                return m[8] * ppu
            if h.get('dwx0') is not None:
                return h['dwx0'] * ppu
            return max(0, m[4] + m[2]) * ppu

        def contours(m):
            return bitmap_contours(_bindata(m), shape, dotsize, ppu, m[4], m[5])

        self.metas = [None]
        self.cps = [None]
        self.unis: list[int | None] = [None]
        dc = iprop(font, 'default_char')
        if dc is not None and dc in font.glyphs:
            self.contours = [contours(font.glyphs[dc])]
            self.adv = [adv(font.glyphs[dc])]
        else:
            self.contours = [[]]
            self.adv = [h['fbbx'] * ppu]
        for cp in sorted(font.glyphs):
            m = font.glyphs[cp]
            self.metas.append(m)
            self.cps.append(cp)
            ch = font.cp2char(cp)
            self.unis.append(ord(ch) if ch is not None and len(ch) == 1 else None)
            self.contours.append(contours(m))
            self.adv.append(adv(m))
        for u in font.unencoded:
            self.metas.append(u['meta'])
            self.cps.append(-1)
            self.unis.append(None)
            self.contours.append(contours(u['meta']))
            self.adv.append(adv(u['meta']))
        self.n = len(self.metas)
        # names
        used = {'.notdef'}
        self.names = ['.notdef']
        for gid in range(1, self.n):
            bn = self.metas[gid][0]
            uni = self.unis[gid]
            if (
                re.fullmatch(r'[A-Za-z_.][A-Za-z0-9_.]{0,62}', bn)
                and bn != '.notdef'
                and bn not in used
            ):
                nm = bn
            elif uni is not None and self._dgn(uni) not in used:
                nm = self._dgn(uni)
            else:
                nm = f'glyph{gid}'
            used.add(nm)
            self.names.append(nm)
        self.cmap: dict[int, int] = {}
        for gid, u in enumerate(self.unis):
            if u is not None and u not in self.cmap:
                self.cmap[u] = gid
        self.bounds = []
        for cs in self.contours:
            pts = [p for c in cs for p in c]
            if pts:
                self.bounds.append(
                    (
                        min(p[0] for p in pts),
                        min(p[1] for p in pts),
                        max(p[0] for p in pts),
                        max(p[1] for p in pts),
                    )
                )
            else:
                self.bounds.append(None)

    @staticmethod
    def _dgn(u):
        return f'uni{u:04X}' if u <= 0xFFFF else (f'u{u:05X}' if u <= 0xFFFFF else f'u{u:06X}')


def check_tables(font: Font, tt: TTFont, data: bytes, shape='square', dotsize=1.0, ppu=64):
    e = Expected(font, shape, dotsize, ppu)
    assert data[:4] == b'\x00\x01\x00\x00'
    # directory: tag order, offsets, padding, checksums (independent implementation)
    (num,) = struct.unpack('>H', data[4:6])
    sr, es, rs = struct.unpack('>HHH', data[6:12])
    assert sr == 16 * 2 ** int(math.log2(num)) and es == int(math.log2(num)) and rs == 16 * num - sr
    entries = [struct.unpack('>4sIII', data[12 + 16 * i : 28 + 16 * i]) for i in range(num)]
    tags = [t for t, *_ in entries]
    exp_tags = [
        b'BDFP',
        b'OS/2',
        b'cmap',
        b'glyf',
        b'head',
        b'hhea',
        b'hmtx',
        b'loca',
        b'maxp',
        b'name',
        b'post',
        b'prep',
    ]
    if 'BDFP' not in tt:
        exp_tags.remove(b'BDFP')
    assert tags == exp_tags
    off = 12 + 16 * num
    for tag, cs, o, ln in entries:
        assert o == off and o % 4 == 0
        padded = data[o : o + ln + (-ln % 4)]
        assert padded[ln:] == b'\0' * (-ln % 4)
        if tag == b'head':
            padded = padded[:8] + b'\0\0\0\0' + padded[12:]
        assert sum(struct.unpack(f'>{len(padded) // 4}I', padded)) & 0xFFFFFFFF == cs
        off += ln + (-ln % 4)
    assert off == len(data)
    assert sum(struct.unpack(f'>{len(data) // 4}I', data)) & 0xFFFFFFFF == 0xB1B0AFBA

    # glyph order & names
    assert tt.getGlyphOrder() == e.names
    assert tt['post'].formatType == 2.0
    # cmap
    order = e.names
    exp_cmap = {u: order[g] for u, g in e.cmap.items()}
    c31 = tt['cmap'].getcmap(3, 1)
    c310 = tt['cmap'].getcmap(3, 10)
    assert [(s.platformID, s.platEncID, s.format) for s in tt['cmap'].tables] == [
        (3, 1, 4),
        (3, 10, 12),
    ]
    assert c310.cmap == exp_cmap
    assert c31.cmap == {u: g for u, g in exp_cmap.items() if u <= 0xFFFE}
    assert tt.getBestCmap() == exp_cmap

    # glyf
    glyf = tt['glyf']
    xs, ys = [], []
    for gid, name in enumerate(order):
        g = glyf[name]
        cs = e.contours[gid]
        assert g.numberOfContours == len(cs)
        assert g.isComposite() is False
        if cs:
            coords, ends, flags = g.getCoordinates(glyf)
            assert list(coords) == [(p[0], p[1]) for c in cs for p in c]
            assert [f & 1 for f in flags] == [int(p[2]) for c in cs for p in c]
            exp_ends, n = [], -1
            for c in cs:
                n += len(c)
                exp_ends.append(n)
            assert list(ends) == exp_ends
            assert (g.xMin, g.yMin, g.xMax, g.yMax) == e.bounds[gid]
            g.recalcBounds(glyf)  # fontTools' own computation equals ours
            assert (g.xMin, g.yMin, g.xMax, g.yMax) == e.bounds[gid]
            assert g.program.getBytecode() == b''
            xs += [e.bounds[gid][0], e.bounds[gid][2]]
            ys += [e.bounds[gid][1], e.bounds[gid][3]]
        adv, lsb = tt['hmtx'][name]
        assert adv == e.adv[gid]
        assert lsb == (e.bounds[gid][0] if e.bounds[gid] else 0)
    inked = [b for b in e.bounds if b]

    head = tt['head']
    assert head.tableVersion == 1.0 and head.fontRevision == 1.0
    assert head.magicNumber == 0x5F0F3CF5 and head.flags == 0x000B
    assert head.unitsPerEm == e.upem
    assert head.created == head.modified == 2082844800
    if inked:
        assert (head.xMin, head.yMin, head.xMax, head.yMax) == (min(xs), min(ys), max(xs), max(ys))
    else:
        assert (head.xMin, head.yMin, head.xMax, head.yMax) == (0, 0, 0, 0)
    assert head.macStyle == (1 if e.bold else 0) | (2 if e.italic else 0)
    assert head.lowestRecPPEM == e.em
    assert (head.fontDirectionHint, head.indexToLocFormat, head.glyphDataFormat) == (2, 1, 0)

    hhea = tt['hhea']
    assert hhea.ascent == e.ascent * ppu and hhea.descent == -e.descent * ppu
    assert hhea.lineGap == 0
    assert hhea.advanceWidthMax == max(e.adv)
    if inked:
        assert hhea.minLeftSideBearing == min(b[0] for b in inked)
        assert hhea.minRightSideBearing == min(e.adv[i] - b[2] for i, b in enumerate(e.bounds) if b)
        assert hhea.xMaxExtent == max(b[2] for b in inked)
    else:
        assert (hhea.minLeftSideBearing, hhea.minRightSideBearing, hhea.xMaxExtent) == (0, 0, 0)
    assert (hhea.caretSlopeRise, hhea.caretSlopeRun, hhea.caretOffset) == (1, 0, 0)
    assert hhea.metricDataFormat == 0 and hhea.numberOfHMetrics == e.n

    maxp = tt['maxp']
    assert maxp.tableVersion == 0x00010000 and maxp.numGlyphs == e.n
    assert maxp.maxPoints == max(sum(len(c) for c in cs) for cs in e.contours)
    assert maxp.maxContours == max(len(cs) for cs in e.contours)
    assert (maxp.maxCompositePoints, maxp.maxCompositeContours, maxp.maxZones) == (0, 0, 2)
    assert maxp.maxSizeOfInstructions == maxp.maxComponentDepth == 0
    assert maxp.maxStackElements == 1
    assert tt['prep'].program.getBytecode() == bytes.fromhex('B801FF85B0048D')

    os2 = tt['OS/2']
    upem = e.upem
    advs = [a for a in e.adv if a > 0]
    assert os2.version == 4
    assert os2.xAvgCharWidth == (r(sum(advs) / len(advs)) if advs else 0)
    assert (
        os2.usWeightClass == (700 if e.bold else 400) and os2.usWidthClass == 5 and os2.fsType == 0
    )
    assert os2.ySubscriptXSize == os2.ySubscriptYSize == upem * 65 // 100
    assert os2.ySuperscriptXSize == os2.ySuperscriptYSize == upem * 65 // 100
    assert (os2.ySubscriptXOffset, os2.ySubscriptYOffset) == (0, upem * 14 // 100)
    assert (os2.ySuperscriptXOffset, os2.ySuperscriptYOffset) == (0, upem * 48 // 100)
    xh = iprop(font, 'x_height')
    xh = xh if xh and xh > 0 else None
    assert os2.yStrikeoutSize == ppu
    assert os2.yStrikeoutPosition == (xh * ppu // 2 if xh else e.ascent * ppu // 3)
    assert os2.sFamilyClass == 0
    assert os2.achVendID == 'BDFP'
    assert os2.fsSelection == (
        (1 if e.italic else 0)
        | (0x20 if e.bold else 0)
        | (0 if e.bold or e.italic else 0x40)
        | 0x80
    )
    codes = sorted(e.cmap)
    assert os2.usFirstCharIndex == (min(codes[0], 0xFFFF) if codes else 0)
    assert os2.usLastCharIndex == (min(codes[-1], 0xFFFF) if codes else 0)
    assert (os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap) == (
        hhea.ascent,
        hhea.descent,
        0,
    )
    assert os2.usWinAscent == max(hhea.ascent, head.yMax)
    assert os2.usWinDescent == max(-hhea.descent, -head.yMin, 0)
    assert (os2.ulCodePageRange1, os2.ulCodePageRange2) == (1, 0)
    assert os2.sxHeight == (xh * ppu if xh else 0)
    ch = iprop(font, 'cap_height')
    assert os2.sCapHeight == (ch * ppu if ch is not None else e.ascent * ppu)
    assert (os2.usDefaultChar, os2.usBreakChar, os2.usMaxContext) == (0, 32, 0)
    assert os2.ulUnicodeRange1 == os2.ulUnicodeRange4 == 0

    post = tt['post']
    up, ut = iprop(font, 'underline_position'), iprop(font, 'underline_thickness')
    assert post.italicAngle == 0
    assert post.underlinePosition == (-up * ppu if up is not None else -ppu)
    assert post.underlineThickness == (ut * ppu if ut is not None else ppu)
    sp = sprop(font, 'spacing')
    assert post.isFixedPitch == (1 if sp and sp.upper() in ('M', 'C') else 0)

    name = tt['name']
    fam = font.props.get('family_name')
    fam = str(fam) if fam not in (None, '') else (font.headers.get('fontname') or 'Untitled')
    sub = {(0, 0): 'Regular', (1, 0): 'Bold', (0, 1): 'Italic', (1, 1): 'Bold Italic'}[
        (e.bold, e.italic)
    ]
    full = fam if sub == 'Regular' else f'{fam} {sub}'
    ps = re.sub(r'[^A-Za-z0-9-]', '', full)[:63] or 'Untitled'
    fv = sprop(font, 'font_version')
    exp_names = {
        1: fam,
        2: sub,
        3: ps,
        4: full,
        5: f'Version {fv}' if fv else 'Version 1.000',
        6: ps,
    }
    if font.props.get('copyright') not in (None, ''):
        exp_names[0] = str(font.props['copyright'])
    if font.props.get('notice') not in (None, ''):
        exp_names[10] = str(font.props['notice'])
    got = {(n.platformID, n.platEncID, n.langID, n.nameID): n.toUnicode() for n in name.names}
    assert got == {(3, 1, 0x409, k): v for k, v in exp_names.items()}
    assert [n.nameID for n in name.names] == sorted(exp_names)

    if 'BDFP' in tt:
        obj = json.loads(tt['BDFP'].data.decode('utf-8'))
        assert list(obj) == [
            'version',
            'ppu',
            'shape',
            'dotsize',
            'headers',
            'props',
            'propnames',
            'glyphs',
        ]
        assert obj['version'] == 1 and obj['ppu'] == ppu and obj['shape'] == shape
        assert len(obj['glyphs']) == e.n - 1
    return e


# ---------------------------------------------------------------------------
# fontTools validation for every test font, both shapes


@pytest.mark.parametrize('name,shape', font_shape_params(slow_hanwang_square=True))
def test_fonttools_validation(name, shape):
    data = ttf_bytes(name, shape)
    tt = tt_of(name, shape)
    check_tables(load(name), tt, data, shape)


@pytest.mark.parametrize(
    'name,shape',
    [
        pytest.param(
            n, sh, marks=slow if (n == 'unifont-13.0.04-reduced.bdf' and sh == 'circle') else []
        )
        for n in SMALL_FONTS
        for sh in SHAPES
    ],
)
def test_fonttools_recompile_and_ttx(name, shape):
    """fontTools recalculates head/hhea/maxp from the glyphs: must equal ours."""
    data = ttf_bytes(name, shape)
    tt = TTFont(io.BytesIO(data), recalcTimestamp=False)
    out = io.BytesIO()
    tt.save(out)
    tt2 = TTFont(io.BytesIO(out.getvalue()), checkChecksums=2)
    orig = TTFont(io.BytesIO(data))
    for tag in ('head', 'hhea', 'maxp', 'OS/2', 'name', 'post', 'hmtx', 'BDFP'):
        a = orig.reader[tag]
        b = tt2.reader[tag]
        if tag == 'head':  # checkSumAdjustment differs as the glyf encoding differs
            a, b = a[:8] + a[12:], b[:8] + b[12:]
        assert a == b, tag
    xml = io.StringIO()
    TTFont(io.BytesIO(data)).saveXML(xml)
    assert '<ttFont sfntVersion="\\x00\\x01\\x00\\x00"' in xml.getvalue()


@pytest.mark.slow
@pytest.mark.skipif(not SLOW, reason='slow test: set BDFPARSER_SLOW=1 to run')
def test_fonttools_ttx_hanwang_square():
    xml = io.StringIO()
    TTFont(io.BytesIO(ttf_bytes('HanWangYanKai-26.bdf', 'square'))).saveXML(
        xml, tables=['glyf', 'cmap', 'post']
    )
    assert '</ttFont>' in xml.getvalue()


@pytest.mark.parametrize(
    'name,shape,dotsize,ppu',
    [
        ('unifont-13.0.04-for-test.bdf', 'square', 0.6, 10),
        ('unifont-13.0.04-for-test.bdf', 'circle', 0.8, 2),
        ('unifont-13.0.04-for-test.bdf', 'square', 1.5, 128),
        ('spec_example_fixed.bdf', 'circle', 1.5, 682),
        ('spec_example_fixed.bdf', 'square', 1.0, 2),
    ],
)
def test_fonttools_validation_options(name, shape, dotsize, ppu):
    data = write_ttf(load(name), shape=shape, dotsize=dotsize, ppu=ppu)
    tt = TTFont(io.BytesIO(data), lazy=False, checkChecksums=2)
    check_tables(load(name), tt, data, shape, dotsize, ppu)


# ---------------------------------------------------------------------------
# FreeType (Pillow)


def ink_set(meta):
    out = set()
    rows = _bindata(meta)
    h = meta[3]
    for i, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch != '0':
                out.add((meta[4] + c, meta[5] + h - 1 - i))
    return out


# (font, shape, dotsize, glyph sample step)
FT_PILLOW_CASES = [
    ('unifont-13.0.04-reduced.bdf', 'square', 1.0, 41),
    ('unifont-13.0.04-reduced.bdf', 'circle', 0.6, 97),
    ('unifont-13.0.04-for-test.bdf', 'square', 1.0, 7),
    ('spec_example_fixed.bdf', 'square', 1.0, 1),
]
FT_NATIVE_CASES = [
    ('unifont-13.0.04-reduced.bdf', 'square', 1.0, 1),  # all 5441 glyphs
    ('unifont-13.0.04-for-test.bdf', 'square', 1.0, 1),
    ('HanWangYanKai-26.bdf', 'square', 1.0, 17),
    ('spec_example_fixed.bdf', 'square', 1.0, 1),
    ('unifont-13.0.04-reduced.bdf', 'square', 0.6, 5),
    ('unifont-13.0.04-reduced.bdf', 'circle', 1.0, 5),
    ('unifont-13.0.04-reduced.bdf', 'circle', 0.6, 5),
    pytest.param('HanWangYanKai-26.bdf', 'circle', 1.0, 97, marks=slow),
]


@pytest.mark.parametrize('name,shape,dotsize,step', FT_PILLOW_CASES)
def test_freetype_pillow_supersampled(name, shape, dotsize, step):
    """
    FreeType via Pillow (``fontmode = "1"``) renders the glyphs identically to
    the BDF bitmaps.

    Pillow's bundled FreeType still distorts 1-pixel features at the native
    size (it cannot be told to skip hinting; even with the ``prep`` table the
    unifont "(" loses pixels there), so we render at 8 × em pixels per em and
    sample the centre device pixel of every 8×8 cell: every sample must equal
    the BDF pixel. Exact native-size identity, hinted and unhinted, is checked
    with FreeType directly in ``test_freetype_native``.
    """
    from PIL import Image, ImageDraw, ImageFont

    font = load(name)
    em = Expected(font).em
    S = 8
    data = ttf_bytes(name, shape, dotsize)
    ft = ImageFont.truetype(io.BytesIO(data), size=em * S, layout_engine=ImageFont.Layout.BASIC)
    cps = sorted(font.glyphs)[::step]
    assert cps
    for cp in cps:
        meta = font.glyphs[cp]
        ch = font.cp2char(cp)
        if ch is None or len(ch) != 1:
            continue
        W = 3 * em * S
        im = Image.new('1', (W, W), 0)
        d = ImageDraw.Draw(im)
        d.fontmode = '1'
        ox, oy = em * S, 2 * em * S
        d.text((ox, oy), ch, font=ft, fill=1, anchor='ls')
        px = im.load()
        got = set()
        for x in range(-em, 2 * em):
            for y in range(-em, 2 * em):
                X, Y = ox + x * S + S // 2, oy - (y + 1) * S + S // 2
                if px[X, Y]:
                    got.add((x, y))
        assert got == ink_set(meta), (name, hex(cp))


def freetype_render(face, ch, flags) -> set[tuple[int, int]]:
    """Ink pixels of a mono FreeType rendering, in BDF coordinates (x right, y up, origin 0)."""
    face.load_char(ch, flags)
    g = face.glyph
    bm = g.bitmap
    assert bm.pixel_mode == 1  # FT_PIXEL_MODE_MONO
    got = set()
    buf = bm.buffer
    for rr in range(bm.rows):
        row = buf[rr * bm.pitch : (rr + 1) * bm.pitch]
        for c in range(bm.width):
            if row[c >> 3] & (0x80 >> (c & 7)):
                got.add((g.bitmap_left + c, g.bitmap_top - 1 - rr))
    return got


@pytest.mark.parametrize('hinting', [True, False], ids=['hinted', 'unhinted'])
@pytest.mark.parametrize('name,shape,dotsize,step', FT_NATIVE_CASES)
def test_freetype_native(name, shape, dotsize, step, hinting, tmp_path):
    """
    FreeType (freetype-py) at the native size (``em`` pixels per em), mono
    rendering, with hinting on (bytecode interpreter; the ``prep`` table keeps
    the auto-hinter away) and off: every glyph is pixel-identical to the BDF
    bitmap and the advance is ``DWIDTH`` pixels.
    """
    import freetype

    font = load(name)
    e = Expected(font)
    path = tmp_path / 'f.ttf'
    path.write_bytes(ttf_bytes(name, shape, dotsize))
    face = freetype.Face(str(path))
    face.set_pixel_sizes(0, e.em)
    flags = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO
    if not hinting:
        flags |= freetype.FT_LOAD_NO_HINTING
    n = 0
    for cp in sorted(font.glyphs)[::step]:
        ch = font.cp2char(cp)
        if ch is None or len(ch) != 1 or e.cmap.get(ord(ch)) != e.cps.index(cp):
            continue
        assert freetype_render(face, ch, flags) == ink_set(font.glyphs[cp]), (name, hex(cp))
        assert face.glyph.advance.x == e.adv[e.cps.index(cp)] // e.ppu * 64
        n += 1
    assert n >= min(50, len(font.glyphs)) or name.startswith('spec_example')


def test_freetype_autohinter_avoided_by_prep(tmp_path):
    """Without ``prep`` FreeType auto-hints and distorts the merged outlines (why §8 has it)."""
    import freetype

    font = load('unifont-13.0.04-reduced.bdf')
    data = write_ttf(font)
    tt = TTFont(io.BytesIO(data))
    del tt['prep']
    tt['maxp'].maxStackElements = 0
    out = io.BytesIO()
    tt.save(out)
    flags = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO
    results = {}
    for label, blob in (('with', data), ('without', out.getvalue())):
        path = tmp_path / f'{label}.ttf'
        path.write_bytes(blob)
        face = freetype.Face(str(path))
        face.set_pixel_sizes(0, 16)
        results[label] = freetype_render(face, '(', flags) == ink_set(font.glyphs[0x28])
    assert results == {'with': True, 'without': False}


# ---------------------------------------------------------------------------
# round trips


def strip_comment(props):
    return {k: v for k, v in props.items() if k != 'comment'}


def normalized_hexdata(meta):
    """hexdata as the reader produces it: exactly bbh rows (missing rows padded with zeros)."""
    rows = list(meta[16][: meta[3]])
    nb = (meta[2] + 7) // 8
    return rows + ['00' * nb] * (meta[3] - len(rows))


def assert_same_font(g: Font, f: Font):
    if any(len(m[16]) != m[3] for m in f.glyphs.values()):  # spec_example_bad.bdf: short BITMAP
        f = f.clone()
        for m in f.glyphs.values():
            m[16] = normalized_hexdata(m)
    assert g.headers == f.headers
    assert list(g.headers) == list(f.headers)
    assert g.props == strip_comment(f.props)
    assert g._propnames == f._propnames
    assert g.glyphs == f.glyphs
    assert list(g.glyphs) == list(f.glyphs)  # storage order is kept too
    assert g.unencoded == f.unencoded


@pytest.mark.parametrize('name,shape', font_shape_params())
def test_round_trip(name, shape):
    assert_same_font(read_ttf(ttf_bytes(name, shape)), load(name))


@pytest.mark.parametrize(
    'shape,dotsize,ppu',
    [
        ('square', 1.0, 2),
        ('square', 0.5, 4),
        ('square', 0.6, 10),
        ('square', 1.5, 16),
        ('circle', 0.5, 8),
        ('circle', 0.6, 2),
        ('circle', 1.2, 100),
        ('circle', 1.5, 512),
    ],
)
@pytest.mark.parametrize('name', ['unifont-13.0.04-for-test.bdf', 'spec_example_fixed.bdf'])
def test_round_trip_options(name, shape, dotsize, ppu):
    f = load(name)
    assert_same_font(read_ttf(write_ttf(f, shape=shape, dotsize=dotsize, ppu=ppu)), f)


def test_round_trip_via_font_load_bytes():
    f = load('unifont-13.0.04-2atest.bdf')
    g = Font().load_bytes(write_ttf(f))
    assert_same_font(g, f)


def test_round_trip_props_comment_dropped():
    f = load('spec_example_fixed.bdf').clone()
    f.props['comment'] = ['hello']
    g = read_ttf(write_ttf(f))
    assert 'comment' not in g.props
    assert g.glyphs == f.glyphs


def trimmed(meta):
    """(bbw, bbh, bbxoff, bbyoff, hexdata) of a glyph after trimming its ink."""
    ink = ink_set(meta)
    if not ink:
        return (0, 0, 0, 0, [])
    x0 = min(x for x, _ in ink)
    x1 = max(x for x, _ in ink)
    y0 = min(y for _, y in ink)
    y1 = max(y for _, y in ink)
    w, h = x1 - x0 + 1, y1 - y0 + 1
    rows = []
    for y in range(y1, y0 - 1, -1):
        bits = ''.join('1' if (x, y) in ink else '0' for x in range(x0, x1 + 1))
        nb = (w + 7) // 8
        rows.append(f'{int(bits.ljust(nb * 8, "0"), 2):0{nb * 2}X}')
    return (w, h, x0, y0, rows)


@pytest.mark.parametrize(
    'name,shape,dotsize,ppu',
    [
        ('unifont-13.0.04-reduced.bdf', 'square', 1.0, 64),
        ('unifont-13.0.04-for-test.bdf', 'circle', 1.0, 64),
        ('unifont-13.0.04-for-test.bdf', 'square', 0.6, 10),
        ('unifont-13.0.04-for-test.bdf', 'circle', 0.5, 6),
        pytest.param('HanWangYanKai-26.bdf', 'square', 1.0, 4, marks=slow),
        ('spec_example_fixed.bdf', 'square', 1.0, 2),
    ],
)
def test_read_without_metadata(name, shape, dotsize, ppu):
    f = load(name)
    e = Expected(f, shape, dotsize, ppu)
    data = write_ttf(f, shape=shape, dotsize=dotsize, ppu=ppu, metadata=False)
    with pytest.raises(ValueError, match='pixelsize'):
        read_ttf(data)
    g = read_ttf(data, pixelsize=e.em)
    # encoded glyphs (unicode identity fonts): same codepoints, same trimmed bitmaps
    assert sorted(g.glyphs) == sorted(u for u in e.cmap)
    for cp, m in f.glyphs.items():
        gm = g.glyphs[cp]
        assert tuple(gm[2:6]) + (gm[16],) == trimmed(m), hex(cp)
        assert gm[8] == e.adv[e.cps.index(cp)] // ppu
        assert gm[9] == 0 and gm[7] == 0
        assert gm[6] == g.swidth(gm[8])
        assert gm[10:16] == [None] * 6
        assert gm[0] == e.names[e.cps.index(cp)]
    # unencoded glyphs come back unencoded, in order
    assert [u['meta'][0] for u in g.unencoded] == e.names[e.n - len(f.unencoded) :]
    for u, gu in zip(f.unencoded, g.unencoded, strict=True):
        assert gu['altcode'] is None and gu['meta'][1] == -1
        assert tuple(gu['meta'][2:6]) + (gu['meta'][16],) == trimmed(u['meta'])
    # headers / props
    assert list(g.headers)[:5] == ['bdfversion', 'fontname', 'pointsize', 'xres', 'yres']
    assert g.headers['bdfversion'] == 2.1 and g.headers['pointsize'] == e.em
    assert g.headers['xres'] == g.headers['yres'] == 75 and g.headers['metricsset'] == 0
    assert g.props['pixel_size'] == e.em
    assert g.props['font_ascent'] == e.ascent and g.props['font_descent'] == e.descent
    assert g.props['charset_registry'] == 'ISO10646' and g.props['charset_encoding'] == '1'
    assert g._propnames['font_ascent'] == 'FONT_ASCENT'
    # FONTBOUNDINGBOX = union of the glyph boxes
    boxes = [m for m in list(g.glyphs.values()) + [u['meta'] for u in g.unencoded] if m[2] and m[3]]
    x0 = min(m[4] for m in boxes)
    y0 = min(m[5] for m in boxes)
    assert (g.headers['fbbxoff'], g.headers['fbbyoff']) == (x0, y0)
    assert g.headers['fbbx'] == max(m[4] + m[2] for m in boxes) - x0
    assert g.headers['fbby'] == max(m[5] + m[3] for m in boxes) - y0


def test_read_without_metadata_non_unicode_charset():
    f = load('unifont-13.0.04-enctest-big5.bdf')
    g = read_ttf(write_ttf(f, metadata=False), pixelsize=16)
    assert sorted(g.glyphs) == sorted(ord(f.cp2char(cp)) for cp in f.glyphs)
    for cp, m in f.glyphs.items():
        assert g.glyphs[ord(f.cp2char(cp))][16] == trimmed(m)[4]


def test_read_without_metadata_unmapped_from_charset():
    # emptylines font: ISO8859-1 charset; cp 0x6FE cannot be represented ⇒ unmapped
    f = load('unifont-13.0.04-for-test-emptylines.bdf')
    data = write_ttf(f, metadata=False)
    tt = TTFont(io.BytesIO(data))
    assert set(tt.getBestCmap()) == {
        ord(f.cp2char(cp)) for cp in f.glyphs if f.cp2char(cp) and len(f.cp2char(cp)) == 1
    }
    g = read_ttf(data, pixelsize=16)
    assert len(g.glyphs) + len(g.unencoded) == len(f.glyphs)


def test_read_without_metadata_empty_font_bbox():
    f = Font()
    f.headers.update(
        {
            'bdfversion': 2.1,
            'fontname': 'E',
            'pointsize': 8,
            'xres': 75,
            'yres': 75,
            'fbbx': 8,
            'fbby': 8,
            'fbbxoff': 0,
            'fbbyoff': -1,
            'metricsset': 0,
        }
    )
    f.setprop('PIXEL_SIZE', 8)
    f.setprop('FONT_ASCENT', 7)
    f.setprop('FONT_DESCENT', 1)
    f.glyphs[32] = ['space', 32, 0, 0, 0, 0, 1000, 0, 8, 0, None, None, None, None, None, None, []]
    g = read_ttf(write_ttf(f, metadata=False), pixelsize=8)
    assert (g.headers['fbbx'], g.headers['fbby'], g.headers['fbbxoff'], g.headers['fbbyoff']) == (
        8,
        8,
        0,
        -1,
    )
    assert g.glyphs[32][2:6] == [0, 0, 0, 0] and g.glyphs[32][16] == []
    assert g.props['family_name'] == 'E' and g.headers['fontname'] == 'E'


# ---------------------------------------------------------------------------
# reading third-party TrueType fonts (fontTools FontBuilder)


def rect(pen, x0, y0, x1, y1):
    pen.moveTo((x0, y0))
    pen.lineTo((x0, y1))
    pen.lineTo((x1, y1))
    pen.lineTo((x1, y0))
    pen.closePath()


def build_thirdparty(upem=1000, post_format=2.0, cmap_formats=None):
    fb = FontBuilder(upem, isTTF=True)
    order = ['.notdef', 'A', 'O', 'C', 'D', 'E', 'M', 'extra', 'ring']
    fb.setupGlyphOrder(order)
    cmap = {
        0x41: 'A',
        0x391: 'A',
        0x4F: 'O',
        0x43: 'C',
        0x44: 'D',
        0x45: 'E',
        0x4D: 'M',
        0x1F600: 'ring',
    }
    fb.setupCharacterMap(cmap)
    glyphs = {}
    p = TTGlyphPen(glyphs)
    glyphs['.notdef'] = p.glyph()
    p = TTGlyphPen(glyphs)
    rect(p, 123, 33, 313, 473)
    glyphs['A'] = p.glyph()
    # quadratic "circle", centre (520, 410), all off-curve points
    p = TTGlyphPen(glyphs)
    cx, cy, rr = 523, 413, 330
    k = rr * 1.0824
    d = k * 0.7071
    pts = [
        (cx, cy + k),
        (cx + d, cy + d),
        (cx + k, cy),
        (cx + d, cy - d),
        (cx, cy - k),
        (cx - d, cy - d),
        (cx - k, cy),
        (cx - d, cy + d),
    ]
    p.qCurveTo(*[(round(x), round(y)) for x, y in pts], None)
    p.closePath()
    glyphs['O'] = p.glyph()
    # mixed on/off-curve contour with a hole
    p = TTGlyphPen(glyphs)
    p.moveTo((33, 33))
    p.lineTo((33, 673))
    p.qCurveTo((693, 673), (693, 33))
    p.closePath()
    rect_hole = [(233, 233), (433, 233), (433, 433), (233, 433)]  # counter-clockwise
    p.moveTo(rect_hole[0])
    for q in rect_hole[1:]:
        p.lineTo(q)
    p.closePath()
    glyphs['ring'] = p.glyph()
    # composites: offset, scale, 2x2
    p = TTGlyphPen(glyphs)
    p.addComponent('A', (1, 0, 0, 1, 410, -220))
    p.addComponent('O', (0.5, 0, 0, 0.5, 30, 20))
    glyphs['C'] = p.glyph()
    p = TTGlyphPen(glyphs)
    p.addComponent('O', (0.75, 0, 0, 1.25, 0, 0))
    glyphs['D'] = p.glyph()
    p = TTGlyphPen(glyphs)
    p.addComponent('A', (0, 1, 1, 0, 0, 0))  # swap x/y
    p.addComponent('C', (1, 0.25, 0, 1, 0, 0))  # nested composite, shear
    glyphs['E'] = p.glyph()
    p = TTGlyphPen(glyphs)
    rect(p, 33, 33, 263, 263)
    glyphs['extra'] = p.glyph()
    # point-matched composite: second A's point 0 matched to first A's point 2
    m = _g_l_y_f.Glyph()
    m.numberOfContours = -1
    c1 = _g_l_y_f.GlyphComponent()
    c1.glyphName, c1.x, c1.y, c1.flags = 'A', 0, 0, 0
    c2 = _g_l_y_f.GlyphComponent()
    c2.glyphName, c2.firstPt, c2.secondPt, c2.flags = 'A', 2, 0, 0
    m.components = [c1, c2]
    glyphs['M'] = m
    fb.setupGlyf(glyphs)
    glyf = fb.font['glyf']
    metrics = {}
    for n in order:
        g = glyf[n]
        g.recalcBounds(glyf)
        metrics[n] = (640 if n != 'M' else 900, getattr(g, 'xMin', 0))
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable(
        {
            'familyName': 'Third Party',
            'styleName': 'Regular',
            'fullName': 'Third Party Regular',
            'psName': 'ThirdParty-Regular',
            'copyright': '(c) T',
        }
    )
    fb.setupOS2()
    fb.setupPost(keepGlyphNames=post_format == 2.0)
    fb.setupMaxp()
    if post_format == 1.0:
        fb.font['post'].formatType = 1.0
    if cmap_formats:
        from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

        tables = []
        for fmt, pid, eid in cmap_formats:
            st = CmapSubtable.newSubtable(fmt)
            st.platformID, st.platEncID, st.language = pid, eid, 0
            st.cmap = {u: g for u, g in cmap.items() if u < 256}
            tables.append(st)
        fb.font['cmap'].tables = tables
    out = io.BytesIO()
    fb.save(out)
    return out.getvalue()


def oracle_ink(tt: TTFont, gname: str, ppu: float, eps: float = 1.5):
    """
    Pixels whose centres are inside the exact (unflattened) outline, using
    fontTools' PointInsidePen (non-zero rule). Returns ``(ink, ambiguous)``:
    centres within ``eps`` font units of the outline (where the spec'd
    16-chord flattening may legitimately differ from the exact curve: the
    chord error of a quadratic is at most ``|P0 - 2·P1 + P2| / 1024``, < 1
    unit for the glyphs below) are reported as ambiguous.
    """
    glyf = tt['glyf']
    coords, ends, flags = glyf[gname].getCoordinates(glyf)
    if not len(coords):
        return set(), set()
    simple = _g_l_y_f.Glyph()
    simple.numberOfContours = len(ends)
    simple.coordinates = coords
    simple.endPtsOfContours = list(ends)
    simple.flags = flags
    simple.program = None

    def inside(x, y):
        pen = PointInsidePen(None, (x, y), evenOdd=False)
        simple.draw(pen, glyf)
        return pen.getResult()

    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    ink, ambiguous = set(), set()
    for x in range(math.floor(min(xs) / ppu) - 1, math.ceil(max(xs) / ppu) + 1):
        for y in range(math.floor(min(ys) / ppu) - 1, math.ceil(max(ys) / ppu) + 1):
            cx, cy = (x + 0.5) * ppu, (y + 0.5) * ppu
            res = {
                inside(cx + dx, cy + dy)
                for dx, dy in ((0, 0), (eps, 0), (-eps, 0), (0, eps), (0, -eps))
            }
            if len(res) > 1:
                ambiguous.add((x, y))
            elif res.pop():
                ink.add((x, y))
    return ink, ambiguous


@pytest.mark.parametrize('pixelsize', [10, 12, 25])
def test_read_thirdparty_fontbuilder(pixelsize):
    data = build_thirdparty()
    tt = TTFont(io.BytesIO(data))
    assert 'BDFP' not in tt
    ppu = 1000 / pixelsize
    g = read_ttf(data, pixelsize=pixelsize)
    expect_cps = {'A': 0x41, 'O': 0x4F, 'C': 0x43, 'D': 0x44, 'E': 0x45, 'M': 0x4D, 'ring': 0x1F600}
    assert sorted(g.glyphs) == sorted(expect_cps.values())
    assert [u['meta'][0] for u in g.unencoded] == ['extra']
    nonempty = 0
    for gname, cp in [*expect_cps.items(), ('extra', None)]:
        meta = g.glyphs[cp] if cp is not None else g.unencoded[0]['meta']
        assert meta[0] == gname
        exp, ambiguous = oracle_ink(tt, gname, ppu)
        assert ink_set(meta) - ambiguous == exp, (gname, pixelsize)
        assert len(ambiguous) <= 4, (gname, pixelsize, ambiguous)
        nonempty += bool(exp)
        adv = 900 if gname == 'M' else 640
        assert meta[8] == math.floor(adv / ppu + 0.5)
        assert meta[6] == g.swidth(meta[8])
    assert nonempty == 8
    assert g.headers['fontname'] == 'ThirdParty-Regular'
    assert g.props['family_name'] == 'Third Party'
    assert g.props['copyright'] == '(c) T'
    assert g.props['font_ascent'] == math.floor(800 / ppu + 0.5)
    assert g.props['font_descent'] == math.floor(200 / ppu + 0.5)
    assert list(g.props) == [
        'family_name',
        'copyright',
        'pixel_size',
        'font_ascent',
        'font_descent',
        'charset_registry',
        'charset_encoding',
    ]
    # the read font can be written again
    tt2 = TTFont(io.BytesIO(write_ttf(g)), checkChecksums=2)
    assert tt2['maxp'].numGlyphs == 9


def test_read_thirdparty_post_formats_and_short_loca():
    data = build_thirdparty(post_format=3.0)
    g = read_ttf(data, pixelsize=10)
    assert g.glyphs[0x41][0] == 'uni0041'
    assert g.glyphs[0x1F600][0] == 'u1F600'
    assert g.unencoded[0]['meta'][0] == 'glyph7'
    # post format 1: standard Macintosh names by gid
    g1 = read_ttf(build_thirdparty(post_format=1.0), pixelsize=10)
    assert g1.glyphs[0x41][0] == '.null'  # gid 1
    assert g1.unencoded[0]['meta'][0] == 'dollar'  # gid 7
    # short loca (fontTools chooses format 0 when possible)
    tt = TTFont(io.BytesIO(data))
    assert tt['head'].indexToLocFormat == 0


@pytest.mark.parametrize(
    'formats',
    [
        [(0, 1, 0)],
        [(6, 1, 0)],
        [(6, 0, 3), (0, 1, 0)],
        [(12, 3, 10), (4, 3, 1)],
        [(4, 0, 3)],
        [(4, 3, 1), (6, 0, 6)],
    ],
)
def test_read_cmap_formats(formats):
    data = build_thirdparty(cmap_formats=formats)
    g = read_ttf(data, pixelsize=10)
    assert sorted(g.glyphs) == [0x41, 0x43, 0x44, 0x45, 0x4D, 0x4F]
    assert len(g.unencoded) == 2


def test_read_cmap_unsupported_format_falls_back():
    data = build_thirdparty(cmap_formats=[(4, 3, 1)])
    tt = TTFont(io.BytesIO(data))
    # add a (0, 5) format 14 subtable first: must be skipped
    from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

    st = CmapSubtable.newSubtable(14)
    st.platformID, st.platEncID, st.language = 0, 5, 0xFF
    st.cmap = {}
    st.uvsDict = {0xFE00: [(0x41, None)]}
    tt['cmap'].tables.insert(0, st)
    out = io.BytesIO()
    tt.save(out)
    g = read_ttf(out.getvalue(), pixelsize=10)
    assert 0x41 in g.glyphs


def test_read_cmap_format4_with_glyph_id_array():
    data = build_thirdparty()
    tt = TTFont(io.BytesIO(data))
    sub = tt['cmap'].getcmap(3, 1)
    # non-contiguous gids in one segment force fontTools to use idRangeOffset
    sub.cmap = {0x61: 'O', 0x62: 'A', 0x63: 'ring', 0x64: 'C'}
    tt['cmap'].tables = [sub]
    out = io.BytesIO()
    tt.save(out)
    raw = out.getvalue()
    g = read_ttf(raw, pixelsize=10)
    assert {cp: m[0] for cp, m in g.glyphs.items()} == {
        0x61: 'O',
        0x62: 'A',
        0x63: 'ring',
        0x64: 'C',
    }


def test_read_name_mac_platform_fallback():
    data = build_thirdparty()
    tt = TTFont(io.BytesIO(data))
    tt['name'].names = []
    tt['name'].setName('MacFamily', 1, 1, 0, 0)
    tt['name'].setName('MacFull', 4, 1, 0, 0)
    tt['name'].setName('Ignored', 6, 3, 1, 0x0407)  # Windows, non-English: lower priority
    tt['name'].setName('Unicode PS', 6, 0, 3, 0)  # Unicode platform beats Mac
    out = io.BytesIO()
    tt.save(out)
    g = read_ttf(out.getvalue(), pixelsize=10)
    assert g.props['family_name'] == 'MacFamily'
    assert g.headers['fontname'] == 'Ignored'
    tt['name'].names = [n for n in tt['name'].names if n.nameID != 6]
    out = io.BytesIO()
    tt.save(out)
    g = read_ttf(out.getvalue(), pixelsize=10)
    assert g.headers['fontname'] == 'MacFull'
    tt['name'].names = []
    out = io.BytesIO()
    tt.save(out)
    g = read_ttf(out.getvalue(), pixelsize=10)
    assert g.headers['fontname'] == 'Untitled' and g.props['family_name'] == 'Untitled'


# ---------------------------------------------------------------------------
# malformed input


def test_otto_rejected():
    with pytest.raises(ValueError, match='CFF-based OpenType is not supported'):
        read_ttf(b'OTTO' + b'\0' * 100)


@pytest.mark.parametrize(
    'data', [b'', b'\x00\x01\x00\x00', b'wOFF' + b'\0' * 40, b'hello world, not a font']
)
def test_garbage_rejected(data):
    with pytest.raises(ValueError):
        read_ttf(data)


def test_truncated_rejected():
    data = ttf_bytes('spec_example_fixed.bdf', 'square')
    for n in (11, 12, 40, 100):
        with pytest.raises(ValueError):
            read_ttf(data[:n])
    (num,) = struct.unpack('>H', data[4:6])
    for i in range(num):
        _, _, off, ln = struct.unpack('>4sIII', data[12 + 16 * i : 28 + 16 * i])
        with pytest.raises(ValueError, match='exceeds the file'):
            read_ttf(data[: off + ln - 1])


def test_missing_table_rejected():
    data = bytearray(ttf_bytes('spec_example_fixed.bdf', 'square'))
    i = data.index(b'glyf', 12)
    data[i : i + 4] = b'glyx'
    with pytest.raises(ValueError, match="missing required table 'glyf'"):
        read_ttf(bytes(data))


def with_table(data: bytes, tag: str, payload: bytes) -> bytes:
    tt = TTFont(io.BytesIO(data))
    t = DefaultTable(tag)
    t.data = payload
    tt[tag] = t
    out = io.BytesIO()
    tt.save(out)
    return out.getvalue()


@pytest.mark.parametrize(
    'payload',
    [
        b'{bad json',
        b'\xff\xfe',
        b'[]',
        b'{"version":1}',
        b'{"version":1,"ppu":0,"headers":{},"props":{},"propnames":{},"glyphs":[]}',
        b'{"version":1,"ppu":64,"headers":[],"props":{},"propnames":{},"glyphs":[]}',
        b'{"version":1,"ppu":64,"headers":{},"props":{},"propnames":{},"glyphs":[[99,65,"A"]]}',
        b'{"version":1,"ppu":64,"headers":{},"props":{},"propnames":{},"glyphs":[[1,65]]}',
        b'{"version":1,"ppu":64,"headers":{},"props":{},"propnames":{},"glyphs":["x"]}',
    ],
)
def test_bad_bdfp_rejected(payload):
    data = with_table(ttf_bytes('spec_example_fixed.bdf', 'square'), 'BDFP', payload)
    with pytest.raises(ValueError, match='BDFP'):
        read_ttf(data)


def test_bdfp_short_entries_accepted():
    """A BDFP with spec-literal [gid, cp, name] entries: boxes are trimmed, DWIDTH from hmtx."""
    f = load('spec_example_fixed.bdf')
    data = ttf_bytes('spec_example_fixed.bdf', 'square')
    obj = json.loads(TTFont(io.BytesIO(data))['BDFP'].data)
    obj['glyphs'] = [e[:3] for e in obj['glyphs']]
    g = read_ttf(with_table(data, 'BDFP', json.dumps(obj).encode()))
    assert g.headers == f.headers
    for cp, m in f.glyphs.items():
        assert g.glyphs[cp][0] == m[0]
        assert tuple(g.glyphs[cp][2:6]) + (g.glyphs[cp][16],) == trimmed(m)
        assert g.glyphs[cp][8] == m[8]


def test_bad_glyf_rejected():
    data = ttf_bytes('spec_example_fixed.bdf', 'square')
    tt = TTFont(io.BytesIO(data))
    raw = tt.reader['glyf']
    # truncated glyf (loca still points past it)
    with pytest.raises(ValueError, match='Malformed'):
        read_ttf(with_table(data, 'glyf', raw[: len(raw) // 2]))
    # bad indexToLocFormat
    b = bytearray(data)
    off = [struct.unpack('>4sIII', data[12 + 16 * i : 28 + 16 * i]) for i in range(11)]
    head_off = next(o for t, _, o, _ in off if t == b'head')
    b[head_off + 50 : head_off + 52] = b'\x00\x05'
    with pytest.raises(ValueError, match='indexToLocFormat'):
        read_ttf(bytes(b), pixelsize=8)
    # bad numberOfHMetrics
    b = bytearray(data)
    hhea_off = next(o for t, _, o, _ in off if t == b'hhea')
    b[hhea_off + 34 : hhea_off + 36] = b'\x00\x00'
    with pytest.raises(ValueError, match='numberOfHMetrics'):
        read_ttf(bytes(b))


def test_composite_cycle_rejected():
    data = bytearray(build_thirdparty())
    tt = TTFont(io.BytesIO(bytes(data)))
    gid = tt.getGlyphID('C')
    tables = {
        t: (o, n)
        for t, _, o, n in (
            struct.unpack('>4sIII', data[12 + 16 * i : 28 + 16 * i])
            for i in range(struct.unpack('>H', data[4:6])[0])
        )
    }
    loca_off = tables[b'loca'][0]
    assert tt['head'].indexToLocFormat == 0
    (start,) = struct.unpack('>H', data[loca_off + 2 * gid : loca_off + 2 * gid + 2])
    comp = tables[b'glyf'][0] + 2 * start + 10 + 2  # first component's glyphIndex
    data[comp : comp + 2] = struct.pack('>H', gid)  # 'C' now references itself
    with pytest.raises(ValueError, match='nesting'):
        read_ttf(bytes(data), pixelsize=10)


@pytest.mark.parametrize('pixelsize', [0, -3, 2.5, True])
def test_bad_pixelsize(pixelsize):
    with pytest.raises(ValueError, match='pixelsize'):
        read_ttf(build_thirdparty(), pixelsize=pixelsize)


# ---------------------------------------------------------------------------
# writer details


def tiny_font() -> Font:
    f = Font()
    f.headers.update(
        {
            'bdfversion': 2.1,
            'fontname': 'Tiny',
            'pointsize': 8,
            'xres': 75,
            'yres': 75,
            'fbbx': 4,
            'fbby': 8,
            'fbbxoff': 0,
            'fbbyoff': -1,
            'metricsset': 0,
        }
    )
    f.setprop('FAMILY_NAME', 'Tiny')
    f.setprop('PIXEL_SIZE', 8)
    f.setprop('FONT_ASCENT', 7)
    f.setprop('FONT_DESCENT', 1)
    f.setprop('CHARSET_REGISTRY', 'ISO10646')
    f.setprop('CHARSET_ENCODING', '1')
    f.glyphs[0x41] = [
        'A',
        0x41,
        1,
        1,
        0,
        0,
        500,
        0,
        4,
        0,
        None,
        None,
        None,
        None,
        None,
        None,
        ['80'],
    ]
    return f


def test_hand_checked_bytes():
    f = tiny_font()
    data = write_ttf(f, ppu=2, metadata=True)
    tt = TTFont(io.BytesIO(data))
    # glyf: one pixel, ppu 2 → (0,0) (0,2) (2,2) (2,0)
    glyf = tt.reader['glyf']
    assert (
        glyf
        == bytes.fromhex(
            '0001 0000 0000 0002 0002'  # 1 contour, bbox
            ' 0003 0000'  # endPts, instructionLength
            ' 31 35 33 15'  # flags: on|xsame|ysame, on|xsame|yshort+, on|xshort+|ysame, on|xsame|yshort-
            ' 02'  # x: +2
            ' 02 02'  # y: +2, -2
            ' 000000'  # pad
        )
    )
    assert tt.reader['loca'] == bytes.fromhex('00000000 00000000 00000018')
    assert tt.reader['hmtx'] == bytes.fromhex('0008 0000 0008 0000')
    assert tt.reader['cmap'] == bytes.fromhex(
        '0000 0002 0003 0001 00000014 0003 000A 00000034'
        ' 0004 0020 0000 0004 0004 0001 0000'
        ' 0041 FFFF 0000 0041 FFFF FFC0 0001 0000 0000'
        ' 000C 0000 0000001C 00000000 00000001 00000041 00000041 00000001'
    )
    assert tt.reader['post'] == bytes.fromhex(
        '00020000 00000000 FFFE 0002 00000000 00000000 00000000 00000000 00000000 0002 0000 0102 0141'
    )
    assert tt.reader['maxp'] == bytes.fromhex(
        '00010000 0002 0004 0001' + ' 0000 0000 0002 0000 0000 0000 0000 0001 0000 0000 0000'
    )
    assert tt.reader['prep'] == bytes.fromhex('B8 01 FF 85 B0 04 8D')
    assert data[12 + 16 * 11 : 12 + 16 * 11 + 4] == b'prep'  # last of 12 directory entries
    assert tt.reader['BDFP'] == (
        b'{"version":1,"ppu":2,"shape":"square","dotsize":1,'
        b'"headers":{"bdfversion":"2.1","fontname":"Tiny","pointsize":8,"xres":75,"yres":75,'
        b'"fbbx":4,"fbby":8,"fbbxoff":0,"fbbyoff":-1,"metricsset":0},'
        b'"props":{"family_name":"Tiny","pixel_size":8,"font_ascent":7,"font_descent":1,'
        b'"charset_registry":"ISO10646","charset_encoding":"1"},'
        b'"propnames":{"family_name":"FAMILY_NAME","pixel_size":"PIXEL_SIZE","font_ascent":"FONT_ASCENT",'
        b'"font_descent":"FONT_DESCENT","charset_registry":"CHARSET_REGISTRY","charset_encoding":"CHARSET_ENCODING"},'
        b'"glyphs":[[1,65,"A",1,1,0,0,500,0,4,0,null,null,null,null,null,null,null]]}'
    )
    name = tt['name']
    assert [n.nameID for n in name.names] == [1, 2, 3, 4, 5, 6]
    assert name.getDebugName(4) == 'Tiny' and name.getDebugName(5) == 'Version 1.000'
    # OS/2 spot checks
    os2 = tt['OS/2']
    assert os2.xAvgCharWidth == 8 and os2.ySubscriptXSize == 10 and os2.yStrikeoutPosition == 4
    assert os2.fsSelection == 0xC0 and os2.usFirstCharIndex == os2.usLastCharIndex == 0x41
    assert os2.usWinAscent == 14 and os2.usWinDescent == 2


def test_deterministic_and_timestamp():
    f = load('unifont-13.0.04-for-test.bdf')
    a = write_ttf(f)
    assert a == write_ttf(f)
    b = write_ttf(f, timestamp=1_700_000_000)
    tt = TTFont(io.BytesIO(b), checkChecksums=2)
    assert tt['head'].created == tt['head'].modified == 1_700_000_000 + 2082844800
    assert len(a) == len(b)


def test_metadata_false():
    data = write_ttf(tiny_font(), metadata=False)
    tt = TTFont(io.BytesIO(data), checkChecksums=2)
    assert 'BDFP' not in tt
    check_tables(tiny_font(), tt, data)


def test_style_names_metrics_props():
    f = tiny_font()
    f.setprop('WEIGHT_NAME', 'Semi Bold')
    f.setprop('SLANT', 'o')
    f.setprop('COPYRIGHT', 2024)
    f.setprop('NOTICE', 'Note')
    f.setprop('FONT_VERSION', '2.5')
    f.setprop('SPACING', 'm')
    f.setprop('X_HEIGHT', 4)
    f.setprop('CAP_HEIGHT', 6)
    f.setprop('UNDERLINE_POSITION', 2)
    f.setprop('UNDERLINE_THICKNESS', 3)
    f.setprop('FAMILY_NAME', 'My Font (Test)')
    data = write_ttf(f, ppu=4)
    tt = TTFont(io.BytesIO(data), checkChecksums=2)
    check_tables(f, tt, data, ppu=4)
    n = tt['name']
    assert n.getDebugName(0) == '2024'
    assert n.getDebugName(2) == 'Bold Italic'
    assert n.getDebugName(4) == 'My Font (Test) Bold Italic'
    assert n.getDebugName(6) == 'MyFontTestBoldItalic'
    assert n.getDebugName(5) == 'Version 2.5'
    assert n.getDebugName(10) == 'Note'
    assert tt['head'].macStyle == 3 and tt['OS/2'].fsSelection == 0x81 | 0x20
    assert tt['OS/2'].usWeightClass == 700
    assert tt['post'].isFixedPitch == 1
    assert tt['post'].underlinePosition == -8 and tt['post'].underlineThickness == 12
    assert tt['OS/2'].sxHeight == 16 and tt['OS/2'].sCapHeight == 24
    assert tt['OS/2'].yStrikeoutPosition == 8


def test_string_props_ignored_where_int_required():
    f = tiny_font()
    f.props['pixel_size'] = '8'  # not an int ⇒ em from ascent + descent
    f.props['font_ascent'] = '7'  # ⇒ fbby + fbbyoff = 7
    f.props['font_descent'] = None  # ⇒ -fbbyoff = 1
    f.props['family_name'] = ''  # empty ⇒ fontname
    f.setprop('WEIGHT_NAME', 7)  # not a str ⇒ not bold
    data = write_ttf(f, ppu=2)
    tt = TTFont(io.BytesIO(data), checkChecksums=2)
    check_tables(f, tt, data, ppu=2)
    assert tt['head'].unitsPerEm == 16
    assert tt['name'].getDebugName(1) == 'Tiny'


def test_names_fallbacks_and_notdef():
    f = tiny_font()
    f.headers['fontname'] = ''
    del f.props['family_name']
    f.setprop('DEFAULT_CHAR', 0x41)
    meta = f.glyphs[0x41]
    # invalid / duplicate / reserved BDF names
    f.glyphs[0x42] = ['bad name', 0x42, *meta[2:]]
    f.glyphs[0x43] = ['A', 0x43, *meta[2:]]
    f.glyphs[0x44] = ['.notdef', 0x44, *meta[2:]]
    f.glyphs[0x45] = ['uni0046', 0x45, *meta[2:]]
    f.glyphs[0x46] = ['x' * 64, 0x46, *meta[2:]]
    f.glyphs[0x110000] = ['ok_name.1', 0x110000, *meta[2:]]  # not representable in Unicode
    f.glyphs[0x110001] = ['', 0x110001, *meta[2:]]
    f.unencoded.append({'altcode': 7, 'meta': ['U', -1, *meta[2:]]})
    f.unencoded.append({'altcode': None, 'meta': ['A', -1, *meta[2:]]})
    data = write_ttf(f, ppu=2)
    tt = TTFont(io.BytesIO(data), checkChecksums=2)
    check_tables(f, tt, data, ppu=2)
    assert tt.getGlyphOrder() == [
        '.notdef',
        'A',
        'uni0042',  # invalid name
        'uni0043',  # 'A' already used
        'uni0044',  # '.notdef' reserved
        'uni0046',  # valid BDF name (even if misleading)
        'glyph6',  # 64 chars is too long; 'uni0046' already used
        'ok_name.1',
        'glyph8',  # empty name, no Unicode mapping
        'U',
        'glyph10',  # unencoded, 'A' already used
    ]
    assert tt['name'].getDebugName(1) == 'Untitled'
    # .notdef copies DEFAULT_CHAR
    assert tt['glyf']['.notdef'].numberOfContours == 1
    assert tt['hmtx']['.notdef'] == (8, 0)
    g = read_ttf(data)
    assert g.glyphs == f.glyphs and g.unencoded == f.unencoded


def test_empty_font():
    f = tiny_font()
    f.glyphs.clear()
    data = write_ttf(f, ppu=2)
    tt = TTFont(io.BytesIO(data), lazy=False, checkChecksums=2)
    check_tables(f, tt, data, ppu=2)
    assert tt['maxp'].numGlyphs == 1 and tt['hmtx']['.notdef'] == (8, 0)
    g = read_ttf(data)
    assert g.glyphs == {} and g.headers == f.headers


def test_advance_fallbacks():
    f = tiny_font()
    m = f.glyphs[0x41]
    f.glyphs[0x42] = [
        'B',
        0x42,
        2,
        1,
        3,
        0,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        ['C0'],
    ]
    f.glyphs[0x43] = [
        'C',
        0x43,
        2,
        1,
        -5,
        0,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        ['C0'],
    ]
    data = write_ttf(f, ppu=2)
    tt = TTFont(io.BytesIO(data))
    assert tt['hmtx']['B'][0] == 10 and tt['hmtx']['C'][0] == 0
    f.headers['dwx0'] = 6
    f.headers['dwy0'] = 0
    tt = TTFont(io.BytesIO(write_ttf(f, ppu=2)))
    assert tt['hmtx']['B'][0] == 12 and tt['hmtx']['A'][0] == m[8] * 2


def test_cmap_ffff_and_duplicates():
    f = tiny_font()
    meta = f.glyphs[0x41]
    f.glyphs[0xFFFF] = ['ffff', 0xFFFF, *meta[2:]]
    f.glyphs[0x10000] = ['astral', 0x10000, *meta[2:]]
    data = write_ttf(f, ppu=2)
    tt = TTFont(io.BytesIO(data), checkChecksums=2)
    check_tables(f, tt, data, ppu=2)
    assert 0xFFFF not in tt['cmap'].getcmap(3, 1).cmap
    assert tt['cmap'].getcmap(3, 10).cmap[0xFFFF] == 'ffff'
    assert tt['OS/2'].usLastCharIndex == 0xFFFF


def test_cmap_format4_overflow_truncated():
    # 9000 isolated codes (every other code point) ⇒ more runs than format 4 can hold
    f = tiny_font()
    meta = f.glyphs[0x41]
    for i in range(9000):
        cp = 0x4E00 + 2 * i
        f.glyphs[cp] = [f'g{i}', cp, *meta[2:]]
    data = write_ttf(f, ppu=2)
    tt = TTFont(io.BytesIO(data), checkChecksums=2)
    c4 = tt['cmap'].getcmap(3, 1).cmap
    c12 = tt['cmap'].getcmap(3, 10).cmap
    assert len(c12) == 9001
    assert len(c4) == 8188
    assert all(c12[u] == g for u, g in c4.items())
    assert max(c4) < min(set(c12) - set(c4))


def test_jsnum():
    assert [
        _jsnum(v)
        for v in (1.0, 1, 0.6, 1.5, 0.1, 1e-7, 1.5e-7, 0.000001, 1e21, 123456789012345680000.0)
    ] == [
        '1',
        '1',
        '0.6',
        '1.5',
        '0.1',
        '1e-7',
        '1.5e-7',
        '0.000001',
        '1e+21',
        '123456789012345680000',
    ]
    data = write_ttf(tiny_font(), dotsize=0.6, ppu=2)
    assert b'"dotsize":0.6,' in TTFont(io.BytesIO(data)).reader['BDFP']


@pytest.mark.parametrize(
    'kwargs',
    [
        {'ppu': 3},
        {'ppu': 0},
        {'ppu': 64.0},
        {'ppu': True},
        {'ppu': 4096},  # upem 32768 > 16384
        {'shape': 'hex'},
        {'dotsize': 0},
        {'dotsize': 1.6},
        {'timestamp': 1.5},
    ],
)
def test_write_bad_options(kwargs):
    with pytest.raises(ValueError):
        write_ttf(tiny_font(), **kwargs)


def test_write_upem_too_small_and_bad_advance():
    with pytest.raises(ValueError, match='unitsPerEm'):
        write_ttf(_with_em(1), ppu=2)
    write_ttf(_with_em(8), ppu=2)  # upem 16 is the minimum
    f = tiny_font()
    f.glyphs[0x41][8] = -1
    with pytest.raises(ValueError, match='out of range'):
        write_ttf(f, ppu=2)


def _with_em(em):
    f = tiny_font()
    f.props['pixel_size'] = em
    return f


@pytest.mark.slow
@pytest.mark.skipif(not SLOW, reason='slow test: set BDFPARSER_SLOW=1 to run (full unifont)')
@pytest.mark.parametrize('shape', SHAPES)
def test_full_unifont_slow(shape):
    f = load(FULL_UNIFONT)
    data = write_ttf(f, shape=shape)
    tt = TTFont(io.BytesIO(data), lazy=False, checkChecksums=2)
    for tag in tt.keys():
        tt[tag]
    check_tables(f, tt, data, shape)
    assert_same_font(read_ttf(data), f)


def table_offsets(data: bytes) -> dict[bytes, tuple[int, int]]:
    (num,) = struct.unpack('>H', data[4:6])
    out = {}
    for i in range(num):
        t, _, o, n = struct.unpack('>4sIII', data[12 + 16 * i : 28 + 16 * i])
        out[t] = (o, n)
    return out


def glyph_offset(data: bytes, gid: int) -> int:
    offs = table_offsets(data)
    lo = offs[b'loca'][0]
    fmt = struct.unpack('>h', data[offs[b'head'][0] + 50 : offs[b'head'][0] + 52])[0]
    if fmt == 0:
        start = 2 * struct.unpack('>H', data[lo + 2 * gid : lo + 2 * gid + 2])[0]
    else:
        start = struct.unpack('>I', data[lo + 4 * gid : lo + 4 * gid + 4])[0]
    return offs[b'glyf'][0] + start


def test_read_fonttools_recompiled_glyf():
    """fontTools re-encodes glyf with REPEAT flags (and short loca): reading still round-trips."""
    f = load('unifont-13.0.04-for-test.bdf')
    for shape in SHAPES:
        tt = TTFont(io.BytesIO(write_ttf(f, shape=shape, ppu=2)))
        glyf = tt['glyf']
        for name in tt.getGlyphOrder():
            glyf[name].expand(glyf)
            if hasattr(glyf[name], 'data'):
                del glyf[name].data
        out = io.BytesIO()
        tt.save(out)
        data = out.getvalue()
        assert data != write_ttf(f, shape=shape, ppu=2)
        assert_same_font(read_ttf(data), f)


def test_repeat_flags_parsed():
    # a staircase with 20 identical flags is encoded by fontTools with REPEAT
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(['.notdef', 'Z'])
    fb.setupCharacterMap({0x5A: 'Z'})
    p = TTGlyphPen({})
    pts = [(0, 0)] + [(100 + 10 * i, 10 * i) for i in range(20)] + [(400, 900), (0, 900)]
    p.moveTo(pts[0])
    for q in pts[1:]:
        p.lineTo(q)
    p.closePath()
    fb.setupGlyf({'.notdef': TTGlyphPen({}).glyph(), 'Z': p.glyph()})
    fb.setupHorizontalMetrics({'.notdef': (500, 0), 'Z': (500, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({'familyName': 'Z', 'styleName': 'Regular'})
    fb.setupOS2()
    fb.setupPost()
    out = io.BytesIO()
    fb.save(out)
    data = out.getvalue()
    gstart = glyph_offset(data, 1)
    ncont, *_ = struct.unpack('>hhhhh', data[gstart : gstart + 10])
    (npts,) = struct.unpack('>H', data[gstart + 10 : gstart + 12])
    flags_start = gstart + 10 + 2 * ncont + 2
    assert any(b & 0x08 for b in data[flags_start : flags_start + npts])
    g = read_ttf(data, pixelsize=10)
    tt = TTFont(io.BytesIO(data))
    exp, amb = oracle_ink(tt, 'Z', 100)
    assert ink_set(g.glyphs[0x5A]) - amb == exp and exp


def test_malformed_glyph_data():
    data = build_thirdparty()
    tt = TTFont(io.BytesIO(data))
    # simple glyph claiming a huge number of contours
    b = bytearray(data)
    o = glyph_offset(data, tt.getGlyphID('A'))
    b[o : o + 2] = struct.pack('>h', 30000)
    with pytest.raises(ValueError, match='Malformed'):
        read_ttf(bytes(b), pixelsize=10)
    # endPtsOfContours not increasing
    b = bytearray(data)
    b[o + 10 : o + 12] = struct.pack('>H', 60000)
    with pytest.raises(ValueError, match='Malformed'):
        read_ttf(bytes(b), pixelsize=10)
    # component referencing a glyph index out of range
    b = bytearray(data)
    o = glyph_offset(data, tt.getGlyphID('C'))
    b[o + 12 : o + 14] = struct.pack('>H', 999)
    with pytest.raises(ValueError, match='out of range'):
        read_ttf(bytes(b), pixelsize=10)
    # point-matched component with a bad point index
    b = bytearray(data)
    o = glyph_offset(data, tt.getGlyphID('M'))
    # second component: after flags(2) gid(2) args(2 bytes, since flags has no ARG_1_AND_2_ARE_WORDS)
    first_flags = struct.unpack('>H', data[o + 10 : o + 12])[0]
    second = o + 10 + 4 + (4 if first_flags & 1 else 2)
    args_off = second + 4
    sflags = struct.unpack('>H', data[second : second + 2])[0]
    assert not sflags & 0x0002  # point matching
    if sflags & 1:
        b[args_off : args_off + 2] = struct.pack('>H', 200)
    else:
        b[args_off] = 200
    with pytest.raises(ValueError, match='point index'):
        read_ttf(bytes(b), pixelsize=10)


def test_malformed_cmap12_group():
    data = build_thirdparty(cmap_formats=[(12, 3, 10)])
    offs = table_offsets(data)
    b = bytearray(data)
    co = offs[b'cmap'][0]
    sub = co + struct.unpack('>I', data[co + 8 : co + 12])[0]
    # first group: start > end
    b[sub + 16 : sub + 24] = struct.pack('>II', 0x50, 0x40)
    with pytest.raises(ValueError, match='format 12'):
        read_ttf(bytes(b), pixelsize=10)


def test_duck_typed_font_without_cp2char():
    """write_ttf only needs the data model (headers/props/glyphs/unencoded/itercps)."""

    class Duck:
        def __init__(self, f):
            self.headers, self.props, self.glyphs = f.headers, f.props, f.glyphs
            self.unencoded = []
            self._propnames = f._propnames

        def itercps(self, order=1):
            return iter(sorted(self.glyphs))

    f = tiny_font()
    f.headers['bdfversion'] = 2.0
    f.glyphs[0x110000] = ['big', 0x110000, *f.glyphs[0x41][2:]]
    data = write_ttf(Duck(f), ppu=2)
    tt = TTFont(io.BytesIO(data))
    assert tt.getBestCmap() == {0x41: 'A'}
    assert b'"bdfversion":"2.0"' in tt.reader['BDFP']
    g = read_ttf(data)
    assert g.headers['bdfversion'] == 2.0 and g.glyphs == f.glyphs
