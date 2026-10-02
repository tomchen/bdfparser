"""SVG output (spec section 7.3): Bitmap.tosvg and Font.tosvgfont."""

import random
import re

import pytest

from bdfparser import Bitmap, Font
from bdfparser.bitmap import fmtnum

from .info import mini_bdf, unifont_path

T = Bitmap.fromstring


def path_to_bindata(d, w, h, pixelsize=1, xoff=0, yoff=0, inverted=False):
    """Rasterise an absolute M/H/V/Z path (non-zero winding) at pixel centres."""
    polys = []
    for sub in re.findall(r'M[^M]*', d):
        toks = re.findall(r'[MHVZ]|-?[0-9.]+(?:e-?[0-9]+)?', sub)
        pts = []
        i = 0
        x = y = 0.0
        while i < len(toks):
            t = toks[i]
            if t == 'M':
                x, y = float(toks[i + 1]), float(toks[i + 2])
                i += 3
            elif t == 'H':
                x = float(toks[i + 1])
                i += 2
            elif t == 'V':
                y = float(toks[i + 1])
                i += 2
            else:  # Z
                i += 1
                continue
            pts.append((x, y))
        polys.append(pts)
    rows = []
    for r in range(h):
        row = []
        for c in range(w):
            px = (c + 0.5) * pixelsize + xoff
            py = ((h - r - 0.5) if inverted else (r + 0.5)) * pixelsize + yoff
            wn = 0
            for pts in polys:
                for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=True):
                    if y0 <= py < y1 and px < x0 + (py - y0) * (x1 - x0) / (y1 - y0):
                        wn += 1
                    elif y1 <= py < y0 and px < x0 + (py - y0) * (x1 - x0) / (y1 - y0):
                        wn -= 1
            row.append('1' if wn else '0')
        rows.append(''.join(row))
    return rows


class TestFmtnum:
    def test_fmtnum(self):
        assert fmtnum(3) == '3'
        assert fmtnum(-3) == '-3'
        assert fmtnum(3.0) == '3'
        assert fmtnum(-0.0) == '0'
        assert fmtnum(0.5) == '0.5'
        assert fmtnum(12.8) == '12.8'
        assert fmtnum(0.1 + 0.2) == '0.30000000000000004'
        assert fmtnum(True) == '1'


