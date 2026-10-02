# bdfparser v3 — shared specification (Python ⇄ TypeScript)

This document is the single source of truth for bdfparser **v3.0.0** in both
repositories:

- Python: `/home/chen/githubprojects/fontpixel/bdfparser` (package `src/bdfparser`)
- TypeScript: `/home/chen/githubprojects/fontpixel/bdfparser-js` (package `src/`)

Both libraries MUST expose the same concepts, method names, argument order and
defaults. Language idioms may differ where noted (Python keyword arguments ⇄
JS trailing `options` object; Python `bytes` ⇄ JS `Uint8Array`; Python
`snake_case` module functions ⇄ JS `camelCase` module functions). Public
**method names on `Font` / `Glyph` / `Bitmap` are identical** (all-lowercase,
no underscores, as in v2: `glyphbycp`, `drawall`, `tobdf`, ...).

All writers (BDF, PCF, TTF, SVG) MUST be **deterministic** and the Python and
JS outputs MUST be **byte-identical** for the same input and options. Golden
cross-language tests enforce this.

Runtime dependencies: **none** in either library (pure Python ≥ 3.10; JS must
run in Node ≥ 20, Deno, Bun and browsers — no `Buffer`, no `fs` in library
code except `src/cli.ts`).

Rounding rule used everywhere a spec says "round": `round(v) = floor(v + 0.5)`
(Python: `math.floor(v + 0.5)`, JS: `Math.floor(v + 0.5)`). Never use Python's
built-in `round()` (banker's rounding) or JS `Math.round` for spec'd values.

Number formatting in text outputs (SVG, JSON-free places): `fmtnum(n)` = the
integer string if `n` is integral, otherwise the shortest round-trip repr
(Python `repr(float(n))`, JS `String(n)`).

---------------------------------------------------------------------------

## 1. Data model

### 1.1 `Font`

| attribute | type | notes |
|---|---|---|
| `headers` | dict / object | keys (insertion order = file order): `bdfversion` (float), `fontname`, `pointsize`, `xres`, `yres`, `fbbx`, `fbby`, `fbbxoff`, `fbbyoff`, optional `swx0 swy0 dwx0 dwy0 swx1 swy1 dwx1 dwy1 vvectorx vvectory`, `metricsset` (int, default 0 inserted after header parse), optional `contentversion`, optional `comment` (list of str). Unchanged from v2. Python: `{}` before loading; JS: `headers` is `{}`-like typed object (v2 had `undefined`; v3 initializes to `{}` cast). |
| `props` | dict / object | keys are **lower-case** property names; values are `int` (unquoted integer in file), `str` (quoted string, with `""` unescaped to `"`, or any other unquoted token), or `None`/`null` (key-only line). `comment` → list of str (COMMENT lines inside the properties block). **Breaking change vs v2 Python**: unquoted integers are now `int`, not `str`. |
| `glyphs` | `dict[int, list]` / `Map<number, GlyphMetaInFont>` | codepoint → 17-slot list `[glyphname, codepoint, bbw, bbh, bbxoff, bbyoff, swx0, swy0, dwx0, dwy0, swx1, swy1, dwx1, dwy1, vvectorx, vvectory, hexdata]` (unchanged from v2). Insertion order = file order. |
| `unencoded` | list / array | glyphs whose `ENCODING` is `-1`: list of `{'altcode': int or None, 'meta': <17-slot list with codepoint -1>}` (JS: `{altcode: number \| null, meta: GlyphMetaInFont}`), file order. Not drawable by codepoint, but preserved by all writers. |
| `charset` | property (read) | resolved charset name, see §4. |

Private bookkeeping: original-case property names (`MinSpace` stays
`MinSpace` on output). Python: `self._propnames: dict[str, str]` (lower →
original); JS: `private __propnames: Map<string,string>`. Properties added
without a known original name are written in UPPER CASE.

### 1.2 `Glyph`

`Glyph(meta, font)` — `meta` is a dict/object with the 17 keys of
`META_TITLES` (same order as the list slots). `font` is the owning `Font`
(required, as in v2).

A glyph obtained from a font (`glyphbycp`, `glyph`, `iterglyphs`,
`newglyph`, after `addglyph`) is **attached**: every editing method writes
the updated meta back into `font.glyphs` immediately (moving the key if the
codepoint changed). A glyph constructed directly with `Glyph(meta, font)` is
**detached** until passed to `font.addglyph()`.

Python: `glyph._attached: bool`; JS: `private __attached = false`
(set by Font via an internal method `_attach()` — name freely chosen, not
public API).

### 1.3 `Bitmap`

`Bitmap(bindata)` — `bindata` is a list of equal-length strings of `'0'`,
`'1'`, `'2'` (row 0 = top). `width()` returns `0` for an empty bitmap
(v2 crashed). Two coordinate conventions coexist (documented in docstrings):

- **pixel addressing** (`getpixel`, `setpixel`, `paste`): `(x, y)` with
  origin at the **top-left**, y grows **downward** (= `bindata[y][x]`,
  canvas/image convention).
- **movement / cropping** (`crop`, `shadow`, `shift`, `bbox`): x grows right,
  y grows **upward**, offsets measured from the **bottom-left** (font
  convention, as in v2 `crop`).

---------------------------------------------------------------------------

## 2. Public API (both languages)

Notation: Python signature; JS is identical with keyword args moved into a
trailing `options` object unless stated. "→ self" means returns `self`/`this`
for chaining. Existing v2 methods keep their v2 signature and behavior unless
listed here.

### 2.1 Loading

| Python | JS | notes |
|---|---|---|
| `Font(source=None)` | `new Font()` | Python: `source` may be `str`/`os.PathLike` (path), text or binary file object, or `bytes` (auto-detected format). |
| `load_file_path(path)` → self | — (CLI only) | auto-detects BDF / PCF / TTF by magic bytes. |
| `load_file_obj(fileobj)` → self | — | text file ⇒ BDF; binary file ⇒ auto-detect. |
| `load_string(text)` → self | `load_string(text)` → this (sync) | BDF text. |
| `load_lines(iterable_of_str)` → self | `load_filelines(asyncIterable)` → Promise<this> (v2, kept) | BDF line by line. |
| `load_bytes(data, **ttfoptions)` → self | `load_bytes(data, options?)` → this (sync) | `data`: bytes / `Uint8Array` / `ArrayBuffer`. Detects: `b'\x01fcp'` ⇒ PCF; gzip magic ⇒ see §6; `00 01 00 00` or `true` ⇒ TTF; `OTTO` ⇒ raise "CFF-based OpenType is not supported"; else decode as UTF-8 (with replacement) and parse as BDF. TTF options: `pixelsize`. |
| — | `load_url(url, init?)` → Promise<this> | uses global `fetch`; reads `arrayBuffer()`, then `load_bytes`. Works in browsers. |
| classmethod `Font.create(pixelsize=16, ascent=None, descent=None, fontname=None, familyname='Untitled', xres=75, yres=75)` | static `Font.create(options?)` | see §2.6. |
| `encoding(charset=None, char2cp=None, cp2char=None)` → self | `encoding({iconv?, charset?, char2cp?, cp2char?})` → this (v3-rc API kept) | override charset resolution / conversion. |

The JS shortcut `$Font(source, encodingOptions?)` (async) accepts an async
iterable of lines, a BDF `string`, a `Uint8Array`/`ArrayBuffer`, or a `URL`.

Parsing rules (BDF): see §3.

### 2.2 Querying (v2, kept)

`length()` (JS getter `length`), `__len__`, `itercps(order=1, r=None)`,
`iterglyphs(order=1, r=None)`, `glyphbycp(cp)`, `glyph(char)`,
`lacksglyphs(string)`, `drawcps`, `draw`, `drawall` — unchanged semantics,
except: `glyph(char)` / `draw(string)` / `lacksglyphs` / `Glyph.chr()` go
through `font.char2cp` / `font.cp2char` (§4) so non-Unicode fonts work
(issue tomchen/bdfparser#4). Python `glyphbycp` of a missing glyph still
warns (with `BDFParserWarning`) and returns `None`. New:

| method | returns |
|---|---|
| `font.char2cp(char)` | int or None |
| `font.cp2char(cp)` | str (1 char) or None if not representable |
| `font.getprop(key)` | value or None (case-insensitive key) |

### 2.3 Font editing (all → self unless noted)

| method | semantics |
|---|---|
| `setprop(key, value)` | case-insensitive; `value` int/str/None; remembers the given spelling as original name if the key is new. |
| `delprop(key)` | removes if present. |
| `addglyph(glyph, replace=True)` | `glyph`: `Glyph` or meta dict. If its codepoint exists: replace when `replace` else keep old and warn. If codepoint is `-1`, append to `unencoded`. Attaches the Glyph (the Glyph object now writes back to this font). |
| `removeglyph(cp_or_glyph)` | no-op if missing. |
| `newglyph(cp, bitmap=None, mode=0, name=None, dwidth=None)` → **Glyph** | creates + attaches (replacing any existing). `name` default = `defaultglyphname(cp)` (§2.8). If `bitmap` is None: `bbw=bbh=bbxoff=bbyoff=0`, `hexdata=[]`, `dwx0 = dwidth ?? headers.fbbx`. Else `dwx0 = dwidth ?? bitmap.width()` and then `setbitmap(bitmap, mode)`. Always `dwy0=0`, `swx0 = swidth(dwx0)` (§2.8), `swy0=0`; all other optional metrics None. |
| `updatebbox()` | FONTBOUNDINGBOX := union of all glyph boxes `[bbxoff, bbxoff+bbw) × [bbyoff, bbyoff+bbh)` over glyphs (encoded + unencoded) with `bbw>0 and bbh>0`. If none, leave unchanged. |
| `subset(r)` → **new Font** | deep copy keeping only glyphs whose cp passes the `r` filter of `itercps` (int / (a,b) tuple / list of tuples; JS: number / [a,b] / [a,b][]). Unencoded glyphs dropped. |
| `merge(other, replace=False)` | copies glyphs (deep) of `other` into self; existing codepoints kept unless `replace`. |
| `transform(fn, r=None, mode=0)` | for each glyph (filtered by `r`): `glyph.transform(fn, mode)`. |
| `clone()` → **new Font** | deep copy (headers, props, propnames, glyphs, unencoded, encoding overrides). |
| `charsetconvert(newcharset)` | re-encode every glyph codepoint from current charset to `newcharset` (glyphs not representable in the new charset are dropped with one summary warning); sets `CHARSET_REGISTRY`/`CHARSET_ENCODING` props from the canonical name (§4); clears any `encoding()` override. |

### 2.4 Glyph

v2 methods kept: `cp()`, `chr()`, `draw(mode=0, bb=None)`, `origin(...)`,
`__str__`/`toString`, `__repr__`/`repr`.

| method | semantics |
|---|---|
| `setbitmap(bitmap, mode=0, bb=None, trim=True)` → self | Inverse of `draw()`. The bitmap's **bottom-left corner** sits at, relative to the glyph origin: mode 0 → `(fbbxoff, fbbyoff)`; mode 1 or 2 → current `(bbxoff, bbyoff)`; mode -1 → `(bb[2], bb[3])` (`bb` = `(w, h, xoff, yoff)`, only xoff/yoff used; raise if missing). If `trim`: drop empty (all-zero) rows/columns on all four sides adjusting offsets; an all-empty bitmap gives `bbw=bbh=bbxoff=bbyoff=0`, `hexdata=[]`. Any non-`'0'` pixel counts as ink and is stored as 1. `hexdata` rows: UPPER-case hex, `ceil(bbw/8)*2` digits, bits left-aligned, zero-padded. Does not touch DWIDTH/SWIDTH. |
| `setmeta(**kwargs)` / `setmeta(obj)` → self | sets any of the 17 meta keys (unknown key ⇒ raise). Changing `codepoint` of an attached glyph moves its key in `font.glyphs` (overwriting a glyph already at the destination). |
| `shift(dx=0, dy=0)` → self | `bbxoff += dx; bbyoff += dy` (y up). |
| `transform(fn, mode=0)` → self | `bm = self.draw(mode)`; `res = fn(bm)`; `self.setbitmap(res if res is not None else bm, mode)`. |
| `clone()` → Glyph | deep-copied meta, same font, **detached**. |

### 2.5 Bitmap

v2 kept: `width height clone crop overlay concatall concat (+) enlarge (*) replace shadow glow bytepad todata tobytes(Python only)`, JS `draw2canvas`.

New (all mutate and → self unless stated):

| method | semantics |
|---|---|
| classmethod `Bitmap.fromstring(text)` (JS static) | rows split on `\n` (ignore `\r`, skip empty lines at start/end); chars: `#`→1, `.`→0, `&`→2, and digits `0 1 2` kept. Any other char ⇒ raise. Rows of different length ⇒ raise. Inverse of `str(bitmap)`. |
| classmethod `Bitmap.blank(w, h)` | all `'0'`. |
| `getpixel(x, y)` → int | top-left origin; out of range ⇒ raise (Python `IndexError`, JS `RangeError`). |
| `setpixel(x, y, value=1)` | value 0/1/2. |
| `fliph()` | mirror left↔right. |
| `flipv()` | mirror top↔bottom. |
| `rotate(angle=90)` | clockwise, `angle` multiple of 90 (negative allowed); else raise. |
| `invert()` | `'0'`→`'1'`, everything else → `'0'`. |
| `shift(dx=0, dy=0)` | moves content (x right, y up), size unchanged, vacated pixels `'0'`. |
| `bbox()` → `(w, h, xoff, yoff)` | ink bounding box in crop() convention, so `bm.crop(*bm.bbox())` trims. Empty ⇒ `(0, 0, 0, 0)`. JS returns a 4-tuple array. |
| `trim()` | `crop(*bbox())`; empty ⇒ bindata `[]`. |
| `bold(n=1)` | width += n; result = overlay of the bitmap shifted right by 0..n (pixel rule `b or a`, like `overlay`). |
| `italic(step=2, base=0)` | row at index `r` counted from the bottom (0 = bottom) is shifted right by `floor((r - base) / step)` (floor division, can be negative); bitmap widened on the left/right as needed (new width = w + max_shift − min_shift; content placed at `x + shift − min_shift`). |
| `paste(bitmap, x=0, y=0)` | draws `bitmap` with its top-left at `(x, y)` (top-left origin); pixels outside are clipped; rule `b or a` (non-zero source pixels win). Size unchanged. |
| `__eq__` / `equals(other)` | same bindata. |
| `tosvg(pixelsize=1, format='path', inverted=False, xoff=0, yoff=0, shape='square')` → str | JS: `tosvg(pixelsize?, format?, inverted?, offsets?: {x?, y?}, shape?)` (v3-rc signature kept, `shape` appended). See §7. |
| `topath(...)` | not public; SVG/TTF use `outline` module. |

`draw2canvas` (JS only): `draw2canvas(context, options?)` with
`options = {x?: number=0, y?: number=0, pixelsize?: number=1, pixelcolors?: {'0','1','2' → color|null}}`;
backward compatible with `draw2canvas(context, pixelcolors?, xoff?, yoff?)`
(if the 2nd arg has any of the keys `'0' '1' '2'`, treat as v2/v3-rc call).
Draws `fillRect(x + col*pixelsize, y + row*pixelsize, pixelsize, pixelsize)`.
(Fixes tomchen/bdfparser-js#2, supersedes PR #3.)

### 2.6 `Font.create`

```
descent = descent ?? floor(pixelsize / 8)
ascent  = ascent  ?? pixelsize - descent
fontname = fontname ?? familyname
headers (this order): bdfversion 2.1, fontname, pointsize=pixelsize, xres, yres,
                      fbbx=pixelsize, fbby=ascent+descent, fbbxoff=0, fbbyoff=-descent, metricsset=0
props (this order, original names upper-case):
  FAMILY_NAME "familyname", PIXEL_SIZE pixelsize, FONT_ASCENT ascent, FONT_DESCENT descent,
  CHARSET_REGISTRY "ISO10646", CHARSET_ENCODING "1"
```

### 2.7 Output

| Python | JS | |
|---|---|---|
| `tobdf()` → str | `tobdf()` → string | §5 |
| `topcf(**opts)` → bytes | `topcf(opts?)` → Uint8Array | §6 |
| `tottf(**opts)` → bytes | `tottf(opts?)` → Uint8Array | §8 |
| `tosvgfont(**opts)` → str | `tosvgfont(opts?)` → string | port of v3-rc JS (§7.3) |
| `save(path, format=None, **opts)` → self | — | format from extension `.bdf .pcf .ttf .svg` |

Module-level equivalents (also exported):

| Python (module) | JS (export) |
|---|---|
| `bdfparser.pcf.read_pcf(data) -> Font` | `readPcf(data): Font` |
| `bdfparser.pcf.write_pcf(font, **opts) -> bytes` | `writePcf(font, opts?): Uint8Array` |
| `bdfparser.ttf.read_ttf(data, pixelsize=None) -> Font` | `readTtf(data, {pixelsize?}): Font` |
| `bdfparser.ttf.write_ttf(font, **opts) -> bytes` | `writeTtf(font, opts?): Uint8Array` |
| `bdfparser.outline.bitmap_contours(bindata, shape='square', dotsize=1.0, ppu=1, xoff=0, yoff=0)` | `bitmapContours(bindata, {shape, dotsize, ppu, xoff, yoff})` |
| `bdfparser.outline.rasterize(contours, ppu, ...)` | `rasterize(...)` |

`Font` methods `topcf/tottf/frompcf...` are thin wrappers (Python: lazy
import inside the method to avoid cycles).

### 2.8 Helpers

- `defaultglyphname(cp, charset_is_unicode=True)`: Unicode: `uniXXXX` (4 upper-hex digits) for cp ≤ 0xFFFF, else `uXXXXX`/`uXXXXXX` (5–6 digits); non-Unicode charset: `char{cp}` (decimal). Exported as module function (`bdfparser.glyph.defaultglyphname` / JS `defaultglyphname`).
- `swidth(dwx)` (Font method, also used by `newglyph`): `round(dwx * 72000 / (pointsize * xres))` using headers `pointsize`, `xres`; if either is 0/missing → `dwx * 1000 / max(fbbx,1)` rounded.

### 2.9 Warnings & errors

- Python: `class BDFParserWarning(UserWarning)` in `bdfparser/errors.py`, exported from the package; every `warnings.warn(..., BDFParserWarning, stacklevel=2)`; **no global `warnings.formatwarning` patching** (fixes #8, implements PR #9). `class BDFParseError(ValueError)`; raised on fatal parse errors (unexpected EOF inside headers, malformed numbers in required fields), message includes the 1-based line number.
- JS: `src/warn.ts`: `warn(msg)` calls the current handler (default `console.warn('[bdfparser] ' + msg)`); `setWarningHandler(fn | null)` (null ⇒ silent) exported. `class BDFParseError extends Error`.

---------------------------------------------------------------------------

## 3. BDF parsing rules

- Accept LF, CRLF, CR line endings; strip leading/trailing whitespace on
  every line; skip blank lines anywhere (except: inside BITMAP they are also
  skipped); tolerate tabs and multiple spaces between tokens.
- Keywords are matched exactly (case-sensitive) on the first token.
- Header: as v2. `COMMENT` value: everything after the keyword with
  surrounding whitespace removed and one pair of surrounding double quotes
  removed if present (v2 stripped all quote chars incl. `'` — v3 strips only a
  single matching pair of `"`). Unknown header keywords are ignored with a
  warning.
- `STARTPROPERTIES n` … `ENDPROPERTIES`: each line `KEY VALUE`:
  - VALUE starts with `"`: string; read up to the closing quote where `""`
    is an escaped quote; text after the closing quote ignored. Missing
    closing quote ⇒ take rest of line (warn).
  - VALUE matches `^[+-]?\d+$` ⇒ int.
  - otherwise ⇒ raw string (non-Adobe / XFree86 style, issue #4 class of
    files).
  - single token line ⇒ `None`. `COMMENT …` lines ⇒ `props['comment']`.
  - Property count mismatch with `n` ⇒ warning only.
- `CHARS n` mismatch ⇒ warning (as v2).
- Glyph: `STARTCHAR name` (name = rest of line, may contain spaces),
  `ENCODING a [b]` (a == -1 ⇒ unencoded, b = altcode), `SWIDTH`, `DWIDTH`,
  `SWIDTH1`, `DWIDTH1`, `VVECTOR`, `BBX`, `BITMAP`, hex rows, `ENDCHAR`.
  VVECTOR delimiter: whitespace and/or comma (JS v3-rc bug: it called
  `String.prototype.split` on the pattern string — fix). Hex rows are kept as
  in the file (stripped). Missing BBX ⇒ BDFParseError. Missing ENDFONT ⇒
  warning. Duplicate codepoint ⇒ later wins, warning.
- Glyph with fewer hex rows than `bbh`: pad with zero rows when drawing
  (warning once per glyph); more rows: ignore extra.
- Unexpected EOF before the end of headers ⇒ `BDFParseError`.

---------------------------------------------------------------------------

## 4. Charsets / encodings

`font.charset` = override from `encoding(charset=...)` if set, else derived
from props `CHARSET_REGISTRY` + `CHARSET_ENCODING`. Canonicalisation
`sanitize_charset(registry, encoding)` → canonical key (lower-case, `-`, `_`,
spaces and anything after a `.` in the registry removed; JS v3-rc
`sanitizeCharsetName` semantics). Mapping (canonical registry → codec):

| registry key (examples) | codec (Python / WHATWG `TextDecoder` label) | notes |
|---|---|---|
| missing, `iso10646`, `unicode`, `utf8`, `utf16*`, `utf32*`, `ucs2`, `ucs4` | Unicode identity | default when nothing known |
| `iso8859` (+ encoding N, default 1) | Python `iso8859_N` (N=1 → `latin-1`); JS `iso-8859-N`, but N=1 ⇒ identity for cp < 256 (WHATWG maps the label `iso-8859-1` to windows-1252, so it must not be used) | |
| `ascii`, `iso646` | ascii | |
| `koi8` (+ `r`/`u` from encoding) , `koi8r`, `koi8u` | `koi8_r` / `koi8-r` etc. | |
| `cp125X`, `windows125X`, `microsoft` + `cp125X` encoding | `cp125X` / `windows-125X` | |
| `gb2312` (GB2312.1980) | `gb2312` (EUC-CN bytes) / `gbk` | 94×94 set: **GL handling** below |
| `gbk`, `gb18030` | `gbk` / `gb18030` | |
| `jisx0208` | `euc_jp` / `euc-jp` | 94×94 set, GL handling |
| `jisx0201` | bytes `< 0x80` ASCII, `0xA1–0xDF` half-width katakana (`shift_jis` single byte) | |
| `ksc5601`, `ksx1001` | `euc_kr` / `euc-kr` | 94×94 set, GL handling |
| `big5` (incl. `big5.eten`) , `big5hkscs` | `big5` / `big5`; `big5hkscs` / `big5` | |
| `shiftjis`, `sjis` | `shift_jis` / `shift_jis` | |
| `eucjp`, `euckr`, `euccn` | `euc_jp`, `euc_kr`, `gb2312` | |
| anything else (e.g. `fontspecific`, `adobe-fontspecific`) | Unicode identity + one warning | |

**GL handling** (94×94 double-byte sets `gb2312`, `jisx0208`, `ksc5601`):
the font is in GL form if `CHARSET_ENCODING == "0"` OR the first glyph (in
ascending cp order) with `0x100 ≤ cp ≤ 0xFFFF` has both bytes in
`0x21–0x7E`. In GL form: `cp → bytes` adds `0x8080` for 2-byte codes before
decoding; `char → cp` subtracts it. (Fixes issue #4: GB2312.1980-0 font with
`ENCODING 12321` (0x3021) must map to 啊 U+554A.)

`cp → bytes`: big-endian minimal length (cp < 0x100 ⇒ 1 byte, < 0x10000 ⇒ 2,
else 4). Decoding must be strict (invalid ⇒ `None`). `char → cp` in JS
without an `iconv` option: build (lazily, cached per charset) a reverse table
by decoding the whole code space: all single bytes, plus for DBCS codecs
every lead byte 0x81–0xFE × trail 0x40–0xFE; 4-byte GB18030 codes not
supported without `iconv`. Python uses `codecs` directly.

---------------------------------------------------------------------------

## 5. BDF writer (`tobdf`) — exact format

Lines joined with `\n`, file ends with `ENDFONT\n`.

```
STARTFONT {fmtver(bdfversion)}          fmtver: integral → "{n}.0", else shortest repr ("2.1")
FONT {fontname}
SIZE {pointsize} {xres} {yres}
FONTBOUNDINGBOX {fbbx} {fbby} {fbbxoff} {fbbyoff}
[METRICSSET {n}]                        only if metricsset present and != 0
[CONTENTVERSION {n}]                    if present
[SWIDTH a b] [DWIDTH a b] [SWIDTH1 a b] [DWIDTH1 a b] [VVECTOR a b]   global, each if both values not None
COMMENT "{text}"                        one per headers['comment'] entry (text written verbatim between quotes)
STARTPROPERTIES {count}                 only if props has any key other than 'comment' or has comments; count excludes comments
COMMENT "{text}"                        props['comment'] entries
{NAME}                                  value None
{NAME} {int}                            value int
{NAME} "{str with " doubled}"           value str
ENDPROPERTIES
CHARS {len(glyphs) + len(unencoded)}
-- for each glyph in glyphs (dict order), then each unencoded entry:
STARTCHAR {glyphname}
ENCODING {cp}                           unencoded: "ENCODING -1" or "ENCODING -1 {altcode}"
[SWIDTH a b] [DWIDTH a b] [SWIDTH1 a b] [DWIDTH1 a b] [VVECTOR a b]   each if both not None
BBX {bbw} {bbh} {bbxoff} {bbyoff}
BITMAP
{hex rows verbatim}
ENDCHAR
ENDFONT
```

`NAME` = original spelling if known else upper-case key. Property order =
dict order (comment key skipped). This format reproduces FontForge-written
files (e.g. `HanWangYanKai-26.bdf`, `unifont-13.0.04.bdf`) byte-for-byte;
tests MUST assert that round trip.

---------------------------------------------------------------------------

## 6. PCF

Reader: full PCF support — any byte order, bit order, glyph pad (1/2/4/8),
scan unit (1/2/4), compressed/uncompressed metrics, optional tables
(INK_METRICS, SWIDTHS, GLYPH_NAMES, ACCELERATORS / BDF_ACCELERATORS). Missing
SWIDTHS ⇒ glyph swidth computed via `font.swidth`; missing GLYPH_NAMES ⇒
`defaultglyphname`. Gzip-compressed `.pcf.gz` input: Python: detect
`\x1f\x8b` and decompress via `gzip`; JS: detect and use
`DecompressionStream('gzip')` only in an async helper — sync `load_bytes`
raises a clear error for gzip in JS.

Reconstruction to BDF model:
- headers: `bdfversion 2.1`, `fontname` = `FONT` property (or ""), `pointsize` = `round(POINT_SIZE / 10)` (fallback `PIXEL_SIZE`), `xres`/`yres` from `RESOLUTION_X/Y` (fallback 75), FONTBOUNDINGBOX from accelerator maxbounds/minbounds: `fbbx = maxbounds.rightSideBearing - minbounds.leftSideBearing`, `fbby = maxbounds.ascent + maxbounds.descent`, `fbbxoff = minbounds.leftSideBearing`, `fbbyoff = -maxbounds.descent`, `metricsset 0`.
- props: all PCF properties in table order (including `FONT`, which is ALSO copied to `headers.fontname`, so PCF → model → PCF is byte-identical), string props → str, others → int. Original names kept.
- glyph: `BBX = (rsb - lsb, ascent + descent, lsb, -descent)`, `DWIDTH = (width, 0)`, `SWIDTH = (swidth, 0)`; bitmap rows converted to MSB-first byte rows of `ceil(bbw/8)` bytes (UPPER hex).
- encodings: `cp = row << 8 | col` (for single-row fonts `firstRow == lastRow == 0`, cp = col).

Writer (`write_pcf(font, byteorder='msb', bitorder='msb', glyphpad=4, scanunit=1)`):
**MUST be byte-identical to `bdftopcf` (libXfont2, as installed at
`/usr/bin/bdftopcf`) with default flags** for every BDF test font in the
repo (tests compare against `bdftopcf` output when the binary is available;
otherwise against committed golden `.pcf` files generated by it). The
implementer derives the exact table set, ordering, property additions,
accelerator computation, ink metrics, padding and compression rules from
`bdftopcf`'s output (and libXfont's `pcfwrite.c`/`bdfread.c` behavior) and
documents them in a comment block at the top of `pcf.py` / `pcf.ts`.
Options other than defaults must also produce valid PCF that round-trips
through the reader.

---------------------------------------------------------------------------

## 7. Outlines & SVG (`outline` module)

Units: a pixel is `ppu × ppu` font units. A glyph bitmap with `bbw × bbh`
and offsets `bbxoff, bbyoff` has pixel `(c, r)` (c from left, r from
**bottom**, both 0-based) covering `[(bbxoff+c)·ppu, (bbxoff+c+1)·ppu] ×
[(bbyoff+r)·ppu, (bbyoff+r+1)·ppu]` (y up). `bitmap_contours(bindata, shape,
dotsize, ppu, xoff, yoff)` uses `xoff, yoff` as the bitmap's bottom-left in
pixels. Output: list of contours; contour = list of `(x, y, oncurve)` with
integer `x, y`. "Ink" = any char other than `'0'`.

### 7.1 `shape='square'`, `dotsize == 1` — merged outline

All ink pixels of the bitmap are merged into the **minimal outline of their
union** (one path, holes included): this is the required "all square dots
simplified into one path".

1. Edge generation. Iterate rows `r = 0 … h-1` (bottom to top), columns
   `c = 0 … w-1`; for each ink pixel emit, in this order, the boundary edges
   whose neighbour is not ink (out-of-bitmap = not ink):
   - bottom: `(c+1, r) → (c, r)`
   - left:   `(c, r) → (c, r+1)`
   - top:    `(c, r+1) → (c+1, r+1)`
   - right:  `(c+1, r+1) → (c+1, r)`
   (Interior on the right ⇒ outer contours clockwise, holes counter-clockwise,
   as TrueType requires.)
2. Tracing. Repeatedly take the first unused edge in emission order and follow
   edges until returning to its start vertex. At a vertex with several unused
   outgoing edges choose, relative to the incoming direction: **right turn,
   then straight, then left turn** (diagonally touching pixels thus form
   separate contours).
3. Simplification: the vertex list is the sequence of edge start vertices;
   remove every vertex where incoming and outgoing directions are equal.
4. Rotation: rotate the list to start at the first vertex (in traced order)
   that is minimal by `(y, x)` lexicographically.
5. Scale: `x = (xoff + vx)·ppu`, `y = (yoff + vy)·ppu`; all on-curve.
Contours are returned in tracing order.

### 7.2 Separate dots

Iterate pixels in the same order as 7.1 (rows bottom→top, columns
left→right), one contour per ink pixel. Centre `cx = (xoff+c+0.5)·ppu`,
`cy = (yoff+r+0.5)·ppu`, half size `s = dotsize·ppu/2`.

- `shape='square'`, `dotsize != 1`: 4 on-curve points, clockwise starting at
  bottom-left: `(cx−s, cy−s), (cx−s, cy+s), (cx+s, cy+s), (cx+s, cy−s)`,
  each coordinate `round()`ed.
- `shape='circle'` (round dots, any dotsize): 8 **off-curve** points
  (TrueType implied on-curve midpoints), clockwise from the top. With
  `K = 1.082392200292394` (1/cos 22.5°), `D = 0.7071067811865476`,
  `R = s · K` (computed exactly as `(dotsize * ppu / 2) * K`),
  direction table `[(0,1), (D,D), (1,0), (D,−D), (0,−1), (−D,−D), (−1,0), (−D,D)]`:
  point i = `(round(cx + R·dx), round(cy + R·dy))`.

`dotsize` ∈ (0, 1.5]; else raise.

### 7.3 SVG

`Bitmap.tosvg(pixelsize=1, format='path', inverted=False, xoff=0, yoff=0, shape='square')`:
SVG coordinates are y-down; bitmap row 0 at top. Implementation: contours
from `bitmap_contours(bindata, shape, dotsize=1, ppu=1)` mapped to SVG units
`X = x·pixelsize + xoff`, `Y = (H − y)·pixelsize + yoff` (H = height) when
not `inverted`, else `Y = y·pixelsize + yoff` (y-up, for SVG fonts).

- `format='path'`: `<svg xmlns="http://www.w3.org/2000/svg" width="{W·ps}" height="{H·ps}"><path d="{d}" fill="#000000" /></svg>`
- `format='pathOnly'`: just `{d}`
- `format='rect'`: unchanged v3-rc behavior (greedy rectangles, `<rect …/>`), square only.
- Path data for square merged contours: per contour `M{X} {Y}` then for each
  next point `H{X}` if Y unchanged else `V{Y}`, then `Z`. Contours
  concatenated without separators. Circles (shape='circle'): per dot
  `M{cx−r} {cy}a{r} {r} 0 1 0 {2r} 0a{r} {r} 0 1 0 {−2r} 0Z` with
  `r = pixelsize/2` (numbers via `fmtnum`). Empty bitmap ⇒ `''` for
  `pathOnly`, and an `<svg>` with no `<path>` otherwise.

`Font.tosvgfont(...)`: port of the v3-rc JS implementation (same options,
same output), with fixes: metadata lines are emitted when their own property
exists (v3-rc wrongly tested `creator`), "Founfry" typo → "Foundry", glyph
paths come from the new `tosvg(..., 'pathOnly', True, ...)`.

### 7.4 Rasterizer (TTF → bitmap)

`rasterize(contours, ppu, xmin_px, ymin_px, w_px, h_px)` where contours have
quadratic TrueType semantics (on/off points, implied midpoints): flatten each
quadratic segment into 16 line segments; for each pixel centre
`((xmin_px + c + 0.5)·ppu, (ymin_px + r + 0.5)·ppu)` compute the **non-zero
winding number** (horizontal ray crossing test, half-open rule `y0 <= Y < y1`
for upward edges, `y1 <= Y < y0` for downward edges); ink iff winding ≠ 0.
Returns bindata (top row first). Exact inverse of 7.1/7.2 for every
`dotsize ≥ 0.5`: tests MUST assert `rasterize(bitmap_contours(b)) == b` for
random bitmaps (both shapes).

---------------------------------------------------------------------------

## 8. TTF writer (`write_ttf`) — exact format

Options: `shape='square'`, `dotsize=1.0`, `ppu=64` (font units per pixel,
even integer ≥ 2), `metadata=True`, `timestamp=0` (Unix seconds for
head.created/modified).

Derived values (pixels unless noted):
- `ascent` = int prop `FONT_ASCENT` else `fbby + fbbyoff`; `descent` = int prop `FONT_DESCENT` else `-fbbyoff`.
- `em` = int prop `PIXEL_SIZE` if > 0, else `ascent + descent` if > 0, else `fbby`. `upem = em·ppu` (must be 16…16384 else raise).
- `bold` = WEIGHT_NAME (str) lower-case contains `"bold"`; `italic` = SLANT in (`"I"`, `"O"`, case-insensitive).
- glyph to Unicode: `font.cp2char(cp)` → its code point if exactly one char, else unmapped.

Glyph order: gid 0 `.notdef`; then every glyph of `itercps(order=1)`; then
`unencoded` in stored order. `.notdef`: if prop `DEFAULT_CHAR` is an int and
that glyph exists, its outline and advance; else empty with advance
`fbbx·ppu`.

Per glyph: contours = `bitmap_contours(draw(mode=1).bindata, shape, dotsize, ppu, bbxoff, bbyoff)`
(empty bitmap ⇒ no contours). advance = `dwx0` (glyph) else headers `dwx0`
else `max(0, bbxoff + bbw)`, times `ppu`. Bounds from all points (incl.
off-curve).

Glyph names (post 2.0): `.notdef` for gid 0. Others: BDF `glyphname` if it
matches `^[A-Za-z_.][A-Za-z0-9_.]{0,62}$`, is not `.notdef` and not yet used;
else `defaultglyphname(unicode)` if mapped and unused; else `glyph{gid}`.

Tables (directory and data both in tag byte order; each table padded with
zero bytes to a multiple of 4; `length` in the directory is unpadded):
`BDFP` (only if `metadata`), `OS/2`, `cmap`, `glyf`, `head`, `hhea`, `hmtx`,
`loca`, `maxp`, `name`, `post`, `prep`.

- **prep** (7 bytes): `B8 01 FF 85 B0 04 8D` (PUSHW 0x01FF, SCANCTRL, PUSHB 4, SCANTYPE: dropout control on). Without any instructions FreeType applies its auto-hinter and distorts merged square glyphs at native size; with this table rendering is pixel-exact with hinting on or off. maxp `maxStackElements` = 1 (because of prep).

Offset table: `0x00010000`, numTables, `searchRange = 16·2^⌊log2 n⌋`,
`entrySelector = ⌊log2 n⌋`, `rangeShift = 16n − searchRange`. Checksums: sum
of big-endian uint32 over the zero-padded table, mod 2³². `head.checkSumAdjustment
= (0xB1B0AFBA − checksum(whole file with adjustment 0)) mod 2³²`.

- **head** (54 bytes): version 0x00010000, fontRevision 0x00010000, checkSumAdjustment, magic 0x5F0F3CF5, flags 0x000B, unitsPerEm, created = modified = `timestamp + 2082844800` (int64), xMin yMin xMax yMax = union of glyph bounds (all 0 if no contours), macStyle (bit0 bold, bit1 italic), lowestRecPPEM = em, fontDirectionHint 2, indexToLocFormat 1, glyphDataFormat 0.
- **hhea** (36 bytes): 0x00010000, ascender `ascent·ppu`, descender `−descent·ppu`, lineGap 0, advanceWidthMax, minLeftSideBearing, minRightSideBearing (`advance − xMax`), xMaxExtent (`xMax`) — the three min/max over glyphs **with contours** only (0 if none), caretSlopeRise 1, caretSlopeRun 0, caretOffset 0, 4× reserved 0, metricDataFormat 0, numberOfHMetrics = numGlyphs.
- **maxp** v1.0 (32 bytes): 0x00010000, numGlyphs, maxPoints, maxContours, then `0,0,2,0,0,0,0,1,0,0,0` (maxCompositePoints, maxCompositeContours, maxZones=2, maxTwilightPoints, maxStorage, maxFunctionDefs, maxInstructionDefs, maxStackElements=1, maxSizeOfInstructions, maxComponentElements, maxComponentDepth).
- **OS/2** v4 (96 bytes): xAvgCharWidth = `round(sum(adv)/count)` over glyphs with adv > 0 (0 if none); usWeightClass 700/400; usWidthClass 5; fsType 0; ySubscriptXSize = ySubscriptYSize = ySuperscriptXSize = ySuperscriptYSize = `upem·65 // 100`; ySubscriptXOffset 0; ySubscriptYOffset `upem·14 // 100`; ySuperscriptXOffset 0; ySuperscriptYOffset `upem·48 // 100`; yStrikeoutSize `ppu`; yStrikeoutPosition = `xh·ppu // 2` if `xh` (int prop X_HEIGHT > 0) else `ascent·ppu // 3`; sFamilyClass 0; panose 10×0; ulUnicodeRange1–4 0; achVendID `"BDFP"`; fsSelection = (italic ? 0x01 : 0) | (bold ? 0x20 : 0) | (neither ? 0x40 : 0) | 0x80; usFirstCharIndex = min(mapped unicode, 0xFFFF) (0 if none); usLastCharIndex = min(max mapped, 0xFFFF); sTypoAscender = hhea.ascender; sTypoDescender = hhea.descender; sTypoLineGap 0; usWinAscent = max(hhea.ascender, head.yMax); usWinDescent = max(−hhea.descender, −head.yMin, 0); ulCodePageRange1 1; ulCodePageRange2 0; sxHeight = `xh·ppu` (0 if none); sCapHeight = int prop CAP_HEIGHT·ppu else `ascent·ppu`; usDefaultChar 0; usBreakChar 32; usMaxContext 0.
- **cmap**: version 0, 2 encoding records `(3,1)` → format 4 subtable, `(3,10)` → format 12 subtable; subtables stored in that order right after the records. Mapping: unicode → gid, first gid wins on duplicates. Format 4: BMP codes only, segments = maximal runs where both code and gid increase by 1; plus final segment 0xFFFF→0xFFFF with idDelta 1; idDelta = `(gid − start) mod 65536`; idRangeOffset all 0; language 0; standard searchRange/entrySelector/rangeShift on segCount (`searchRange = 2·2^⌊log2 segCount⌋`). Format 12: all codes, groups = same maximal runs; reserved 0, language 0.
- **glyf**: simple glyphs only. Glyph with no contours ⇒ zero length. Otherwise: numberOfContours, xMin yMin xMax yMax, endPtsOfContours, instructionLength 0, flags (one byte per point, **no REPEAT**): bit0 on-curve; x: `dx == 0` ⇒ bit4 set; `0 < |dx| ≤ 255` ⇒ bit1 set (+ bit4 if dx > 0), 1 byte; else 2-byte int16; y likewise with bits 2 and 5. Each glyph padded to 4 bytes with zeros.
- **loca**: long (uint32) offsets, numGlyphs+1 entries.
- **hmtx**: per glyph advanceWidth (uint16), lsb = xMin (0 for empty).
- **name**: format 0, records platform 3, encoding 1, language 0x0409, strings UTF-16BE, records sorted by nameID, strings stored in record order (no dedupe). IDs: 0 COPYRIGHT (if prop present), 1 family = FAMILY_NAME prop else `fontname` else `"Untitled"`, 2 subfamily `Regular | Bold | Italic | Bold Italic`, 3 = PS name, 4 full = family if subfamily is Regular else `family + " " + subfamily`, 5 `"Version " + FONT_VERSION` (if str prop) else `"Version 1.000"`, 6 PS name = full name with every char not in `[A-Za-z0-9-]` removed, truncated to 63, `"Untitled"` if empty, 10 NOTICE (if prop present). Prop values converted with `str()` if int.
- **post** v2.0: 0x00020000, italicAngle 0, underlinePosition `−UNDERLINE_POSITION·ppu` (int prop) else `−ppu`, underlineThickness `UNDERLINE_THICKNESS·ppu` else `ppu`, isFixedPitch 1 if SPACING ∈ {M, C} (case-insens.) else 0, 4×uint32 0, numGlyphs, glyphNameIndex (`.notdef` → 0, others → 258 + k in gid order), then Pascal strings of the custom names in gid order.
- **BDFP** (private, optional): UTF-8 JSON, no whitespace, `{"version":1,"ppu":P,"shape":"square|circle","dotsize":D,"headers":{…},"props":{…},"propnames":{…},"glyphs":[[gid,cp,name,bbw,bbh,bbxoff,bbyoff,swx0,swy0,dwx0,dwy0,swx1,swy1,dwx1,dwy1,vvectorx,vvectory,altcode],…]}` — `headers` with `bdfversion` serialized as the `fmtver` **string**; `props` excluding `comment`; `propnames` lower → original; `glyphs` lists every glyph in **storage order** (`font.glyphs` order, then `unencoded`) with its gid, original BDF codepoint (−1 for unencoded), original BDF glyph name, original BBX and all optional metrics (null for None) and altcode (null if none) — so the reader restores the exact untrimmed BBX, metrics and order (it rasterizes into the stored box without trimming); readers also accept the legacy 3-element form; `D` via JSON number (Python `json.dumps` of float `1.0` is `1.0`, JS gives `1` ⇒ serialize dotsize with `fmtnum`, i.e. `1`). Key order exactly as listed; Python `json.dumps(..., ensure_ascii=False, separators=(',', ':'))`, JS `JSON.stringify`.

### 8.1 TTF reader (`read_ttf`)

Reads TrueType-outline fonts (`0x00010000` / `true`): tables head, hhea,
maxp, hmtx, loca, glyf (simple + composite, with offsets and 2×2 scale),
cmap (formats 0, 4, 6, 12; prefer (3,10), then (0,4)/(0,6), then (3,1), then
(0,3), then others), post (v1 standard Mac names, v2 custom), name, OS/2,
BDFP. If `BDFP` exists: `ppu` from it, headers/props/propnames restored,
glyph codepoints & names restored from its glyph list. Otherwise:
`pixelsize` argument required (raise if missing) and `ppu = upem /
pixelsize` (float); codepoints from cmap (unmapped glyphs → unencoded, gid 0
skipped), names from post or `defaultglyphname`; headers: `fontname` = name
ID 6 or 4, `pointsize = pixelsize`, `xres = yres = 75`, props:
`FAMILY_NAME` (ID 1), `COPYRIGHT` (ID 0, if any), `PIXEL_SIZE`,
`FONT_ASCENT = round(hhea.ascender/ppu)`, `FONT_DESCENT = round(−hhea.descender/ppu)`,
`CHARSET_REGISTRY "ISO10646"`, `CHARSET_ENCODING "1"`; FONTBOUNDINGBOX via
`updatebbox()` afterwards (if no ink: `(em, ascent+descent, 0, −descent)`).
Glyph pixel box: `xmin_px = floor(xMin/ppu)`, `ymin_px = floor(yMin/ppu)`,
`w = ceil(xMax/ppu) − xmin_px`, `h = ceil(yMax/ppu) − ymin_px` (use exact
integer arithmetic when ppu is an int), rasterize (§7.4), then `setbitmap(...,
mode=-1, bb=(w, h, xmin_px, ymin_px), trim=True)`; `DWIDTH = round(advance/ppu)`,
`SWIDTH` via `font.swidth`.

**Round-trip guarantee** (tested): for every test font F and both shapes,
`read_ttf(write_ttf(F))` has identical `glyphs` (all 17 slots), `unencoded`,
`headers`, `props`.

---------------------------------------------------------------------------

## 9. CLI

Python console script `bdfparser` (`bdfparser.cli:main`), JS bin
`bdfparser` (`src/cli.ts`, Node only):

```
bdfparser convert INPUT OUTPUT [--shape square|circle] [--dotsize F] [--ppu N]
                               [--pixelsize N] [--charset NAME]
bdfparser info INPUT            # prints fontname, glyph count, bbox, charset, props
bdfparser preview INPUT TEXT    # prints TEXT rendered with # and .
```

Formats by extension (`.bdf`, `.pcf`, `.pcf.gz` input only, `.ttf`, `.svg`
output only). `--charset` converts glyph codepoints via `charsetconvert`
before writing.

---------------------------------------------------------------------------

## 10. Tests (both repos)

- Keep every v2 test passing except where this spec intentionally changes
  behavior (props ints, `COMMENT` quote stripping) — update those
  assertions and mention them in `CHANGELOG.md`.
- Unit-test every public method, including error paths and edge cases
  (empty bitmaps, zero-size glyphs, negative offsets, unencoded glyphs,
  non-Unicode charsets, CRLF input, malformed files).
- Round trips: BDF→BDF byte-identical for FontForge-style fonts; BDF→PCF
  equals `bdftopcf`; PCF→BDF→PCF stable; BDF→TTF→BDF identical (both shapes,
  several dotsizes/ppu); bitmap_contours/rasterize property tests with
  seeded random bitmaps (≥ 500 cases).
- External validation (Python): TTF parsed by `fontTools` (`TTFont`, all
  tables decompiled, `ttx` dump without error), glyph outlines checked with
  fontTools pens; FreeType (via Pillow `ImageFont.truetype(..., size=em)` +
  `fontmode="1"`) renders square-dot glyphs identical to the BDF bitmap; PCF
  validated by Pillow `PcfFontFile`. (JS): TTF parsed by `opentype.js`.
- Cross-language golden files (generated by the Python implementation) in
  `bdfparser-js/test/fixtures/golden/` — JS tests assert byte equality.
