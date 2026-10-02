"""Editing APIs (spec 2.3, 2.4, 2.6, 2.8): Font and Glyph."""

import pytest

from bdfparser import BDFParserWarning, Bitmap, Font, Glyph, defaultglyphname
from bdfparser.glyph import META_TITLES

from .info import bitmap_mini_A_fbb, enctest_path, mini_bdf, unifont_path

pytestmark = pytest.mark.filterwarnings('ignore::bdfparser.BDFParserWarning')


@pytest.fixture
def font():
    return Font().load_string(mini_bdf)


def meta(cp=70, **kw):
    m = {
        'glyphname': 'F',
        'codepoint': cp,
        'bbw': 3,
        'bbh': 2,
        'bbxoff': 1,
        'bbyoff': 0,
        'swx0': 750,
        'swy0': 0,
        'dwx0': 6,
        'dwy0': 0,
        'swx1': None,
        'swy1': None,
        'dwx1': None,
        'dwy1': None,
        'vvectorx': None,
        'vvectory': None,
        'hexdata': ['E0', '80'],
    }
    m.update(kw)
    return m


# ---------------------------------------------------------------------------
# helpers


class TestHelpers:
    def test_defaultglyphname(self):
        assert defaultglyphname(0x41) == 'uni0041'
        assert defaultglyphname(0) == 'uni0000'
        assert defaultglyphname(0xFFFF) == 'uniFFFF'
        assert defaultglyphname(0x1F600) == 'u1F600'
        assert defaultglyphname(0xFFFFF) == 'uFFFFF'
        assert defaultglyphname(0x10FFFF) == 'u10FFFF'
        assert defaultglyphname(0xB0A1, False) == 'char45217'

    def test_swidth(self, font):
        assert font.swidth(6) == 720  # 6 * 72000 / (8 * 75)
        assert font.swidth(5) == 600
        f = Font()
        f.headers = {'fbbx': 16}
        assert f.swidth(8) == 500
        assert Font().swidth(3) == 3000

    def test_swidth_rounding(self):
        f = Font()
        f.headers = {'pointsize': 16, 'xres': 75}
        assert f.swidth(1) == 60  # 60.0
        f.headers = {'pointsize': 26, 'xres': 75}
        assert f.swidth(13) == 480  # 480.0
        assert f.swidth(1) == 37  # 36.92 -> 37


# ---------------------------------------------------------------------------
# Font.create


class TestCreate:
    def test_defaults(self):
        f = Font.create()
        assert f.headers == {
            'bdfversion': 2.1,
            'fontname': 'Untitled',
            'pointsize': 16,
            'xres': 75,
            'yres': 75,
            'fbbx': 16,
            'fbby': 16,
            'fbbxoff': 0,
            'fbbyoff': -2,
            'metricsset': 0,
        }
        assert list(f.props.items()) == [
            ('family_name', 'Untitled'),
            ('pixel_size', 16),
            ('font_ascent', 14),
            ('font_descent', 2),
            ('charset_registry', 'ISO10646'),
            ('charset_encoding', '1'),
        ]
        assert f._propnames['family_name'] == 'FAMILY_NAME'
        assert len(f) == 0 and f.unencoded == []
        assert f.charset == 'iso10646'

    def test_custom(self):
        f = Font.create(
            pixelsize=12,
            ascent=10,
            descent=3,
            fontname='-x-Foo',
            familyname='Foo',
            xres=96,
            yres=72,
        )
        h = f.headers
        assert (h['fontname'], h['pointsize'], h['xres'], h['yres']) == ('-x-Foo', 12, 96, 72)
        assert (h['fbbx'], h['fbby'], h['fbbxoff'], h['fbbyoff']) == (12, 13, 0, -3)
        assert f.props['family_name'] == 'Foo'

    def test_descent_only(self):
        f = Font.create(pixelsize=7, descent=0)
        assert (f.props['font_ascent'], f.props['font_descent']) == (7, 0)
        assert Font.create(pixelsize=7).props['font_descent'] == 0

    def test_create_and_write(self):
        f = Font.create(pixelsize=8, familyname='T')
        f.newglyph(65, Bitmap.fromstring('.#.\n#.#\n###\n#.#'), mode=1)
        out = f.tobdf()
        assert out.startswith(
            'STARTFONT 2.1\nFONT T\nSIZE 8 75 75\nFONTBOUNDINGBOX 8 8 0 -1\nSTARTPROPERTIES 6\n'
        )
        assert Font().load_string(out).tobdf() == out