class TestToSvg:
    def test_single_pixel(self):
        assert T('#').tosvg() == (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
            '<path d="M0 1V0H1V1Z" fill="#000000" /></svg>'
        )

    def test_merged_with_hole(self):
        assert T('###\n#.#\n###').tosvg(format='pathOnly') == 'M0 3V0H3V3ZM1 2H2V1H1Z'

    def test_diagonal_pixels_separate_contours(self):
        assert T('#.\n.#').tosvg(format='pathOnly') == 'M1 2V1H2V2ZM0 1V0H1V1Z'

    def test_inverted(self):
        assert T('#.\n.#').tosvg(format='pathOnly', inverted=True) == 'M1 0V1H2V0ZM0 1V2H1V1Z'

    def test_pixelsize_offsets_floats(self):
        assert (
            T('#.\n.#').tosvg(0.5, 'pathOnly', False, 0.25, -1)
            == 'M0.75 0V-0.5H1.25V0ZM0.25 -0.5V-1H0.75V-0.5Z'
        )
        out = T('#').tosvg(3, xoff=1, yoff=2)
        assert out == (
            '<svg xmlns="http://www.w3.org/2000/svg" width="3" height="3">'
            '<path d="M1 5V2H4V5Z" fill="#000000" /></svg>'
        )

    def test_value_2_is_ink(self):
        assert T('&').tosvg(format='pathOnly') == T('#').tosvg(format='pathOnly')

    def test_circle(self):
        assert T('#.\n.&').tosvg(2, 'path', shape='circle') == (
            '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4">'
            '<path d="M2 3a1 1 0 1 0 2 0a1 1 0 1 0 -2 0ZM0 1a1 1 0 1 0 2 0a1 1 0 1 0 -2 0Z" fill="#000000" /></svg>'
        )
        assert T('#.\n.#').tosvg(2, 'pathOnly', True, 1, 1, 'circle') == (
            'M3 2a1 1 0 1 0 2 0a1 1 0 1 0 -2 0ZM1 4a1 1 0 1 0 2 0a1 1 0 1 0 -2 0Z'
        )
        assert (
            T('#').tosvg(1, 'pathOnly', shape='circle')
            == 'M0 0.5a0.5 0.5 0 1 0 1 0a0.5 0.5 0 1 0 -1 0Z'
        )

    def test_rect(self):
        assert T('##.\n##&\n...').tosvg(format='rect') == (
            '<svg xmlns="http://www.w3.org/2000/svg" width="3" height="3">'
            '<rect x="0" y="0" width="2" height="2" fill="#000000" />'
            '<rect x="2" y="1" width="1" height="1" fill="#000000" /></svg>'
        )
        assert T('##.\n##&\n...').tosvg(2, format='rect', inverted=True, xoff=1, yoff=0.5) == (
            '<svg xmlns="http://www.w3.org/2000/svg" width="6" height="6">'
            '<rect x="1" y="2.5" width="4" height="4" fill="#000000" />'
            '<rect x="5" y="2.5" width="2" height="2" fill="#000000" /></svg>'
        )

    def test_rect_greedy_v3rc(self):
        # greedy: widest run first, then grow downwards
        assert T('###\n#..').tosvg(format='rect') == (
            '<svg xmlns="http://www.w3.org/2000/svg" width="3" height="2">'
            '<rect x="0" y="0" width="3" height="1" fill="#000000" />'
            '<rect x="0" y="1" width="1" height="1" fill="#000000" /></svg>'
        )

    def test_empty(self):
        head = '<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}">'
        assert Bitmap([]).tosvg(format='pathOnly') == ''
        assert Bitmap([]).tosvg() == head.format(0, 0) + '</svg>'
        assert T('...\n...').tosvg(format='pathOnly') == ''
        assert T('...\n...').tosvg(2) == head.format(6, 4) + '</svg>'
        assert T('...').tosvg(format='rect') == head.format(3, 1) + '</svg>'
        assert T('...').tosvg(shape='circle') == head.format(3, 1) + '</svg>'
        assert Bitmap([]).tosvg(format='rect') == head.format(0, 0) + '</svg>'

    def test_errors(self):
        with pytest.raises(ValueError, match='format'):
            T('#').tosvg(format='png')
        with pytest.raises(ValueError, match='shape'):
            T('#').tosvg(shape='hexagon')
        with pytest.raises(ValueError, match='rect'):
            T('#').tosvg(format='rect', shape='circle')

    @pytest.mark.parametrize('inverted', [False, True])
    def test_random_bitmaps_rasterise_back(self, inverted):
        rnd = random.Random(20261002 + inverted)
        for _ in range(300):
            w = rnd.randint(1, 9)
            h = rnd.randint(1, 9)
            p = rnd.random()
            rows = [''.join('1' if rnd.random() < p else '0' for _ in range(w)) for _ in range(h)]
            ps = rnd.choice([1, 2, 0.5, 3])
            xoff = rnd.choice([0, 1, -2.5])
            yoff = rnd.choice([0, 3, -1])
            d = Bitmap(rows).tosvg(ps, 'pathOnly', inverted, xoff, yoff)
            assert path_to_bindata(d, w, h, ps, xoff, yoff, inverted) == rows, rows

    def test_glyph_rasterise_back(self):
        font = Font(unifont_path)
        for cp in (0x41, 0x61, 0x0644, 0x7684, 0x40):
            bm = font.glyphbycp(cp).draw()
            d = bm.tosvg(format='pathOnly')
            assert path_to_bindata(d, bm.width(), bm.height()) == bm.bindata


EXPECTED_MINI_SVGFONT = """<svg xmlns="http://www.w3.org/2000/svg" version="1.1">
<metadata>
  Title: Mini
  Weight: Medium
</metadata>
<defs>
  <font id="test-mini-medium-r-normal--8-80-75-75-c-60-iso10646-1" horiz-adv-x="8">
<font-face
  font-family="Mini"
  font-weight="Medium"
  font-style="normal"
  units-per-em="8"
  cap-height="7"
  x-height="3.5"
  ascent="7"
  descent="1"
  bbox="0 -1 6 8"
  underline-thickness="0"
  underline-position="-1"
  unicode-range="U+0020, U+0041-0042"
></font-face>
<missing-glyph horiz-adv-x="8" d="M0,0h8v8h-8z" />
<glyph glyph-name=".notdef" horiz-adv-x="8" d="M0,0h8v8h-8z" />
<glyph
  glyph-name="A"
  unicode="&#x41;"
  horiz-adv-x="6"
  d="M0 1V6H1V5H4V6H5V1H4V4H1V1ZM1 6V7H2V6ZM3 6V7H4V6ZM2 7V8H3V7Z"
></glyph>
<glyph
  glyph-name="B"
  unicode="&#x42;"
  horiz-adv-x="6"
  d="M1 1V8H4V7H2V5H4V4H2V2H4V1ZM4 2V4H5V2ZM4 5V7H5V5Z"
></glyph>
</font>
</defs>
</svg>"""


