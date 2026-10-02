unifont_path = 'tests/fonts/unifont-13.0.04-for-test.bdf'

# glyph 'a'
glyph_a_meta = {
    'glyphname': 'U+0061',
    'codepoint': 97,
    'bbw': 8,
    'bbh': 16,
    'bbxoff': 0,
    'bbyoff': -2,
    'swx0': 500,
    'swy0': 0,
    'dwx0': 8,
    'dwy0': 0,
    'swx1': None,
    'swy1': None,
    'dwx1': None,
    'dwy1': None,
    'vvectorx': None,
    'vvectory': None,
    'hexdata': [
        '00',
        '00',
        '00',
        '00',
        '00',
        '00',
        '3C',
        '42',
        '02',
        '3E',
        '42',
        '42',
        '46',
        '3A',
        '00',
        '00',
    ],
}

# glyph 'a''s bitmap
bitmap_a_bindata = [
    '0000000000000000',
    '0000000000000000',
    '0000000000000000',
    '0000000000000000',
    '0000000000000000',
    '0000000000000000',
    '0011110000000000',
    '0100001000000000',
    '0000001000000000',
    '0011111000000000',
    '0100001000000000',
    '0100001000000000',
    '0100011000000000',
    '0011101000000000',
    '0000000000000000',
    '0000000000000000',
]


specfont_path = 'tests/fonts/spec_example_fixed.bdf'

bitmap_qr2_bindata = ['01110', '02112', '01102', '10200', '01000']

bitmap_qr3_bindata = ['0111000000', '0211200000', '0110200030', '1020000021', '0100000000']

missing_glyph_meta = {
    'glyphname': 'missing glyph',
    'codepoint': 0,
    'bbw': 16,
    'bbh': 16,
    'bbxoff': 0,
    'bbyoff': -2,
    'swx0': 1000,
    'swy0': 0,
    'dwx0': 16,
    'dwy0': 0,
    'swx1': None,
    'swy1': None,
    'dwx1': None,
    'dwy1': None,
    'vvectorx': None,
    'vvectory': None,
    'hexdata': [
        '0000',
        '0000',
        '0000',
        '3ff8',
        '3018',
        '2828',
        '2448',
        '2288',
        '2108',
        '2288',
        '2448',
        '2828',
        '3018',
        '3ff8',
        '0000',
        '0000',
    ],
}

hanwang_path = 'tests/fonts/HanWangYanKai-26.bdf'
unifont_full_path = 'tests/fonts/unifont-13.0.04.bdf'
unifont_reduced_path = 'tests/fonts/unifont-13.0.04-reduced.bdf'
emptylines_path = 'tests/fonts/unifont-13.0.04-for-test-emptylines.bdf'
specfont_bad_path = 'tests/fonts/spec_example_bad.bdf'


def enctest_path(name):
    return f'tests/fonts/unifont-13.0.04-enctest-{name}.bdf'


# A tiny, FontForge-style BDF font used by many v3 tests
mini_bdf = """STARTFONT 2.1
FONT -Test-Mini-Medium-R-Normal--8-80-75-75-C-60-ISO10646-1
SIZE 8 75 75
FONTBOUNDINGBOX 6 8 0 -1
COMMENT "mini test font"
STARTPROPERTIES 6
FAMILY_NAME "Mini"
WEIGHT_NAME "Medium"
PIXEL_SIZE 8
FONT_ASCENT 7
FONT_DESCENT 1
DEFAULT_CHAR 65
ENDPROPERTIES
CHARS 3
STARTCHAR space
ENCODING 32
SWIDTH 750 0
DWIDTH 6 0
BBX 0 0 0 0
BITMAP
ENDCHAR
STARTCHAR A
ENCODING 65
SWIDTH 750 0
DWIDTH 6 0
BBX 5 7 0 0
BITMAP
20
50
88
F8
88
88
88
ENDCHAR
STARTCHAR B
ENCODING 66
SWIDTH 750 0
DWIDTH 6 0
BBX 4 7 1 0
BITMAP
E0
90
90
E0
90
90
E0
ENDCHAR
ENDFONT
"""

bitmap_mini_A_fbb = [
    '001000',
    '010100',
    '100010',
    '111110',
    '100010',
    '100010',
    '100010',
    '000000',
]
