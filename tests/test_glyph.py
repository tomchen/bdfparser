import unittest
from bdfparser import Font, Glyph
from .info import unifont_path, glyph_a_meta, bitmap_a_bindata, specfont_path


# Test all `Glyph` attributes and methods, with "a" in Unifont and "'" and "j" in fixed spec example font


class TestGlyph(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None
        self.font = Font(unifont_path)
        self.glyph_a = Glyph(glyph_a_meta, self.font)

    def test_init(self):
        self.assertIsInstance(self.glyph_a, Glyph)

    def test_meta(self):
        self.assertEqual(self.glyph_a.meta, glyph_a_meta)

    def test_font(self):
        self.assertEqual(self.glyph_a.font, self.font)

    def test_cp(self):
        self.assertEqual(self.glyph_a.cp(), 97)

    def test_chr(self):
        self.assertEqual(self.glyph_a.chr(), 'a')


class TestGlyphDraw(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None
        self.font = Font(unifont_path)
        self.glyph_a = Glyph(glyph_a_meta, self.font)

    def test_draw_default(self):
        self.assertEqual(self.glyph_a.draw().bindata, bitmap_a_bindata)

    def test_draw_mode1(self):
        self.assertEqual(self.glyph_a.draw(mode=1).bindata, ['00000000',
                                                             '00000000',
                                                             '00000000',
                                                             '00000000',
                                                             '00000000',
                                                             '00000000',
                                                             '00111100',
                                                             '01000010',
                                                             '00000010',
                                                             '00111110',
                                                             '01000010',
                                                             '01000010',
                                                             '01000110',
                                                             '00111010',
                                                             '00000000',
                                                             '00000000'])

    def test_draw_mode2(self):
        self.assertEqual(self.glyph_a.draw(mode=2).bindata, ['00000000',
                                                             '00000000',
                                                             '00000000',
                                                             '00000000',
                                                             '00000000',
                                                             '00000000',
                                                             '00111100',
                                                             '01000010',
                                                             '00000010',
                                                             '00111110',
                                                             '01000010',
                                                             '01000010',
                                                             '01000110',
                                                             '00111010',
                                                             '00000000',
                                                             '00000000'])

    def test_draw_mode_m1(self):
        self.assertEqual(self.glyph_a.draw(mode=-1, bb=(10, 10, -1, -1)).bindata, ['0000000000',
                                                                                   '0001111000',
                                                                                   '0010000100',
                                                                                   '0000000100',
                                                                                   '0001111100',
                                                                                   '0010000100',
                                                                                   '0010000100',
                                                                                   '0010001100',
                                                                                   '0001110100',
                                                                                   '0000000000'])

    def test_draw_mode_m1_without_bb(self):
        def draw_mode_m1_without_bb():
            self.glyph_a.draw(mode=-1)
        self.assertRaisesRegex(
            Exception, r'Parameter bb in draw\(\) method must be set when mode=-1', draw_mode_m1_without_bb)


class TestGlyphStrRepr(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None
        self.font = Font(unifont_path)
        self.glyph_a = Glyph(glyph_a_meta, self.font)

    def test_str(self):
        self.assertEqual(str(self.glyph_a),
                         '................\n'
                         '................\n'
                         '................\n'
                         '................\n'
                         '................\n'
                         '................\n'
                         '..####..........\n'
                         '.#....#.........\n'
                         '......#.........\n'
                         '..#####.........\n'
                         '.#....#.........\n'
                         '.#....#.........\n'
                         '.#...##.........\n'
                         '..###.#.........\n'
                         '................\n'
                         '................')

    def test_repr(self):
        self.assertEqual(repr(self.glyph_a)[:7], 'Glyph({')


class TestGlyphDrawSpecQuoteright(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None
        self.font = Font(specfont_path)
        self.glyph_qr = self.font.glyph("'")

    def test_draw_default(self):
        self.assertEqual(self.glyph_qr.draw().bindata, ['000001110',
                                                        '000001110',
                                                        '000001110',
                                                        '000001100',
                                                        '000011100',
                                                        '000011000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000',
                                                        '000000000'])

    def test_draw_mode1(self):
        self.assertEqual(self.glyph_qr.draw(mode=1).bindata, ['0111',
                                                              '0111',
                                                              '0111',
                                                              '0110',
                                                              '1110',
                                                              '1100'])

    def test_draw_mode2(self):
        self.assertEqual(self.glyph_qr.draw(mode=2).bindata, ['01110000',
                                                              '01110000',
                                                              '01110000',
                                                              '01100000',
                                                              '11100000',
                                                              '11000000'])

    def test_draw_mode_m1(self):
        self.assertEqual(self.glyph_qr.draw(
            mode=-1, bb=(6, 17, 1, 1)).bindata, ['001110',
                                                 '001110',
                                                 '001110',
                                                 '001100',
                                                 '011100',
                                                 '011000',
                                                 '000000',
                                                 '000000',
                                                 '000000',
                                                 '000000',
                                                 '000000',
                                                 '000000',
                                                 '000000',
                                                 '000000',
                                                 '000000',
                                                 '000000',
                                                 '000000'])


class TestGlyphOriginSpecQuoteright(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None
        self.font = Font(specfont_path)
        self.glyph_qr = self.font.glyph("'")

    def test_origin(self):
        self.assertEqual(self.glyph_qr.origin(), (2, 6))
        self.assertEqual(self.glyph_qr.origin(mode=1), (-2, -12))
        self.assertEqual(self.glyph_qr.origin(mode=2), (-2, -12))
        self.assertEqual(self.glyph_qr.origin(
            mode=-1, xoff=1, yoff=1), (-1, -1))
        self.assertEqual(self.glyph_qr.origin(fromorigin=True), (-2, -6))
        self.assertEqual(self.glyph_qr.origin(
            mode=1, fromorigin=True), (2, 12))
        self.assertEqual(self.glyph_qr.origin(
            mode=2, fromorigin=True), (2, 12))
        self.assertEqual(self.glyph_qr.origin(
            mode=-1, fromorigin=True, xoff=1, yoff=1), (1, 1))


class TestGlyphDrawSpecj(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None
        self.font = Font(specfont_path)
        self.glyph_j = self.font.glyph("j")

    def test_draw_default(self):
        self.assertEqual(self.glyph_j.draw().bindata, ['000000000',
                                                       '000000000',
                                                       '000000111',
                                                       '000000111',
                                                       '000000111',
                                                       '000000111',
                                                       '000000000',
                                                       '000001110',
                                                       '000001110',
                                                       '000001110',
                                                       '000001110',
                                                       '000011100',
                                                       '000011100',
                                                       '000011100',
                                                       '000011100',
                                                       '000011100',
                                                       '000111000',
                                                       '000111000',
                                                       '000111000',
                                                       '000111000',
                                                       '001011000',
                                                       '011110000',
                                                       '111100000',
                                                       '111000000'])

    def test_draw_mode1(self):
        self.assertEqual(self.glyph_j.draw(mode=1).bindata, ['000000111',
                                                             '000000111',
                                                             '000000111',
                                                             '000000111',
                                                             '000000000',
                                                             '000001110',
                                                             '000001110',
                                                             '000001110',
                                                             '000001110',
                                                             '000011100',
                                                             '000011100',
                                                             '000011100',
                                                             '000011100',
                                                             '000011100',
                                                             '000111000',
                                                             '000111000',
                                                             '000111000',
                                                             '000111000',
                                                             '001011000',
                                                             '011110000',
                                                             '111100000',
                                                             '111000000'])

    def test_draw_mode2(self):
        self.assertEqual(self.glyph_j.draw(mode=2).bindata, ['0000001110000000',
                                                             '0000001110000000',
                                                             '0000001110000000',
                                                             '0000001110000000',
                                                             '0000000000000000',
                                                             '0000011100000000',
                                                             '0000011100000000',
                                                             '0000011100000000',
                                                             '0000011100000000',
                                                             '0000111000000000',
                                                             '0000111000000000',
                                                             '0000111000000000',
                                                             '0000111000000000',
                                                             '0000111000000000',
                                                             '0001110000000000',
                                                             '0001110000000000',
                                                             '0001110000000000',
                                                             '0001110000000000',
                                                             '0010110000000000',
                                                             '0111100000000000',
                                                             '1111000000000000',
                                                             '1110000000000000'])

    def test_draw_mode_m1(self):
        self.assertEqual(self.glyph_j.draw(
            mode=-1, bb=(6, 17, 1, 1)).bindata, ['000000',
                                                 '000000',
                                                 '000111',
                                                 '000111',
                                                 '000111',
                                                 '000111',
                                                 '000000',
                                                 '001110',
                                                 '001110',
                                                 '001110',
                                                 '001110',
                                                 '011100',
                                                 '011100',
                                                 '011100',
                                                 '011100',
                                                 '011100',
                                                 '111000'])


# if __name__ == '__main__':
#     unittest.main()