class TestSvgFont:
    def test_mini_exact(self):
        assert Font().load_string(mini_bdf).tosvgfont() == EXPECTED_MINI_SVGFONT

    def test_offsets(self):
        out = Font().load_string(mini_bdf).tosvgfont(xoff=1, yoff=-1)
        assert 'd="M1 0V5H2V4H5V5H6V0H5V3H2V0ZM2 5V6H3V5ZM4 5V6H5V5ZM3 6V7H4V6Z"' in out

    def test_unicode_formats(self):
        font = Font().load_string(mini_bdf)
        font.glyphbycp(66).setmeta(codepoint=0x4E2D)
        assert 'unicode="&#x4e2d;"' in font.tosvgfont()
        assert 'unicode="&#20013;"' in font.tosvgfont(unicodeformat='decncr')
        assert 'unicode="中"' in font.tosvgfont(unicodeformat='char')
        font.glyphbycp(65).setmeta(codepoint=ord('&'))
        assert 'unicode="&amp;"' in font.tosvgfont(unicodeformat='char')

    def test_control_chars(self):
        font = Font().load_string(mini_bdf)
        font.glyphbycp(65).setmeta(codepoint=1)
        assert 'unicode="&#x1;"' not in font.tosvgfont()
        assert 'unicode="&#x1;"' in font.tosvgfont(controlcharnoskip=True)

    def test_metadata_fixed(self):
        font = Font().load_string(mini_bdf)
        font.setprop('FONT_VERSION', '1.0').setprop('FOUNDRY', 'Acme & Co').setprop('NOTICE', 'n')
        font.setprop('COPYRIGHT', '<c>').delprop('WEIGHT_NAME')
        out = font.tosvgfont()
        assert (
            '<metadata>\n  Title: Mini\n  Version: 1.0\n  Foundry: Acme &amp; Co\n'
            '  Copyright: &lt;c&gt;\n  Notice: n\n</metadata>\n'
        ) in out
        assert 'Founfry' not in out and 'Weight' not in out
        font.setprop('CREATOR', 'x')  # v3-rc wrongly keyed metadata on CREATOR
        assert 'Weight' not in font.tosvgfont()

    def test_no_metadata_and_family_fallbacks(self):
        font = Font().load_string(mini_bdf)
        font.delprop('FAMILY_NAME').delprop('WEIGHT_NAME')
        out = font.tosvgfont()
        assert '<metadata>' not in out
        assert 'font-family="-Test-Mini-Medium-R-Normal--8-80-75-75-C-60-ISO10646-1"' in out
        font.setprop('FAMILY', 'Fam')
        out = font.tosvgfont()
        assert 'font-family="Fam"' in out and 'Title: Fam' in out

    def test_props_from_strings_and_defaults(self):
        font = Font().load_string(mini_bdf)
        font.setprop('FONT_ASCENT', '6px').setprop('FONT_DESCENT', 'x').setprop('CAP_HEIGHT', 5)
        font.setprop('X_HEIGHT', '4').setprop('UNDERLINE_THICKNESS', 2).setprop(
            'UNDERLINE_POSITION', -2
        )
        font.setprop('SLANT', 'I')
        font.headers['dwx0'] = 5
        out = font.tosvgfont()
        assert 'ascent="6"' in out and 'descent="-1.6"' in out
        assert 'cap-height="5"' in out and 'x-height="4"' in out
        assert 'underline-thickness="2"' in out and 'underline-position="-2"' in out
        assert 'font-style="I"' in out
        assert 'horiz-adv-x="5" d="M0,0h8v8h-8z"' in out

    def test_vertical_metrics(self):
        font = Font().load_string(mini_bdf)
        font.glyphbycp(65).setmeta(swy0=3, vvectorx=2, vvectory=7)
        out = font.tosvgfont()
        assert (
            '  d="M0 1V6H1V5H4V6H5V1H4V4H1V1ZM1 6V7H2V6ZM3 6V7H4V6ZM2 7V8H3V7Z"\n  vert-adv-y="3"\n  vert-origin-x="2"\n  vert-origin-y="7"\n></glyph>'
            in out
        )

    def test_empty_font(self):
        font = Font.create()
        out = font.tosvgfont()
        assert 'unicode-range=""' in out
        assert '<glyph\n' not in out
        assert 'units-per-em="16"' in out and 'ascent="14"' in out and 'descent="2"' in out

    def test_no_headers(self):
        out = Font().tosvgfont()
        assert 'units-per-em="100"' in out and 'bbox="0 0 100 100"' in out
        assert '<font id="" horiz-adv-x="100">' in out
        assert 'ascent="80"' in out and 'descent="-20"' in out

    def test_unifont_smoke(self):
        out = Font(unifont_path).tosvgfont()
        assert out.count('<glyph\n') == 849 - 2  # U+0020 and U+00A0 have no path (v3-rc behaviour)
        assert 'unicode-range="U+0000-024F, U+0600-06FF, U+7684"' in out


