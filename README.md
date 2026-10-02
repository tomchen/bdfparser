# BDF Parser Python library

[![PyPI package](https://img.shields.io/badge/pip%20install-bdfparser-brightgreen)](https://pypi.org/project/bdfparser/) [![version number](https://img.shields.io/pypi/v/bdfparser?color=green&label=version)](https://github.com/tomchen/bdfparser/releases) [![Actions Status](https://github.com/tomchen/bdfparser/workflows/Test/badge.svg)](https://github.com/tomchen/bdfparser/actions) [![codecov](https://codecov.io/gh/tomchen/bdfparser/branch/master/graph/badge.svg?token=IMVVQEC04H)](https://codecov.io/gh/tomchen/bdfparser) [![License](https://img.shields.io/github/license/tomchen/bdfparser)](https://github.com/tomchen/bdfparser/blob/master/LICENSE)

BDF (Glyph Bitmap Distribution; [Wikipedia](https://en.wikipedia.org/wiki/Glyph_Bitmap_Distribution_Format); [Spec](https://font.tomchen.org/bdf_spec/)) bitmap font parser, editor and converter library in pure Python, with no dependencies.

It supports parsing, editing and export of BDF fonts, reading and writing PCF fonts, converting bitmap fonts to TrueType (TTF) fonts with square or round pixel dots (and back), SVG output, pixelated text bitmap rendering in any writing direction, bitmap image modification, non-Unicode charsets (GB2312, Big5, Shift-JIS, KOI8-R, ISO 8859, Windows code pages, ...), a command line tool, and more. The library features the [`Font`](https://font.tomchen.org/bdfparser_py/font), [`Glyph`](https://font.tomchen.org/bdfparser_py/glyph) and [`Bitmap`](https://font.tomchen.org/bdfparser_py/bitmap) classes, which provide over 80 chainable API methods.

It works seamlessly with [PIL / Pillow](https://pillow.readthedocs.io/en/stable/) and [NumPy](https://numpy.org/), and includes detailed documentation, tutorials, and an API reference.

**BDF Parser TypeScript (JavaScript) library** ([documentation](https://font.tomchen.org/bdfparser_js/); [GitHub page](https://github.com/tomchen/bdfparser-js); [npm page](https://www.npmjs.com/package/bdfparser); `npm i bdfparser`) is a port of **BDF Parser Python library** ([documentation](https://font.tomchen.org/bdfparser_py/); [GitHub page](https://github.com/tomchen/bdfparser); [PyPI page](https://pypi.org/project/bdfparser/); `pip install bdfparser`). Both follow the same specification, have the same API and produce byte-identical output. Both are written by [Tom Chen](https://github.com/tomchen/) and under the MIT License.

The BDF Parser TypeScript (JavaScript) library has a [**Live Demo & Editor**](https://font.tomchen.org/bdfparser_js/editor) you can try.

Below I'll show you some quick examples, but it is still strongly recommended you go to [**BDF Parser Python Library's official website to read the detailed documentation / tutorials / API reference**](https://font.tomchen.org/bdfparser_py/).

Install bdfparser Python library (Python 3.10 or later) with [pip](https://pip.pypa.io/en/stable/installing/#do-i-need-to-install-pip):

```bash
pip install bdfparser
```

Then:

```python
from bdfparser import Font
font = Font('tests/fonts/unifont-13.0.04.bdf')
print(f"This font's global size is "
      f"{font.headers['fbbx']} x {font.headers['fbby']} (pixel), "
      f"it contains {len(font)} glyphs.")

# =================================

ac = font.glyph("a").draw().crop(6, 8, 1, 2).concat(
    font.glyph("c").draw().crop(6, 8, 1, 2)
    ).shadow()
ac_8x8 = ac * 8

from PIL import Image
im_ac = Image.frombytes('RGBA',
                        (ac_8x8.width(), ac_8x8.height()),
                        ac_8x8.tobytes('RGBA'))
im_ac.save("ac.png", "PNG")

# =================================

hello = font.draw('Hello!', direction='rl').glow()
print(hello)

import numpy
import matplotlib.pyplot as plt
nparr = numpy.array(hello.todata(2))
plt.imshow(nparr, 'Blues')
plt.show()

# =================================

font_preview = font.drawall()
im_ac = Image.frombytes('1',
                        (font_preview.width(), font_preview.height()),
                        font_preview.tobytes('1'))
im_ac.save("font_preview.png", "PNG")
```

### Editing and converting (new in v3)

```python
from bdfparser import Bitmap, Font

# create a font from scratch, or load one (BDF, PCF, .pcf.gz or TTF)
font = Font.create(pixelsize=8, familyname='Tiny')
font.newglyph(ord('A'), Bitmap.fromstring("""
..#..
.#.#.
#...#
#####
#...#
#...#
#...#
"""), mode=1, dwidth=6)

# glyphs from a font are "attached": edits are written back immediately
font.glyph('A').shift(1, 0)
font.transform(lambda bitmap: bitmap.bold(), mode=1)  # embolden every glyph
font.setprop('WEIGHT_NAME', 'Bold').updatebbox()

font.save('tiny.bdf')                               # BDF (FontForge style)
font.save('tiny.pcf')                               # PCF (same bytes as bdftopcf)
font.save('tiny.ttf', shape='circle', dotsize=0.9)  # TrueType with round dots
font.save('tiny.svg')                               # SVG font
print(font.glyph('A').draw().tosvg(pixelsize=10))   # one SVG image

# non-Unicode fonts: characters are converted with the font's charset
gb = Font('some-gb2312-font.bdf')                   # CHARSET_REGISTRY "GB2312.1980"
print(gb.draw('你好'))
gb.charsetconvert('ISO10646-1')                     # re-encode the font to Unicode
```

Warnings (problems in a font, missing glyphs, ...) use the `bdfparser.BDFParserWarning` category and can be filtered with the standard [`warnings`](https://docs.python.org/3/library/warnings.html) module; fatal parse errors raise `bdfparser.BDFParseError` with the line number.

### Command line

```bash
bdfparser info font.bdf                       # font name, glyph count, bounding box, charset, properties
bdfparser preview font.bdf "Hello"            # print text rendered with # and .
bdfparser convert font.bdf font.ttf --shape circle --dotsize 0.9 --ppu 64
bdfparser convert font.pcf.gz font.bdf
bdfparser convert font.ttf font.bdf --pixelsize 16   # TTF not made by bdfparser
bdfparser convert gb2312.bdf unicode.bdf --charset ISO10646-1
```

See [CHANGELOG.md](https://github.com/tomchen/bdfparser/blob/master/CHANGELOG.md) for what changed in v3 (including breaking changes).

You probably understand what I did in these examples. Whether you do or not, go to [**bdfparser's documentation website**](https://font.tomchen.org/bdfparser_py/).

<p align="center">
<a href="https://font.tomchen.org/bdfparser_py/">
<img src="https://font.tomchen.org/img/bdfparser_py/ac.png" /><br>
<img src="https://font.tomchen.org/img/bdfparser_py/plot.png" /><br>
<img src="https://font.tomchen.org/img/bdfparser_py/font_preview_part.png" />
</a>
<a href="https://font.tomchen.org/bdfparser_js/editor" title="BDF Parser Live Demo & Code Editor"><img src="https://font.tomchen.org/img/bdfparser_js/bdfparser_live_editor_demo.gif" width="700" alt="BDF Parser Live Demo & Code Editor"></a>
</p>
