"""
Charset (encoding) support: maps BDF `CHARSET_REGISTRY` / `CHARSET_ENCODING`
to a codec, and converts between glyph codepoints and characters.

https://font.tomchen.org/bdfparser_py/font#encoding
"""

from __future__ import annotations

import codecs
import re
from dataclasses import dataclass

__all__ = [
    'CharsetCodec',
    'sanitize_charset',
    'canonical_charset',
    'charset_codec',
    'charset_props',
    'is_unicode_charset',
    'char2cp',
    'cp2char',
]

_UNICODE_KEYS = frozenset(
    {'', 'iso10646', 'unicode', 'utf8', 'utf7', 'ucs2', 'ucs4', 'ucs', 'utf16', 'utf32'}
)
_UNICODE_PREFIXES = ('utf16', 'utf32', 'ucs2', 'ucs4')

# canonical key -> Python codec name
_CODECS = {
    'ascii': 'ascii',
    'iso646': 'ascii',
    'koi8r': 'koi8_r',
    'koi8u': 'koi8_u',
    'gb2312': 'gb2312',
    'euccn': 'gb2312',
    'iso2022cn': 'gb2312',
    'gbk': 'gbk',
    'gb18030': 'gb18030',
    'jisx0208': 'euc_jp',
    'eucjp': 'euc_jp',
    'ksc5601': 'euc_kr',
    'ksx1001': 'euc_kr',
    'euckr': 'euc_kr',
    'big5': 'big5',
    'big5hkscs': 'big5hkscs',
    'shiftjis': 'shift_jis',
    'sjis': 'shift_jis',
    'tis620': 'tis_620',
    'macroman': 'mac_roman',
}

# 94x94 double-byte sets that may be stored in GL form (both bytes 0x21-0x7E)
_GL_CAPABLE = frozenset({'gb2312', 'jisx0208', 'ksc5601', 'ksx1001'})
# always GL form
_FORCE_GL = frozenset({'iso2022cn'})

# canonical key -> (CHARSET_REGISTRY, CHARSET_ENCODING) written by `charsetconvert`
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
    'ksx1001': ('KSC5601.1987', '0'),
}

_RE_ISO8859 = re.compile(r'iso8859(\d+)')
_RE_CP = re.compile(r'(?:cp|windows|win|ms)?(125\d)')
_RE_STRIP = re.compile(r'[-_\s]')


def _clean(name: object) -> str:
    s = str(name).strip()
    if s.startswith('-'):
        s = s[1:]
    dot = s.find('.')
    if dot != -1:
        s = s[:dot]
    return _RE_STRIP.sub('', s).lower()


def sanitize_charset(registry: object = None, encoding: object = None) -> str:
    """
    Canonicalise a charset from a `CHARSET_REGISTRY` (and optional
    `CHARSET_ENCODING`) value: lower-case; `-`, `_`, spaces and anything after
    a `.` in the registry removed; registry-specific encodings folded in
    (`ISO8859` + `5` -> `iso88595`, `KOI8` + `R` -> `koi8r`,
    `MICROSOFT` + `CP1252` -> `cp1252`). A missing registry gives `iso10646`.

    https://font.tomchen.org/bdfparser_py/font#charset
    """

    reg = '' if registry is None else _clean(registry)
    enc = '' if encoding is None else _RE_STRIP.sub('', str(encoding)).lower()
    if reg == '':
        return 'iso10646'
    if reg == 'iso8859':
        n = int(enc) if enc.isdigit() and int(enc) > 0 else 1
        return f'iso8859{n}'
    if reg == 'koi8':
        return 'koi8u' if enc == 'u' else 'koi8r'
    if reg in ('microsoft', 'windows', 'ms'):
        m = _RE_CP.fullmatch(enc)
        return f'cp{m.group(1)}' if m else reg
    m = _RE_CP.fullmatch(reg)
    if m and not reg.isdigit():
        return f'cp{m.group(1)}'
    if reg == 'sjis':
        return 'shiftjis'
    if reg == 'ksx1001':
        return 'ksc5601'
    return reg


def _is_unicode_key(key: str) -> bool:
    return key in _UNICODE_KEYS or key.startswith(_UNICODE_PREFIXES)


def _codec_name(key: str) -> str | None:
    """Python codec name for a canonical key, `None` if unknown / Unicode."""
    if key in _CODECS:
        return _CODECS[key]
    m = _RE_ISO8859.fullmatch(key)
    if m:
        n = int(m.group(1))
        name = 'latin-1' if n == 1 else f'iso8859_{n}'
    elif re.fullmatch(r'cp125\d', key):
        name = key
    else:
        return None
    try:
        codecs.lookup(name)
    except LookupError:
        return None
    return name


