"""
`Font` object

https://font.tomchen.org/bdfparser_py/font
"""

from __future__ import annotations

import io
import math
import os
import re
from collections.abc import Callable, Iterable, Iterator
from typing import Any

from .bitmap import Bitmap, fmtnum
from .encoding import (
    CharsetCodec,
    canonical_charset,
    charset_codec,
    charset_props,
    is_unicode_charset,
    sanitize_charset,
)
from .encoding import _force_gl as _charset_force_gl
from .encoding import _gl_capable as _charset_gl_capable
from .errors import BDFParseError, _warn
from .glyph import META_TITLES, Glyph, _snapshot, defaultglyphname

__all__ = ['Font']

Range = int | tuple[int, int] | list[tuple[int, int]]

# BDF whitespace: ASCII space, \t, \n, \v, \f, \r only (SPEC-v3 §11.4)
_WS = ' \t\n\v\f\r'
_RE_WS = re.compile(r'[ \t\n\v\f\r]+')
_RE_INT = re.compile(r'[+-]?[0-9]+')
_RE_VERSION = re.compile(r'[0-9]+(?:\.[0-9]+)?')
_RE_VVECTOR = re.compile(r'[, \t\n\v\f\r]+')
# second letter of COMMENT, ENDCHAR / ENDFONT, STARTCHAR (never a hex digit)
_KW2 = frozenset('ONT')
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
# unquoted property values are ints only within this range (SPEC-v3 §11.2)
_PROPINT_MIN = -(2**31)
_PROPINT_MAX = 2**32 - 1
_RE_PARSEINT = re.compile(r'\s*([+-]?[0-9]+)')

_PCF_MAGIC = b'\x01fcp'
_GZIP_MAGIC = b'\x1f\x8b'
_TTF_MAGICS = (b'\x00\x01\x00\x00', b'true')

_GLOBAL_METRICS = (
    ('SWIDTH', 'swx0', 'swy0'),
    ('DWIDTH', 'dwx0', 'dwy0'),
    ('SWIDTH1', 'swx1', 'swy1'),
    ('DWIDTH1', 'dwx1', 'dwy1'),
    ('VVECTOR', 'vvectorx', 'vvectory'),
)
# keyword -> index of the first of the two slots in the 17-slot glyph list
_GLYPH_METRICS = {'SWIDTH': 6, 'DWIDTH': 8, 'SWIDTH1': 10, 'DWIDTH1': 12, 'VVECTOR': 14}

_EMPTY_GLYPH = {
    'glyphname': 'empty',
    'codepoint': 8203,  # zero-width space's codepoint
    'bbw': 0,
    'bbh': 0,
    'bbxoff': 0,
    'bbyoff': 0,
    'swx0': 0,
    'swy0': 0,
    'dwx0': 0,
    'dwy0': 0,
    'swx1': 0,
    'swy1': 0,
    'dwx1': 0,
    'dwy1': 0,
    'vvectorx': 0,
    'vvectory': 0,
    'hexdata': [],
}

_NOTHING = object()

_REQUIRED_HEADERS = ('pointsize', 'xres', 'yres', 'fbbx', 'fbby', 'fbbxoff', 'fbbyoff')


def fmtver(v: float) -> str:
    """`2` -> `'2.0'`, `2.1` -> `'2.1'` (BDF version number formatting)."""
    f = float(v)
    return f'{int(f)}.0' if f.is_integer() else repr(f)


def _split_kv(line: str) -> tuple[str, str]:
    """`'KEY  rest of line'` -> `('KEY', 'rest of line')` (line already stripped)."""
    # fast paths: a printable string has no whitespace other than ' '
    i = line.find(' ')
    if i == -1:
        if line.isprintable():
            return line, ''
    else:
        key = line[:i]
        if key.isprintable():
            return key, line[i + 1 :].lstrip(_WS)
    m = _RE_WS.search(line)
    if m is None:
        return line, ''
    return line[: m.start()], line[m.end() :]


def _tokens(value: str) -> list[str]:
    if value.isprintable():  # fast path: ' ' is the only whitespace
        return value.split()
    value = value.strip(_WS)
    return _RE_WS.split(value) if value else []


def _unquote_comment(value: str) -> str:
    value = value.strip(_WS)
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _parse_prop_value(value: str, lineno: int) -> int | str:
    if value.startswith('"'):
        out = []
        i = 1
        n = len(value)
        while i < n:
            c = value[i]
            if c == '"':
                if i + 1 < n and value[i + 1] == '"':
                    out.append('"')
                    i += 2
                    continue
                return ''.join(out)
            out.append(c)
            i += 1
        _warn(f'line {lineno}: property value has no closing quote')
        return ''.join(out)
    if _RE_INT.fullmatch(value):
        v = int(value)
        if _PROPINT_MIN <= v <= _PROPINT_MAX:
            return v
    return value


def _parseint(value: Any) -> int:
    """JS `parseInt(String(value), 10) || 0`-like conversion."""
    if value is None:
        return 0
    if isinstance(value, int):
        return int(value)
    m = _RE_PARSEINT.match(str(value))
    return int(m.group(1)) if m else 0


def _xml(value: Any) -> str:
    s = fmtnum(value) if isinstance(value, (int, float)) else str(value)
    return (
        s.replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
        .replace("'", '&apos;')
    )


def _split_text(text: str) -> list[str]:
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    return lines


def _cp_filter(r: Range) -> Callable[[int], bool]:
    if isinstance(r, int):
        return lambda cp: cp < r
    if isinstance(r, tuple):
        return lambda cp: r[0] <= cp <= r[1]
    return lambda cp: any(t[0] <= cp <= t[1] for t in r)


def _copy_list(lst: list) -> list:
    new = list(lst)
    if new[16] is not None:
        new[16] = list(new[16])
    return new