# Expected outputs copied from bdfparser-js test/font.test.ts (cross-language check)
TWOA_SVGFONT_CASES = [
    (
        {},
        '<svg xmlns="http://www.w3.org/2000/svg" version="1.1">\n<metadata>\n  Title: Unifont\n  Weight: Medium\n  Version: 13.0.04\n  Foundry: GNU\n  Copyright: Copyright (C) 1998-2020 Roman Czyborra, Paul Hardy, Qianqian Fang, Andrew Miller, Johnnie Weaver, David Corbett, Rebecca Bettencourt, et al. License: SIL Open Font License version 1.1 and GPLv2+: GNU GPL version 2 or later &lt;http://gnu.org/licenses/gpl.html&gt; with the GNU Font Embedding Exception.\n</metadata>\n<defs>\n  <font id="gnu-unifont-medium-r-normal-sans-16-160-75-75-c-80-iso10646-1" horiz-adv-x="16">\n<font-face\n  font-family="Unifont"\n  font-weight="Medium"\n  font-style="R"\n  units-per-em="16"\n  cap-height="10"\n  x-height="8"\n  ascent="14"\n  descent="2"\n  bbox="0 -2 16 16"\n  underline-thickness="1"\n  underline-position="-2"\n  unicode-range="U+0002, U+FFFC"\n></font-face>\n<missing-glyph horiz-adv-x="16" d="M0,0h16v16h-16z" />\n<glyph glyph-name=".notdef" horiz-adv-x="16" d="M0,0h16v16h-16z" />\n<glyph\n  glyph-name="U+0002"\n  horiz-adv-x="16"\n  d="M1 0V1H2V0ZM3 0V1H4V0ZM5 0V1H6V0ZM7 0V1H8V0ZM9 0V1H10V0ZM11 0V1H12V0ZM13 0V1H14V0ZM15 0V1H16V0ZM0 1V2H1V1ZM15 2V3H16V2ZM0 3V4H1V3ZM15 4V5H16V4ZM0 5V6H1V5ZM1 6V7H4V6ZM7 6V10H6V11H9V10H8V6ZM10 6V8H11V6ZM13 6V8H14V6ZM15 6V7H16V6ZM0 7V8H1V7ZM4 7V8H5V7ZM2 8V9H4V8ZM11 8V9H13V8ZM15 8V9H16V8ZM0 9V10H2V9ZM10 9V11H11V9ZM13 9V11H14V9ZM2 10V11H5V10ZM15 10V11H16V10ZM0 11V12H1V11ZM15 12V13H16V12ZM0 13V14H1V13ZM15 14V15H16V14ZM0 15V16H1V15ZM2 15V16H3V15ZM4 15V16H5V15ZM6 15V16H7V15ZM8 15V16H9V15ZM10 15V16H11V15ZM12 15V16H13V15ZM14 15V16H15V15Z"\n></glyph>\n<glyph\n  glyph-name="U+FFFC"\n  unicode="&#xfffc;"\n  horiz-adv-x="16"\n  d="M0 0V1H1V0ZM2 0V1H3V0ZM4 0V1H5V0ZM6 0V1H7V0ZM8 0V1H9V0ZM10 0V1H11V0ZM12 0V1H13V0ZM14 0V1H15V0ZM15 1V2H16V1ZM0 2V3H1V2ZM15 3V4H16V3ZM0 4V5H1V4ZM3 5V6H4V5ZM7 5V10H9V9H8V8H9V7H8V6H9V5ZM11 5V6H13V5ZM15 5V6H16V5ZM0 6V7H1V6ZM2 6V9H3V6ZM4 6V9H5V6ZM9 6V7H10V6ZM13 6V10H14V6ZM15 7V8H16V7ZM0 8V9H1V8ZM9 8V9H10V8ZM3 9V10H4V9ZM15 9V10H16V9ZM0 10V11H1V10ZM15 11V12H16V11ZM0 12V13H1V12ZM15 13V14H16V13ZM0 14V15H1V14ZM1 15V16H2V15ZM3 15V16H4V15ZM5 15V16H6V15ZM7 15V16H8V15ZM9 15V16H10V15ZM11 15V16H12V15ZM13 15V16H14V15ZM15 15V16H16V15Z"\n></glyph>\n</font>\n</defs>\n</svg>',
    ),
    (
        {'yoff': -2},
        '<svg xmlns="http://www.w3.org/2000/svg" version="1.1">\n<metadata>\n  Title: Unifont\n  Weight: Medium\n  Version: 13.0.04\n  Foundry: GNU\n  Copyright: Copyright (C) 1998-2020 Roman Czyborra, Paul Hardy, Qianqian Fang, Andrew Miller, Johnnie Weaver, David Corbett, Rebecca Bettencourt, et al. License: SIL Open Font License version 1.1 and GPLv2+: GNU GPL version 2 or later &lt;http://gnu.org/licenses/gpl.html&gt; with the GNU Font Embedding Exception.\n</metadata>\n<defs>\n  <font id="gnu-unifont-medium-r-normal-sans-16-160-75-75-c-80-iso10646-1" horiz-adv-x="16">\n<font-face\n  font-family="Unifont"\n  font-weight="Medium"\n  font-style="R"\n  units-per-em="16"\n  cap-height="10"\n  x-height="8"\n  ascent="14"\n  descent="2"\n  bbox="0 -2 16 16"\n  underline-thickness="1"\n  underline-position="-2"\n  unicode-range="U+0002, U+FFFC"\n></font-face>\n<missing-glyph horiz-adv-x="16" d="M0,0h16v16h-16z" />\n<glyph glyph-name=".notdef" horiz-adv-x="16" d="M0,0h16v16h-16z" />\n<glyph\n  glyph-name="U+0002"\n  horiz-adv-x="16"\n  d="M1 -2V-1H2V-2ZM3 -2V-1H4V-2ZM5 -2V-1H6V-2ZM7 -2V-1H8V-2ZM9 -2V-1H10V-2ZM11 -2V-1H12V-2ZM13 -2V-1H14V-2ZM15 -2V-1H16V-2ZM0 -1V0H1V-1ZM15 0V1H16V0ZM0 1V2H1V1ZM15 2V3H16V2ZM0 3V4H1V3ZM1 4V5H4V4ZM7 4V8H6V9H9V8H8V4ZM10 4V6H11V4ZM13 4V6H14V4ZM15 4V5H16V4ZM0 5V6H1V5ZM4 5V6H5V5ZM2 6V7H4V6ZM11 6V7H13V6ZM15 6V7H16V6ZM0 7V8H2V7ZM10 7V9H11V7ZM13 7V9H14V7ZM2 8V9H5V8ZM15 8V9H16V8ZM0 9V10H1V9ZM15 10V11H16V10ZM0 11V12H1V11ZM15 12V13H16V12ZM0 13V14H1V13ZM2 13V14H3V13ZM4 13V14H5V13ZM6 13V14H7V13ZM8 13V14H9V13ZM10 13V14H11V13ZM12 13V14H13V13ZM14 13V14H15V13Z"\n></glyph>\n<glyph\n  glyph-name="U+FFFC"\n  unicode="&#xfffc;"\n  horiz-adv-x="16"\n  d="M0 -2V-1H1V-2ZM2 -2V-1H3V-2ZM4 -2V-1H5V-2ZM6 -2V-1H7V-2ZM8 -2V-1H9V-2ZM10 -2V-1H11V-2ZM12 -2V-1H13V-2ZM14 -2V-1H15V-2ZM15 -1V0H16V-1ZM0 0V1H1V0ZM15 1V2H16V1ZM0 2V3H1V2ZM3 3V4H4V3ZM7 3V8H9V7H8V6H9V5H8V4H9V3ZM11 3V4H13V3ZM15 3V4H16V3ZM0 4V5H1V4ZM2 4V7H3V4ZM4 4V7H5V4ZM9 4V5H10V4ZM13 4V8H14V4ZM15 5V6H16V5ZM0 6V7H1V6ZM9 6V7H10V6ZM3 7V8H4V7ZM15 7V8H16V7ZM0 8V9H1V8ZM15 9V10H16V9ZM0 10V11H1V10ZM15 11V12H16V11ZM0 12V13H1V12ZM1 13V14H2V13ZM3 13V14H4V13ZM5 13V14H6V13ZM7 13V14H8V13ZM9 13V14H10V13ZM11 13V14H12V13ZM13 13V14H14V13ZM15 13V14H16V13Z"\n></glyph>\n</font>\n</defs>\n</svg>',
    ),
    (
        {'controlcharnoskip': True},
        '<svg xmlns="http://www.w3.org/2000/svg" version="1.1">\n<metadata>\n  Title: Unifont\n  Weight: Medium\n  Version: 13.0.04\n  Foundry: GNU\n  Copyright: Copyright (C) 1998-2020 Roman Czyborra, Paul Hardy, Qianqian Fang, Andrew Miller, Johnnie Weaver, David Corbett, Rebecca Bettencourt, et al. License: SIL Open Font License version 1.1 and GPLv2+: GNU GPL version 2 or later &lt;http://gnu.org/licenses/gpl.html&gt; with the GNU Font Embedding Exception.\n</metadata>\n<defs>\n  <font id="gnu-unifont-medium-r-normal-sans-16-160-75-75-c-80-iso10646-1" horiz-adv-x="16">\n<font-face\n  font-family="Unifont"\n  font-weight="Medium"\n  font-style="R"\n  units-per-em="16"\n  cap-height="10"\n  x-height="8"\n  ascent="14"\n  descent="2"\n  bbox="0 -2 16 16"\n  underline-thickness="1"\n  underline-position="-2"\n  unicode-range="U+0002, U+FFFC"\n></font-face>\n<missing-glyph horiz-adv-x="16" d="M0,0h16v16h-16z" />\n<glyph glyph-name=".notdef" horiz-adv-x="16" d="M0,0h16v16h-16z" />\n<glyph\n  glyph-name="U+0002"\n  unicode="&#x2;"\n  horiz-adv-x="16"\n  d="M1 0V1H2V0ZM3 0V1H4V0ZM5 0V1H6V0ZM7 0V1H8V0ZM9 0V1H10V0ZM11 0V1H12V0ZM13 0V1H14V0ZM15 0V1H16V0ZM0 1V2H1V1ZM15 2V3H16V2ZM0 3V4H1V3ZM15 4V5H16V4ZM0 5V6H1V5ZM1 6V7H4V6ZM7 6V10H6V11H9V10H8V6ZM10 6V8H11V6ZM13 6V8H14V6ZM15 6V7H16V6ZM0 7V8H1V7ZM4 7V8H5V7ZM2 8V9H4V8ZM11 8V9H13V8ZM15 8V9H16V8ZM0 9V10H2V9ZM10 9V11H11V9ZM13 9V11H14V9ZM2 10V11H5V10ZM15 10V11H16V10ZM0 11V12H1V11ZM15 12V13H16V12ZM0 13V14H1V13ZM15 14V15H16V14ZM0 15V16H1V15ZM2 15V16H3V15ZM4 15V16H5V15ZM6 15V16H7V15ZM8 15V16H9V15ZM10 15V16H11V15ZM12 15V16H13V15ZM14 15V16H15V15Z"\n></glyph>\n<glyph\n  glyph-name="U+FFFC"\n  unicode="&#xfffc;"\n  horiz-adv-x="16"\n  d="M0 0V1H1V0ZM2 0V1H3V0ZM4 0V1H5V0ZM6 0V1H7V0ZM8 0V1H9V0ZM10 0V1H11V0ZM12 0V1H13V0ZM14 0V1H15V0ZM15 1V2H16V1ZM0 2V3H1V2ZM15 3V4H16V3ZM0 4V5H1V4ZM3 5V6H4V5ZM7 5V10H9V9H8V8H9V7H8V6H9V5ZM11 5V6H13V5ZM15 5V6H16V5ZM0 6V7H1V6ZM2 6V9H3V6ZM4 6V9H5V6ZM9 6V7H10V6ZM13 6V10H14V6ZM15 7V8H16V7ZM0 8V9H1V8ZM9 8V9H10V8ZM3 9V10H4V9ZM15 9V10H16V9ZM0 10V11H1V10ZM15 11V12H16V11ZM0 12V13H1V12ZM15 13V14H16V13ZM0 14V15H1V14ZM1 15V16H2V15ZM3 15V16H4V15ZM5 15V16H6V15ZM7 15V16H8V15ZM9 15V16H10V15ZM11 15V16H12V15ZM13 15V16H14V15ZM15 15V16H16V15Z"\n></glyph>\n</font>\n</defs>\n</svg>',
    ),
    (
        {'xoff': -2, 'yoff': 4, 'controlcharnoskip': True, 'unicodeformat': 'decncr'},
        '<svg xmlns="http://www.w3.org/2000/svg" version="1.1">\n<metadata>\n  Title: Unifont\n  Weight: Medium\n  Version: 13.0.04\n  Foundry: GNU\n  Copyright: Copyright (C) 1998-2020 Roman Czyborra, Paul Hardy, Qianqian Fang, Andrew Miller, Johnnie Weaver, David Corbett, Rebecca Bettencourt, et al. License: SIL Open Font License version 1.1 and GPLv2+: GNU GPL version 2 or later &lt;http://gnu.org/licenses/gpl.html&gt; with the GNU Font Embedding Exception.\n</metadata>\n<defs>\n  <font id="gnu-unifont-medium-r-normal-sans-16-160-75-75-c-80-iso10646-1" horiz-adv-x="16">\n<font-face\n  font-family="Unifont"\n  font-weight="Medium"\n  font-style="R"\n  units-per-em="16"\n  cap-height="10"\n  x-height="8"\n  ascent="14"\n  descent="2"\n  bbox="0 -2 16 16"\n  underline-thickness="1"\n  underline-position="-2"\n  unicode-range="U+0002, U+FFFC"\n></font-face>\n<missing-glyph horiz-adv-x="16" d="M0,0h16v16h-16z" />\n<glyph glyph-name=".notdef" horiz-adv-x="16" d="M0,0h16v16h-16z" />\n<glyph\n  glyph-name="U+0002"\n  unicode="&#2;"\n  horiz-adv-x="16"\n  d="M-1 4V5H0V4ZM1 4V5H2V4ZM3 4V5H4V4ZM5 4V5H6V4ZM7 4V5H8V4ZM9 4V5H10V4ZM11 4V5H12V4ZM13 4V5H14V4ZM-2 5V6H-1V5ZM13 6V7H14V6ZM-2 7V8H-1V7ZM13 8V9H14V8ZM-2 9V10H-1V9ZM-1 10V11H2V10ZM5 10V14H4V15H7V14H6V10ZM8 10V12H9V10ZM11 10V12H12V10ZM13 10V11H14V10ZM-2 11V12H-1V11ZM2 11V12H3V11ZM0 12V13H2V12ZM9 12V13H11V12ZM13 12V13H14V12ZM-2 13V14H0V13ZM8 13V15H9V13ZM11 13V15H12V13ZM0 14V15H3V14ZM13 14V15H14V14ZM-2 15V16H-1V15ZM13 16V17H14V16ZM-2 17V18H-1V17ZM13 18V19H14V18ZM-2 19V20H-1V19ZM0 19V20H1V19ZM2 19V20H3V19ZM4 19V20H5V19ZM6 19V20H7V19ZM8 19V20H9V19ZM10 19V20H11V19ZM12 19V20H13V19Z"\n></glyph>\n<glyph\n  glyph-name="U+FFFC"\n  unicode="&#65532;"\n  horiz-adv-x="16"\n  d="M-2 4V5H-1V4ZM0 4V5H1V4ZM2 4V5H3V4ZM4 4V5H5V4ZM6 4V5H7V4ZM8 4V5H9V4ZM10 4V5H11V4ZM12 4V5H13V4ZM13 5V6H14V5ZM-2 6V7H-1V6ZM13 7V8H14V7ZM-2 8V9H-1V8ZM1 9V10H2V9ZM5 9V14H7V13H6V12H7V11H6V10H7V9ZM9 9V10H11V9ZM13 9V10H14V9ZM-2 10V11H-1V10ZM0 10V13H1V10ZM2 10V13H3V10ZM7 10V11H8V10ZM11 10V14H12V10ZM13 11V12H14V11ZM-2 12V13H-1V12ZM7 12V13H8V12ZM1 13V14H2V13ZM13 13V14H14V13ZM-2 14V15H-1V14ZM13 15V16H14V15ZM-2 16V17H-1V16ZM13 17V18H14V17ZM-2 18V19H-1V18ZM-1 19V20H0V19ZM1 19V20H2V19ZM3 19V20H4V19ZM5 19V20H6V19ZM7 19V20H8V19ZM9 19V20H10V19ZM11 19V20H12V19ZM13 19V20H14V19Z"\n></glyph>\n</font>\n</defs>\n</svg>',
    ),
    (
        {'unicodeformat': 'char'},
        '<svg xmlns="http://www.w3.org/2000/svg" version="1.1">\n<metadata>\n  Title: Unifont\n  Weight: Medium\n  Version: 13.0.04\n  Foundry: GNU\n  Copyright: Copyright (C) 1998-2020 Roman Czyborra, Paul Hardy, Qianqian Fang, Andrew Miller, Johnnie Weaver, David Corbett, Rebecca Bettencourt, et al. License: SIL Open Font License version 1.1 and GPLv2+: GNU GPL version 2 or later &lt;http://gnu.org/licenses/gpl.html&gt; with the GNU Font Embedding Exception.\n</metadata>\n<defs>\n  <font id="gnu-unifont-medium-r-normal-sans-16-160-75-75-c-80-iso10646-1" horiz-adv-x="16">\n<font-face\n  font-family="Unifont"\n  font-weight="Medium"\n  font-style="R"\n  units-per-em="16"\n  cap-height="10"\n  x-height="8"\n  ascent="14"\n  descent="2"\n  bbox="0 -2 16 16"\n  underline-thickness="1"\n  underline-position="-2"\n  unicode-range="U+0002, U+FFFC"\n></font-face>\n<missing-glyph horiz-adv-x="16" d="M0,0h16v16h-16z" />\n<glyph glyph-name=".notdef" horiz-adv-x="16" d="M0,0h16v16h-16z" />\n<glyph\n  glyph-name="U+0002"\n  horiz-adv-x="16"\n  d="M1 0V1H2V0ZM3 0V1H4V0ZM5 0V1H6V0ZM7 0V1H8V0ZM9 0V1H10V0ZM11 0V1H12V0ZM13 0V1H14V0ZM15 0V1H16V0ZM0 1V2H1V1ZM15 2V3H16V2ZM0 3V4H1V3ZM15 4V5H16V4ZM0 5V6H1V5ZM1 6V7H4V6ZM7 6V10H6V11H9V10H8V6ZM10 6V8H11V6ZM13 6V8H14V6ZM15 6V7H16V6ZM0 7V8H1V7ZM4 7V8H5V7ZM2 8V9H4V8ZM11 8V9H13V8ZM15 8V9H16V8ZM0 9V10H2V9ZM10 9V11H11V9ZM13 9V11H14V9ZM2 10V11H5V10ZM15 10V11H16V10ZM0 11V12H1V11ZM15 12V13H16V12ZM0 13V14H1V13ZM15 14V15H16V14ZM0 15V16H1V15ZM2 15V16H3V15ZM4 15V16H5V15ZM6 15V16H7V15ZM8 15V16H9V15ZM10 15V16H11V15ZM12 15V16H13V15ZM14 15V16H15V15Z"\n></glyph>\n<glyph\n  glyph-name="U+FFFC"\n  unicode="￼"\n  horiz-adv-x="16"\n  d="M0 0V1H1V0ZM2 0V1H3V0ZM4 0V1H5V0ZM6 0V1H7V0ZM8 0V1H9V0ZM10 0V1H11V0ZM12 0V1H13V0ZM14 0V1H15V0ZM15 1V2H16V1ZM0 2V3H1V2ZM15 3V4H16V3ZM0 4V5H1V4ZM3 5V6H4V5ZM7 5V10H9V9H8V8H9V7H8V6H9V5ZM11 5V6H13V5ZM15 5V6H16V5ZM0 6V7H1V6ZM2 6V9H3V6ZM4 6V9H5V6ZM9 6V7H10V6ZM13 6V10H14V6ZM15 7V8H16V7ZM0 8V9H1V8ZM9 8V9H10V8ZM3 9V10H4V9ZM15 9V10H16V9ZM0 10V11H1V10ZM15 11V12H16V11ZM0 12V13H1V12ZM15 13V14H16V13ZM0 14V15H1V14ZM1 15V16H2V15ZM3 15V16H4V15ZM5 15V16H6V15ZM7 15V16H8V15ZM9 15V16H10V15ZM11 15V16H12V15ZM13 15V16H14V15ZM15 15V16H16V15Z"\n></glyph>\n</font>\n</defs>\n</svg>',
    ),
]


@pytest.mark.parametrize('opts, expected', TWOA_SVGFONT_CASES)
def test_2atest_svgfont_matches_js(opts, expected):
    assert Font('tests/fonts/unifont-13.0.04-2atest.bdf').tosvgfont(**opts) == expected
