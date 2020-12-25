# BDF Parser

[![PyPI package](https://img.shields.io/badge/pip%20install-bdfparser-brightgreen)](https://pypi.org/project/example-pypi-package/) [![Actions Status](https://github.com/tomchen/bdfparser/workflows/Test/badge.svg)](https://github.com/tomchen/bdfparser/actions) [![License](https://img.shields.io/github/license/tomchen/bdfparser)](https://github.com/tomchen/bdfparser/blob/master/LICENSE)

BDF (Glyph Bitmap Distribution; [Wikipedia](https://en.wikipedia.org/wiki/Glyph_Bitmap_Distribution_Format); [Spec](https://font.tomchen.org/bdf_spec/)) format bitmap font file parser library in Python. It has [`Font`](https://font.tomchen.org/bdfparser_py/font), [`Glyph`](https://font.tomchen.org/bdfparser_py/glyph) and [`Bitmap`](https://font.tomchen.org/bdfparser_py/bitmap) classes providing more than 30 enriched API methods of parsing BDF fonts, getting their meta information, rendering text in any writing direction, adding special effects and manipulating bitmap images. It works seamlessly with [PIL / Pillow](https://pillow.readthedocs.io/en/stable/) and [NumPy](https://numpy.org/).

Below I'll show you some quick examples, but it is still strongly recommended you go to [**BDF Parser Python Library's official website to read the detailed documentation / tutorials / API reference**](https://font.tomchen.org/bdfparser_py/).

Install bdfparser library with [pip](https://pip.pypa.io/en/stable/installing/#do-i-need-to-install-pip):

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

You probably understand what I did in these examples. If you don't, go to [bdfparser's documentation website](https://font.tomchen.org/bdfparser_py/).
