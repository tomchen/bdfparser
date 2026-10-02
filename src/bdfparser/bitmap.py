"""
`Bitmap` object

https://font.tomchen.org/bdfparser_py/bitmap
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from typing import Literal

from .errors import BDFParserWarning

__all__ = ['Bitmap', 'fmtnum']

_FROMSTRING_MAP = {'#': '1', '.': '0', '&': '2', '0': '0', '1': '1', '2': '2'}


def fmtnum(n: float) -> str:
    """
    Format a number for text output: the integer string if `n` is integral,
    otherwise the shortest round-trip representation.
    """

    if isinstance(n, bool):
        n = int(n)
    if isinstance(n, int):
        return str(n)
    f = float(n)
    if f.is_integer():
        return str(int(f))
    return repr(f)


class Bitmap:
    """
    `Bitmap` object

    `bindata` is a `list` of equal-length `str`s of `'0'`, `'1'` (and `'2'`), row 0
    at the top.

    Two coordinate conventions are used:

    - pixel addressing (`getpixel`, `setpixel`, `paste`): `(x, y)` with the origin
      at the top-left, y grows downward (`bindata[y][x]`);
    - movement / cropping (`crop`, `shadow`, `shift`, `bbox`): x grows right, y
      grows upward, offsets are measured from the bottom-left (font convention).

    https://font.tomchen.org/bdfparser_py/bitmap
    """

    def __init__(self, bin_bitmap_list: list[str]) -> None:
        """
        Initialize a `Bitmap` object. Load binary bitmap data (`list` of `str`s).

        https://font.tomchen.org/bdfparser_py/bitmap#bitmap
        """

        self.bindata = bin_bitmap_list

    def __str__(self) -> str:
        """
        Gets a human-readable (multi-line) `str` representation of the `Bitmap` object.

        https://font.tomchen.org/bdfparser_py/bitmap#str-and-print
        """

        return '\n'.join(self.bindata).replace('0', '.').replace('1', '#').replace('2', '&')

    def __repr__(self) -> str:
        """
        Gets a programmer-readable (multi-line) `str` representation of the `Bitmap` object.

        https://font.tomchen.org/bdfparser_py/bitmap#repr
        """

        return "Bitmap(['" + "',\n        '".join(self.bindata) + "'])"

    def __eq__(self, other: object) -> bool:
        """
        Two bitmaps are equal if their `bindata` are equal.

        https://font.tomchen.org/bdfparser_py/bitmap#equals
        """

        if not isinstance(other, Bitmap):
            return NotImplemented
        return list(self.bindata) == list(other.bindata)

    __hash__ = None  # type: ignore[assignment]

    def equals(self, other: Bitmap) -> bool:
        """
        Same as `==`.

        https://font.tomchen.org/bdfparser_py/bitmap#equals
        """

        return self == other

    @classmethod
    def fromstring(cls, text: str) -> Bitmap:
        """
        Create a `Bitmap` from its `str()` representation (`#` = 1, `.` = 0,
        `&` = 2; the digits `0`, `1`, `2` are also accepted). Rows are separated by
        newlines; empty lines at the start and the end are ignored.

        https://font.tomchen.org/bdfparser_py/bitmap#bitmapfromstring
        """

        lines = text.replace('\r', '').split('\n')
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        rows = []
        for i, line in enumerate(lines):
            try:
                rows.append(''.join(_FROMSTRING_MAP[c] for c in line))
            except KeyError as e:
                raise ValueError(f'Invalid character {e.args[0]!r} in bitmap row {i}') from None
        if rows and any(len(r) != len(rows[0]) for r in rows):
            raise ValueError('Bitmap rows have different lengths')
        return cls(rows)

    @classmethod
    def blank(cls, w: int, h: int) -> Bitmap:
        """
        Create an empty (all `'0'`) bitmap of width `w` and height `h`.

        https://font.tomchen.org/bdfparser_py/bitmap#bitmapblank
        """

        if w < 0 or h < 0:
            raise ValueError('Bitmap size must not be negative')
        return cls(['0' * w for _ in range(h)])

    def width(self) -> int:
        """
        Get the width of the bitmap (`0` for an empty bitmap).

        https://font.tomchen.org/bdfparser_py/bitmap#width
        """

        return len(self.bindata[0]) if self.bindata else 0

    def height(self) -> int:
        """
        Get the height of the bitmap.

        https://font.tomchen.org/bdfparser_py/bitmap#height
        """

        return len(self.bindata)

    def clone(self) -> Bitmap:
        """
        Get a deep copy / clone of the `Bitmap` object.

        https://font.tomchen.org/bdfparser_py/bitmap#clone
        """

        return self.__class__(list(self.bindata))

    @staticmethod
    def __crop_string(s: str, start: int, length: int) -> str:
        stemp = s
        n = len(s)
        left = 0
        if start < 0:
            left = 0 - start
            stemp = stemp.zfill(left + n)
        if start + length > n:
            stemp = stemp.ljust(start + length - n + len(stemp), '0')
        newstart = start + left
        return stemp[newstart : newstart + length]

    @classmethod
    def __string_offset_concat(cls, s1: str, s2: str, offset: int = 0) -> str:
        if offset == 0:
            return s1 + s2
        len1 = len(s1)
        len2 = len(s2)
        s2start = len1 + offset
        s2end = s2start + len2
        finalstart = min(0, s2start)
        finalend = max(len1, s2end)
        news1 = cls.__crop_string(s1, finalstart, finalend - finalstart)
        news2 = cls.__crop_string(s2, finalstart - s2start, finalend - finalstart)
        return ''.join(b if b != '0' else a for a, b in zip(news1, news2, strict=False))

    @staticmethod
    def __listofstr_offset_concat(list1: list[str], list2: list[str], offset: int = 0) -> list[str]:
        if offset == 0:
            return list1 + list2
        width = len(list1[0]) if list1 else len(list2[0]) if list2 else 0
        len1 = len(list1)
        len2 = len(list2)
        s2start = len1 + offset
        s2end = s2start + len2
        finalstart = min(0, s2start)
        finalend = max(len1, s2end)
        retlist = []
        for i in range(finalstart, finalend):
            s1 = '0' * width if i < 0 or i >= len1 else list1[i]
            s2 = '0' * width if i < s2start or i >= s2end else list2[i - s2start]
            retlist.append(''.join(b if b != '0' else a for a, b in zip(s1, s2, strict=False)))
        return retlist

    @classmethod
    def __crop_bitmap(cls, bitmap: list[str], w: int, h: int, xoff: int, yoff: int) -> list[str]:
        retlist = []
        n = len(bitmap)
        for i in range(h):
            bn = n - yoff - h + i
            if bn < 0 or bn >= n:
                retlist.append('0' * w)
            else:
                retlist.append(cls.__crop_string(bitmap[bn], xoff, w))
        return retlist

    def crop(self, w: int, h: int, xoff: int = 0, yoff: int = 0) -> Bitmap:
        """
        Crop and/or extend the bitmap to `w` x `h`; `(xoff, yoff)` is the position of
        the new bitmap's bottom-left corner relative to the current one's (y up).

        Raises `ValueError` if `w` or `h` is negative.

        https://font.tomchen.org/bdfparser_py/bitmap#crop
        """

        if w < 0 or h < 0:
            raise ValueError(f'Bitmap.crop: negative width or height ({w}, {h})')
        self.bindata = self.__crop_bitmap(self.bindata, w, h, xoff, yoff)
        return self

    def overlay(self, bitmap: Bitmap) -> Bitmap:
        """
        Overlay another bitmap over the current one: non-`'0'` pixels of `bitmap`
        win. The size of the current bitmap is kept; `bitmap` is aligned at the
        top-left and clipped, missing pixels count as `'0'` (a warning is
        emitted if the sizes differ).

        https://font.tomchen.org/bdfparser_py/bitmap#overlay
        """

        bindata_a = self.bindata
        bindata_b = bitmap.bindata
        if len(bindata_a) != len(bindata_b):
            warnings.warn(
                'the bitmaps to overlay have different height', BDFParserWarning, stacklevel=2
            )
        if self.width() != bitmap.width():
            warnings.warn(
                'the bitmaps to overlay have different width', BDFParserWarning, stacklevel=2
            )
        # b over a
        out = []
        for i, la in enumerate(bindata_a):
            lb = bindata_b[i] if i < len(bindata_b) else ''
            if len(lb) < len(la):
                lb = lb.ljust(len(la), '0')
            out.append(''.join(b if b != '0' else a for a, b in zip(la, lb, strict=False)))
        self.bindata = out
        return self

    @classmethod
    def concatall(
        cls,
        bitmaplist: Sequence[Bitmap],
        direction: int = 1,
        align: int = 1,
        offsetlist: Sequence[int] | None = None,
    ) -> Bitmap:
        """
        Concatenate all `Bitmap` objects in a `list`.

        https://font.tomchen.org/bdfparser_py/bitmap#bitmapconcatall
        """

        if not bitmaplist:  # e.g. `font.draw('')`: an empty bitmap (as in bdfparser-js)
            return cls([])
        if direction > 0:  # horizontal
            maxsize = max(bitmap.height() for bitmap in bitmaplist)
            ret = [''] * maxsize

            def stroffconcat(s1: str, s2: str, offset: int) -> str:
                if direction == 1:  # right
                    return cls.__string_offset_concat(s1, s2, offset)
                return cls.__string_offset_concat(s2, s1, offset)  # left

            for i in range(maxsize):
                ireal = -i - 1 if align else i  # bottom / top
                offset = 0
                for bi, bitmap in enumerate(bitmaplist):
                    if offsetlist and bi != 0:
                        offset = offsetlist[bi - 1]
                    if i < bitmap.height():
                        ret[ireal] = stroffconcat(ret[ireal], bitmap.bindata[ireal], offset)
                    else:
                        ret[ireal] = stroffconcat(ret[ireal], '0' * bitmap.width(), offset)

        else:  # vertical
            # empty (0-height or 0-width) bitmaps are skipped, together with the
            # offset before them (SPEC-v3 §11.4); the first kept bitmap gets no offset
            kept: list[tuple[Bitmap, int]] = []
            for bi, bitmap in enumerate(bitmaplist):
                if bitmap.height() and bitmap.width():
                    off = offsetlist[bi - 1] if offsetlist and bi != 0 else 0
                    kept.append((bitmap, off if kept else 0))
            if not kept:
                return cls([])
            maxsize = max(bitmap.width() for bitmap, _ in kept)
            ret = []
            for bitmap, offset in kept:
                bd = bitmap.bindata
                w = bitmap.width()
                if w != maxsize:
                    xoff = 0 if align else w - maxsize  # left / right
                    bd = cls.__crop_bitmap(bd, maxsize, bitmap.height(), xoff, 0)
                if direction == 0:  # down
                    ret = cls.__listofstr_offset_concat(ret, bd, offset)
                else:  # up
                    ret = cls.__listofstr_offset_concat(bd, ret, offset)

        return cls(ret)

    def __add__(self, bitmap: Bitmap) -> Bitmap:
        """
        `+` is a shortcut of `Bitmap.concatall()`. Use `+` to concatenate two `Bitmap` objects and get a new `Bitmap` objects.

        https://font.tomchen.org/bdfparser_py/bitmap#-concat
        """

        return self.__class__.concatall([self, bitmap])

    def concat(self, bitmap: Bitmap, direction: int = 1, align: int = 1, offset: int = 0) -> Bitmap:
        """
        Concatenate another `Bitmap` objects to the current one.

        https://font.tomchen.org/bdfparser_py/bitmap#concat
        """

        self.bindata = self.__class__.concatall([self, bitmap], direction, align, [offset]).bindata
        return self

    @staticmethod
    def __enlarge_bindata(bindata: list[str], x: int = 1, y: int = 1) -> list[str]:
        bindata_temp = list(bindata)
        if x > 1:
            bindata_temp = [''.join(p * x for p in row) for row in bindata_temp]
        if y > 1:
            bindata_temp = [row for row in bindata_temp for _ in range(y)]
        return bindata_temp

    def enlarge(self, x: int = 1, y: int = 1) -> Bitmap:
        """
        Enlarge a `Bitmap` object, by multiplying every pixel in x (right) direction and in y (top) direction.

        https://font.tomchen.org/bdfparser_py/bitmap#enlarge
        """

        self.bindata = self.__enlarge_bindata(self.bindata, x, y)
        return self

    def __mul__(self, mul: int | tuple[int, int]) -> Bitmap:
        """
        `*` is a shortcut of `.enlarge()`.

        https://font.tomchen.org/bdfparser_py/bitmap#-enlarge
        """

        if isinstance(mul, int):
            x = y = mul
        else:
            (x, y) = mul
        return self.__class__(self.__enlarge_bindata(self.bindata, x, y))

    def replace(self, substr: str | int, newsubstr: str | int) -> Bitmap:
        """
        Replace a string by another in the bitmap.

        https://font.tomchen.org/bdfparser_py/bitmap#replace
        """

        if isinstance(substr, int):
            substr = str(substr)
        if isinstance(newsubstr, int):
            newsubstr = str(newsubstr)
        self.bindata = [row.replace(substr, newsubstr) for row in self.bindata]
        return self

    def shadow(self, xoff: int = 1, yoff: int = -1) -> Bitmap:
        """
        Add shadow to the shape in the bitmap.

        The shadow will be filled by `'2'`s.

        https://font.tomchen.org/bdfparser_py/bitmap#shadow
        """

        bitmap_shadow = self.clone()
        w = self.width() + abs(xoff)
        h = self.height() + abs(yoff)
        bitmap_shadow.bindata = [row.replace('1', '2') for row in bitmap_shadow.bindata]

        if xoff > 0:
            resized_xoff = 0
            shadow_xoff = -xoff
        else:
            resized_xoff = xoff
            shadow_xoff = 0

        if yoff > 0:
            resized_yoff = 0
            shadow_yoff = -yoff
        else:
            resized_yoff = yoff
            shadow_yoff = 0

        self.crop(w, h, resized_xoff, resized_yoff)
        bitmap_shadow.crop(w, h, shadow_xoff, shadow_yoff)
        bitmap_shadow.overlay(self)
        self.bindata = bitmap_shadow.bindata
        return self

    def glow(self, mode: int = 0) -> Bitmap:
        """
        Add glow effect to the shape in the bitmap.

        The glowing area is one pixel up, right, bottom and left to the original pixels (corners will not be filled in default mode 0 but will in mode 1), and will be filled by `'2'`s.

        https://font.tomchen.org/bdfparser_py/bitmap#glow
        """

        w = self.width() + 2
        h = self.height() + 2
        self.crop(w, h, -1, -1)
        b = self.todata(2)
        for i_line, line in enumerate(b):
            for i_pixel, pixel in enumerate(line):
                if pixel == 1:
                    b[i_line][i_pixel - 1] = b[i_line][i_pixel - 1] or 2
                    b[i_line][i_pixel + 1] = b[i_line][i_pixel + 1] or 2
                    b[i_line - 1][i_pixel] = b[i_line - 1][i_pixel] or 2
                    b[i_line + 1][i_pixel] = b[i_line + 1][i_pixel] or 2
                    if mode == 1:
                        b[i_line - 1][i_pixel - 1] = b[i_line - 1][i_pixel - 1] or 2
                        b[i_line - 1][i_pixel + 1] = b[i_line - 1][i_pixel + 1] or 2
                        b[i_line + 1][i_pixel - 1] = b[i_line + 1][i_pixel - 1] or 2
                        b[i_line + 1][i_pixel + 1] = b[i_line + 1][i_pixel + 1] or 2
        self.bindata = [''.join(str(p) for p in row) for row in b]
        return self

    def bytepad(self, bits: int = 8) -> Bitmap:
        """
        Pad each line (row) to multiple of 8 (or other numbers) bits/pixels, with `'0'`s.

        Do this before using the bitmap for a glyph in a BDF font.

        https://font.tomchen.org/bdfparser_py/bitmap#bytepad
        """

        w = self.width()
        h = self.height()
        mod = w % bits
        if mod == 0:
            return self
        return self.crop(w + bits - mod, h)

    def todata(self, datatype: int = 1) -> str | list:
        """
        Get the bitmap's data in the specified type and format.

        https://font.tomchen.org/bdfparser_py/bitmap#todata
        """

        if datatype == 0:
            return '\n'.join(self.bindata)
        elif datatype == 1:
            return self.bindata
        elif datatype == 2:
            return [[int(p) for p in row] for row in self.bindata]
        elif datatype == 3:
            return [int(p) for row in self.bindata for p in row]
        elif datatype == 4:
            # if there are '2's, it will throw error; zero-width rows give ''
            return [
                hex(int(row, 2))[2:].zfill(-1 * self.width() // 4 * -1) if row else ''
                for row in self.bindata
            ]
        elif datatype == 5:
            # if there are '2's, it will throw error; zero-width rows give 0
            return [int(row, 2) if row else 0 for row in self.bindata]
        raise ValueError(f'Unknown datatype {datatype!r}')

    def tobytes(self, mode: str = 'RGB', bytesdict: dict | None = None) -> bytes:
        """
        Get the bitmap's data as `bytes` to be used with Pillow library's `Image.frombytes(mode, size, data)`.

        https://font.tomchen.org/bdfparser_py/bitmap#tobytes
        """

        if mode == '1':
            if bytesdict is None:
                bytesdict = {0: 1, 1: 0, 2: 0}
            # For PIL Image mode '1', if the line bit count is not multiples of 8, it must be padded with 0 to the right
            bits = []
            w = self.width()
            mod = w % 8
            padcount = 8 - mod
            for row in self.bindata:
                bits.extend(int(p) for p in row)
                if mod != 0:
                    bits.extend(0 for _ in range(padcount))
            octets = (bits[i : i + 8] for i in range(0, len(bits), 8))

            def bits2byte(octet: list[int]) -> int:
                res = 0
                for bit in octet:
                    res <<= 1
                    res |= bytesdict[bit]
                return res

            return bytes(bits2byte(octet) for octet in octets)

        if mode == 'L':
            bytesdict = bytesdict or {0: b'\xff', 1: b'\x00', 2: b'\x7f'}
        elif mode == 'RGBA':
            bytesdict = bytesdict or {
                0: b'\xff\xff\xff\x00',
                1: b'\x00\x00\x00\xff',
                2: b'\xff\x00\x00\xff',
            }
        else:
            if mode != 'RGB':
                warnings.warn('Unknown mode, fallback to RGB', BDFParserWarning, stacklevel=2)
            bytesdict = bytesdict or {
                0: b'\xff\xff\xff',
                1: b'\x00\x00\x00',
                2: b'\xff\x00\x00',
            }
        return b''.join(bytesdict[int(p)] for row in self.bindata for p in row)

    # ------------------------------------------------------------------
    # v3 editing methods

    def __check_xy(self, x: int, y: int) -> None:
        if not (0 <= y < self.height() and 0 <= x < self.width()):
            raise IndexError(
                f'Pixel ({x}, {y}) is out of range of the {self.width()}x{self.height()} bitmap'
            )

    def getpixel(self, x: int, y: int) -> int:
        """
        Get the value (0, 1 or 2) of the pixel at `(x, y)` (top-left origin, y down).

        https://font.tomchen.org/bdfparser_py/bitmap#getpixel
        """

        self.__check_xy(x, y)
        return int(self.bindata[y][x])

    def setpixel(self, x: int, y: int, value: int = 1) -> Bitmap:
        """
        Set the pixel at `(x, y)` (top-left origin, y down) to `value` (0, 1 or 2).

        https://font.tomchen.org/bdfparser_py/bitmap#setpixel
        """

        if value not in (0, 1, 2):
            raise ValueError(f'Pixel value must be 0, 1 or 2, not {value!r}')
        self.__check_xy(x, y)
        row = self.bindata[y]
        self.bindata = list(self.bindata)
        self.bindata[y] = f'{row[:x]}{value}{row[x + 1 :]}'
        return self

    def fliph(self) -> Bitmap:
        """
        Mirror the bitmap left <-> right.

        https://font.tomchen.org/bdfparser_py/bitmap#fliph
        """

        self.bindata = [row[::-1] for row in self.bindata]
        return self

    def flipv(self) -> Bitmap:
        """
        Mirror the bitmap top <-> bottom.

        https://font.tomchen.org/bdfparser_py/bitmap#flipv
        """

        self.bindata = self.bindata[::-1]
        return self

    def rotate(self, angle: int = 90) -> Bitmap:
        """
        Rotate the bitmap clockwise by `angle` degrees (a multiple of 90, may be negative).

        https://font.tomchen.org/bdfparser_py/bitmap#rotate
        """

        if angle % 90 != 0:
            raise ValueError(f'Rotation angle must be a multiple of 90, not {angle!r}')
        turns = (angle // 90) % 4
        for _ in range(turns):
            w = self.width()
            src = self.bindata
            self.bindata = [''.join(row[c] for row in reversed(src)) for c in range(w)]
        return self

    def invert(self) -> Bitmap:
        """
        Invert the bitmap: `'0'` becomes `'1'`, every other pixel becomes `'0'`.

        https://font.tomchen.org/bdfparser_py/bitmap#invert
        """

        self.bindata = [''.join('1' if p == '0' else '0' for p in row) for row in self.bindata]
        return self

    def shift(self, dx: int = 0, dy: int = 0) -> Bitmap:
        """
        Move the content by `dx` pixels to the right and `dy` pixels up, keeping the
        size; vacated pixels become `'0'`.

        https://font.tomchen.org/bdfparser_py/bitmap#shift
        """

        return self.crop(self.width(), self.height(), -dx, -dy)

    def bbox(self) -> tuple[int, int, int, int]:
        """
        Ink bounding box `(w, h, xoff, yoff)` in `crop()` convention (offsets from
        the bottom-left), so `bitmap.crop(*bitmap.bbox())` trims the bitmap.
        `(0, 0, 0, 0)` if there is no ink.

        https://font.tomchen.org/bdfparser_py/bitmap#bbox
        """

        rows = [i for i, row in enumerate(self.bindata) if row.strip('0')]
        if not rows:
            return (0, 0, 0, 0)
        left = min(len(self.bindata[i]) - len(self.bindata[i].lstrip('0')) for i in rows)
        right = max(len(self.bindata[i].rstrip('0')) for i in rows)
        top, bottom = rows[0], rows[-1]
        return (right - left, bottom - top + 1, left, self.height() - 1 - bottom)

    def trim(self) -> Bitmap:
        """
        Remove empty rows and columns on all four sides (`crop(*bbox())`). A bitmap
        without ink becomes empty (`bindata == []`).

        https://font.tomchen.org/bdfparser_py/bitmap#trim
        """

        bb = self.bbox()
        if bb[0] == 0:
            self.bindata = []
            return self
        return self.crop(*bb)

    def bold(self, n: int = 1) -> Bitmap:
        """
        Embolden: the width grows by `n` and the result is the overlay of the bitmap
        shifted right by 0 .. `n` pixels.

        https://font.tomchen.org/bdfparser_py/bitmap#bold
        """

        if n < 0:
            raise ValueError('n must not be negative')
        out = []
        for row in self.bindata:
            padded = row + '0' * n
            cur = list(padded)
            for k in range(1, n + 1):
                for x in range(k, len(padded)):
                    b = row[x - k] if x - k < len(row) else '0'
                    if b != '0':
                        cur[x] = b
            out.append(''.join(cur))
        self.bindata = out
        return self

    def italic(self, step: int = 2, base: int = 0) -> Bitmap:
        """
        Slant the bitmap: the row at index `r` counted from the bottom (0 = bottom
        row) is shifted right by `(r - base) // step` pixels; the bitmap is widened
        as needed.

        https://font.tomchen.org/bdfparser_py/bitmap#italic
        """

        if step <= 0:
            raise ValueError('step must be a positive integer')
        h = self.height()
        if h == 0:
            return self
        w = self.width()
        shifts = [(r - base) // step for r in range(h)]  # r from the bottom
        lo = min(shifts)
        hi = max(shifts)
        nw = w + hi - lo
        out = []
        for i, row in enumerate(self.bindata):
            s = shifts[h - 1 - i] - lo
            out.append('0' * s + row + '0' * (nw - s - w))
        self.bindata = out
        return self

    def paste(self, bitmap: Bitmap, x: int = 0, y: int = 0) -> Bitmap:
        """
        Draw `bitmap` over this one with its top-left corner at `(x, y)` (top-left
        origin, y down). Pixels outside are clipped; non-`'0'` source pixels win.
        The size is unchanged.

        https://font.tomchen.org/bdfparser_py/bitmap#paste
        """

        w = self.width()
        out = list(self.bindata)
        for j, srow in enumerate(bitmap.bindata):
            ty = y + j
            if ty < 0 or ty >= len(out):
                continue
            row = list(out[ty])
            for i, p in enumerate(srow):
                tx = x + i
                if 0 <= tx < w and p != '0':
                    row[tx] = p
            out[ty] = ''.join(row)
        self.bindata = out
        return self

    def tosvg(
        self,
        pixelsize: float = 1,
        format: Literal['path', 'pathOnly', 'rect'] = 'path',
        inverted: bool = False,
        xoff: float = 0,
        yoff: float = 0,
        shape: Literal['square', 'circle'] = 'square',
    ) -> str:
        """
        Convert the bitmap to SVG.

        - `format='path'`: a complete `<svg>` with one `<path>` (all square pixels
          merged into one outline, holes included);
        - `format='pathOnly'`: only the path data (`d` attribute);
        - `format='rect'`: a complete `<svg>` with one `<rect>` per greedy rectangle
          (square only).

        `shape='circle'` draws every pixel as a round dot. `inverted=True` uses y-up
        coordinates (for SVG fonts). `xoff`/`yoff` are added to every coordinate.

        https://font.tomchen.org/bdfparser_py/bitmap#tosvg
        """

        if format not in ('path', 'pathOnly', 'rect'):
            raise ValueError(f'Unknown SVG format {format!r}')
        if shape not in ('square', 'circle'):
            raise ValueError(f'Unknown shape {shape!r}')
        bindata = self.bindata
        h = self.height()
        w = self.width()
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmtnum(w * pixelsize)}"'
            f' height="{fmtnum(h * pixelsize)}">'
        )

        if format == 'rect':
            if shape != 'square':
                raise ValueError("format='rect' only supports shape='square'")
            return head + self.__svgrects(pixelsize, inverted, xoff, yoff) + '</svg>'

        parts: list[str] = []
        if shape == 'circle':
            r = pixelsize / 2
            arc = f'a{fmtnum(r)} {fmtnum(r)} 0 1 0 '
            for rb in range(h):
                row = bindata[h - 1 - rb]
                for c in range(w):
                    if row[c] == '0':
                        continue
                    cx = (c + 0.5) * pixelsize + xoff
                    cy = ((rb + 0.5) if inverted else (h - rb - 0.5)) * pixelsize + yoff
                    parts.append(
                        f'M{fmtnum(cx - r)} {fmtnum(cy)}{arc}{fmtnum(2 * r)} 0{arc}{fmtnum(-2 * r)} 0Z'
                    )
        elif h and w:
            from .outline import bitmap_contours

            for contour in bitmap_contours(bindata, shape='square', dotsize=1, ppu=1):
                pts = [
                    (
                        x * pixelsize + xoff,
                        (y if inverted else h - y) * pixelsize + yoff,
                    )
                    for (x, y, _on) in contour
                ]
                seg = [f'M{fmtnum(pts[0][0])} {fmtnum(pts[0][1])}']
                prev_y = pts[0][1]
                for px, py in pts[1:]:
                    if py == prev_y:
                        seg.append(f'H{fmtnum(px)}')
                    else:
                        seg.append(f'V{fmtnum(py)}')
                    prev_y = py
                seg.append('Z')
                parts.append(''.join(seg))
        d = ''.join(parts)
        if format == 'pathOnly':
            return d
        if not d:
            return head + '</svg>'
        return f'{head}<path d="{d}" fill="#000000" /></svg>'

    def __svgrects(self, pixelsize: float, inverted: bool, xoff: float, yoff: float) -> str:
        bitmap = self.bindata
        height = self.height()
        width = self.width()
        visited = [[False] * width for _ in range(height)]
        svg_height = height * pixelsize
        out = []
        for y in range(height):
            for x in range(width):
                if visited[y][x]:
                    continue
                v = bitmap[y][x]
                mw = 1
                while x + mw < width and bitmap[y][x + mw] == v and not visited[y][x + mw]:
                    mw += 1
                mh = 1
                while y + mh < height and all(
                    bitmap[y + mh][x + dx] == v and not visited[y + mh][x + dx] for dx in range(mw)
                ):
                    mh += 1
                for dy in range(mh):
                    for dx in range(mw):
                        visited[y + dy][x + dx] = True
                if v != '0':
                    rx = x * pixelsize + xoff
                    if inverted:
                        ry = svg_height - y * pixelsize - mh * pixelsize + yoff
                    else:
                        ry = y * pixelsize + yoff
                    out.append(
                        f'<rect x="{fmtnum(rx)}" y="{fmtnum(ry)}" width="{fmtnum(mw * pixelsize)}"'
                        f' height="{fmtnum(mh * pixelsize)}" fill="#000000" />'
                    )
        return ''.join(out)
