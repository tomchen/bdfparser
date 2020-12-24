# BDF Parser

[![PyPI package](https://img.shields.io/badge/pip%20install-bdfparser-brightgreen)](https://pypi.org/project/example-pypi-package/) [![Actions Status](https://github.com/tomchen/bdfparser/workflows/Test/badge.svg)](https://github.com/tomchen/bdfparser/actions) [![License](https://img.shields.io/github/license/tomchen/bdfparser)](https://github.com/tomchen/bdfparser/blob/master/LICENSE)

BDF (Glyph Bitmap Distribution) format bitmap font file parser library in Python. It has 3 classes `Font`, `Glyph` and `Bitmap` providing more than 30 enriched API methods (functions) for parsing BDF fonts, getting their meta information, rendering text in any writing direction, adding special effects and manipulating bitmap images. It works seamlessly with PIL / Pillow and NumPy. It also has [**detailed documentation / tutorials / API reference**](https://tomchen.org/bdfparser_py/ "BDF Parser Python library's documentation / tutorials / API reference") that I strongly recommend you read.

## Other tools
* [Example .bdf fonts](https://github.com/tomchen/bdfparser/tree/master/example_fonts/bdf):
  * GNU Unifont ([Wikipedia article](https://en.wikipedia.org/wiki/GNU_Unifont); [Homepage](https://unifoundry.com/unifont/index.html)): Unicode font (intended to support "all" common languages)
  * M+ FONTS ([Wikipedia article](https://en.wikipedia.org/wiki/M%2B_FONTS); [Homepage](https://mplus-fonts.osdn.jp/about-en.html)): Japanese font
  * HanWangYanKai 王漢宗自由字型顏體 ([Chinese Wikipedia article](https://zh.wikipedia.org/wiki/%E7%8E%8B%E6%BC%A2%E5%AE%97%E8%87%AA%E7%94%B1%E5%AD%97%E5%9E%8B); [download .ttf](https://github.com/hepochen/fonts/raw/master/gpl-cjk-fonts/wang/wt064.ttf)): Traditional Chinese font
  * See also some typical but non-free, fair-used Chinese fonts in [another repo](https://github.com/might-and-magic/fnt-generator#other-tools)
* [otf2bdf](https://github.com/tomchen/bdfparser/tree/master/tools/otf2bdf): OpenType to BDF Converter. Just an archive. Not written by me.

## Projects that use this library

[FNT Generator](https://github.com/might-and-magic/fnt-generator): Might and Magic 6 7 8 and Heroes 3 font File Generator in Python. Another project of mine

## License

* Python code is written by me (Tom CHEN) and is released under the MIT License.
* [otf2bdf](https://github.com/tomchen/bdfparser/tree/master/tools/otf2bdf): see its page.
* Example .bdf fonts:
  * GNU Unifont: [GNU General Public License v2](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html), by Roman Czyborra, Paul Hardy, part of the GNU Project
  * M+ FONTS: [a free license](https://mplus-fonts.osdn.jp/about-en.html#license), designed by Coji Morishita
  * HanWangYanKai 王漢宗自由字型顏體: [GNU General Public License v2](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html), by 王漢宗
  * Other fonts are proprietary, and are used non-commercially and fairly
