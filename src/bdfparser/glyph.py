"""
`Glyph` object

https://font.tomchen.org/bdfparser_py/glyph
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from .bitmap import Bitmap
from .errors import _warn

if TYPE_CHECKING:
    from .font import Font

__all__ = ['Glyph', 'defaultglyphname', 'META_TITLES']

META_TITLES = (
    'glyphname',
    'codepoint',
    'bbw',
    'bbh',
    'bbxoff',
    'bbyoff',
    'swx0',
    'swy0',
    'dwx0',
    'dwy0',
    'swx1',
    'swy1',
    'dwx1',
    'dwy1',
    'vvectorx',
    'vvectory',
    'hexdata',
)


def defaultglyphname(cp: int, charset_is_unicode: bool = True) -> str:
    """
    Default glyph name for a codepoint: `uniXXXX` (cp <= 0xFFFF) / `uXXXXX` /
    `uXXXXXX` (Unicode) or `char{cp}` (other charsets).

    https://font.tomchen.org/bdfparser_py/glyph#defaultglyphname
    """

    if not charset_is_unicode:
        return 'char' + str(cp)
    if cp <= 0xFFFF:
        return f'uni{cp:04X}'
    return f'u{cp:X}' if cp > 0xFFFFF else f'u{cp:05X}'


def _hexrow(row: str, ndigits: int) -> str:
    return format(int(row.ljust(ndigits * 4, '0'), 2), f'0{ndigits}X')


class Glyph:
    """
    `Glyph` object

    A glyph obtained from a font (`glyphbycp`, `glyph`, `iterglyphs`, `newglyph`,
    or passed to `addglyph`) is *attached*: every editing method writes the updated
    meta back into the font immediately. A glyph constructed directly is detached.

    https://font.tomchen.org/bdfparser_py/glyph
    """

    def __init__(self, meta_dict: Mapping[str, Any], font: Font) -> None:
        """
        Initialize a `Glyph` object. Load a `dict` of meta information and the font the glyph belongs.

        https://font.tomchen.org/bdfparser_py/glyph#glyph
        """

        self.meta: dict[str, Any] = dict(meta_dict)
        self.font = font
        self._attached = False
        self._store: list | None = None  # the 17-slot list stored in the font

    def _attach(self, store: list) -> None:
        self._attached = True
        self._store = store

    def _sync(self) -> None:
        if self._attached:
            self.font._writeback(self)

    def __str__(self) -> str:
        """
        Gets a human-readable (multi-line) `str` representation of the `Glyph` object.

        https://font.tomchen.org/bdfparser_py/glyph#str-and-print
        """

        return str(self.draw())

    def __repr__(self) -> str:
        """
        Gets a programmer-readable `str` representation of the `Glyph` object.

        https://font.tomchen.org/bdfparser_py/glyph#repr
        """

        return 'Glyph(' + str(self.meta) + ', ' + str(self.font) + ')'

    def cp(self) -> int:
        """
        Get the codepoint of the glyph.

        https://font.tomchen.org/bdfparser_py/glyph#cp
        """

        return self.meta['codepoint']

    def chr(self) -> str | None:
        """
        Get the character of the glyph (converted with the font's charset);
        `None` if the codepoint is not representable (e.g. unencoded glyphs).

        https://font.tomchen.org/bdfparser_py/glyph#chr
        """

        return self.font.cp2char(self.cp())

    def draw(self, mode: int = 0, bb: tuple[int, int, int, int] | None = None) -> Bitmap:
        """
        Draw the glyph to a `Bitmap` object.

        - `mode=0`: in the font's bounding box (FONTBOUNDINGBOX);
        - `mode=1`: in the glyph's own bounding box (BBX);
        - `mode=2`: the original hex data, including the padding bits;
        - `mode=-1`: in the user specified bounding box `bb` (`(w, h, xoff, yoff)`).

        https://font.tomchen.org/bdfparser_py/glyph#draw
        """

        if mode == 0:
            return self.__draw_fbb()
        if mode == 1:
            return self.__draw_bb()
        if mode == 2:
            return self.__draw_original()
        if mode == -1:
            if bb is None:
                raise ValueError('Parameter bb in draw() method must be set when mode=-1')
            return self.__draw_user_specified(bb)
        raise ValueError(f'Unknown draw mode {mode!r}')

    def __draw_user_specified(self, fbb: tuple[int, int, int, int]) -> Bitmap:
        bbxoff = self.meta.get('bbxoff') or 0
        bbyoff = self.meta.get('bbyoff') or 0
        (fbbx, fbby, fbbxoff, fbbyoff) = fbb
        bitmap = self.__draw_bb()
        return bitmap.crop(fbbx, fbby, -bbxoff + fbbxoff, -bbyoff + fbbyoff)

    def __draw_original(self) -> Bitmap:
        return Bitmap(
            [
                format(int(h, 16), f'0{len(h) * 4}b') if h else ''
                for h in self.meta.get('hexdata') or []
            ]
        )

    def __draw_bb(self) -> Bitmap:
        bbw = self.meta.get('bbw') or 0
        bbh = self.meta.get('bbh') or 0
        bindata = self.__draw_original().bindata
        n = len(bindata)
        if n < bbh:
            _warn(
                f'Glyph "{self.meta.get("glyphname")}" (codepoint {self.meta.get("codepoint")}) '
                f'has {n} bitmap rows but its BBX height is {bbh}; padded with empty rows'
            )
            bindata = bindata + [''] * (bbh - n)
        return Bitmap([b[:bbw].ljust(bbw, '0') for b in bindata[:bbh]])

    def __draw_fbb(self) -> Bitmap:
        fh = self.font.headers
        return self.__draw_user_specified(
            (fh.get('fbbx', 0), fh.get('fbby', 0), fh.get('fbbxoff', 0), fh.get('fbbyoff', 0))
        )

    def origin(
        self,
        mode: int = 0,
        fromorigin: bool = False,
        xoff: int | None = None,
        yoff: int | None = None,
    ) -> tuple[int, int]:
        """
        Get the relative position (displacement) of the origin from the left bottom corner of the bitmap drawn by the method `.draw()`, or vice versa.

        https://font.tomchen.org/bdfparser_py/glyph#origin
        """

        bbxoff = self.meta.get('bbxoff')
        bbyoff = self.meta.get('bbyoff')
        if mode == 0:
            fh = self.font.headers
            ret = (fh['fbbxoff'], fh['fbbyoff'])
        elif mode in (1, 2):
            ret = (bbxoff, bbyoff)
        elif mode == -1:
            if xoff is None or yoff is None:
                raise ValueError(
                    'Parameter xoff and yoff in origin() method must be all set when mode=-1'
                )
            ret = (xoff, yoff)
        else:
            raise ValueError(f'Unknown origin mode {mode!r}')
        return ret if fromorigin else (0 - ret[0], 0 - ret[1])

    # ------------------------------------------------------------------
    # v3 editing methods

    def setbitmap(
        self,
        bitmap: Bitmap,
        mode: int = 0,
        bb: tuple[int, int, int, int] | None = None,
        trim: bool = True,
    ) -> Glyph:
        """
        Set the glyph's bitmap (inverse of `draw()`). The bitmap's bottom-left
        corner is placed, relative to the glyph origin, at: `mode=0` the font's
        `(fbbxoff, fbbyoff)`; `mode=1`/`2` the glyph's current `(bbxoff, bbyoff)`;
        `mode=-1` `(bb[2], bb[3])`. With `trim` (default), empty rows and columns
        are removed on all four sides. Any non-`'0'` pixel is ink. DWIDTH / SWIDTH
        are not changed.

        https://font.tomchen.org/bdfparser_py/glyph#setbitmap
        """

        bindata = bitmap.bindata if isinstance(bitmap, Bitmap) else list(bitmap)
        if mode == 0:
            fh = self.font.headers
            xoff, yoff = fh.get('fbbxoff', 0), fh.get('fbbyoff', 0)
        elif mode in (1, 2):
            xoff, yoff = self.meta.get('bbxoff') or 0, self.meta.get('bbyoff') or 0
        elif mode == -1:
            if bb is None:
                raise ValueError('Parameter bb in setbitmap() method must be set when mode=-1')
            xoff, yoff = bb[2], bb[3]
        else:
            raise ValueError(f'Unknown setbitmap mode {mode!r}')

        rows = [''.join('0' if p == '0' else '1' for p in row) for row in bindata]
        h = len(rows)
        w = len(rows[0]) if rows else 0
        if any(len(r) != w for r in rows):
            raise ValueError('Bitmap rows have different lengths')
        if trim:
            ink = [i for i, r in enumerate(rows) if '1' in r]
            if not ink:
                rows, w, xoff, yoff = [], 0, 0, 0
            else:
                top, bottom = ink[0], ink[-1]
                left = min(r.find('1') for r in rows[top : bottom + 1] if '1' in r)
                right = max(r.rfind('1') for r in rows[top : bottom + 1]) + 1
                rows = [r[left:right] for r in rows[top : bottom + 1]]
                xoff += left
                yoff += h - 1 - bottom
                w = right - left
        ndigits = -(-w // 8) * 2
        self.meta['bbw'] = w
        self.meta['bbh'] = len(rows)
        self.meta['bbxoff'] = xoff
        self.meta['bbyoff'] = yoff
        self.meta['hexdata'] = [_hexrow(r, ndigits) for r in rows] if w else []
        self._sync()
        return self

    def setmeta(self, obj: Mapping[str, Any] | None = None, /, **kwargs: Any) -> Glyph:
        """
        Set any of the 17 meta keys, e.g. `glyph.setmeta(dwx0=8, glyphname='A')` or
        `glyph.setmeta({'codepoint': 65})`. Unknown keys raise `KeyError`.
        Changing the codepoint of an attached glyph moves it in the font
        (overwriting a glyph already at the destination).

        https://font.tomchen.org/bdfparser_py/glyph#setmeta
        """

        items = dict(obj or {})
        items.update(kwargs)
        for k in items:
            if k not in META_TITLES:
                raise KeyError(f'Unknown glyph meta key {k!r}')
        for k, v in items.items():
            self.meta[k] = list(v) if k == 'hexdata' and v is not None else v
        self._sync()
        return self

    def shift(self, dx: int = 0, dy: int = 0) -> Glyph:
        """
        Move the glyph's bitmap relative to the origin: `bbxoff += dx`,
        `bbyoff += dy` (y up).

        https://font.tomchen.org/bdfparser_py/glyph#shift
        """

        self.meta['bbxoff'] = (self.meta.get('bbxoff') or 0) + dx
        self.meta['bbyoff'] = (self.meta.get('bbyoff') or 0) + dy
        self._sync()
        return self

    def transform(self, fn: Callable[[Bitmap], Bitmap | None], mode: int = 0) -> Glyph:
        """
        Draw the glyph (`draw(mode)`), pass the bitmap to `fn` and set the result
        (or the bitmap itself if `fn` returns `None`, i.e. mutated it in place)
        back with `setbitmap(..., mode)`.

        https://font.tomchen.org/bdfparser_py/glyph#transform
        """

        bm = self.draw(mode)
        res = fn(bm)
        return self.setbitmap(res if res is not None else bm, mode)

    def clone(self) -> Glyph:
        """
        Get a deep copy of the glyph (same font, detached).

        https://font.tomchen.org/bdfparser_py/glyph#clone
        """

        meta = dict(self.meta)
        if meta.get('hexdata') is not None:
            meta['hexdata'] = list(meta['hexdata'])
        return Glyph(meta, self.font)
