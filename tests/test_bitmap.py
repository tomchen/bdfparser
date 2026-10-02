import unittest

from bdfparser import Bitmap, Font

from .info import bitmap_qr2_bindata, bitmap_qr3_bindata, specfont_path

# Test all `Bitmap` attributes and methods, with "a" and other glyphs in Unifont


class TestBitmap(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.font = Font(specfont_path)
        self.bitmap_qr = self.font.glyph("'").draw(mode=2)
        self.bitmap_qr2 = Bitmap(bitmap_qr2_bindata)

    def test_bindata(self):
        self.assertEqual(
            self.bitmap_qr.bindata,
            ['01110000', '01110000', '01110000', '01100000', '11100000', '11000000'],
        )
        self.assertEqual(self.bitmap_qr2.bindata, ['01110', '02112', '01102', '10200', '01000'])

    def test_width(self):
        self.assertEqual(self.bitmap_qr.width(), 8)
        self.assertEqual(self.bitmap_qr2.width(), 5)

    def test_height(self):
        self.assertEqual(self.bitmap_qr.height(), 6)
        self.assertEqual(self.bitmap_qr2.height(), 5)

    def test_clone(self):
        self.assertIsNot(self.bitmap_qr.clone(), self.bitmap_qr)
        self.assertIsNot(self.bitmap_qr.clone().bindata, self.bitmap_qr.bindata)
        # v3: bitmaps compare equal by content
        self.assertEqual(self.bitmap_qr.clone(), self.bitmap_qr)
        self.assertEqual(self.bitmap_qr.clone().bindata, self.bitmap_qr.bindata)


class TestBitmapAlter(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.font = Font(specfont_path)
        self.bitmap_qr = self.font.glyph("'").draw(mode=2)
        self.bitmap_qr2 = Bitmap(bitmap_qr2_bindata)

    def test_crop_default(self):
        self.assertEqual(
            self.bitmap_qr2.crop(6, 10).bindata,
            [
                '000000',
                '000000',
                '000000',
                '000000',
                '000000',
                '011100',
                '021120',
                '011020',
                '102000',
                '010000',
            ],
        )

    def test_crop(self):
        self.assertEqual(
            self.bitmap_qr.crop(6, 10, -1, -2).bindata,
            [
                '000000',
                '000000',
                '001110',
                '001110',
                '001110',
                '001100',
                '011100',
                '011000',
                '000000',
                '000000',
            ],
        )

    def test_replace(self):
        self.assertEqual(
            self.bitmap_qr2.replace('2', '3').bindata, ['01110', '03113', '01103', '10300', '01000']
        )


class TestBitmapOverlay(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.font = Font(specfont_path)
        self.bitmap_qr = self.font.glyph("'").draw(mode=2)
        self.bitmap_qr2 = Bitmap(bitmap_qr2_bindata)

    def test_overlay(self):
        self.assertEqual(
            self.bitmap_qr.overlay(
                self.bitmap_qr2.crop(self.bitmap_qr.width(), self.bitmap_qr.height())
            ).bindata,
            ['01110000', '01110000', '02112000', '01102000', '11200000', '11000000'],
        )


class TestBitmapConcat(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.font = Font(specfont_path)
        self.bitmap_qr = self.font.glyph("'").draw(mode=2)
        self.bitmap_qr2 = Bitmap(bitmap_qr2_bindata)
        self.bitmap_j = self.font.glyph('j').draw(mode=2)

    def test_concatall_onlyone(self):
        self.assertEqual(Bitmap.concatall([self.bitmap_qr]).bindata, self.bitmap_qr.bindata)

    def test_concatall(self):
        w = self.bitmap_qr.width()
        self.assertEqual(
            Bitmap.concatall([self.bitmap_qr, self.bitmap_j, self.bitmap_qr2]).bindata,
            [
                '00000000000000111000000000000',
                '00000000000000111000000000000',
                '00000000000000111000000000000',
                '00000000000000111000000000000',
                '00000000000000000000000000000',
                '00000000000001110000000000000',
                '00000000000001110000000000000',
                '00000000000001110000000000000',
                '00000000000001110000000000000',
                '00000000000011100000000000000',
                '00000000000011100000000000000',
                '00000000000011100000000000000',
                '00000000000011100000000000000',
                '00000000000011100000000000000',
                '00000000000111000000000000000',
                '00000000000111000000000000000',
                '01110000000111000000000000000',
                '01110000000111000000000001110',
                '01110000001011000000000002112',
                '01100000011110000000000001102',
                '11100000111100000000000010200',
                '11000000111000000000000001000',
            ],
        )
        self.assertEqual(self.bitmap_qr.width(), w)

    def test_concatall_offsetlist(self):
        self.assertEqual(
            Bitmap.concatall(
                [self.bitmap_qr, self.bitmap_j, self.bitmap_qr2], offsetlist=[-5, 4]
            ).bindata,
            [
                '0000000001110000000000000000',
                '0000000001110000000000000000',
                '0000000001110000000000000000',
                '0000000001110000000000000000',
                '0000000000000000000000000000',
                '0000000011100000000000000000',
                '0000000011100000000000000000',
                '0000000011100000000000000000',
                '0000000011100000000000000000',
                '0000000111000000000000000000',
                '0000000111000000000000000000',
                '0000000111000000000000000000',
                '0000000111000000000000000000',
                '0000000111000000000000000000',
                '0000001110000000000000000000',
                '0000001110000000000000000000',
                '0111001110000000000000000000',
                '0111001110000000000000001110',
                '0111010110000000000000002112',
                '0110111100000000000000001102',
                '1111111000000000000000010200',
                '1101110000000000000000001000',
            ],
        )

    def test_concatall_direction_2(self):
        self.assertEqual(
            Bitmap.concatall([self.bitmap_qr, self.bitmap_j, self.bitmap_qr2], direction=2).bindata,
            [
                '00000000000111000000000000000',
                '00000000000111000000000000000',
                '00000000000111000000000000000',
                '00000000000111000000000000000',
                '00000000000000000000000000000',
                '00000000001110000000000000000',
                '00000000001110000000000000000',
                '00000000001110000000000000000',
                '00000000001110000000000000000',
                '00000000011100000000000000000',
                '00000000011100000000000000000',
                '00000000011100000000000000000',
                '00000000011100000000000000000',
                '00000000011100000000000000000',
                '00000000111000000000000000000',
                '00000000111000000000000000000',
                '00000000111000000000001110000',
                '01110000111000000000001110000',
                '02112001011000000000001110000',
                '01102011110000000000001100000',
                '10200111100000000000011100000',
                '01000111000000000000011000000',
            ],
        )

    def test_concatall_direction_0(self):
        self.assertEqual(
            Bitmap.concatall([self.bitmap_qr, self.bitmap_j, self.bitmap_qr2], direction=0).bindata,
            [
                '0111000000000000',
                '0111000000000000',
                '0111000000000000',
                '0110000000000000',
                '1110000000000000',
                '1100000000000000',
                '0000001110000000',
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
                '1110000000000000',
                '0111000000000000',
                '0211200000000000',
                '0110200000000000',
                '1020000000000000',
                '0100000000000000',
            ],
        )

    def test_concatall_direction_m1(self):
        self.assertEqual(
            Bitmap.concatall(
                [self.bitmap_qr, self.bitmap_j, self.bitmap_qr2], direction=-1
            ).bindata,
            [
                '0111000000000000',
                '0211200000000000',
                '0110200000000000',
                '1020000000000000',
                '0100000000000000',
                '0000001110000000',
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
                '1110000000000000',
                '0111000000000000',
                '0111000000000000',
                '0111000000000000',
                '0110000000000000',
                '1110000000000000',
                '1100000000000000',
            ],
        )

    def test_concatall_align_0(self):
        self.assertEqual(
            Bitmap.concatall([self.bitmap_qr, self.bitmap_j, self.bitmap_qr2], align=0).bindata,
            [
                '01110000000000111000000001110',
                '01110000000000111000000002112',
                '01110000000000111000000001102',
                '01100000000000111000000010200',
                '11100000000000000000000001000',
                '11000000000001110000000000000',
                '00000000000001110000000000000',
                '00000000000001110000000000000',
                '00000000000001110000000000000',
                '00000000000011100000000000000',
                '00000000000011100000000000000',
                '00000000000011100000000000000',
                '00000000000011100000000000000',
                '00000000000011100000000000000',
                '00000000000111000000000000000',
                '00000000000111000000000000000',
                '00000000000111000000000000000',
                '00000000000111000000000000000',
                '00000000001011000000000000000',
                '00000000011110000000000000000',
                '00000000111100000000000000000',
                '00000000111000000000000000000',
            ],
        )

    def test_concatall_direction_2_align_0(self):
        self.assertEqual(
            Bitmap.concatall(
                [self.bitmap_qr, self.bitmap_j, self.bitmap_qr2], direction=2, align=0
            ).bindata,
            [
                '01110000000111000000001110000',
                '02112000000111000000001110000',
                '01102000000111000000001110000',
                '10200000000111000000001100000',
                '01000000000000000000011100000',
                '00000000001110000000011000000',
                '00000000001110000000000000000',
                '00000000001110000000000000000',
                '00000000001110000000000000000',
                '00000000011100000000000000000',
                '00000000011100000000000000000',
                '00000000011100000000000000000',
                '00000000011100000000000000000',
                '00000000011100000000000000000',
                '00000000111000000000000000000',
                '00000000111000000000000000000',
                '00000000111000000000000000000',
                '00000000111000000000000000000',
                '00000001011000000000000000000',
                '00000011110000000000000000000',
                '00000111100000000000000000000',
                '00000111000000000000000000000',
            ],
        )

    def test_concatall_direction_0_align_0(self):
        self.assertEqual(
            Bitmap.concatall(
                [self.bitmap_qr, self.bitmap_j, self.bitmap_qr2], direction=0, align=0
            ).bindata,
            [
                '0000000001110000',
                '0000000001110000',
                '0000000001110000',
                '0000000001100000',
                '0000000011100000',
                '0000000011000000',
                '0000001110000000',
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
                '1110000000000000',
                '0000000000001110',
                '0000000000002112',
                '0000000000001102',
                '0000000000010200',
                '0000000000001000',
            ],
        )

    def test_concatall_direction_m1_align_0(self):
        self.assertEqual(
            Bitmap.concatall(
                [self.bitmap_qr, self.bitmap_j, self.bitmap_qr2], direction=-1, align=0
            ).bindata,
            [
                '0000000000001110',
                '0000000000002112',
                '0000000000001102',
                '0000000000010200',
                '0000000000001000',
                '0000001110000000',
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
                '1110000000000000',
                '0000000001110000',
                '0000000001110000',
                '0000000001110000',
                '0000000001100000',
                '0000000011100000',
                '0000000011000000',
            ],
        )

    def test_plus(self):
        w = self.bitmap_qr.width()
        self.assertEqual(
            (self.bitmap_qr + self.bitmap_j).bindata,
            [
                '000000000000001110000000',
                '000000000000001110000000',
                '000000000000001110000000',
                '000000000000001110000000',
                '000000000000000000000000',
                '000000000000011100000000',
                '000000000000011100000000',
                '000000000000011100000000',
                '000000000000011100000000',
                '000000000000111000000000',
                '000000000000111000000000',
                '000000000000111000000000',
                '000000000000111000000000',
                '000000000000111000000000',
                '000000000001110000000000',
                '000000000001110000000000',
                '011100000001110000000000',
                '011100000001110000000000',
                '011100000010110000000000',
                '011000000111100000000000',
                '111000001111000000000000',
                '110000001110000000000000',
            ],
        )
        self.assertEqual(self.bitmap_qr.width(), w)

    def test_concat(self):
        w = self.bitmap_qr.width()
        w2 = self.bitmap_j.width()
        self.assertEqual(
            self.bitmap_qr.concat(self.bitmap_j).bindata,
            [
                '000000000000001110000000',
                '000000000000001110000000',
                '000000000000001110000000',
                '000000000000001110000000',
                '000000000000000000000000',
                '000000000000011100000000',
                '000000000000011100000000',
                '000000000000011100000000',
                '000000000000011100000000',
                '000000000000111000000000',
                '000000000000111000000000',
                '000000000000111000000000',
                '000000000000111000000000',
                '000000000000111000000000',
                '000000000001110000000000',
                '000000000001110000000000',
                '011100000001110000000000',
                '011100000001110000000000',
                '011100000010110000000000',
                '011000000111100000000000',
                '111000001111000000000000',
                '110000001110000000000000',
            ],
        )
        self.assertEqual(self.bitmap_qr.width(), w + w2)


class TestBitmapEnlarge(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.font = Font(specfont_path)
        self.bitmap_qr = self.font.glyph("'").draw(mode=2)
        self.bitmap_qr2 = Bitmap(bitmap_qr2_bindata)

    def test_enlarge(self):
        self.assertEqual(
            self.bitmap_qr2.enlarge(2, 3).bindata,
            [
                '0011111100',
                '0011111100',
                '0011111100',
                '0022111122',
                '0022111122',
                '0022111122',
                '0011110022',
                '0011110022',
                '0011110022',
                '1100220000',
                '1100220000',
                '1100220000',
                '0011000000',
                '0011000000',
                '0011000000',
            ],
        )

    def test_asterisk(self):
        w = self.bitmap_qr.width()
        self.assertEqual((self.bitmap_qr * 3).bindata, self.bitmap_qr.enlarge(3, 3).bindata)
        self.assertEqual(self.bitmap_qr.width(), w * 3)

    def test_asterisk2(self):
        self.assertEqual((self.bitmap_qr * (2, 3)).bindata, self.bitmap_qr.enlarge(2, 3).bindata)


class TestBitmapEffect(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.font = Font(specfont_path)
        self.bitmap_qr = self.font.glyph("'").draw(mode=2)

    def test_shadow(self):
        self.assertEqual(
            self.bitmap_qr.shadow(2, -3).bindata,
            [
                '0111000000',
                '0111000000',
                '0111000000',
                '0112220000',
                '1112220000',
                '1102220000',
                '0002200000',
                '0022200000',
                '0022000000',
            ],
        )

    def test_glow0(self):
        self.assertEqual(
            self.bitmap_qr.glow().bindata,
            [
                '0022200000',
                '0211120000',
                '0211120000',
                '0211120000',
                '0211200000',
                '2111200000',
                '2112000000',
                '0220000000',
            ],
        )

    def test_glow1(self):
        self.assertEqual(
            self.bitmap_qr.glow(1).bindata,
            [
                '0222220000',
                '0211120000',
                '0211120000',
                '0211120000',
                '2211220000',
                '2111200000',
                '2112200000',
                '2222000000',
            ],
        )


class TestBitmapPad(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.bitmap_qr2 = Bitmap(bitmap_qr2_bindata)
        self.bitmap_qr3 = Bitmap(bitmap_qr3_bindata)

    def test_bytepad(self):
        self.assertEqual(
            self.bitmap_qr2.bytepad().bindata,
            ['01110000', '02112000', '01102000', '10200000', '01000000'],
        )

    def test_bytepad4(self):
        self.assertEqual(
            self.bitmap_qr3.bytepad(4).bindata,
            ['011100000000', '021120000000', '011020003000', '102000002100', '010000000000'],
        )


class TestBitmapTodata(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.font = Font(specfont_path)
        self.bitmap_todata_test = Bitmap(['00010', '11010', '00201'])
        self.bitmap_todata_test2 = Bitmap(['00010', '11010'])

    def test_todata0(self):
        self.assertEqual(self.bitmap_todata_test.todata(0), '00010\n11010\n00201')

    def test_todata1_default(self):
        self.assertEqual(self.bitmap_todata_test.todata(), ['00010', '11010', '00201'])

    def test_todata2(self):
        self.assertEqual(
            self.bitmap_todata_test.todata(2), [[0, 0, 0, 1, 0], [1, 1, 0, 1, 0], [0, 0, 2, 0, 1]]
        )

    def test_todata3(self):
        self.assertEqual(
            self.bitmap_todata_test.todata(3), [0, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 0, 2, 0, 1]
        )

    def test_todata4(self):
        self.assertEqual(self.bitmap_todata_test2.todata(4), ['02', '1a'])

    def test_todata4_error(self):
        def todata4_error():
            self.bitmap_todata_test.todata(4)

        self.assertRaises(ValueError, todata4_error)

    def test_todata5(self):
        self.assertEqual(self.bitmap_todata_test2.todata(5), [2, 26])

    def test_todata5_error(self):
        def todata5_error():
            self.bitmap_todata_test.todata(5)

        self.assertRaises(ValueError, todata5_error)


class TestBitmapTobytes(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.font = Font(specfont_path)
        self.bitmap_qr = self.font.glyph("'").draw(mode=2)
        self.bitmap_qr2 = Bitmap(bitmap_qr2_bindata)

    def test_tobytes_1(self):
        self.assertEqual(self.bitmap_qr.tobytes(mode='1'), b'\x8f\x8f\x8f\x9f\x1f?')
        self.assertEqual(self.bitmap_qr2.tobytes(mode='1'), b'\x8f\x87\x97_\xbf')

    def test_tobytes_L(self):
        self.assertEqual(
            self.bitmap_qr.tobytes(mode='L'),
            b'\xff\x00\x00\x00\xff\xff\xff\xff\xff\x00\x00\x00\xff\xff\xff\xff\xff\x00\x00\x00\xff\xff\xff\xff\xff\x00\x00\xff\xff\xff\xff\xff\x00\x00\x00\xff\xff\xff\xff\xff\x00\x00\xff\xff\xff\xff\xff\xff',
        )
        self.assertEqual(
            self.bitmap_qr2.tobytes(mode='L'),
            b'\xff\x00\x00\x00\xff\xff\x7f\x00\x00\x7f\xff\x00\x00\xff\x7f\x00\xff\x7f\xff\xff\xff\x00\xff\xff\xff',
        )

    def test_tobytes_RGB_default(self):
        self.assertEqual(
            self.bitmap_qr.tobytes(),
            b'\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff',
        )
        self.assertEqual(
            self.bitmap_qr2.tobytes(),
            b'\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\xff\x00\x00\xff\xff\xff\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff',
        )

    def test_tobytes_RGBA(self):
        self.assertEqual(
            self.bitmap_qr.tobytes('RGBA'),
            b'\xff\xff\xff\x00\x00\x00\x00\xff\x00\x00\x00\xff\x00\x00\x00\xff\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\x00\x00\x00\xff\x00\x00\x00\xff\x00\x00\x00\xff\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\x00\x00\x00\xff\x00\x00\x00\xff\x00\x00\x00\xff\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\x00\x00\x00\xff\x00\x00\x00\xff\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\x00\x00\x00\xff\x00\x00\x00\xff\x00\x00\x00\xff\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\x00\x00\x00\xff\x00\x00\x00\xff\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00',
        )
        self.assertEqual(
            self.bitmap_qr2.tobytes('RGBA'),
            b'\xff\xff\xff\x00\x00\x00\x00\xff\x00\x00\x00\xff\x00\x00\x00\xff\xff\xff\xff\x00\xff\xff\xff\x00\xff\x00\x00\xff\x00\x00\x00\xff\x00\x00\x00\xff\xff\x00\x00\xff\xff\xff\xff\x00\x00\x00\x00\xff\x00\x00\x00\xff\xff\xff\xff\x00\xff\x00\x00\xff\x00\x00\x00\xff\xff\xff\xff\x00\xff\x00\x00\xff\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00\x00\x00\x00\xff\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\xff\x00',
        )


class TestBitmapStrRepr(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.font = Font(specfont_path)
        self.bitmap_qr = self.font.glyph("'").draw(mode=2)

    def test_str(self):
        self.assertEqual(
            str(self.bitmap_qr), '.###....\n.###....\n.###....\n.##.....\n###.....\n##......'
        )

    def test_repr(self):
        self.assertEqual(
            repr(self.bitmap_qr),
            "Bitmap(['01110000',\n"
            "        '01110000',\n"
            "        '01110000',\n"
            "        '01100000',\n"
            "        '11100000',\n"
            "        '11000000'])",
        )


# ---------------------------------------------------------------------------
# v3 Bitmap API

import pytest  # noqa: E402

from bdfparser import BDFParserWarning  # noqa: E402

T = Bitmap.fromstring  # shorthand


class TestBitmapV3Basics:
    def test_width_empty(self):
        assert Bitmap([]).width() == 0
        assert Bitmap([]).height() == 0
        assert Bitmap(['', '']).width() == 0

    def test_fromstring(self):
        assert T('.#&\n#..').bindata == ['012', '100']
        assert T('012\n210').bindata == ['012', '210']
        assert T('\n\n  \n.#\r\n#.\r\n\n   ').bindata == ['01', '10']
        assert T('').bindata == []

    def test_fromstring_inverse_of_str(self):
        b = Bitmap(bitmap_qr2_bindata)
        assert T(str(b)) == b

    def test_fromstring_errors(self):
        with pytest.raises(ValueError, match="Invalid character 'x'"):
            T('.#\n.x')
        with pytest.raises(ValueError, match='different lengths'):
            T('.#\n.')
        with pytest.raises(ValueError):
            T('.#\n\n.#')  # interior empty line

    def test_blank(self):
        assert Bitmap.blank(3, 2).bindata == ['000', '000']
        assert Bitmap.blank(0, 0).bindata == []
        with pytest.raises(ValueError):
            Bitmap.blank(-1, 2)

    def test_eq(self):
        assert Bitmap(['01']) == Bitmap(['01'])
        assert Bitmap(['01']) != Bitmap(['10'])
        assert Bitmap(['01']).equals(Bitmap(['01']))
        assert not Bitmap(['01']).equals(Bitmap(['011']))
        assert Bitmap(['01']) != ['01']
        assert Bitmap([]) == Bitmap([])
        with pytest.raises(TypeError):
            hash(Bitmap([]))

    def test_clone_independent(self):
        b = T('.#\n#.')
        c = b.clone().setpixel(0, 0)
        assert b.bindata == ['01', '10'] and c.bindata == ['11', '10']

    def test_todata_unknown(self):
        with pytest.raises(ValueError):
            T('#').todata(9)

    def test_tobytes_unknown_mode_warns(self):
        with pytest.warns(BDFParserWarning, match='Unknown mode'):
            assert T('#.').tobytes('CMYK') == b'\x00\x00\x00\xff\xff\xff'

    def test_overlay_size_warnings(self):
        with pytest.warns(BDFParserWarning, match='different height'):
            T('#\n.').overlay(T('#'))
        with pytest.warns(BDFParserWarning, match='different width'):
            T('#.').overlay(T('#'))


class TestBitmapPixels:
    def test_getpixel(self):
        b = T('.#&\n#..')
        assert [b.getpixel(x, 0) for x in range(3)] == [0, 1, 2]
        assert b.getpixel(0, 1) == 1

    @pytest.mark.parametrize('x, y', [(3, 0), (0, 2), (-1, 0), (0, -1)])
    def test_getpixel_out_of_range(self, x, y):
        with pytest.raises(IndexError):
            T('.#&\n#..').getpixel(x, y)

    def test_setpixel(self):
        b = T('...\n...')
        assert b.setpixel(1, 0) is b
        b.setpixel(2, 1, 2).setpixel(1, 0, 0).setpixel(0, 1)
        assert b.bindata == ['000', '102']

    def test_setpixel_errors(self):
        b = T('..')
        with pytest.raises(IndexError):
            b.setpixel(2, 0)
        with pytest.raises(ValueError):
            b.setpixel(0, 0, 3)
        with pytest.raises(ValueError):
            b.setpixel(0, 0, '1')

    def test_setpixel_does_not_mutate_shared_list(self):
        rows = ['00']
        Bitmap(rows).setpixel(0, 0)
        assert rows == ['00']


class TestBitmapTransforms:
    def test_flip(self):
        b = T('##.\n#..')
        assert b.clone().fliph().bindata == ['011', '001']
        assert b.clone().flipv().bindata == ['100', '110']
        assert Bitmap([]).fliph().bindata == [] and Bitmap([]).flipv().bindata == []

    def test_rotate(self):
        b = T('##.\n#..')
        assert b.clone().rotate().bindata == ['11', '01', '00']
        assert b.clone().rotate(90).bindata == ['11', '01', '00']
        assert b.clone().rotate(180).bindata == ['001', '011']
        assert b.clone().rotate(270).bindata == ['00', '10', '11']
        assert b.clone().rotate(-90).bindata == ['00', '10', '11']
        assert b.clone().rotate(0) == b
        assert b.clone().rotate(360) == b
        assert b.clone().rotate(-450) == b.clone().rotate(270)
        assert Bitmap([]).rotate().bindata == []

    def test_rotate_error(self):
        with pytest.raises(ValueError):
            T('#').rotate(45)

    def test_invert(self):
        assert T('.#&').invert().bindata == ['100']
        assert T('.#&').invert().invert().bindata == ['011']

    def test_shift(self):
        b = T('#..\n...\n...')
        assert b.clone().shift(1).bindata == ['010', '000', '000']
        assert b.clone().shift(0, -1).bindata == ['000', '100', '000']
        assert b.clone().shift(2, -2).bindata == ['000', '000', '001']
        assert b.clone().shift(-1, 1).bindata == ['000', '000', '000']
        assert b.clone().shift().bindata == b.bindata

    def test_bbox(self):
        b = T('.....\n..#..\n.#&..\n.....')
        assert b.bbox() == (2, 2, 1, 1)
        assert b.clone().crop(*b.bbox()).bindata == ['01', '12']
        assert T('#').bbox() == (1, 1, 0, 0)
        assert T('...\n...').bbox() == (0, 0, 0, 0)
        assert Bitmap([]).bbox() == (0, 0, 0, 0)
        assert T('#..\n..#').bbox() == (3, 2, 0, 0)

    def test_trim(self):
        b = T('.....\n..#..\n.#&..\n.....')
        assert b.trim() is b
        assert b.bindata == ['01', '12']
        assert T('...\n...').trim().bindata == []
        assert Bitmap([]).trim().bindata == []

    def test_bold(self):
        assert T('#.#..').bold().bindata == ['111100']
        assert T('#....').bold(2).bindata == ['1110000']
        assert T('#&.').bold().bindata == ['1120']  # shifted pixel wins (b over a)
        assert T('#.').bold(0).bindata == ['10']
        assert Bitmap([]).bold().bindata == []
        with pytest.raises(ValueError):
            T('#').bold(-1)

    def test_italic(self):
        b = T('#\n#\n#\n#\n#')
        assert b.clone().italic().bindata == ['001', '010', '010', '100', '100']
        assert b.clone().italic(1).bindata == ['00001', '00010', '00100', '01000', '10000']
        assert b.clone().italic(2, 2).bindata == ['001', '010', '010', '100', '100']
        assert b.clone().italic(2, 1).bindata == ['001', '001', '010', '010', '100']
        assert b.clone().italic(3, 4).bindata == ['001', '010', '010', '010', '100']

    def test_italic_negative_shift(self):
        # base above the bottom: lower rows shift left (negative floor division)
        b = T('#\n#\n#\n#')
        assert b.clone().italic(2, 2).bindata == ['01', '01', '10', '10']
        assert b.clone().italic(1, 3).bindata == ['0001', '0010', '0100', '1000']

    def test_italic_errors_and_empty(self):
        with pytest.raises(ValueError):
            T('#').italic(0)
        assert Bitmap([]).italic().bindata == []

    def test_paste(self):
        b = Bitmap.blank(4, 3)
        assert b.paste(T('#&\n.#'), 1, 1) is b
        assert b.bindata == ['0000', '0120', '0010']
        b.paste(T('##\n##'), 3, 2)
        assert b.bindata == ['0000', '0120', '0011']
        b.paste(T('##\n##'), -1, -1)
        assert b.bindata == ['1000', '0120', '0011']
        b.paste(T('...\n...'), 0, 0)  # zeros never overwrite
        assert b.bindata == ['1000', '0120', '0011']
        b.paste(T('#'), 10, 10)
        assert b.bindata == ['1000', '0120', '0011']


class TestBitmapV2Extras:
    def test_replace_int(self):
        assert T('#.').replace(1, 2).bindata == ['20']
        assert T('#.').replace('0', 2).bindata == ['12']

    def test_shadow_other_directions(self):
        assert T('#').shadow(-1, 1).bindata == ['20', '01']
        assert T('#').shadow(0, 0).bindata == ['1']

    def test_bytepad_aligned(self):
        b = T('########')
        assert b.bytepad() is b and b.width() == 8