# ---------------------------------------------------------------------------
# properties


class TestProps:
    def test_getprop(self, font):
        assert font.getprop('PIXEL_SIZE') == 8
        assert font.getprop('pixel_size') == 8
        assert font.getprop('nope') is None

    def test_setprop_new_and_existing(self, font):
        assert font.setprop('MinSpace', 2) is font
        assert font.props['minspace'] == 2
        assert font._propnames['minspace'] == 'MinSpace'
        font.setprop('MINSPACE', 3)
        assert font._propnames['minspace'] == 'MinSpace'  # first spelling kept
        assert '\nMinSpace 3\n' in font.tobdf()
        font.setprop('weight_name', 'Bold')
        assert '\nWEIGHT_NAME "Bold"\n' in font.tobdf()

    def test_setprop_none(self, font):
        font.setprop('FLAG', None)
        assert font.props['flag'] is None
        assert '\nFLAG\nENDPROPERTIES' in font.tobdf()

    def test_setprop_comment(self, font):
        font.setprop('comment', ['c1'])
        assert 'comment' not in font._propnames
        assert 'STARTPROPERTIES 6\nCOMMENT "c1"\nFAMILY_NAME' in font.tobdf()

    def test_unknown_name_written_upper(self, font):
        font.props['lower_key'] = 1
        assert '\nLOWER_KEY 1\n' in font.tobdf()

    def test_delprop(self, font):
        font.setprop('MinSpace', 2)
        assert font.delprop('minspace') is font
        assert 'minspace' not in font.props and 'minspace' not in font._propnames
        font.delprop('does_not_exist')
        font.delprop('Family_Name')
        assert 'family_name' not in font.props


# ---------------------------------------------------------------------------
# attached glyphs and write-back


class TestAttached:
    def test_glyphbycp_is_attached(self, font):
        g = font.glyphbycp(65)
        assert g._attached
        g.shift(1, 2)
        assert font.glyphs[65][4:6] == [1, 2]
        assert font.glyphbycp(65).meta['bbxoff'] == 1

    def test_glyph_and_iterglyphs_attached(self, font):
        font.glyph('B').setmeta(glyphname='Bee')
        assert font.glyphs[66][0] == 'Bee'
        for g in font.iterglyphs():
            g.setmeta(dwx0=7)
        assert all(m[8] == 7 for m in font.glyphs.values())

    def test_detached_glyph_does_not_write(self, font):
        g = Glyph(dict(zip(META_TITLES, font.glyphs[65], strict=True)), font)
        assert not g._attached
        g.shift(5, 5)
        assert font.glyphs[65][4:6] == [0, 0]

    def test_constructor_copies_meta(self, font):
        m = meta()
        g = Glyph(m, font)
        g.shift(1)
        assert m['bbxoff'] == 1  # caller's dict untouched
        assert g.meta['bbxoff'] == 2

    def test_clone_is_detached(self, font):
        g = font.glyphbycp(65)
        c = g.clone()
        assert not c._attached and c.font is font
        assert c.meta == g.meta and c.meta['hexdata'] is not g.meta['hexdata']
        c.shift(3)
        assert font.glyphs[65][4] == 0

    def test_clone_without_hexdata(self, font):
        g = Glyph({'codepoint': 1, 'hexdata': None}, font)
        assert g.clone().meta['hexdata'] is None

    def test_codepoint_change_moves_key(self, font):
        g = font.glyphbycp(65)
        g.setmeta(codepoint=97)
        assert 65 not in font.glyphs and font.glyphs[97][0] == 'A'
        assert font.glyphs[97][1] == 97
        g.shift(1)  # still attached after the move
        assert font.glyphs[97][4] == 1

    def test_codepoint_change_overwrites_destination(self, font):
        font.glyphbycp(65).setmeta({'codepoint': 66})
        assert sorted(font.glyphs) == [32, 66]
        assert font.glyphs[66][0] == 'A'

    def test_codepoint_change_to_unencoded_and_back(self, font):
        g = font.glyphbycp(65)
        g.setmeta(codepoint=-1)
        assert 65 not in font.glyphs
        assert len(font.unencoded) == 1 and font.unencoded[0]['meta'][0] == 'A'
        assert font.unencoded[0]['altcode'] is None
        g.setmeta(glyphname='A2')
        assert font.unencoded[0]['meta'][0] == 'A2'
        g.setmeta(codepoint=200)
        assert font.unencoded == [] and font.glyphs[200][0] == 'A2'

    def test_removed_glyph_detaches(self, font):
        g = font.glyphbycp(65)
        font.removeglyph(65)
        g.shift(1)
        assert 65 not in font.glyphs
        assert not g._attached

    def test_replaced_glyph_detaches(self, font):
        g = font.glyphbycp(65)
        font.addglyph(meta(65))
        g.shift(1)
        assert font.glyphs[65][0] == 'F' and font.glyphs[65][4] == 1

    def test_two_views_of_same_glyph(self, font):
        g1 = font.glyphbycp(65)
        g2 = font.glyphbycp(65)
        g1.setmeta(codepoint=90)
        g2.shift(2)  # stale view of the same stored glyph: last writer wins (moves it back)
        assert sorted(font.glyphs) == [32, 65, 66]
        assert font.glyphs[65][4] == 2

    def test_writeback_without_store(self, font):
        g = Glyph(meta(), font)
        g._attached = True  # inconsistent state: no store, nothing happens
        g.shift(1)
        assert 70 not in font.glyphs


