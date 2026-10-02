# Changelog

## 3.0.0

bdfparser 3 turns the BDF parser into a parser, editor and converter for BDF, PCF and pixel TrueType fonts. The Python and the TypeScript ([bdfparser-js](https://github.com/tomchen/bdfparser-js)) libraries now follow one shared specification and produce byte-identical output.

### Breaking changes

- **Python ≥ 3.10** is required (3.5 – 3.9 support dropped). The package is now built from `pyproject.toml` and ships type hints (`py.typed`).
- **Typed properties**: unquoted integer property values are now `int` (e.g. `font.props['pixel_size'] == 16`; v2: `'16'`). Quoted values stay `str` (`CHARSET_ENCODING "1"` → `'1'`), unquoted non-integers are raw `str`, key-only lines are `None`.
- **Quoted strings** are parsed properly: `""` inside a quoted value is an escaped `"`, text after the closing quote is ignored (v2 stripped every `"` and `'` from both ends of the value).
- **`COMMENT`** values (header and properties): only one pair of surrounding double quotes is removed (v2 stripped all `"` and `'` characters from both ends).
- **Warnings** are emitted with the new category `bdfparser.BDFParserWarning` (a `UserWarning`) and `stacklevel=2`; the library **no longer replaces `warnings.formatwarning` globally** (fixes [#8](https://github.com/tomchen/bdfparser/issues/8), implements [#9](https://github.com/tomchen/bdfparser/pull/9) by [@ty-porter](https://github.com/ty-porter) — thanks!).
- **Fatal parse errors** raise `bdfparser.BDFParseError` (a `ValueError`) whose message starts with the 1-based line number (unexpected end of file inside the headers, malformed numbers in `STARTFONT`/`SIZE`/`FONTBOUNDINGBOX`/`CHARS`/`ENCODING`/`BBX`/`SWIDTH`/`DWIDTH`/..., glyph without `BBX`). v2 leaked `StopIteration`, `IndexError` or `ValueError`.
- **Unencoded glyphs** (`ENCODING -1`, optionally with an alternative code) are kept in the new `font.unencoded` list (`{'altcode': int | None, 'meta': [...]}`) instead of all being stored under the key `-1` of `font.glyphs` (where only the last one survived). A glyph without `ENCODING` is treated as unencoded (with a warning).
- **Charsets**: `Font.glyph()`, `Font.draw()`, `Font.lacksglyphs()` and `Glyph.chr()` now convert characters with the font's charset (`CHARSET_REGISTRY` / `CHARSET_ENCODING`), so non-Unicode fonts (GB2312, Big5, Shift-JIS, KOI8-R, ISO 8859-x, Windows code pages, ...) work (fixes [#4](https://github.com/tomchen/bdfparser/issues/4)). `Glyph.chr()` returns `None` when the codepoint is not representable.
- `Font(source)` replaces `Font(*argv)`: `source` may be a path (`str` / `os.PathLike`), a text or binary file object, or `bytes`; anything else raises `TypeError`.
- `load_file_path()` reads the file in binary mode and auto-detects BDF / PCF / `.pcf.gz` / TTF; BDF bytes are decoded as UTF-8 (invalid bytes replaced) instead of with the locale's default encoding.
- Loading a font into an existing `Font` object replaces its previous content (an `encoding()` override is kept).
- `Glyph.draw()`: a glyph with fewer bitmap rows than its `BBX` height is padded with empty rows (with a warning) instead of raising; extra rows are ignored; short hex rows are padded.
- `Glyph(meta, font)` stores a (shallow) copy of `meta`.
- `Bitmap` equality: `==` compares the pixels (v2 compared identity); `Bitmap` objects are no longer hashable. `Bitmap.width()` returns `0` for an empty bitmap (v2 raised `IndexError`).
- `ValueError` (instead of a bare `Exception`, `UnboundLocalError` or `None`) for invalid arguments: `Glyph.draw(mode=-1)` without `bb`, unknown draw / origin modes, `Glyph.origin(mode=-1)` without offsets, unknown `itercps()` order, unknown `Bitmap.todata()` type, and a `linelimit` too small for one glyph (the v2 message itself crashed with a `TypeError`).
- Unknown header keywords and stray lines are ignored **with a warning**; a duplicate codepoint warns (the later glyph still wins).

### New

- **Loading**: `load_string()`, `load_lines()`, `load_bytes()` (BDF, PCF, gzip, TTF; `CFF`-based OpenType is rejected), `Font(bytes)`. Robust parser: LF / CRLF / CR line endings, UTF-8 BOM, blank lines and extra whitespace anywhere, missing `STARTPROPERTIES` / `ENDPROPERTIES` / `CHARS` / `ENDCHAR` / `ENDFONT`, property and glyph count mismatches (warnings).
- **Properties**: any (non-Adobe) property name works and its original spelling is preserved on output (`MinSpace` stays `MinSpace`); `getprop()`, `setprop()`, `delprop()`.
- **Charsets**: `font.charset`, `font.char2cp()`, `font.cp2char()`, `font.encoding(charset=..., char2cp=..., cp2char=...)` override, `font.charsetconvert(newcharset)`; module `bdfparser.encoding`. GB2312 / JIS X 0208 / KS C 5601 fonts in GL form (e.g. `GB2312.1980-0`, `ENCODING 12321` = 啊) are detected.
- **Font editing**: `Font.create()`, `addglyph()`, `removeglyph()`, `newglyph()`, `updatebbox()`, `subset()`, `merge()`, `transform()`, `clone()`, `swidth()`.
- **Glyph editing**: glyphs obtained from a font are *attached* and write every change back: `setbitmap()` (the inverse of `draw()`, with trimming), `setmeta()`, `shift()`, `transform()`, `clone()`; `bdfparser.defaultglyphname()`.
- **Bitmap editing**: `Bitmap.fromstring()`, `Bitmap.blank()`, `getpixel()`, `setpixel()`, `fliph()`, `flipv()`, `rotate()`, `invert()`, `shift()`, `bbox()`, `trim()`, `bold()`, `italic()`, `paste()`, `equals()`.
- **Output**: `tobdf()` (FontForge-style, reproduces FontForge-written files byte for byte), `topcf()` (identical to `bdftopcf`), `tottf()` (pixel TrueType font with square or round dots, lossless round trip), `tosvgfont()`, `Bitmap.tosvg()` (merged outline paths with holes, round dots, or rectangles), `save(path)`.
- Modules `bdfparser.pcf` (`read_pcf`, `write_pcf`), `bdfparser.ttf` (`read_ttf`, `write_ttf`), `bdfparser.outline` (`bitmap_contours`, `rasterize`).
- **Command line**: `bdfparser convert | info | preview` (also `python -m bdfparser`).

### Fixed

- Missing `import warnings` in `bitmap.py`.
- `drawcps()` error message for a too small `linelimit`.

## 2.2.0 and earlier

See the [GitHub releases](https://github.com/tomchen/bdfparser/releases).
