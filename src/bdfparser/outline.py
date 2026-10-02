"""
Bitmap → outline conversion and outline → bitmap rasterization (SPEC-v3 §7).

Coordinates are font units, y grows **upward**. A pixel is ``ppu × ppu``
units. ``bitmap_contours`` turns a bitmap (``bindata``, top row first) into
TrueType-style contours (lists of ``(x, y, oncurve)`` with integer ``x, y``);
``rasterize`` is its exact inverse (pixel-centre sampling, non-zero winding).

Implementation notes (choices where SPEC-v3 §7 leaves room; the TypeScript
port MUST make the same choices):

- §7.1 tracing: "follow edges until returning to its start vertex". Because the
  first unused edge in emission order can never start at a vertex that its
  contour visits twice (both incoming edges at such a pinch vertex are emitted
  earlier), this is equivalent to "follow until no unused outgoing edge is
  left" — both give the same contours.
- §7.1 rotation: ties of the minimal ``(y, x)`` vertex (only possible at pinch
  vertices) are broken by the first occurrence in traced order, the traced
  order starting at the start vertex of the start edge (after removal of
  collinear vertices).
- §7.2 floating point evaluation order (IEEE double, identical in JS):
  ``cx = (xoff + c + 0.5) * ppu`` (left-to-right), ``s = dotsize * ppu / 2``,
  square corners ``round(cx - s)`` / ``round(cx + s)``, circle
  ``R = (dotsize * ppu / 2) * K`` and point ``round(cx + R * dx)``; ``round(v)``
  is ``floor(v + 0.5)``.
- ``bindata`` rows of different lengths are tolerated: a missing character
  counts as not ink. ``ppu`` must be a positive ``int`` (contour coordinates
  must be integers); ``dotsize`` must be in ``(0, 1.5]``; ``shape`` must be
  ``'square'`` or ``'circle'`` (else ``ValueError``).
- §7.4 crossing test: the ray goes from the pixel centre ``(X, Y)`` towards
  ``+x``; an edge with ``min(y0, y1) <= Y < max(y0, y1)`` is crossed iff its
  intersection ``x0 + (Y - y0) * (x1 - x0) / (y1 - y0)`` is ``> X`` (strictly;
  so a centre lying exactly on a left/bottom boundary is inside, on a
  right/top boundary outside). Upward edges count +1, downward −1. Quadratic
  segments ``P0, P1 (off), P2`` are flattened into the 16 chords between
  ``B(i/16)``, ``i = 0..16``, with ``B(t) = (1-t)²·P0 + 2(1-t)t·P1 + t²·P2``
  evaluated as ``mt*mt*p0 + 2*mt*t*p1 + t*t*p2`` with ``mt = 1 - t``
  (``B(0)``/``B(16/16)`` taken as exactly ``P0``/``P2``). A contour made only of
  off-curve points starts at the midpoint of its last and first point.
  Contours with fewer than 2 points are ignored.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Iterable, Iterator, Sequence

__all__ = ['bitmap_contours', 'rasterize', 'Contour', 'Point']

Point = tuple[int, int, bool]
Contour = list[Point]

#: 1 / cos(22.5°)
K = 1.082392200292394
#: cos(45°)
D = 0.7071067811865476
_CIRCLE_DIRS = (
    (0.0, 1.0),
    (D, D),
    (1.0, 0.0),
    (D, -D),
    (0.0, -1.0),
    (-D, -D),
    (-1.0, 0.0),
    (-D, D),
)
_FLATTEN_STEPS = 16


def _round(v: float) -> int:
    return math.floor(v + 0.5)


def _check_args(shape: str, dotsize: float, ppu: int) -> None:
    if shape not in ('square', 'circle'):
        raise ValueError(f"shape must be 'square' or 'circle', not {shape!r}")
    if isinstance(dotsize, bool) or not isinstance(dotsize, (int, float)):
        raise ValueError(f'dotsize must be a number in (0, 1.5], not {dotsize!r}')
    if not (0 < dotsize <= 1.5):
        raise ValueError(f'dotsize must be in (0, 1.5], not {dotsize!r}')
    if isinstance(ppu, bool) or not isinstance(ppu, int) or ppu < 1:
        raise ValueError(f'ppu must be a positive integer, not {ppu!r}')


def _ink_rows(bindata: Sequence[str]) -> list[list[bool]]:
    """Rows bottom → top as lists of booleans (``True`` = ink)."""
    return [[ch != '0' for ch in row] for row in reversed(bindata)]


def _merged_contours(rows: list[list[bool]], ppu: int, xoff: int, yoff: int) -> list[Contour]:
    def ink(c: int, r: int) -> bool:
        if r < 0 or r >= len(rows) or c < 0:
            return False
        row = rows[r]
        return c < len(row) and row[c]

    # 1. Edge generation (emission order); edge = (sx, sy, dx, dy)
    edges: list[tuple[int, int, int, int]] = []
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            if not v:
                continue
            if not ink(c, r - 1):
                edges.append((c + 1, r, -1, 0))  # bottom
            if not ink(c - 1, r):
                edges.append((c, r, 0, 1))  # left
            if not ink(c, r + 1):
                edges.append((c, r + 1, 1, 0))  # top
            if not ink(c + 1, r):
                edges.append((c + 1, r + 1, 0, -1))  # right
    if not edges:
        return []

    outgoing: dict[tuple[int, int], list[int]] = {}
    for i, (sx, sy, _, _) in enumerate(edges):
        outgoing.setdefault((sx, sy), []).append(i)
    used = bytearray(len(edges))

    contours: list[Contour] = []
    first = 0
    n = len(edges)
    while True:
        while first < n and used[first]:
            first += 1
        if first >= n:
            break
        # 2. Tracing
        start = edges[first]
        startv = (start[0], start[1])
        walk: list[int] = [first]
        used[first] = 1
        sx, sy, dx, dy = start
        x, y = sx + dx, sy + dy
        while (x, y) != startv:
            cands = outgoing[(x, y)]
            chosen = -1
            # right turn, straight, left turn (y-up coordinates)
            for want in ((dy, -dx), (dx, dy), (-dy, dx)):
                for ei in cands:
                    if not used[ei] and (edges[ei][2], edges[ei][3]) == want:
                        chosen = ei
                        break
                if chosen >= 0:
                    break
            if chosen < 0:  # pragma: no cover - impossible for a valid edge set
                raise RuntimeError('outline tracing failed')
            used[chosen] = 1
            walk.append(chosen)
            _, _, dx, dy = edges[chosen]
            x, y = x + dx, y + dy
        # 3. Simplification
        m = len(walk)
        verts: list[tuple[int, int]] = []
        for k in range(m):
            e = edges[walk[k]]
            p = edges[walk[k - 1]]
            if (p[2], p[3]) != (e[2], e[3]):
                verts.append((e[0], e[1]))
        # 4. Rotation
        best = 0
        for k in range(1, len(verts)):
            vx, vy = verts[k]
            bx, by = verts[best]
            if vy < by or (vy == by and vx < bx):
                best = k
        verts = verts[best:] + verts[:best]
        # 5. Scale
        contours.append([((xoff + vx) * ppu, (yoff + vy) * ppu, True) for vx, vy in verts])
    return contours


def _dot_contours(
    rows: list[list[bool]],
    shape: str,
    dotsize: float,
    ppu: int,
    xoff: int,
    yoff: int,
) -> list[Contour]:
    contours: list[Contour] = []
    s = dotsize * ppu / 2
    rr = (dotsize * ppu / 2) * K
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            if not v:
                continue
            cx = (xoff + c + 0.5) * ppu
            cy = (yoff + r + 0.5) * ppu
            if shape == 'square':
                x0, x1 = _round(cx - s), _round(cx + s)
                y0, y1 = _round(cy - s), _round(cy + s)
                contours.append([(x0, y0, True), (x0, y1, True), (x1, y1, True), (x1, y0, True)])
            else:
                contours.append(
                    [
                        (_round(cx + rr * ddx), _round(cy + rr * ddy), False)
                        for ddx, ddy in _CIRCLE_DIRS
                    ]
                )
    return contours


def bitmap_contours(
    bindata: Sequence[str],
    shape: str = 'square',
    dotsize: float = 1.0,
    ppu: int = 1,
    xoff: int = 0,
    yoff: int = 0,
) -> list[Contour]:
    """
    Convert a bitmap to TrueType-style contours (SPEC-v3 §7.1 / §7.2).

    :param bindata: bitmap rows (strings of ``'0'``/``'1'``/``'2'``), top row
        first; any character other than ``'0'`` is ink.
    :param shape: ``'square'`` (with ``dotsize == 1``: merged minimal outline
        of the union of all pixels, holes included; otherwise one square per
        pixel) or ``'circle'`` (one round dot per pixel, 8 off-curve points).
    :param dotsize: dot size relative to the pixel, in ``(0, 1.5]``.
    :param ppu: font units per pixel (positive int).
    :param xoff: x of the bitmap's bottom-left corner, in pixels.
    :param yoff: y of the bitmap's bottom-left corner, in pixels (y up).
    :returns: list of contours, each a list of ``(x, y, oncurve)``; outer
        contours are clockwise and holes counter-clockwise (y up), as
        TrueType requires.
    """
    _check_args(shape, dotsize, ppu)
    rows = _ink_rows(bindata)
    if shape == 'square' and dotsize == 1:
        return _merged_contours(rows, ppu, xoff, yoff)
    return _dot_contours(rows, shape, dotsize, ppu, xoff, yoff)


def _segments(
    contour: Sequence[tuple[float, float, bool]],
) -> Iterator[tuple[float, ...]]:
    """
    Decode one TrueType contour into segments: ``(x0, y0, x1, y1)`` for lines
    and ``(x0, y0, cx, cy, x1, y1)`` for quadratic curves.
    """
    pts = [(p[0], p[1], bool(p[2])) for p in contour]
    start = -1
    for i, p in enumerate(pts):
        if p[2]:
            start = i
            break
    if start < 0:  # only off-curve points: start at the implied midpoint
        a, b = pts[-1], pts[0]
        seq = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, True), *pts]
    else:
        seq = pts[start:] + pts[:start]
    seq.append(seq[0])  # close
    cx0, cy0 = seq[0][0], seq[0][1]
    ctrl: tuple[float, float] | None = None
    for x, y, on in seq[1:]:
        if on:
            if ctrl is None:
                yield (cx0, cy0, x, y)
            else:
                yield (cx0, cy0, ctrl[0], ctrl[1], x, y)
                ctrl = None
            cx0, cy0 = x, y
        else:
            if ctrl is not None:
                mx, my = (ctrl[0] + x) / 2, (ctrl[1] + y) / 2
                yield (cx0, cy0, ctrl[0], ctrl[1], mx, my)
                cx0, cy0 = mx, my
            ctrl = (x, y)


def _bezier_coefs(steps: int) -> list[tuple[float, float, float]]:
    out = []
    for i in range(1, steps):
        t = i / steps
        mt = 1 - t
        out.append((mt * mt, 2 * mt * t, t * t))
    return out


_COEFS = _bezier_coefs(_FLATTEN_STEPS)


def _flatten_quad(seg: tuple[float, ...]) -> list[tuple[float, float]]:
    """The 17 points ``B(i/16)``, ``i = 0..16`` of a quadratic segment."""
    x0, y0, x1, y1, x2, y2 = seg
    out = [(x0, y0)]
    out += [(a * x0 + b * x1 + c * x2, a * y0 + b * y1 + c * y2) for a, b, c in _COEFS]
    out.append((x2, y2))
    return out


def rasterize(
    contours: Iterable[Sequence[tuple[float, float, bool]]],
    ppu: float,
    xmin_px: int,
    ymin_px: int,
    w_px: int,
    h_px: int,
) -> list[str]:
    """
    Rasterize TrueType quadratic contours to a bitmap (SPEC-v3 §7.4).

    Pixel ``(c, r)`` (``r`` counted from the bottom) is ink iff the non-zero
    winding number at its centre ``((xmin_px + c + 0.5)·ppu,
    (ymin_px + r + 0.5)·ppu)`` is not 0.

    :returns: ``bindata`` (top row first) of ``h_px`` rows × ``w_px`` chars.
    """
    if w_px <= 0 or h_px <= 0:
        return [] if h_px <= 0 else ['' for _ in range(h_px)]
    ys = [(ymin_px + r + 0.5) * ppu for r in range(h_px)]
    xs = [(xmin_px + c + 0.5) * ppu for c in range(w_px)]
    crossings: list[list[tuple[float, int]]] = [[] for _ in range(h_px)]

    def edge(x0: float, y0: float, x1: float, y1: float) -> None:
        if y0 == y1:
            return
        if y0 < y1:
            lo, hi, wdir = y0, y1, 1
        else:
            lo, hi, wdir = y1, y0, -1
        r = bisect_left(ys, lo)  # first centre with lo <= Y
        while r < h_px and ys[r] < hi:
            yy = ys[r]
            crossings[r].append((x0 + (yy - y0) * (x1 - x0) / (y1 - y0), wdir))
            r += 1

    for contour in contours:
        if len(contour) < 2:
            continue
        for seg in _segments(contour):
            if len(seg) == 4:
                edge(*seg)
                continue
            # a quadratic segment lies within the convex hull of its control
            # points: skip flattening when no pixel-centre row is in its y-range
            lo = min(seg[1], seg[3], seg[5])
            hi = max(seg[1], seg[3], seg[5])
            r = bisect_left(ys, lo)
            if r >= h_px or ys[r] > hi:
                continue
            rows = []
            while r < h_px and ys[r] <= hi:
                rows.append(r)
                r += 1
            poly = _flatten_quad(seg)
            for i in range(_FLATTEN_STEPS):
                x0, y0 = poly[i]
                x1, y1 = poly[i + 1]
                if y0 == y1:
                    continue
                if y0 < y1:
                    clo, chi, wdir = y0, y1, 1
                else:
                    clo, chi, wdir = y1, y0, -1
                for rr in rows:
                    yy = ys[rr]
                    if clo <= yy < chi:
                        crossings[rr].append((x0 + (yy - y0) * (x1 - x0) / (y1 - y0), wdir))

    bindata: list[str] = []
    for r in range(h_px - 1, -1, -1):
        cr = crossings[r]
        if not cr:
            bindata.append('0' * w_px)
            continue
        cr.sort(key=lambda t: t[0])
        # winding(X) = sum of wdir over crossings with xi > X
        acc = sum(wd for _, wd in cr)
        row = []
        k = 0
        n = len(cr)
        for xx in xs:
            while k < n and cr[k][0] <= xx:
                acc -= cr[k][1]
                k += 1
            row.append('1' if acc != 0 else '0')
        bindata.append(''.join(row))
    return bindata