# ---------------------------------------------------------------------------
# addglyph / removeglyph / newglyph


class TestAddRemove:
    def test_addglyph_dict(self, font):
        m = meta()
        assert font.addglyph(m) is font
        assert font.glyphs[70] == [m[k] for k in META_TITLES]
        assert font.glyphs[70][16] is not m['hexdata']
        assert list(font.glyphs)[-1] == 70

    def test_addglyph_glyph_attaches(self, font):
        g = Glyph(meta(), font)
        font.addglyph(g)
        assert g._attached
        g.shift(0, 1)
        assert font.glyphs[70][5] == 1

    def test_addglyph_from_other_font(self, font):
        other = Font().load_string(mini_bdf)
        g = other.glyphbycp(65)
        font2 = Font.create()
        font2.addglyph(g)
        assert g.font is font2
        g.shift(1)
        assert font2.glyphs[65][4] == 1
        assert other.glyphs[65][4] == 0

    def test_addglyph_replace(self, font):
        font.addglyph(meta(65))
        assert font.glyphs[65][0] == 'F'
        assert list(font.glyphs) == [32, 65, 66]

    def test_addglyph_no_replace_warns(self, font):
        with pytest.warns(BDFParserWarning, match='already exists'):
            font.addglyph(meta(65), replace=False)
        assert font.glyphs[65][0] == 'A'
        g = Glyph(meta(65), font)
        with pytest.warns(BDFParserWarning):
            font.addglyph(g, replace=False)
        assert not g._attached

    def test_addglyph_unencoded(self, font):
        font.addglyph(meta(-1))
        font.addglyph(meta(-7))
        assert len(font.unencoded) == 2
        assert all(e['meta'][1] == -1 and e['altcode'] is None for e in font.unencoded)
        assert len(font) == 3

    def test_addglyph_partial_dict(self, font):
        font.addglyph({'codepoint': 0x4E00})
        assert font.glyphs[0x4E00] == ['uni4E00', 0x4E00, 0, 0, 0, 0] + [None] * 10 + [[]]
        font.addglyph({'codepoint': -1})
        assert font.unencoded[0]['meta'][0] == 'char-1'

    def test_addglyph_non_unicode_default_name(self):
        f = Font(enctest_path('gb2312'))
        f.addglyph({'codepoint': 0xB0A1})
        assert f.glyphs[0xB0A1][0] == 'char45217'

    def test_addglyph_errors(self, font):
        with pytest.raises(KeyError, match='bogus'):
            font.addglyph({'codepoint': 1, 'bogus': 2})
        with pytest.raises(ValueError, match='no codepoint'):
            font.addglyph({'glyphname': 'x'})

    def test_removeglyph(self, font):
        assert font.removeglyph(65) is font
        assert 65 not in font.glyphs
        font.removeglyph(12345)  # no-op
        font.removeglyph(font.glyphbycp(66))
        assert list(font.glyphs) == [32]

    def test_removeglyph_unencoded_glyph(self, font):
        font.addglyph(meta(-1, glyphname='u1'))
        font.addglyph(meta(-1, glyphname='u2'))
        g = Glyph(meta(-1, glyphname='u3'), font)
        font.addglyph(g)
        font.removeglyph(g)
        assert [e['meta'][0] for e in font.unencoded] == ['u1', 'u2']
        assert not g._attached
        font.removeglyph(-1)  # codepoint -1 is ambiguous: no-op
        assert len(font.unencoded) == 2

    def test_newglyph_empty(self, font):
        g = font.newglyph(0x263A)
        assert g._attached
        assert font.glyphs[0x263A] == ['uni263A', 0x263A, 0, 0, 0, 0, 720, 0, 6, 0] + [None] * 6 + [
            []
        ]

    def test_newglyph_bitmap(self, font):
        bm = Bitmap.fromstring('.#.\n###\n.#.')
        g = font.newglyph(43, bm, mode=1, name='plus')
        assert g.meta['glyphname'] == 'plus'
        assert font.glyphs[43] == ['plus', 43, 3, 3, 0, 0, 360, 0, 3, 0] + [None] * 6 + [
            ['40', 'E0', '40']
        ]
        assert g.draw(1) == bm

    def test_newglyph_mode0_dwidth(self, font):
        bm = Bitmap(
            ['000000', '000000', '000000', '000000', '000000', '001100', '001100', '000000']
        )
        g = font.newglyph(46, bm, dwidth=4)
        assert g.meta['dwx0'] == 4 and g.meta['swx0'] == 480
        assert font.glyphs[46][2:6] == [2, 2, 2, 0]
        assert g.draw() == bm

    def test_newglyph_replaces(self, font):
        font.newglyph(65)
        assert font.glyphs[65][0] == 'uni0041' and font.glyphs[65][16] == []

    def test_newglyph_on_empty_font(self):
        f = Font()
        g = f.newglyph(65, Bitmap(['1']))
        assert f.glyphs[65][2:6] == [1, 1, 0, 0]
        assert g.meta['dwx0'] == 1