class Font:
    """
    `Font` object

    https://font.tomchen.org/bdfparser_py/font
    """

    def __init__(self, source: Any = None) -> None:
        """
        Initialize a `Font` object. `source` (optional) may be a file path (`str` or
        `os.PathLike`), a text or binary file object, or `bytes` (BDF, PCF or TTF,
        auto-detected).

        https://font.tomchen.org/bdfparser_py/font#font
        """

        self.headers: dict[str, Any] = {}
        self.props: dict[str, Any] = {}
        self.glyphs: dict[int, list] = {}
        self.unencoded: list[dict[str, Any]] = []
        self._propnames: dict[str, str] = {}
        self._charset_override: str | None = None
        self._char2cp_override: Callable[[str], int | None] | None = None
        self._cp2char_override: Callable[[int], str | None] | None = None
        self._warned_charsets: set[str] = set()
        self._codec_cache: tuple[tuple, CharsetCodec] | None = None

        if source is None:
            return
        if isinstance(source, (str, os.PathLike)):
            self.load_file_path(source)
        elif isinstance(source, (bytes, bytearray, memoryview)):
            self.load_bytes(source)
        elif hasattr(source, 'read') or isinstance(source, io.IOBase):
            self.load_file_obj(source)
        else:
            raise TypeError(f'Cannot load a font from {type(source).__name__}')

    def _reset(self) -> None:
        self.headers = {}
        self.props = {}
        self.glyphs = {}
        self.unencoded = []
        self._propnames = {}
        self._codec_cache = None

    def _assign(self, other: Font) -> Font:
        self.headers = other.headers
        self.props = other.props
        self.glyphs = other.glyphs
        self.unencoded = other.unencoded
        self._propnames = other._propnames
        self._codec_cache = None
        return self

    # ------------------------------------------------------------------
    # loading

    def load_file_path(self, file_path: str | os.PathLike) -> Font:
        """
        Load a font file (BDF, PCF, `.pcf.gz` or TTF, auto-detected by its content).

        https://font.tomchen.org/bdfparser_py/font#load_file_path
        """

        with open(file_path, 'rb') as f:
            data = f.read()
        return self.load_bytes(data)

    def load_file_obj(self, file_obj: Any) -> Font:
        """
        Load a font from a file object: a text file is parsed as BDF, a binary file
        is auto-detected (BDF, PCF, TTF).

        https://font.tomchen.org/bdfparser_py/font#load_file_obj
        """

        if isinstance(file_obj, io.TextIOBase):
            return self.load_lines(file_obj)
        if not hasattr(file_obj, 'read'):
            return self.load_lines(file_obj)
        data = file_obj.read()
        if isinstance(data, str):
            return self.load_string(data)
        return self.load_bytes(data)

    def load_string(self, text: str) -> Font:
        """
        Load a BDF font from a `str`.

        https://font.tomchen.org/bdfparser_py/font#load_string
        """

        if text.startswith('\ufeff'):
            text = text[1:]
        return self.load_lines(_split_text(text))

    def load_lines(self, lines: Iterable[str]) -> Font:
        """
        Load a BDF font from an iterable of lines (`str`s, line endings optional).

        https://font.tomchen.org/bdfparser_py/font#load_lines
        """

        self._reset()
        self.__parse(lines)
        return self

    def load_bytes(self, data: bytes | bytearray | memoryview, **ttfoptions: Any) -> Font:
        """
        Load a font from `bytes`; the format is auto-detected: PCF, gzip-compressed
        PCF/BDF, TrueType (`pixelsize=` option may be needed, see `read_ttf`), else
        BDF (decoded as UTF-8).

        https://font.tomchen.org/bdfparser_py/font#load_bytes
        """

        data = bytes(data)
        head = data[:4]
        if head[:2] == _GZIP_MAGIC:
            import gzip
            import zlib

            try:
                data = gzip.decompress(data)
            except (OSError, EOFError, zlib.error) as e:
                raise ValueError(f'Malformed gzip data: {e}') from None
            return self.load_bytes(data, **ttfoptions)
        if head == _PCF_MAGIC:
            from .pcf import read_pcf

            return self._assign(read_pcf(data))
        if head in _TTF_MAGICS:
            from .ttf import read_ttf

            return self._assign(read_ttf(data, **ttfoptions))
        if head == b'OTTO':
            raise ValueError('CFF-based OpenType is not supported')
        return self.load_string(data.decode('utf-8', errors='replace'))

    @classmethod
    def create(
        cls,
        pixelsize: int = 16,
        ascent: int | None = None,
        descent: int | None = None,
        fontname: str | None = None,
        familyname: str = 'Untitled',
        xres: int = 75,
        yres: int = 75,
    ) -> Font:
        """
        Create a new empty font.

        https://font.tomchen.org/bdfparser_py/font#fontcreate
        """

        if descent is None:
            descent = pixelsize // 8
        if ascent is None:
            ascent = pixelsize - descent
        if fontname is None:
            fontname = familyname
        font = cls()
        font.headers = {
            'bdfversion': 2.1,
            'fontname': fontname,
            'pointsize': pixelsize,
            'xres': xres,
            'yres': yres,
            'fbbx': pixelsize,
            'fbby': ascent + descent,
            'fbbxoff': 0,
            'fbbyoff': -descent,
            'metricsset': 0,
        }
        font.setprop('FAMILY_NAME', familyname)
        font.setprop('PIXEL_SIZE', pixelsize)
        font.setprop('FONT_ASCENT', ascent)
        font.setprop('FONT_DESCENT', descent)
        font.setprop('CHARSET_REGISTRY', 'ISO10646')
        font.setprop('CHARSET_ENCODING', '1')
        return font

    # ------------------------------------------------------------------
    # BDF parser

    def __parse(self, lines: Iterable[str]) -> None:  # noqa: C901 (state machine)
        headers = self.headers
        props = self.props
        glyphs = self.glyphs
        unencoded = self.unencoded
        propnames = self._propnames

        # states: 0 header, 1 properties, 2 after properties (expect CHARS),
        #         3 between glyphs, 4 in glyph, 5 in BITMAP, 6 after ENDFONT
        state = 0
        lineno = 0
        chars: int | None = None
        propcount: int | None = None
        propseen = 0
        nglyphs = 0
        meta: list = []
        hexdata: list[str] = []
        used: set[str] = set()
        startline = 0
        altcode: int | None = None

        def num(tok: str, key: str, value: str) -> int:
            # strict ASCII integer syntax, signed 32-bit range (SPEC-v3 §11.2)
            if not (tok.isascii() and (tok.isdigit() or (tok[:1] in '+-' and tok[1:].isdigit()))):
                raise BDFParseError(f'malformed number in {key} {value!r}', lineno)
            v = int(tok)
            if not _INT32_MIN <= v <= _INT32_MAX:
                raise BDFParseError(f'number {tok} in {key} is out of the 32-bit range', lineno)
            return v

        def ints(value: str, n: int, key: str, sep: re.Pattern | None = None) -> list[int]:
            if sep:
                v = value.strip(_WS)
                parts = sep.split(v) if v else []
            elif value.isprintable():  # fast path: ' ' is the only whitespace
                parts = value.split()
            else:
                parts = _tokens(value)
            if len(parts) < n:
                raise BDFParseError(f'{key} needs {n} numbers, got {value!r}', lineno)
            return [num(p, key, value) for p in parts[:n]]

        def end_headers() -> None:
            if 'metricsset' not in headers:
                headers['metricsset'] = 0

        def start_glyph(value: str) -> None:
            nonlocal meta, hexdata, used, startline, altcode, nglyphs
            meta = [
                value,
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
                None,
                None,
                None,
                None,
                None,
                [],
            ]
            hexdata = meta[16]
            used = set()
            startline = lineno
            altcode = None
            nglyphs += 1

        def finish_glyph() -> None:
            name = meta[0]
            if 'BBX' not in used:
                raise BDFParseError(
                    f"glyph '{name}' (starting at line {startline}) has no BBX", lineno
                )
            if 'ENCODING' not in used:
                _warn(f"line {startline}: glyph '{name}' has no ENCODING, treated as unencoded")
                meta[1] = -1
            if meta[1] < 0:
                if meta[1] != -1:
                    _warn(
                        f"line {startline}: glyph '{name}' has negative ENCODING {meta[1]}, treated as unencoded"
                    )
                    meta[1] = -1
                unencoded.append({'altcode': altcode, 'meta': meta})
                return
            cp = meta[1]
            if cp in glyphs:
                _warn(
                    f"line {startline}: duplicate codepoint {cp} (glyph '{name}'), the later one wins"
                )
                del glyphs[cp]
            glyphs[cp] = meta

        for raw in lines:
            lineno += 1
            if lineno == 1 and raw.startswith('\ufeff'):  # UTF-8 BOM (text file objects)
                raw = raw[1:]
            line = raw.strip(_WS)
            if not line:
                continue

            if state == 5:  # BITMAP rows (hot path)
                if line[1:2] not in _KW2 or line[0] not in 'CES':  # cannot be a keyword
                    hexdata.append(line)
                    continue
                first, value = _split_kv(line)
                if first == 'ENDCHAR':
                    finish_glyph()
                    state = 3
                elif first == 'COMMENT':
                    pass  # comments inside BITMAP are ignored (SPEC-v3 §11.4)
                elif first == 'STARTCHAR':
                    _warn(f"line {lineno}: missing ENDCHAR for glyph '{meta[0]}'")
                    finish_glyph()
                    start_glyph(value)
                    state = 4
                elif first == 'ENDFONT':
                    _warn(f"line {lineno}: missing ENDCHAR for glyph '{meta[0]}'")
                    finish_glyph()
                    state = 6
                    break
                else:
                    hexdata.append(line)
                continue

            key, value = _split_kv(line)

            if state == 4:  # inside a glyph, before BITMAP
                if key == 'ENCODING':
                    if 'ENCODING' not in used:
                        parts = _tokens(value)
                        if not parts:
                            raise BDFParseError('ENCODING needs a number', lineno)
                        nums = [num(p, key, value) for p in parts[:2]]
                        meta[1] = nums[0]
                        if nums[0] < 0 and len(nums) > 1:
                            altcode = nums[1]
                        used.add(key)
                elif key == 'BBX':
                    if 'BBX' not in used:
                        meta[2:6] = ints(value, 4, key)
                        if meta[2] < 0 or meta[3] < 0:
                            raise BDFParseError(
                                f"glyph '{meta[0]}' has a negative BBX size {meta[2]} {meta[3]}",
                                lineno,
                            )
                        used.add(key)
                elif key in _GLYPH_METRICS:
                    if key not in used:
                        i = _GLYPH_METRICS[key]
                        meta[i : i + 2] = ints(
                            value, 2, key, _RE_VVECTOR if key == 'VVECTOR' else None
                        )
                        used.add(key)
                elif key == 'BITMAP':
                    state = 5
                elif key == 'ENDCHAR':
                    finish_glyph()
                    state = 3
                elif key == 'STARTCHAR':
                    _warn(f"line {lineno}: missing ENDCHAR for glyph '{meta[0]}'")
                    finish_glyph()
                    start_glyph(value)
                elif key == 'ENDFONT':
                    _warn(f"line {lineno}: missing ENDCHAR for glyph '{meta[0]}'")
                    finish_glyph()
                    state = 6
                    break
                else:
                    _warn(f'line {lineno}: unknown keyword {key!r} in glyph {meta[0]!r} ignored')
                continue

            if state == 3:  # between glyphs
                if key == 'STARTCHAR':
                    start_glyph(value)
                    state = 4
                elif key == 'ENDFONT':
                    state = 6
                    break
                elif key == 'CHARS' and chars is None:
                    chars = ints(value, 1, key)[0]
                else:
                    _warn(f'line {lineno}: unexpected line {line!r} ignored')
                continue

            if state == 1:  # properties
                if key == 'ENDPROPERTIES':
                    if propcount is not None and propcount != propseen:
                        _warn(
                            f"The property count next to 'STARTPROPERTIES' keyword is {propcount}, "
                            f'which does not match the actual property count {propseen}'
                        )
                    state = 2
                elif key == 'COMMENT' or (key.isascii() and key.lower() == 'comment'):
                    if key != 'COMMENT':
                        # `comment`, `Comment` ... would collide with the comment
                        # list `props['comment']` (SPEC-v3 §11.3)
                        _warn(f'line {lineno}: property {key!r} treated as a COMMENT line')
                    props.setdefault('comment', []).append(_unquote_comment(value))
                elif key in ('CHARS', 'STARTCHAR', 'ENDFONT'):
                    _warn(f"line {lineno}: missing 'ENDPROPERTIES'")
                    if key == 'CHARS':
                        chars = ints(value, 1, key)[0]
                        state = 3
                    elif key == 'STARTCHAR':
                        _warn("Cannot find 'CHARS' line")
                        start_glyph(value)
                        state = 4
                    else:
                        _warn('This font does not have any glyphs')
                        state = 6
                        break
                else:
                    k = key.lower()
                    propseen += 1
                    props[k] = _parse_prop_value(value, lineno) if value else None
                    propnames[k] = key
                continue

            if state == 2:  # after ENDPROPERTIES
                if key == 'CHARS':
                    chars = ints(value, 1, key)[0]
                    state = 3
                elif key == 'STARTCHAR':
                    _warn("Cannot find 'CHARS' line next to 'ENDPROPERTIES' line")
                    start_glyph(value)
                    state = 4
                elif key == 'ENDFONT':
                    _warn('This font does not have any glyphs')
                    state = 6
                    break
                else:
                    _warn(f'line {lineno}: unexpected line {line!r} ignored')
                continue

            # state 0: header
            if key == 'STARTFONT':
                if not _RE_VERSION.fullmatch(value):
                    raise BDFParseError(f'malformed version number in STARTFONT {value!r}', lineno)
                headers['bdfversion'] = float(value)
            elif key == 'FONT':
                headers['fontname'] = value
            elif key == 'SIZE':
                headers['pointsize'], headers['xres'], headers['yres'] = ints(value, 3, key)
            elif key == 'FONTBOUNDINGBOX':
                (headers['fbbx'], headers['fbby'], headers['fbbxoff'], headers['fbbyoff']) = ints(
                    value, 4, key
                )
                if headers['fbbx'] < 0 or headers['fbby'] < 0:
                    raise BDFParseError(
                        f'negative FONTBOUNDINGBOX size {headers["fbbx"]} {headers["fbby"]}', lineno
                    )
            elif key == 'COMMENT':
                headers.setdefault('comment', []).append(_unquote_comment(value))
            elif key in ('METRICSSET', 'CONTENTVERSION'):
                headers[key.lower()] = ints(value, 1, key)[0]
            elif key in _GLYPH_METRICS:
                k0, k1 = next((a, b) for (kw, a, b) in _GLOBAL_METRICS if kw == key)
                headers[k0], headers[k1] = ints(
                    value, 2, key, _RE_VVECTOR if key == 'VVECTOR' else None
                )
            elif key == 'STARTPROPERTIES':
                end_headers()
                parts = _tokens(value)
                if parts and _RE_INT.fullmatch(parts[0]):
                    propcount = int(parts[0])
                elif parts:
                    _warn(f'line {lineno}: malformed property count {value!r}')
                state = 1
            elif key == 'CHARS':
                _warn(
                    "It looks like the font does not have property block beginning with 'STARTPROPERTIES' keyword"
                )
                end_headers()
                chars = ints(value, 1, key)[0]
                state = 3
            elif key == 'STARTCHAR':
                _warn(
                    "It looks like the font does not have property block beginning with 'STARTPROPERTIES' keyword"
                )
                _warn("Cannot find 'CHARS' line")
                end_headers()
                start_glyph(value)
                state = 4
            elif key == 'ENDFONT':
                _warn(
                    "It looks like the font does not have property block beginning with 'STARTPROPERTIES' keyword"
                )
                _warn('This font does not have any glyphs')
                end_headers()
                state = 6
                break
            else:
                _warn(f'line {lineno}: unknown header keyword {key!r} ignored')

        if state <= 1:
            raise BDFParseError('Unexpected end of file before the end of the headers', lineno + 1)
        if state in (4, 5):
            _warn(f"Unexpected end of file: missing ENDCHAR for glyph '{meta[0]}'")
            finish_glyph()
        if state != 6:
            _warn("This font does not have 'ENDFONT' keyword")
        if state >= 3 and (chars is not None or nglyphs):
            if chars is None:
                _warn("The glyph count next to 'CHARS' keyword does not exist")
            elif chars != nglyphs:
                _warn(
                    f"The glyph count next to 'CHARS' keyword is {chars}, "
                    f'which does not match the actual glyph count {nglyphs}'
                )

    # ------------------------------------------------------------------
    # charsets

    def encoding(
        self,
        charset: str | None = None,
        char2cp: Callable[[str], int | None] | None = None,
        cp2char: Callable[[int], str | None] | None = None,
    ) -> Font:
        """
        Override the charset resolution (`charset`, any spelling, e.g. `'GB2312'`,
        `'Shift-JIS'`; `''` clears the override) and/or the character <-> codepoint
        conversion functions.

        https://font.tomchen.org/bdfparser_py/font#encoding
        """

        if charset is not None:
            self._charset_override = canonical_charset(charset) if charset else None
        if char2cp is not None:
            self._char2cp_override = char2cp
        if cp2char is not None:
            self._cp2char_override = cp2char
        return self

    @property
    def charset(self) -> str:
        """
        Canonical charset key: the `encoding(charset=...)` override if set, else
        derived from the `CHARSET_REGISTRY` and `CHARSET_ENCODING` properties
        (`'iso10646'` when absent).

        https://font.tomchen.org/bdfparser_py/font#charset
        """

        if self._charset_override:
            return self._charset_override
        return sanitize_charset(
            self.props.get('charset_registry'), self.props.get('charset_encoding')
        )

    def _is_gl(self, key: str) -> bool:
        if _charset_force_gl(key):
            return True
        if not _charset_gl_capable(key):
            return False
        enc = self.props.get('charset_encoding')
        if enc is not None and str(enc).strip(_WS) == '0':
            return True
        twobyte = [cp for cp in self.glyphs if 0x100 <= cp <= 0xFFFF]
        if not twobyte:
            return False
        m = min(twobyte)
        return 0x21 <= m >> 8 <= 0x7E and 0x21 <= m & 0xFF <= 0x7E

    def _codec(self) -> CharsetCodec:
        # cached per font (SPEC-v3 §11.1); the cache is keyed on everything the
        # resolution depends on: the `encoding()` override, the CHARSET_REGISTRY /
        # CHARSET_ENCODING properties and the glyph set (identity and size of
        # `glyphs`; library methods that change the codepoints also invalidate it)
        glyphs = self.glyphs
        token = (
            self._charset_override,
            self.props.get('charset_registry'),
            self.props.get('charset_encoding'),
            id(glyphs),
            len(glyphs),
        )
        cache = self._codec_cache
        if cache is not None and cache[0] == token:
            return cache[1]
        key = self.charset
        codec = charset_codec(key, self._is_gl(key))
        if not codec.known and key not in self._warned_charsets:
            self._warned_charsets.add(key)
            _warn(f"Unknown charset '{key}', characters are mapped to codepoints as Unicode")
        self._codec_cache = (token, codec)
        return codec

    def _converters(self) -> tuple[Callable[[str], int | None], Callable[[int], str | None]]:
        c2p = self._char2cp_override
        p2c = self._cp2char_override
        if c2p is None or p2c is None:
            codec = self._codec()
            c2p = c2p or codec.char2cp
            p2c = p2c or codec.cp2char
        return c2p, p2c

    def _is_unicode(self) -> bool:
        return is_unicode_charset(self.charset)

    def char2cp(self, char: str) -> int | None:
        """
        Convert a character to a codepoint of the font's charset (`None` if not
        representable).

        https://font.tomchen.org/bdfparser_py/font#char2cp
        """

        return self._converters()[0](char)

    def cp2char(self, cp: int) -> str | None:
        """
        Convert a codepoint of the font's charset to a character (`None` if not
        representable).

        https://font.tomchen.org/bdfparser_py/font#cp2char
        """

        return self._converters()[1](cp)

    # ------------------------------------------------------------------
    # properties

    def getprop(self, key: str) -> Any:
        """
        Get a property value (case-insensitive key), `None` if absent.

        https://font.tomchen.org/bdfparser_py/font#getprop
        """

        return self.props.get(key.lower())

    def setprop(self, key: str, value: int | str | None) -> Font:
        """
        Set a property (case-insensitive key). Remembers the given spelling of a new key.

        https://font.tomchen.org/bdfparser_py/font#setprop
        """

        k = key.lower()
        if k not in self._propnames and k != 'comment':
            self._propnames[k] = key
        self.props[k] = value
        return self

    def delprop(self, key: str) -> Font:
        """
        Remove a property (case-insensitive key) if present.

        https://font.tomchen.org/bdfparser_py/font#delprop
        """

        k = key.lower()
        self.props.pop(k, None)
        self._propnames.pop(k, None)
        return self

    def swidth(self, dwx: int) -> int:
        """
        Compute SWIDTH (scalable width, 1/1000 em) from DWIDTH (pixels).

        https://font.tomchen.org/bdfparser_py/font#swidth
        """

        pointsize = self.headers.get('pointsize')
        xres = self.headers.get('xres')
        if pointsize and xres:
            return math.floor(dwx * 72000 / (pointsize * xres) + 0.5)
        return math.floor(dwx * 1000 / max(self.headers.get('fbbx') or 1, 1) + 0.5)

    # ------------------------------------------------------------------
    # querying

    def length(self) -> int:
        """
        Returns how many glyphs actually exist in the font.

        https://font.tomchen.org/bdfparser_py/font#length
        """

        return len(self.glyphs)

    def __len__(self) -> int:
        """
        Same as `.length()`
        """
        return self.length()

    def itercps(self, order: int = 1, r: Range | None = None) -> Iterator[int]:
        """
        Almost identical to `.iterglyphs()`, except it returns an `iterator` of glyph codepoints instead of an `iterator` of `Glyph` objects.

        https://font.tomchen.org/bdfparser_py/font#itercps
        """

        ks = self.glyphs.keys()
        if order == 1:
            retiterator: Iterator[int] = iter(sorted(ks))
        elif order == 0:
            retiterator = iter(list(ks))
        elif order == 2:
            retiterator = iter(sorted(ks, reverse=True))
        elif order == -1:
            retiterator = reversed(list(ks))
        else:
            raise ValueError(f'Unknown order {order!r}')
        if r is not None:
            retiterator = filter(_cp_filter(r), retiterator)
        return retiterator

    def iterglyphs(self, order: int = 1, r: Range | None = None) -> Iterator[Glyph]:
        """
        Returns an iterator of all the glyphs (as `Glyph` objects) in the font (default) or in the specified codepoint range in the font, sorted by the specified order (or by the ascending codepoint order by default).

        https://font.tomchen.org/bdfparser_py/font#iterglyphs
        """

        for cp in self.itercps(order, r):
            if cp in self.glyphs:
                yield self.__glyph(self.glyphs[cp])

    def __glyph(self, store: list) -> Glyph:
        g = Glyph(dict(zip(META_TITLES, store, strict=False)), self)
        g._attach(store)
        return g

    def __describe_cp(self, codepoint: int) -> str:
        try:
            ch = self.cp2char(codepoint)
        except Exception:
            ch = None
        return f'Glyph "{ch}" (codepoint {codepoint})' if ch else f'Glyph (codepoint {codepoint})'

    def glyphbycp(self, codepoint: int) -> Glyph | None:
        """
        Get a glyph (as Glyph object) by its codepoint.

        https://font.tomchen.org/bdfparser_py/font#glyphbycp
        """

        if codepoint not in self.glyphs:
            _warn(f'{self.__describe_cp(codepoint)} does not exist in the font. Will return `None`')
            return None
        return self.__glyph(self.glyphs[codepoint])

    def glyph(self, character: str) -> Glyph | None:
        """
        Get a glyph (as `Glyph` object) by its character.

        https://font.tomchen.org/bdfparser_py/font#glyph
        """

        cp = self.char2cp(character)
        if cp is None:
            _warn(
                f'Character "{character}" cannot be encoded in the charset {self.charset!r}. Will return `None`'
            )
            return None
        return self.glyphbycp(cp)

    def lacksglyphs(self, string: str) -> list[str] | None:
        """
        Check if there is any missing glyph and gets these glyphs' character.

        https://font.tomchen.org/bdfparser_py/font#lacksglyphs
        """

        c2p = self._converters()[0]
        missing = []
        for char in string:
            cp = c2p(char)
            if cp is None or cp not in self.glyphs:
                missing.append(char)
        return missing or None

    def drawcps(
        self,
        cps: Iterable[int | None],
        linelimit: int = 512,
        mode: int = 1,
        direction: str = 'lrtb',
        usecurrentglyphspacing: bool = False,
        missing: Glyph | dict | None = None,
    ) -> Bitmap:
        """
        Draw the glyphs of the specified codepoints, to a `Bitmap` object.

        https://font.tomchen.org/bdfparser_py/font#drawcps
        """

        dire_shortcut_dict = {'lr': 'lrtb', 'rl': 'rltb', 'tb': 'tbrl', 'bt': 'btrl'}
        dire = dire_shortcut_dict.get(direction) or direction
        dire_dict = {'lr': 1, 'rl': 2, 'tb': 0, 'bt': -1}
        dire_glyph_str = dire[0:2]
        dire_line_str = dire[2:4]
        if dire_glyph_str in dire_dict and dire_line_str in dire_dict:
            dire_glyph = dire_dict[dire_glyph_str]
            dire_line = dire_dict[dire_line_str]
        else:
            dire_glyph = 1
            dire_line = 0

        # 'xxtb' or 'xxrl' -> bottom or left; 'xxlr' or 'xxbt' -> right or top
        align_glyph = 1 if dire_line in (0, 2) else 0
        # 'lrxx' or 'btxx' -> left or bottom; 'rlxx' or 'tbxx' -> right or top
        align_line = 1 if dire_glyph in (1, -1) else 0

        fbbsize = 0
        interglyph_global = None
        interglyph_str = interglyph_str2 = ''
        if mode == 1:  # dwidth / dwidth1 mode
            fbbsize = self.headers['fbbx'] if dire_glyph > 0 else self.headers['fbby']
            if dire_glyph > 0:  # 'lrxx'/'rlxx'
                interglyph_str, interglyph_str2 = 'dwx0', 'dwy0'
            else:  # 'tbxx'/'btxx'
                interglyph_str, interglyph_str2 = 'dwx1', 'dwy1'
            if interglyph_str in self.headers:
                interglyph_global = self.headers[interglyph_str]
            elif interglyph_str2 in self.headers:
                interglyph_global = self.headers[interglyph_str2]

        list_of_bitmaplist: list[list[Bitmap]] = []
        bitmaplist: list[Bitmap] = []
        list_of_offsetlist: list[list[int]] = []
        offsetlist: list[int] = []
        size = 0

        def append_bitmaplist_and_offsetlist() -> None:
            list_of_bitmaplist.append(bitmaplist)
            if usecurrentglyphspacing:
                offsetlist.pop(0)
            else:  # use previous glyph spacing (default)
                offsetlist.pop()
            list_of_offsetlist.append(offsetlist)

        if isinstance(missing, dict):
            missing = Glyph(missing, self)
        cpsiter = iter(cps)
        skip = False
        while True:
            if skip:
                skip = False
            else:
                cp = next(cpsiter, _NOTHING)
                if cp is _NOTHING:
                    break
                if cp is not None and cp in self.glyphs:
                    glyph = self.__glyph(self.glyphs[cp])
                elif missing:
                    glyph = missing
                else:
                    glyph = Glyph(_EMPTY_GLYPH, self)

                bitmap = glyph.draw()
                w = bitmap.width()

                offset = 0
                if mode == 1:
                    interglyph = glyph.meta.get(interglyph_str) or glyph.meta.get(interglyph_str2)
                    if interglyph is None:
                        interglyph = interglyph_global
                    if interglyph is not None:
                        offset = interglyph - fbbsize

            size += w + offset
            if size <= linelimit:
                bitmaplist.append(bitmap)
                offsetlist.append(offset)
            else:
                if len(bitmaplist) == 0:
                    raise ValueError(
                        f"`linelimit` ({linelimit}) is too small the line can't even contain one glyph: "
                        f'"{glyph.chr()}" (codepoint {cp}, width: {w})'
                    )
                append_bitmaplist_and_offsetlist()
                size = 0
                bitmaplist = []
                offsetlist = []
                skip = True
        if len(bitmaplist) != 0:
            append_bitmaplist_and_offsetlist()

        list_of_bitmap_line_lists = [
            Bitmap.concatall(
                bl, direction=dire_glyph, align=align_glyph, offsetlist=list_of_offsetlist[i]
            )
            for i, bl in enumerate(list_of_bitmaplist)
        ]

        return Bitmap.concatall(list_of_bitmap_line_lists, direction=dire_line, align=align_line)

    def draw(
        self,
        string: str,
        linelimit: int = 512,
        mode: int = 1,
        direction: str = 'lrtb',
        usecurrentglyphspacing: bool = False,
        missing: Glyph | dict | None = None,
    ) -> Bitmap:
        """
        Draw (render) the glyphs of the specified words / setences / paragraphs (as a `str`), to a `Bitmap` object.

        https://font.tomchen.org/bdfparser_py/font#draw
        """

        c2p = self._converters()[0]
        return self.drawcps(
            (c2p(char) for char in string),
            linelimit,
            mode,
            direction,
            usecurrentglyphspacing,
            missing,
        )

    def drawall(
        self,
        order: int = 1,
        r: Range | None = None,
        linelimit: int = 512,
        mode: int = 0,
        direction: str = 'lrtb',
        usecurrentglyphspacing: bool = False,
    ) -> Bitmap:
        """
        Draw all the glyphs in the font (default) or in the specified codepoint range in the font, sorted by the specified order (or by the ascending codepoint order by default), to a `Bitmap` object.

        https://font.tomchen.org/bdfparser_py/font#drawall
        """

        return self.drawcps(
            self.itercps(order, r), linelimit, mode, direction, usecurrentglyphspacing
        )

    # ------------------------------------------------------------------
    # editing

    def _writeback(self, glyph: Glyph) -> None:
        """Write an attached glyph's meta back into the font (internal)."""
        store = glyph._store
        if store is None:
            return
        oldcp = store[1]
        uidx = -1
        if oldcp is None or oldcp < 0:
            uidx = next((i for i, e in enumerate(self.unencoded) if e['meta'] is store), -1)
            if uidx == -1:
                glyph._attached = False
                return
        elif self.glyphs.get(oldcp) is not store:
            # the glyph was removed from / replaced in the font: no longer attached
            glyph._attached = False
            return
        new = [glyph.meta.get(k) for k in META_TITLES]
        synced = glyph._synced
        if synced is not None:
            # slots this Glyph object did not change but that were changed in the
            # font meanwhile (by another Glyph object on the same glyph, or by
            # `charsetconvert`) keep the font's value instead of being reverted
            for i in range(17):
                if new[i] == synced[i] and store[i] != synced[i]:
                    new[i] = store[i]
        if new[16] is None:
            new[16] = []
        newcp = new[1]
        if newcp is None or newcp < 0:
            newcp = new[1] = -1
        store[:] = new
        if newcp != oldcp:
            self._codec_cache = None
        if uidx != -1:
            if newcp >= 0:
                del self.unencoded[uidx]
                self.glyphs[newcp] = store
        elif newcp != oldcp:
            del self.glyphs[oldcp]
            if newcp < 0:
                self.unencoded.append({'altcode': None, 'meta': store})
            else:
                self.glyphs[newcp] = store
        glyph.meta.update(zip(META_TITLES, store, strict=True))
        glyph._synced = _snapshot(store)

    def __meta_to_list(self, meta: Any) -> list:
        if isinstance(meta, Glyph):
            meta = meta.meta
        for k in meta:
            if k not in META_TITLES:
                raise KeyError(f'Unknown glyph meta key {k!r}')
        if meta.get('codepoint') is None:
            raise ValueError('The glyph has no codepoint')
        cp = meta['codepoint']
        lst = [meta.get(k) for k in META_TITLES]
        if lst[0] is None:
            lst[0] = defaultglyphname(cp, self._is_unicode()) if cp >= 0 else f'char{cp}'
        for i in (2, 3, 4, 5):
            if lst[i] is None:
                lst[i] = 0
        lst[16] = list(lst[16] or [])
        return lst

    def addglyph(self, glyph: Glyph | dict[str, Any], replace: bool = True) -> Font:
        """
        Add a glyph (a `Glyph` object or a meta `dict`) to the font. If its codepoint
        already exists, it is replaced when `replace` is true (default), otherwise
        the old one is kept (with a warning). A codepoint of `-1` adds an unencoded
        glyph. A `Glyph` object becomes attached to this font.

        https://font.tomchen.org/bdfparser_py/font#addglyph
        """

        lst = self.__meta_to_list(glyph)
        cp = lst[1]
        self._codec_cache = None
        if cp < 0:
            lst[1] = -1
            self.unencoded.append({'altcode': None, 'meta': lst})
        else:
            if cp in self.glyphs and not replace:
                _warn(f'{self.__describe_cp(cp)} already exists in the font, the old one is kept')
                return self
            self.glyphs[cp] = lst
        if isinstance(glyph, Glyph):
            glyph.font = self
            glyph.meta = dict(zip(META_TITLES, lst, strict=False))
            glyph._attach(lst)
        return self

    def removeglyph(self, cp_or_glyph: int | Glyph) -> Font:
        """
        Remove a glyph (by codepoint or `Glyph` object); no-op if missing.

        https://font.tomchen.org/bdfparser_py/font#removeglyph
        """

        self._codec_cache = None
        if not isinstance(cp_or_glyph, Glyph):
            self.glyphs.pop(cp_or_glyph, None)
            return self
        store = cp_or_glyph._store
        if store is not None and cp_or_glyph.font is self:
            # an attached glyph removes exactly its own slot (no-op if it was already
            # removed or replaced: never the glyph that now has its codepoint)
            cp = store[1]
            if cp is None or cp < 0:
                for i, e in enumerate(self.unencoded):
                    if e['meta'] is store:
                        del self.unencoded[i]
                        break
            elif self.glyphs.get(cp) is store:
                del self.glyphs[cp]
        else:
            cp = cp_or_glyph.cp()
            if cp is not None and cp >= 0:
                self.glyphs.pop(cp, None)
        cp_or_glyph._attached = False
        return self

    def newglyph(
        self,
        cp: int,
        bitmap: Bitmap | None = None,
        mode: int = 0,
        name: str | None = None,
        dwidth: int | None = None,
    ) -> Glyph:
        """
        Create a new glyph at codepoint `cp` (replacing any existing one), optionally
        with a bitmap (placed as in `Glyph.setbitmap(bitmap, mode)`), and return it
        (attached). `name` defaults to `uniXXXX` (`charNNN` for non-Unicode
        charsets); `dwidth` defaults to the bitmap width (or the font bounding box
        width if there is no bitmap).

        https://font.tomchen.org/bdfparser_py/font#newglyph
        """

        if dwidth is None:
            dwidth = self.headers.get('fbbx', 0) if bitmap is None else bitmap.width()
        meta = dict.fromkeys(META_TITLES)
        meta.update(
            glyphname=name,
            codepoint=cp,
            bbw=0,
            bbh=0,
            bbxoff=0,
            bbyoff=0,
            swx0=self.swidth(dwidth),
            swy0=0,
            dwx0=dwidth,
            dwy0=0,
            hexdata=[],
        )
        glyph = Glyph(meta, self)
        self.addglyph(glyph, replace=True)
        if bitmap is not None:
            glyph.setbitmap(bitmap, mode)
        return glyph

    def updatebbox(self) -> Font:
        """
        Set FONTBOUNDINGBOX to the union of all glyphs' bounding boxes (glyphs with
        an empty box are ignored; unchanged if there is none).

        https://font.tomchen.org/bdfparser_py/font#updatebbox
        """

        boxes = [
            (m[4], m[5], m[4] + m[2], m[5] + m[3])
            for m in [*self.glyphs.values(), *(e['meta'] for e in self.unencoded)]
            if (m[2] or 0) > 0 and (m[3] or 0) > 0
        ]
        if boxes:
            x0 = min(b[0] for b in boxes)
            y0 = min(b[1] for b in boxes)
            x1 = max(b[2] for b in boxes)
            y1 = max(b[3] for b in boxes)
            self.headers['fbbx'] = x1 - x0
            self.headers['fbby'] = y1 - y0
            self.headers['fbbxoff'] = x0
            self.headers['fbbyoff'] = y0
        return self

    def clone(self) -> Font:
        """
        Get a deep copy of the font.

        https://font.tomchen.org/bdfparser_py/font#clone
        """

        return self.__clone(True)

    def __clone(self, with_glyphs: bool) -> Font:
        font = self.__class__()
        font.headers = {k: (list(v) if isinstance(v, list) else v) for k, v in self.headers.items()}
        font.props = {k: (list(v) if isinstance(v, list) else v) for k, v in self.props.items()}
        font._propnames = dict(self._propnames)
        font._charset_override = self._charset_override
        font._char2cp_override = self._char2cp_override
        font._cp2char_override = self._cp2char_override
        if with_glyphs:
            font.glyphs = {cp: _copy_list(lst) for cp, lst in self.glyphs.items()}
            font.unencoded = [
                {'altcode': e['altcode'], 'meta': _copy_list(e['meta'])} for e in self.unencoded
            ]
        return font

    def subset(self, r: Range) -> Font:
        """
        Get a new font (deep copy) with only the glyphs whose codepoints are in `r`
        (same format as in `itercps()`). Unencoded glyphs are dropped.

        https://font.tomchen.org/bdfparser_py/font#subset
        """

        font = self.__clone(False)
        keep = _cp_filter(r)
        font.glyphs = {cp: _copy_list(lst) for cp, lst in self.glyphs.items() if keep(cp)}
        return font

    def merge(self, other: Font, replace: bool = False) -> Font:
        """
        Copy the (encoded) glyphs of another font into this one; existing codepoints
        are kept unless `replace`. Codepoints are copied as they are (no charset
        conversion).

        https://font.tomchen.org/bdfparser_py/font#merge
        """

        self._codec_cache = None
        for cp, lst in other.glyphs.items():
            if cp in self.glyphs and not replace:
                continue
            self.glyphs[cp] = _copy_list(lst)
        return self

    def transform(
        self, fn: Callable[[Bitmap], Bitmap | None], r: Range | None = None, mode: int = 0
    ) -> Font:
        """
        Apply `Glyph.transform(fn, mode)` to every glyph (or to the glyphs whose
        codepoints are in `r`; unencoded glyphs are included only when `r` is `None`).

        https://font.tomchen.org/bdfparser_py/font#transform
        """

        stores = [self.glyphs[cp] for cp in self.itercps(0, r)]
        if r is None:
            stores += [e['meta'] for e in self.unencoded]
        for store in stores:
            self.__glyph(store).transform(fn, mode)
        return self

    def charsetconvert(self, newcharset: str) -> Font:
        """
        Re-encode every glyph's codepoint from the current charset to `newcharset`
        (glyphs not representable in the new charset are dropped, with a warning),
        set the `CHARSET_REGISTRY` / `CHARSET_ENCODING` properties accordingly and
        clear any `encoding()` override.

        https://font.tomchen.org/bdfparser_py/font#charsetconvert
        """

        p2c = self._converters()[1]
        key = canonical_charset(newcharset)
        newcodec = charset_codec(key, _charset_gl_capable(key) or _charset_force_gl(key))
        if not newcodec.known:
            _warn(f"Unknown charset '{key}', characters are mapped to codepoints as Unicode")
        newglyphs: dict[int, list] = {}
        dropped = 0
        for cp, lst in self.glyphs.items():
            ch = p2c(cp)
            newcp = newcodec.char2cp(ch) if ch and len(ch) == 1 else None
            if newcp is None:
                dropped += 1
                continue
            if newcp in newglyphs:
                # two glyphs map to the same codepoint: the later one wins and, as
                # for a duplicate ENCODING in a BDF file, takes the later position
                dropped += 1
                del newglyphs[newcp]
            lst[1] = newcp
            newglyphs[newcp] = lst
        if dropped:
            _warn(
                f"{dropped} glyph(s) could not be converted to the charset '{key}' and were dropped"
            )
        self.glyphs = newglyphs
        self._codec_cache = None
        registry, enc = charset_props(key)
        self.setprop('CHARSET_REGISTRY', registry)
        self.setprop('CHARSET_ENCODING', enc)
        self._charset_override = None
        self._char2cp_override = None
        self._cp2char_override = None
        return self

    # ------------------------------------------------------------------
    # output

    def tobdf(self) -> str:
        """
        Get the font as a BDF `str` (FontForge-style formatting).

        https://font.tomchen.org/bdfparser_py/font#tobdf
        """

        h = self.headers
        missing = [k for k in _REQUIRED_HEADERS if h.get(k) is None]
        if missing:
            raise ValueError(
                f'Cannot write BDF: missing header(s) {", ".join(missing)} (font not loaded?)'
            )
        lines = [
            f'STARTFONT {fmtver(h.get("bdfversion", 2.1))}',
            f'FONT {h.get("fontname", "")}',
            f'SIZE {h.get("pointsize")} {h.get("xres")} {h.get("yres")}',
            f'FONTBOUNDINGBOX {h.get("fbbx")} {h.get("fbby")} {h.get("fbbxoff")} {h.get("fbbyoff")}',
        ]
        if h.get('metricsset'):
            lines.append(f'METRICSSET {h["metricsset"]}')
        if h.get('contentversion') is not None:
            lines.append(f'CONTENTVERSION {h["contentversion"]}')
        for kw, a, b in _GLOBAL_METRICS:
            if h.get(a) is not None and h.get(b) is not None:
                lines.append(f'{kw} {h[a]} {h[b]}')
        for c in h.get('comment') or []:
            lines.append(f'COMMENT "{c}"')

        propkeys = [k for k in self.props if k != 'comment']
        propcomments = self.props.get('comment') or []
        if propkeys or propcomments:
            lines.append(f'STARTPROPERTIES {len(propkeys)}')
            for c in propcomments:
                lines.append(f'COMMENT "{c}"')
            for k in propkeys:
                name = self._propnames.get(k, k.upper())
                v = self.props[k]
                if v is None:
                    lines.append(name)
                elif isinstance(v, int):
                    lines.append(f'{name} {int(v)}')
                else:
                    s = str(v).replace('"', '""')
                    lines.append(f'{name} "{s}"')
            lines.append('ENDPROPERTIES')

        lines.append(f'CHARS {len(self.glyphs) + len(self.unencoded)}')

        def glyphlines(m: list, encoding: str) -> None:
            lines.append(f'STARTCHAR {m[0]}')
            lines.append(encoding)
            for kw, i in _GLYPH_METRICS.items():
                if m[i] is not None and m[i + 1] is not None:
                    lines.append(f'{kw} {m[i]} {m[i + 1]}')
            lines.append(f'BBX {m[2]} {m[3]} {m[4]} {m[5]}')
            lines.append('BITMAP')
            lines.extend(m[16] or [])
            lines.append('ENDCHAR')

        for cp, m in self.glyphs.items():
            glyphlines(m, f'ENCODING {cp}')
        for e in self.unencoded:
            alt = e.get('altcode')
            glyphlines(e['meta'], 'ENCODING -1' if alt is None else f'ENCODING -1 {alt}')
        lines.append('ENDFONT')
        return '\n'.join(lines) + '\n'

    def topcf(self, **opts: Any) -> bytes:
        """
        Get the font as PCF `bytes` (see `bdfparser.pcf.write_pcf` for options).

        https://font.tomchen.org/bdfparser_py/font#topcf
        """

        from .pcf import write_pcf

        return write_pcf(self, **opts)

    def tottf(self, **opts: Any) -> bytes:
        """
        Get the font as TrueType `bytes` with square or round pixel dots (see
        `bdfparser.ttf.write_ttf` for options: `shape`, `dotsize`, `ppu`, ...).

        https://font.tomchen.org/bdfparser_py/font#tottf
        """

        from .ttf import write_ttf

        return write_ttf(self, **opts)

    def tosvgfont(
        self,
        xoff: float = 0,
        yoff: float = 0,
        controlcharnoskip: bool = False,
        unicodeformat: str = 'hexncr',
    ) -> str:
        """
        Get the font as an SVG font `str`.

        - `xoff`, `yoff`: offsets added to all glyph paths;
        - `controlcharnoskip`: also write the `unicode` attribute for control
          characters (< U+0020), default `False` (FontForge can't load them);
        - `unicodeformat`: `'hexncr'` (`&#x4ab;`, default), `'decncr'` (`&#1195;`)
          or `'char'` (the character itself).

        The `unicode` attributes and `unicode-range` use the Unicode values of
        the glyphs (`cp2char`, so non-Unicode charsets are converted); glyphs
        with no Unicode mapping get no `unicode` attribute.

        https://font.tomchen.org/bdfparser_py/font#tosvgfont
        """

        h = self.headers
        p = self.props
        upem = max(h.get('fbbx') or 0, h.get('fbby') or 0) or 100
        ascent = _parseint(p.get('font_ascent')) or upem * 0.8
        descent = _parseint(p.get('font_descent')) or -upem * 0.2
        dwx0 = h.get('dwx0') or upem

        out = ['<svg xmlns="http://www.w3.org/2000/svg" version="1.1">\n']
        meta = []
        if p.get('family_name') or p.get('family'):
            meta.append(f'Title: {p.get("family_name") or p.get("family")}')
        for label, key in (
            ('Weight', 'weight_name'),
            ('Version', 'font_version'),
            ('Foundry', 'foundry'),
            ('Copyright', 'copyright'),
            ('Notice', 'notice'),
        ):
            if p.get(key):
                meta.append(f'{label}: {p[key]}')
        if meta:
            out.append('<metadata>\n  ' + _xml('\n  '.join(meta)) + '\n</metadata>\n')

        # Unicode values (SPEC-v3 §11.5): `cp2char` of the font's charset; glyphs
        # without a Unicode mapping (or mapped to a surrogate) get no `unicode`
        p2c = self._converters()[1]

        def unicode_of(cp: int) -> int | None:
            ch = p2c(cp)
            if isinstance(ch, str) and len(ch) == 1:
                u = ord(ch)
                return None if 0xD800 <= u <= 0xDFFF else u
            return None

        unis = {cp: unicode_of(cp) for cp in self.glyphs}
        cps = sorted({u for u in unis.values() if u is not None})
        ranges = []
        i = 0
        while i < len(cps):
            j = i
            while j + 1 < len(cps) and cps[j + 1] == cps[j] + 1:
                j += 1
            a, b = cps[i], cps[j]
            ranges.append(f'U+{a:04X}' if a == b else f'U+{a:04X}-{b:04X}')
            i = j + 1

        fontid = (h.get('fontname') or '').lower()
        if fontid.startswith('-'):
            fontid = fontid[1:]
        out.append(f'<defs>\n  <font id="{_xml(fontid)}" horiz-adv-x="{fmtnum(dwx0)}">')

        face = {
            'font-family': p.get('family_name') or p.get('family') or h.get('fontname') or '',
            'font-weight': p.get('weight_name') or 'normal',
            'font-style': p.get('slant') or 'normal',
            'units-per-em': upem,
            'cap-height': _parseint(p.get('cap_height')) or ascent,
            'x-height': _parseint(p.get('x_height')) or ascent * 0.5,
            'ascent': ascent,
            'descent': descent,
            'bbox': (
                f'{fmtnum(h.get("fbbxoff") or 0)} {fmtnum(h.get("fbbyoff") or 0)} '
                f'{fmtnum(h.get("fbbx") or upem)} {fmtnum(h.get("fbby") or upem)}'
            ),
            'underline-thickness': _parseint(p.get('underline_thickness'))
            or math.floor(upem * 0.05 + 0.5),
            'underline-position': _parseint(p.get('underline_position'))
            or math.floor(-upem * 0.075 + 0.5),
            'unicode-range': ', '.join(ranges),
        }
        out.append('\n<font-face\n')
        for k, v in face.items():
            out.append(f'  {k}="{_xml(v)}"\n')
        out.append('></font-face>\n')

        u = fmtnum(upem)
        box = f'M0,0h{u}v{u}h-{u}z'
        out.append(
            f'<missing-glyph horiz-adv-x="{fmtnum(dwx0)}" d="{box}" />\n'
            f'<glyph glyph-name=".notdef" horiz-adv-x="{fmtnum(dwx0)}" d="{box}" />\n'
        )

        for glyph in self.iterglyphs():
            path = glyph.draw().tosvg(1, 'pathOnly', True, xoff, yoff)
            if not path:
                continue
            m = glyph.meta
            u = unis.get(m['codepoint'])
            attrs: list[tuple[str, Any]] = [('glyph-name', _xml(m['glyphname']))]
            if u is not None and (controlcharnoskip or u >= 32):
                if unicodeformat == 'decncr':
                    uni = f'&#{u};'
                elif unicodeformat == 'char':
                    uni = _xml(chr(u))
                else:
                    uni = f'&#x{u:x};'
                attrs.append(('unicode', uni))
            attrs.append(('horiz-adv-x', _xml(m.get('dwx0') or h.get('dwx0') or upem)))
            attrs.append(('d', _xml(path)))
            if m.get('swy0'):
                attrs.append(('vert-adv-y', _xml(m['swy0'])))
            if m.get('vvectorx'):
                attrs.append(('vert-origin-x', _xml(m['vvectorx'])))
            if m.get('vvectory'):
                attrs.append(('vert-origin-y', _xml(m['vvectory'])))
            out.append('<glyph\n')
            for k, v in attrs:
                out.append(f'  {k}="{v}"\n')
            out.append('></glyph>\n')

        out.append('</font>\n</defs>\n</svg>')
        return ''.join(out)

    def save(self, path: str | os.PathLike, format: str | None = None, **opts: Any) -> Font:
        """
        Save the font to a file. The format (`'bdf'`, `'pcf'`, `'ttf'`, `'svg'`) is
        taken from `format` or from the file extension; `opts` are passed to the
        writer (`topcf`, `tottf`, `tosvgfont`).

        https://font.tomchen.org/bdfparser_py/font#save
        """

        fmt = (format or os.path.splitext(os.fspath(path))[1].lstrip('.')).lower()
        if fmt == 'bdf':
            data = self.tobdf().encode('utf-8')
        elif fmt == 'pcf':
            data = self.topcf(**opts)
        elif fmt == 'ttf':
            data = self.tottf(**opts)
        elif fmt == 'svg':
            data = self.tosvgfont(**opts).encode('utf-8')
        else:
            raise ValueError(f'Unknown output format {fmt!r} (use bdf, pcf, ttf or svg)')
        with open(path, 'wb') as f:
            f.write(data)
        return self
