"""Tests for bdfparser.outline (SPEC-v3 §7.1, §7.2, §7.4)."""

from __future__ import annotations

import random

import pytest

from bdfparser.outline import D, K, bitmap_contours, rasterize


def B(text: str) -> list[str]:
    """Bitmap from '#'/'.' picture (top row first)."""
    return [row.replace('#', '1').replace('.', '0') for row in text.strip().split()]


def signed_area2(contour) -> int:
    """Twice the signed area (shoelace, y up): clockwise ⇒ negative."""
    s = 0
    n = len(contour)
    for i in range(n):
        x0, y0, _ = contour[i]
        x1, y1, _ = contour[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s


def P(*pts) -> list[tuple[int, int, bool]]:
    return [(x, y, True) for x, y in pts]


def assert_axis_aligned_minimal(contour):
    """Every edge is axis aligned, directions alternate (no collinear points)."""
    n = len(contour)
    assert n >= 4 and n % 2 == 0
    for i in range(n):
        x0, y0, on = contour[i]
        x1, y1, _ = contour[(i + 1) % n]
        x2, y2, _ = contour[(i + 2) % n]
        assert on is True
        assert (x0 == x1) != (y0 == y1), 'edge must be horizontal or vertical, non-empty'
        # consecutive edges must change orientation (else the middle point is collinear)
        assert (x0 == x1) != (x1 == x2)


# ---------------------------------------------------------------------------
# §7.1 merged square outline, hand-checked


class TestMergedHandChecked:
    def test_empty(self):
        assert bitmap_contours([]) == []
        assert bitmap_contours(['000', '000']) == []
        assert bitmap_contours(['']) == []

    def test_single_pixel(self):
        assert bitmap_contours(['1']) == [P((0, 0), (0, 1), (1, 1), (1, 0))]

    def test_single_pixel_scaled_and_offset(self):
        assert bitmap_contours(['1'], ppu=64, xoff=2, yoff=-3) == [
            P((128, -192), (128, -128), (192, -128), (192, -192))
        ]

    def test_ink_values(self):
        # '2' counts as ink, like '1'
        assert bitmap_contours(['2']) == bitmap_contours(['1'])

    def test_2x2_block(self):
        assert bitmap_contours(['11', '11']) == [P((0, 0), (0, 2), (2, 2), (2, 0))]

    def test_ring_with_hole(self):
        res = bitmap_contours(B('### #.# ###'))
        assert res == [
            P((0, 0), (0, 3), (3, 3), (3, 0)),
            P((1, 1), (2, 1), (2, 2), (1, 2)),
        ]
        assert signed_area2(res[0]) == -18  # outer: clockwise
        assert signed_area2(res[1]) == 2  # hole: counter-clockwise

    def test_diagonal_touching_two_contours(self):
        # '/' diagonal: bottom-left + top-right
        assert bitmap_contours(B('.# #.')) == [
            P((0, 0), (0, 1), (1, 1), (1, 0)),
            P((1, 1), (1, 2), (2, 2), (2, 1)),
        ]
        # '\' diagonal: bottom-right + top-left
        assert bitmap_contours(B('#. .#')) == [
            P((1, 0), (1, 1), (2, 1), (2, 0)),
            P((0, 1), (0, 2), (1, 2), (1, 1)),
        ]

    def test_checkerboard(self):
        bm = B('#.#. .#.# #.#. .#.#')
        res = bitmap_contours(bm)
        assert len(res) == 8  # every pixel is its own contour
        for c in res:
            assert len(c) == 4
            assert signed_area2(c) == -2
        # emission order: rows bottom → top, columns left → right
        starts = [c[0][:2] for c in res]
        assert starts == [(1, 0), (3, 0), (0, 1), (2, 1), (1, 2), (3, 2), (0, 3), (2, 3)]

    def test_c_touching_diagonally(self):
        # a "C" whose two ends touch diagonally at (2, 1): the cavity is not a
        # hole (background is 8-connected), so there is one contour visiting
        # the pinch vertex twice
        res = bitmap_contours(B('### #.# ##.'))
        assert res == [
            P(
                (0, 0),
                (0, 3),
                (3, 3),
                (3, 1),
                (2, 1),
                (2, 2),
                (1, 2),
                (1, 1),
                (2, 1),
                (2, 0),
            )
        ]
        assert signed_area2(res[0]) == -2 * 7

    def test_ring_touching_diagonally_inner(self):
        # hole whose pixels touch diagonally: one hole contour (pinched)
        res = bitmap_contours(B('#### #.## ##.# ####'))
        assert len(res) == 2
        outer, hole = res
        assert outer == P((0, 0), (0, 4), (4, 4), (4, 0))
        assert signed_area2(hole) == 2 * 2
        assert sorted(hole) == sorted(
            P((2, 1), (3, 1), (3, 2), (2, 2), (2, 2), (1, 2), (1, 3), (2, 3))
        )
        assert hole[0] == (2, 1, True)

    def test_two_separate_rings_and_island(self):
        bm = B('##### #...# #.#.# #...# #####')
        res = bitmap_contours(bm)
        assert len(res) == 3
        assert signed_area2(res[0]) < 0  # outer
        assert signed_area2(res[1]) > 0  # hole
        assert signed_area2(res[2]) < 0  # island inside hole
        assert res[2] == P((2, 2), (2, 3), (3, 3), (3, 2))

    def test_l_shape_minimal(self):
        res = bitmap_contours(B('#.. #.. ###'))
        assert res == [P((0, 0), (0, 3), (1, 3), (1, 1), (3, 1), (3, 0))]

    def test_plus_shape(self):
        res = bitmap_contours(B('.#. ### .#.'))
        assert len(res) == 1 and len(res[0]) == 12
        assert res[0][0] == (1, 0, True)
        assert signed_area2(res[0]) == -10

    def test_rotation_starts_at_min_yx(self):
        # first edge emitted is the bottom edge of (2, 0); after rotation the
        # contour starts at the lowest-then-leftmost vertex
        res = bitmap_contours(B('### ..#'))
        assert res[0][0] == (2, 0, True)
        for c in bitmap_contours(B('.##.# ##.## #.###')):
            m = min((y, x) for x, y, _ in c)
            assert (c[0][1], c[0][0]) == m

    def test_uneven_rows_tolerated(self):
        assert bitmap_contours(['1', '11']) == bitmap_contours(['10', '11'])


# ---------------------------------------------------------------------------
# §7.2 separate dots


class TestDots:
    def test_square_dot_06(self):
        res = bitmap_contours(['1'], 'square', 0.6, 10)
        # cx = cy = 5, s = 3
        assert res == [P((2, 2), (2, 8), (8, 8), (8, 2))]

    def test_square_dot_rounding(self):
        # s = 0.5 * 2 / 2 = 0.5; cx = 1 → 0.5 → round = 1 (floor(v + 0.5)), 1.5 → 2
        assert bitmap_contours(['1'], 'square', 0.5, 2) == [P((1, 1), (1, 2), (2, 2), (2, 1))]

    def test_square_dot_negative_offsets(self):
        # floor(v + 0.5) rounding, not banker's: cx - s = -2.5 → -2
        assert bitmap_contours(['1'], 'square', 0.5, 2, xoff=-2, yoff=-2) == [
            P((-3, -3), (-3, -2), (-2, -2), (-2, -3))
        ]

    def test_square_dot_order_and_direction(self):
        res = bitmap_contours(B('#. ##'), 'square', 0.8, 10)
        assert [c[0][:2] for c in res] == [(1, 1), (11, 1), (1, 11)]
        for c in res:
            assert signed_area2(c) < 0

    def test_square_big_dots_overlap_not_merged(self):
        res = bitmap_contours(['11'], 'square', 1.5, 4)
        assert len(res) == 2

    def test_circle(self):
        res = bitmap_contours(['1'], 'circle', 1.0, 64)
        r = 32 * K
        exp = [
            (32 + r * dx, 32 + r * dy)
            for dx, dy in [(0, 1), (D, D), (1, 0), (D, -D), (0, -1), (-D, -D), (-1, 0), (-D, D)]
        ]
        import math

        assert res == [[(math.floor(x + 0.5), math.floor(y + 0.5), False) for x, y in exp]]
        assert res == [
            [
                (32, 67, False),
                (56, 56, False),
                (67, 32, False),
                (56, 8, False),
                (32, -3, False),
                (8, 8, False),
                (-3, 32, False),
                (8, 56, False),
            ]
        ]
        assert signed_area2(res[0]) < 0

    def test_circle_dotsize_one_is_not_merged(self):
        assert len(bitmap_contours(['11'], 'circle', 1.0, 8)) == 2

    @pytest.mark.parametrize('dotsize', [0, -1, 1.5000001, 2, float('nan')])
    def test_bad_dotsize(self, dotsize):
        with pytest.raises(ValueError):
            bitmap_contours(['1'], 'square', dotsize)

    def test_bad_shape_ppu(self):
        with pytest.raises(ValueError):
            bitmap_contours(['1'], 'triangle')
        with pytest.raises(ValueError):
            bitmap_contours(['1'], ppu=0)
        with pytest.raises(ValueError):
            bitmap_contours(['1'], ppu=1.5)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            bitmap_contours(['1'], dotsize='1')  # type: ignore[arg-type]

    def test_dotsize_15_ok(self):
        assert len(bitmap_contours(['1'], 'circle', 1.5, 2)) == 1


# ---------------------------------------------------------------------------
# §7.4 rasterizer


class TestRasterize:
    def test_square(self):
        c = bitmap_contours(['1'], ppu=4)
        assert rasterize(c, 4, 0, 0, 1, 1) == ['1']
        assert rasterize(c, 4, -1, -1, 3, 3) == ['000', '010', '000']

    def test_empty(self):
        assert rasterize([], 4, 0, 0, 2, 1) == ['00']
        assert rasterize([], 4, 0, 0, 0, 0) == []
        assert rasterize([[(0, 0, True)]], 1, 0, 0, 1, 1) == ['0']

    def test_hole(self):
        bm = B('### #.# ###')
        assert rasterize(bitmap_contours(bm, ppu=2), 2, 0, 0, 3, 3) == bm

    def test_nonzero_winding_overlap(self):
        # two overlapping clockwise squares: overlap stays ink (winding 2)
        a = P((0, 0), (0, 2), (2, 2), (2, 0))
        b = P((1, 0), (1, 2), (3, 2), (3, 0))
        assert rasterize([a, b], 1, 0, 0, 3, 2) == ['111', '111']
        # opposite direction cancels
        rb = list(reversed(b))
        assert rasterize([a, rb], 1, 0, 0, 3, 2) == ['101', '101']

    def test_half_open_boundaries(self):
        # centre exactly on the left/bottom edge is inside, on the right/top edge outside
        sq = P((0, 0), (0, 1), (1, 1), (1, 0))
        assert rasterize([sq], 2, 0, 0, 1, 1) == ['0']  # centre (1, 1) = top-right corner
        sq2 = P((1, 1), (1, 3), (3, 3), (3, 1))
        assert rasterize([sq2], 2, 0, 0, 2, 2) == ['00', '10']

    def test_quadratic_and_implied(self):
        # all off-curve contour (implied on-curve midpoints) = circle dot
        c = bitmap_contours(['1'], 'circle', 1.0, 64)
        assert rasterize(c, 64, 0, 0, 1, 1) == ['1']
        # mixed on/off: a quarter-disc-ish shape
        q = [(0, 0, True), (0, 10, True), (10, 10, False), (10, 0, True)]
        assert rasterize([q], 1, 0, 0, 10, 10)[-1] == '1' * 10

    def test_float_ppu(self):
        c = bitmap_contours(B('#. .#'), ppu=3)
        # ppu 1.5: twice the resolution
        assert rasterize(c, 1.5, 0, 0, 4, 4) == ['1100', '1100', '0011', '0011']


# ---------------------------------------------------------------------------
# property tests


def random_bitmap(rng: random.Random) -> list[str]:
    w = rng.randint(1, 12)
    h = rng.randint(1, 12)
    density = rng.choice([0.1, 0.3, 0.5, 0.7, 0.9])
    return [''.join('1' if rng.random() < density else '0' for _ in range(w)) for _ in range(h)]


CASES = [
    ('square', 1.0, [1, 2, 3, 64]),
    ('square', 0.6, [2, 5, 8, 64]),
    ('square', 0.5, [4, 10, 64]),
    ('square', 1.5, [2, 4, 64]),
    ('circle', 1.0, [2, 4, 7, 64]),
    ('circle', 0.6, [4, 10, 64]),
    ('circle', 0.5, [8, 20, 64]),
    ('circle', 1.5, [4, 16, 64]),
]


@pytest.mark.parametrize('shape,dotsize,ppus', CASES)
def test_property_rasterize_inverse(shape, dotsize, ppus):
    rng = random.Random(f'{shape}-{dotsize}')
    for i in range(500):
        bm = random_bitmap(rng)
        ppu = ppus[i % len(ppus)]
        xoff = rng.randint(-5, 5)
        yoff = rng.randint(-5, 5)
        cs = bitmap_contours(bm, shape, dotsize, ppu, xoff, yoff)
        got = rasterize(cs, ppu, xoff, yoff, len(bm[0]), len(bm))
        assert got == bm, (shape, dotsize, ppu, bm)


def test_property_merged_outline():
    rng = random.Random(20261002)
    for _ in range(600):
        bm = random_bitmap(rng)
        ppu = rng.choice([1, 2, 64])
        cs = bitmap_contours(bm, ppu=ppu)
        ink = sum(row.count('1') for row in bm)
        # union area (holes negative, outer clockwise ⇒ negative shoelace)
        assert -sum(signed_area2(c) for c in cs) == 2 * ink * ppu * ppu
        for c in cs:
            assert_axis_aligned_minimal(c)
            assert all(x % ppu == 0 and y % ppu == 0 for x, y, _ in c)
            # rotation rule: first vertex is a minimal (y, x)
            assert (c[0][1], c[0][0]) == min((y, x) for x, y, _ in c)
            # the vertex is visited at most twice (pinch points)
            pts = [p[:2] for p in c]
            assert all(pts.count(p) <= 2 for p in pts)
        # minimal point count: each corner of the union is exactly one point.
        corners = 0
        g = [[ch == '1' for ch in row] for row in reversed(bm)]
        h, w = len(g), len(g[0])

        def ink_at(cc, rr, g=g, h=h, w=w):
            return 0 <= rr < h and 0 <= cc < w and g[rr][cc]

        for vy in range(h + 1):
            for vx in range(w + 1):
                q = [ink_at(vx - 1, vy - 1), ink_at(vx, vy - 1), ink_at(vx - 1, vy), ink_at(vx, vy)]
                n = sum(q)
                if n in (1, 3):
                    corners += 1
                elif n == 2 and q[0] == q[3]:  # diagonal pinch: 2 corners
                    corners += 2
        assert sum(len(c) for c in cs) == corners


def test_property_contour_count():
    """Contours = 4-connected ink components + 8-connected background holes."""
    rng = random.Random(7)
    for _ in range(300):
        bm = random_bitmap(rng)
        h, w = len(bm), len(bm[0])
        ink = {(c, r) for r, row in enumerate(bm) for c, ch in enumerate(row) if ch == '1'}

        def components(cells, nbrs):
            seen, n = set(), 0
            for s in cells:
                if s in seen:
                    continue
                n += 1
                stack = [s]
                seen.add(s)
                while stack:
                    x, y = stack.pop()
                    for dx, dy in nbrs:
                        q = (x + dx, y + dy)
                        if q in cells and q not in seen:
                            seen.add(q)
                            stack.append(q)
            return n

        n4 = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        n8 = n4 + [(1, 1), (1, -1), (-1, 1), (-1, -1)]
        bg = {(c, r) for r in range(-1, h + 1) for c in range(-1, w + 1)} - ink
        holes = components(bg, n8) - 1  # minus the outside
        cs = bitmap_contours(bm)
        assert len(cs) == components(ink, n4) + holes
        outer = [c for c in cs if signed_area2(c) < 0]
        assert len(outer) == components(ink, n4)