# ---------------------------------------------------------------------------
# updatebbox / clone / subset / merge / transform


class TestFontOps:
    def test_updatebbox(self, font):
        font.headers['fbbx'] = 99
        assert font.updatebbox() is font
        h = font.headers
        assert (h['fbbx'], h['fbby'], h['fbbxoff'], h['fbbyoff']) == (5, 7, 0, 0)
        font.addglyph(meta(-1, bbw=2, bbh=3, bbxoff=-2, bbyoff=-3))
        font.updatebbox()
        assert (h['fbbx'], h['fbby'], h['fbbxoff'], h['fbbyoff']) == (7, 10, -2, -3)

    def test_updatebbox_no_ink(self):
        f = Font.create()
        f.newglyph(32)
        f.updatebbox()
        assert (f.headers['fbbx'], f.headers['fbby']) == (16, 16)

    def test_clone(self, font):
        font.addglyph(meta(-1))
        font.encoding(charset='utf8')
        c = font.clone()
        assert c is not font
        assert c.tobdf() == font.tobdf()
        assert c.headers == font.headers and c.headers['comment'] is not font.headers['comment']
        assert c.glyphs == font.glyphs and c.glyphs[65] is not font.glyphs[65]
        assert c.glyphs[65][16] is not font.glyphs[65][16]
        assert c.unencoded == font.unencoded and c.unencoded[0] is not font.unencoded[0]
        assert c._propnames == font._propnames and c._propnames is not font._propnames
        assert c.charset == 'utf8'
        c.glyphbycp(65).shift(1)
        c.props['comment'] = ['x']
        assert font.glyphs[65][4] == 0 and 'comment' not in font.props

    def test_clone_props_comment_copied(self, font):
        font.props['comment'] = ['a']
        c = font.clone()
        c.props['comment'].append('b')
        assert font.props['comment'] == ['a']

    def test_subset(self):
        f = Font(unifont_path)
        f.addglyph(meta(-1))
        s = f.subset((65, 90))
        assert sorted(s.glyphs) == list(range(65, 91))
        assert s.unencoded == []
        assert s.headers == f.headers and s.props == f.props
        s.glyphbycp(65).shift(1)
        assert f.glyphs[65][4] == 0
        assert sorted(f.subset(3).glyphs) == [0, 1, 2]
        assert sorted(f.subset([(48, 49), (30340, 30340)]).glyphs) == [48, 49, 30340]
        assert len(f.subset((0x20000, 0x2FFFF))) == 0

    def test_merge(self, font):
        other = Font(unifont_path)
        assert font.merge(other) is font
        assert len(font) == 849
        assert font.glyphs[65][0] == 'A'  # kept
        assert font.glyphs[97][0] == 'U+0061'
        assert font.glyphs[97] is not other.glyphs[97]
        assert font.glyphs[97][16] is not other.glyphs[97][16]
        font.merge(other, replace=True)
        assert font.glyphs[65][0] == 'U+0041'

    def test_transform_all(self, font):
        assert font.transform(lambda bm: bm.fliph()) is font
        assert (
            font.glyphbycp(66).draw() == Font().load_string(mini_bdf).glyphbycp(66).draw().fliph()
        )

    def test_transform_range_and_unencoded(self, font):
        font.addglyph(meta(-1))
        font.transform(lambda bm: bm.invert(), r=(65, 65), mode=1)
        assert font.glyphs[65][16] == ['D8', 'A8', '70', '00', '70', '70', '70']
        assert font.glyphs[66][16] == ['E0', '90', '90', 'E0', '90', '90', 'E0']
        assert font.unencoded[0]['meta'][16] == ['E0', '80']
        font.transform(lambda bm: bm.invert(), mode=1)
        assert font.unencoded[0]['meta'][16] == ['C0']  # ['111', '100'] inverted, trimmed
        assert font.unencoded[0]['meta'][2:6] == [2, 1, 2, 0]


