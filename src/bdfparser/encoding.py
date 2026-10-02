"""
Charset (encoding) support: maps BDF `CHARSET_REGISTRY` / `CHARSET_ENCODING`
to a codec, and converts between glyph codepoints and characters.

There is one canonical charset table (`charset_table()`); every charset name is
canonicalised to one of its keys (`canonical_charset`, `sanitize_charset`), and
names that are not in the table are "unknown" (Unicode identity mapping, with
one warning). Python's `codecs` are the reference for every non-Unicode key
(bdfparser-js ships tables generated from them, see `charset_map`).

Conversions are strict (SPEC-v3 §4, §11.1):

- `cp2char(cp)` returns a single character (one Unicode code point) or `None`;
  a code is 1 byte (`cp < 0x100`), 2 bytes (`cp < 0x10000`) or 4 bytes
  (gb18030 only), big-endian; the bytes must decode as exactly one character;
- `char2cp(char)` returns a code only if its byte length is allowed for the
  charset (1 for single-byte charsets, 1-2 for double-byte charsets, 1, 2 or
  4 for gb18030) and `cp2char(code) == char` (round trip), else `None`.

https://font.tomchen.org/bdfparser_py/font#encoding
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

__all__ = [
    'CharsetCodec',
    'sanitize_charset',
    'canonical_charset',
    'charset_codec',
    'charset_props',
    'charset_table',
    'charset_map',
    'codec_name',
    'gb18030_ranges',
    'is_unicode_charset',
    'char2cp',
    'cp2char',
    'UNICODE_PREFIXES',
]

# ---------------------------------------------------------------------------
# the canonical charset table

_UNICODE_KEYS = (
    'iso10646',
    'unicode',
    'utf8',
    'utf7',
    'ucs2',
    'ucs4',
    'ucs',
    'utf16',
    'utf32',
)
#: any canonical key starting with one of these is a Unicode charset too
UNICODE_PREFIXES = ('utf16', 'utf32', 'ucs2', 'ucs4')

# canonical key -> (Python codec name, kind); kind: 'sbcs' | 'dbcs' | 'gb18030'
_TABLE: dict[str, tuple[str, str]] = {
    'ascii': ('ascii', 'sbcs'),
    'iso646': ('ascii', 'sbcs'),
    'iso88591': ('latin_1', 'sbcs'),
    **{
        f'iso8859{n}': (f'iso8859_{n}', 'sbcs')
        for n in (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16)
    },
    'koi8r': ('koi8_r', 'sbcs'),
    'koi8u': ('koi8_u', 'sbcs'),
    **{f'cp125{n}': (f'cp125{n}', 'sbcs') for n in range(9)},
    'cp437': ('cp437', 'sbcs'),
    'cp850': ('cp850', 'sbcs'),
    'cp852': ('cp852', 'sbcs'),
    'cp866': ('cp866', 'sbcs'),
    'cp874': ('cp874', 'sbcs'),
    'tis620': ('tis_620', 'sbcs'),
    'macroman': ('mac_roman', 'sbcs'),
    # bytes < 0x80 ASCII, 0xA1-0xDF half-width katakana (shift_jis single bytes)
    'jisx0201': ('shift_jis', 'sbcs'),
    'gb2312': ('gb2312', 'dbcs'),
    'euccn': ('gb2312', 'dbcs'),
    'iso2022cn': ('gb2312', 'dbcs'),
    'gbk': ('gbk', 'dbcs'),
    'cp936': ('cp936', 'dbcs'),
    'gb18030': ('gb18030', 'gb18030'),
    'jisx0208': ('euc_jp', 'dbcs'),
    'eucjp': ('euc_jp', 'dbcs'),
    'shiftjis': ('shift_jis', 'dbcs'),
    'cp932': ('cp932', 'dbcs'),
    'ksc5601': ('euc_kr', 'dbcs'),
    'euckr': ('euc_kr', 'dbcs'),
    'cp949': ('cp949', 'dbcs'),
    'johab': ('johab', 'dbcs'),
    'big5': ('big5', 'dbcs'),
    'big5hkscs': ('big5hkscs', 'dbcs'),
    'cp950': ('cp950', 'dbcs'),
}

# alias (already lower-case, `-`/`_`/spaces removed) -> canonical key
_ALIASES = {'sjis': 'shiftjis', 'ksx1001': 'ksc5601'}

# 94x94 double-byte sets that may be stored in GL form (both bytes 0x21-0x7E)
_GL_CAPABLE = frozenset({'gb2312', 'jisx0208', 'ksc5601'})
# always GL form
_FORCE_GL = frozenset({'iso2022cn'})

# allowed code byte lengths per kind
_LENGTHS = {'sbcs': (1,), 'dbcs': (1, 2), 'gb18030': (1, 2, 4)}

# canonical key -> (CHARSET_REGISTRY, CHARSET_ENCODING) written by `charsetconvert`
# (keys not listed: see `charset_props`)
_PROPS = {
    'ascii': ('ISO646.1991', 'IRV'),
    'iso646': ('ISO646.1991', 'IRV'),
    'koi8r': ('KOI8', 'R'),
    'koi8u': ('KOI8', 'U'),
    'gb2312': ('GB2312.1980', '0'),
    'iso2022cn': ('GB2312.1980', '0'),
    'jisx0208': ('JISX0208.1983', '0'),
    'jisx0201': ('JISX0201.1976', '0'),
    'ksc5601': ('KSC5601.1987', '0'),
    'cp437': ('IBM', 'CP437'),
    'cp850': ('IBM', 'CP850'),
    'cp852': ('IBM', 'CP852'),
    'cp866': ('IBM', 'CP866'),
}

# ASCII whitespace only (SPEC-v3 §11.4)
_WS = ' \t\n\v\f\r'
_RE_ISO8859 = re.compile(r'iso8859([0-9]+)')
_RE_CP = re.compile(r'(?:cp|windows|win|ms|ibm)?([0-9]+)')
_RE_DIGITS = re.compile(r'[0-9]+')
_RE_STRIP = re.compile(r'[-_ \t\n\v\f\r]')
_CP_REGISTRIES = ('microsoft', 'windows', 'ms', 'ibm')


def _clean(name: object) -> str:
    s = str(name).strip(_WS)
    if s.startswith('-'):
        s = s[1:]
    dot = s.find('.')
    if dot != -1:
        s = s[:dot]
    return _RE_STRIP.sub('', s).lower()


def _cp_key(s: str) -> str | None:
    """`cp1252`, `windows1252`, `win1252`, `ms932`, `ibm437` ... -> `cpN` if in the table."""
    m = _RE_CP.fullmatch(s)
    if m is None:
        return None
    key = f'cp{int(m.group(1))}'
    return key if key in _TABLE else None


def sanitize_charset(registry: object = None, encoding: object = None) -> str:
    """
    Canonicalise a charset from a `CHARSET_REGISTRY` (and optional
    `CHARSET_ENCODING`) value: lower-case; `-`, `_`, spaces and anything after
    a `.` in the registry removed; registry-specific encodings folded in
    (`ISO8859` + `5` -> `iso88595`, `KOI8` + `R` -> `koi8r`,
    `MICROSOFT` + `CP1252` -> `cp1252`, `IBM` + `CP437` -> `cp437`); aliases
    resolved (`sjis` -> `shiftjis`, `ksx1001` -> `ksc5601`,
    `windows1252` -> `cp1252`). A missing registry gives `iso10646`.

    https://font.tomchen.org/bdfparser_py/font#charset
    """

    reg = '' if registry is None else _clean(registry)
    enc = '' if encoding is None else _RE_STRIP.sub('', str(encoding)).lower()
    if reg == '':
        return 'iso10646'
    if reg == 'iso8859':
        n = int(enc) if _RE_DIGITS.fullmatch(enc) and int(enc) > 0 else 1
        return f'iso8859{n}'
    if reg == 'koi8':
        if enc in ('', 'r'):
            return 'koi8r'
        return 'koi8u' if enc == 'u' else f'koi8{enc}'
    if reg in _CP_REGISTRIES:
        return _cp_key(enc) or reg
    if not _RE_DIGITS.fullmatch(reg):
        key = _cp_key(reg)
        if key is not None:
            return key
    return _ALIASES.get(reg, reg)


def _is_unicode_key(key: str) -> bool:
    return key == '' or key in _UNICODE_KEYS or key.startswith(UNICODE_PREFIXES)


def is_unicode_charset(key: str) -> bool:
    """Whether the canonical charset key is a Unicode charset (identity mapping)."""
    return _is_unicode_key(key)


def _is_known(key: str) -> bool:
    return _is_unicode_key(key) or key in _TABLE


def codec_name(key: str) -> str | None:
    """
    Python codec name of a canonical charset key (e.g. `'gb2312'` ->
    `'gb2312'`, `'iso88595'` -> `'iso8859_5'`); `None` for Unicode and unknown
    keys.
    """

    entry = _TABLE.get(_ALIASES.get(key, key))
    return entry[0] if entry else None


def canonical_charset(name: str) -> str:
    """
    Canonicalise a user-supplied charset name such as `'GB2312'`, `'Shift-JIS'`,
    `'ISO-8859-5'`, `'ISO8859-01'`, `'ISO10646-1'`, `'microsoft-cp1252'`,
    `'big5-0'`: `sanitize_charset(name)` if that is a known key, else
    `sanitize_charset(registry, encoding)` with the name split at its last
    `-` if that is known, else `sanitize_charset(name)` (unknown).
    """

    key = sanitize_charset(name)
    if _is_known(key):
        return key
    s = str(name).strip(_WS)
    if '-' in s[1:]:
        reg, enc = s.rsplit('-', 1)
        key2 = sanitize_charset(reg, enc)
        if _is_known(key2):
            return key2
    return key


def charset_props(key: str) -> tuple[str, str]:
    """
    `(CHARSET_REGISTRY, CHARSET_ENCODING)` property values for a canonical
    charset key (used by `Font.charsetconvert`).
    """

    key = _ALIASES.get(key, key)
    if _is_unicode_key(key):
        return ('ISO10646', '1')
    m = _RE_ISO8859.fullmatch(key)
    if m:
        return ('ISO8859', str(int(m.group(1))))
    if key in _PROPS:
        return _PROPS[key]
    if re.fullmatch(r'cp[0-9]+', key):
        return ('MICROSOFT', key.upper())
    return (key.upper(), '0')


def charset_table() -> dict[str, dict[str, Any]]:
    """
    The canonical charset table: `{key: info}` for every known canonical key
    (the Unicode keys included; any key starting with one of
    `UNICODE_PREFIXES` is Unicode as well). `info` is a new dict with:

    - `codec`: Python codec name (`None` for Unicode);
    - `kind`: `'unicode'`, `'sbcs'` (codes are 1 byte), `'dbcs'` (1 or 2
      bytes) or `'gb18030'` (1, 2 or 4 bytes);
    - `gl`: GL-capable 94x94 set (GL form detected per font, SPEC-v3 §4);
    - `forcegl`: always in GL form;
    - `props`: `(CHARSET_REGISTRY, CHARSET_ENCODING)` written by
      `charsetconvert`;
    - `aliases`: other spellings `sanitize_charset` maps to this key (besides
      the registry/encoding folding rules).

    Used by bdfparser-js's table generator (`tools/gen_charsets.py`) together
    with `charset_map` and `gb18030_ranges`.
    """

    out: dict[str, dict[str, Any]] = {}
    for key in _UNICODE_KEYS:
        out[key] = {
            'codec': None,
            'kind': 'unicode',
            'gl': False,
            'forcegl': False,
            'props': charset_props(key),
            'aliases': [],
        }
    for key, (codec, kind) in _TABLE.items():
        out[key] = {
            'codec': codec,
            'kind': kind,
            'gl': key in _GL_CAPABLE,
            'forcegl': key in _FORCE_GL,
            'props': charset_props(key),
            'aliases': sorted(a for a, k in _ALIASES.items() if k == key),
        }
    return out


def charset_map(key: str) -> dict[int, str]:
    """
    Every valid 1- and 2-byte code of a non-Unicode charset (in non-GL form) ->
    its character, exactly as `charset_codec(key, gl=False).cp2char` converts
    it (4-byte GB18030 codes: see `gb18030_ranges`). The reverse direction
    is `charset_codec(key).char2cp(char)` for each character of the map
    (when several codes decode to the same character it picks the one the
    Python encoder produces; other characters are never mapped). The GL form
    of a GL-capable charset is the 2-byte codes with both bytes in
    0xA1-0xFE, minus 0x8080.
    """

    codec = charset_codec(_ALIASES.get(key, key), False)
    if codec.codec is None:
        raise ValueError(f'{key!r} is not a known non-Unicode charset')
    top = 0x100 if codec.kind == 'sbcs' else 0x10000
    out = {}
    for cp in range(top):
        ch = codec.cp2char(cp)
        if ch is not None:
            out[cp] = ch
    return out


def _gb18030_index(b: bytes) -> int:
    return (((b[0] - 0x81) * 10 + (b[1] - 0x30)) * 126 + (b[2] - 0x81)) * 10 + (b[3] - 0x30)


def gb18030_ranges() -> list[tuple[int, int, int]]:
    """
    The 4-byte GB18030 codes of Python's `gb18030` codec as runs
    `(index, codepoint, length)`: the `length` codes starting at linear index
    `index` map to the code points starting at `codepoint`, where for a code
    with bytes `b0 b1 b2 b3`:
    `index = (((b0 - 0x81) * 10 + (b1 - 0x30)) * 126 + (b2 - 0x81)) * 10 + (b3 - 0x30)`.
    """

    runs: list[list[int]] = []
    for c in range(0x80, 0x10000):
        if 0xD800 <= c <= 0xDFFF:
            continue
        b = chr(c).encode('gb18030')
        if len(b) != 4:
            continue
        idx = _gb18030_index(b)
        if runs and runs[-1][0] + runs[-1][2] == idx and runs[-1][1] + runs[-1][2] == c:
            runs[-1][2] += 1
        else:
            runs.append([idx, c, 1])
    # supplementary planes: one linear run (checked at both ends)
    first = _gb18030_index(chr(0x10000).encode('gb18030'))
    last = _gb18030_index(chr(0x10FFFF).encode('gb18030'))
    assert last - first == 0x10FFFF - 0x10000
    runs.append([first, 0x10000, 0x100000])
    return [(a, b, n) for a, b, n in runs]


# ---------------------------------------------------------------------------
# codec objects


@dataclass(frozen=True)
class CharsetCodec:
    """
    Converter between glyph codepoints and characters for one charset.

    `name` is the canonical charset key, `codec` the Python codec (`None` =
    Unicode identity), `gl` whether 2-byte codes are stored in GL form (both
    bytes 0x21-0x7E, i.e. EUC code minus 0x8080), `known` whether the charset was
    recognised (unknown charsets fall back to Unicode identity).
    """

    name: str
    codec: str | None = None
    gl: bool = False
    known: bool = True

    @property
    def kind(self) -> str:
        """`'unicode'`, `'sbcs'`, `'dbcs'` or `'gb18030'`."""
        if self.codec is None:
            return 'unicode'
        entry = _TABLE.get(self.name)
        return entry[1] if entry else 'dbcs'

    def char2cp(self, char: str) -> int | None:
        """Codepoint of a single character, `None` if not representable."""
        if len(char) != 1:
            raise TypeError(f'char2cp() expected a single character, got {char!r}')
        if self.codec is None:
            return ord(char)
        if self.name == 'jisx0201':
            o = ord(char)
            if o < 0x80:
                return o
        try:
            b = char.encode(self.codec)
        except UnicodeEncodeError:
            return None
        if len(b) not in _LENGTHS.get(self.kind, (1, 2)):
            return None
        cp = int.from_bytes(b, 'big')
        if self.gl and len(b) == 2:
            cp -= 0x8080
        # the code must convert back to the same character (e.g. Shift_JIS
        # encodes '¥' as 0x5C, which decodes to '\\')
        return cp if self.cp2char(cp) == char else None

    def cp2char(self, cp: int) -> str | None:
        """Character of a codepoint, `None` if not representable."""
        if cp is None or cp < 0:
            return None
        if self.codec is None:
            return chr(cp) if cp <= 0x10FFFF else None
        if self.name == 'jisx0201':
            if cp < 0x80:
                return chr(cp)
            if 0xA1 <= cp <= 0xDF:
                return bytes([cp]).decode('shift_jis')
            return None
        kind = self.kind
        if cp < 0x100:
            b = bytes([cp])
        elif cp < 0x10000:
            if kind == 'sbcs':
                return None
            if self.gl:
                if not (0x21 <= cp >> 8 <= 0x7E and 0x21 <= cp & 0xFF <= 0x7E):
                    return None
                cp += 0x8080
            b = cp.to_bytes(2, 'big')
        elif kind == 'gb18030' and cp <= 0xFFFFFFFF:
            b = cp.to_bytes(4, 'big')
        else:
            return None
        try:
            s = b.decode(self.codec, 'strict')
        except UnicodeDecodeError:
            return None
        # the whole byte sequence must decode as one single character (e.g.
        # 0x0041 0x42 is two characters; Big5-HKSCS 0x8862 is Ê + U+0304)
        return s if len(s) == 1 else None


def charset_codec(key: str, gl: bool | None = None) -> CharsetCodec:
    """
    Build a `CharsetCodec` for a canonical charset key. `gl=None` means: GL form
    only for charsets that are always GL (`iso2022cn`); GL detection for a font is
    done by `Font`. GL is ignored for charsets that are not 94x94 sets.
    """

    key = _ALIASES.get(key, key)
    if gl is None:
        gl = key in _FORCE_GL
    gl = bool(gl) and (key in _GL_CAPABLE or key in _FORCE_GL)
    if _is_unicode_key(key):
        return CharsetCodec(key)
    entry = _TABLE.get(key)
    if entry is None:
        return CharsetCodec(key, known=False)
    return CharsetCodec(key, entry[0], gl)


def _gl_capable(key: str) -> bool:
    return key in _GL_CAPABLE


def _force_gl(key: str) -> bool:
    return key in _FORCE_GL


_warned_unknown: set[str] = set()


def _module_codec(charset: str, gl: bool | None) -> CharsetCodec:
    codec = charset_codec(canonical_charset(charset), gl)
    if not codec.known and codec.name not in _warned_unknown:
        from .errors import _warn

        _warned_unknown.add(codec.name)
        _warn(f"Unknown charset '{codec.name}', characters are mapped to codepoints as Unicode")
    return codec


def char2cp(char: str, charset: str = 'iso10646', gl: bool | None = None) -> int | None:
    """
    Convert a character to a codepoint in the given charset (any spelling, e.g.
    `'GB2312'`, `'ISO-8859-5'`). `None` if not representable. An unknown
    charset maps as Unicode (one warning per charset name).
    """

    return _module_codec(charset, gl).char2cp(char)


def cp2char(cp: int, charset: str = 'iso10646', gl: bool | None = None) -> str | None:
    """
    Convert a codepoint in the given charset to a character. `None` if not
    representable. An unknown charset maps as Unicode (one warning per
    charset name).
    """

    return _module_codec(charset, gl).cp2char(cp)