def is_unicode_charset(key: str) -> bool:
    """Whether the canonical charset key is a Unicode charset (identity mapping)."""
    return _is_unicode_key(key)


def _is_known(key: str) -> bool:
    return _is_unicode_key(key) or key == 'jisx0201' or _codec_name(key) is not None


def canonical_charset(name: str) -> str:
    """
    Canonicalise a user-supplied charset name such as `'GB2312'`, `'Shift-JIS'`,
    `'ISO-8859-5'`, `'ISO10646-1'`, `'microsoft-cp1252'`, `'big5-0'`.
    """

    key = sanitize_charset(name)
    if _is_known(key):
        return key
    s = str(name).strip()
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

    if _is_unicode_key(key):
        return ('ISO10646', '1')
    m = _RE_ISO8859.fullmatch(key)
    if m:
        return ('ISO8859', str(int(m.group(1))))
    m = re.fullmatch(r'cp(125\d)', key)
    if m:
        return ('MICROSOFT', key.upper())
    if key in _PROPS:
        return _PROPS[key]
    return (key.upper(), '0')


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

    def char2cp(self, char: str) -> int | None:
        """Codepoint of a single character, `None` if not representable."""
        if len(char) != 1:
            raise TypeError(f'char2cp() expected a single character, got {char!r}')
        if self.name == 'jisx0201':
            o = ord(char)
            if o < 0x80:
                return o
            try:
                b = char.encode('shift_jis')
            except UnicodeEncodeError:
                return None
            return b[0] if len(b) == 1 and 0xA1 <= b[0] <= 0xDF else None
        if self.codec is None:
            return ord(char)
        try:
            b = char.encode(self.codec)
        except UnicodeEncodeError:
            return None
        cp = int.from_bytes(b, 'big')
        if self.gl and len(b) == 2:
            cp -= 0x8080
        return cp

    def cp2char(self, cp: int) -> str | None:
        """Character of a codepoint, `None` if not representable."""
        if cp is None or cp < 0:
            return None
        if self.name == 'jisx0201':
            if cp < 0x80:
                return chr(cp)
            if 0xA1 <= cp <= 0xDF:
                return bytes([cp]).decode('shift_jis')
            return None
        if self.codec is None:
            return chr(cp) if cp <= 0x10FFFF else None
        if self.gl and 0x100 <= cp <= 0xFFFF:
            cp += 0x8080
        if cp < 0x100:
            b = bytes([cp])
        elif cp < 0x10000:
            b = cp.to_bytes(2, 'big')
        elif cp < 0x100000000:
            b = cp.to_bytes(4, 'big')
        else:
            return None
        # the whole byte sequence must decode as one unit: no output before the last byte
        # (e.g. 0x06FE in a single-byte charset is two characters, not one -> None)
        dec = codecs.getincrementaldecoder(self.codec)('strict')
        try:
            for i in range(len(b) - 1):
                if dec.decode(b[i : i + 1]):
                    return None
            s = dec.decode(b[-1:], final=True)
        except UnicodeDecodeError:
            return None
        return s or None


def charset_codec(key: str, gl: bool | None = None) -> CharsetCodec:
    """
    Build a `CharsetCodec` for a canonical charset key. `gl=None` means: GL form
    only for charsets that are always GL (`iso2022cn`); GL detection for a font is
    done by `Font`. GL is ignored for charsets that are not 94x94 sets.
    """

    if gl is None:
        gl = key in _FORCE_GL
    gl = bool(gl) and (key in _GL_CAPABLE or key in _FORCE_GL)
    if _is_unicode_key(key):
        return CharsetCodec(key)
    if key == 'jisx0201':
        return CharsetCodec(key, 'shift_jis')
    name = _codec_name(key)
    if name is None:
        return CharsetCodec(key, known=False)
    return CharsetCodec(key, name, gl)


def _gl_capable(key: str) -> bool:
    return key in _GL_CAPABLE


def _force_gl(key: str) -> bool:
    return key in _FORCE_GL


def char2cp(char: str, charset: str = 'iso10646', gl: bool | None = None) -> int | None:
    """
    Convert a character to a codepoint in the given charset (any spelling, e.g.
    `'GB2312'`, `'ISO-8859-5'`). `None` if not representable.
    """

    return charset_codec(canonical_charset(charset), gl).char2cp(char)


def cp2char(cp: int, charset: str = 'iso10646', gl: bool | None = None) -> str | None:
    """
    Convert a codepoint in the given charset to a character. `None` if not
    representable.
    """

    return charset_codec(canonical_charset(charset), gl).cp2char(cp)