# ---------------------------------------------------------------------------
# Glyph editing


class TestGlyphEdit:
    def test_setbitmap_inverse_of_draw_mode0(self, font):
        g = font.glyphbycp(65)
        bm = g.draw()
        assert bm.bindata == bitmap_mini_A_fbb
        g.setbitmap(bm)
        assert font.glyphs[65][2:6] == [5, 7, 0, 0]
        assert font.glyphs[65][16] == ['20', '50', '88', 'F8', '88', '88', '88']

    def test_setbitmap_modes(self, font):
        g = font.glyphbycp(66)  # BBX 4 7 1 0
        g.setbitmap(Bitmap(['11', '01']), mode=1)
        assert g.meta['bbxoff'] == 1 and g.meta['bbyoff'] == 0
        assert g.meta['hexdata'] == ['C0', '40']
        g.setbitmap(Bitmap(['11', '01']), mode=2)
        assert (g.meta['bbxoff'], g.meta['bbyoff']) == (1, 0)
        g.setbitmap(Bitmap(['11', '01']), mode=-1, bb=(9, 9, -3, 4))
        assert (g.meta['bbw'], g.meta['bbh'], g.meta['bbxoff'], g.meta['bbyoff']) == (2, 2, -3, 4)
        g.setbitmap(Bitmap(['11', '01']), mode=0)
        assert (g.meta['bbxoff'], g.meta['bbyoff']) == (0, -1)
        assert font.glyphs[66][2:6] == [2, 2, 0, -1]

    def test_setbitmap_errors(self, font):
        g = font.glyphbycp(66)
        with pytest.raises(ValueError, match='bb'):
            g.setbitmap(Bitmap(['1']), mode=-1)
        with pytest.raises(ValueError, match='mode'):
            g.setbitmap(Bitmap(['1']), mode=5)
        with pytest.raises(ValueError, match='different lengths'):
            g.setbitmap(['10', '1'])

    def test_setbitmap_trim(self, font):
        g = font.glyphbycp(66)
        bm = Bitmap(['00000', '00000', '01020', '00100', '00000'])
        g.setbitmap(bm, mode=-1, bb=(5, 5, 10, 20))
        assert (g.meta['bbw'], g.meta['bbh'], g.meta['bbxoff'], g.meta['bbyoff']) == (3, 2, 11, 21)
        assert g.meta['hexdata'] == ['A0', '40']  # '2' counts as ink, stored as 1

    def test_setbitmap_no_trim(self, font):
        g = font.glyphbycp(66)
        g.setbitmap(Bitmap(['000000000', '010000001']), mode=-1, bb=(0, 0, -1, -2), trim=False)
        assert (g.meta['bbw'], g.meta['bbh'], g.meta['bbxoff'], g.meta['bbyoff']) == (9, 2, -1, -2)
        assert g.meta['hexdata'] == ['0000', '4080']

    def test_setbitmap_empty(self, font):
        g = font.glyphbycp(66)
        g.setbitmap(Bitmap(['000', '000']), mode=-1, bb=(0, 0, 5, 5))
        assert font.glyphs[66][2:6] == [0, 0, 0, 0] and font.glyphs[66][16] == []
        g.setbitmap(Bitmap([]))
        assert font.glyphs[66][16] == []
        g.setbitmap(Bitmap(['', '']), trim=False)
        assert font.glyphs[66][2:4] == [0, 2] and font.glyphs[66][16] == []

    def test_setbitmap_wide(self, font):
        g = font.glyphbycp(66)
        g.setbitmap(Bitmap(['1' * 17]), mode=1)
        assert g.meta['hexdata'] == ['FFFF80']
        assert g.meta['bbw'] == 17

    def test_setbitmap_keeps_widths(self, font):
        g = font.glyphbycp(66)
        g.setbitmap(Bitmap(['1' * 12]), mode=1)
        assert (g.meta['dwx0'], g.meta['swx0']) == (6, 750)

    def test_setbitmap_round_trip_all_modes(self):
        f = Font(unifont_path)
        for cp in (0, 97, 0x0644, 30340):
            for mode in (0, 1, 2):
                g = f.glyphbycp(cp)
                before = g.draw(mode)
                g2 = g.clone()
                g2.setbitmap(before, mode, trim=False)
                assert g2.draw(mode) == before
                g3 = g.clone()
                g3.setbitmap(before, mode)
                assert g3.draw(0) == g.draw(0)

    def test_setmeta(self, font):
        g = font.glyphbycp(65)
        assert g.setmeta(dwx0=9, swx0=1000) is g
        assert font.glyphs[65][6:10] == [1000, 0, 9, 0]
        g.setmeta({'glyphname': 'AA'}, vvectorx=1)
        assert font.glyphs[65][0] == 'AA' and font.glyphs[65][14] == 1
        hd = ['F0']
        g.setmeta(hexdata=hd, bbw=4, bbh=1)
        assert font.glyphs[65][16] == ['F0'] and font.glyphs[65][16] is not hd
        with pytest.raises(KeyError, match='bogus'):
            g.setmeta(bogus=1)
        g.setmeta(hexdata=None)
        assert font.glyphs[65][16] == []

    def test_shift(self, font):
        g = font.glyphbycp(66)
        assert g.shift(-1, 2) is g
        assert font.glyphs[66][4:6] == [0, 2]
        g.shift()
        assert font.glyphs[66][4:6] == [0, 2]
        assert g.draw(1) == Font().load_string(mini_bdf).glyphbycp(66).draw(1)

    def test_shift_none_offsets(self, font):
        g = Glyph({'codepoint': 1, 'bbxoff': None}, font)
        g.shift(1, 1)
        assert (g.meta['bbxoff'], g.meta['bbyoff']) == (1, 1)

    def test_transform(self, font):
        g = font.glyphbycp(65)
        assert g.transform(lambda bm: bm.flipv()) is g
        assert g.draw().bindata == ['000000'] + bitmap_mini_A_fbb[:7][::-1]
        g.transform(lambda bm: None, mode=1)  # in-place / unchanged
        assert g.draw().bindata == ['000000'] + bitmap_mini_A_fbb[:7][::-1]

    def test_transform_inplace_mutation(self, font):
        g = font.glyphbycp(65)

        def mutate(bm):
            bm.setpixel(4, 0, 1)

        g.transform(mutate, mode=1)
        assert font.glyphs[65][16][0] == '28'

    def test_transform_bold_italic(self, font):
        font.transform(lambda bm: bm.bold(), mode=1)
        assert font.glyphs[65][2] == 6
        font.transform(lambda bm: bm.italic(), mode=1)
        assert font.glyphs[65][2] == 8  # 6 + 3 shifts, last column empty -> trimmed

    def test_chr_unencoded(self, font):
        font.addglyph(meta(-1))
        g = Glyph(dict(zip(META_TITLES, font.unencoded[0]['meta'], strict=True)), font)
        assert g.chr() is None

    def test_draw_mode_errors(self, font):
        g = font.glyphbycp(65)
        with pytest.raises(ValueError, match='Unknown draw mode'):
            g.draw(7)
        with pytest.raises(ValueError, match='xoff and yoff'):
            g.origin(-1)
        with pytest.raises(ValueError, match='Unknown origin mode'):
            g.origin(9)
        assert g.origin(-1, xoff=1, yoff=2) == (-1, -2)
        assert g.origin(2, fromorigin=True) == (0, 0)
