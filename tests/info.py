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
        '00'
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
    '0000000000000000'
]


specfont_path = 'tests/fonts/spec_example_fixed.bdf'

bitmap_qr2_bindata = [
    '01110',
    '02112',
    '01102',
    '10200',
    '01000'
]

bitmap_qr3_bindata = [
    '0111000000',
    '0211200000',
    '0110200030',
    '1020000021',
    '0100000000'
]

missing_glyph_meta = {'glyphname': 'missing glyph', 'codepoint': 0, 'bbw': 16, 'bbh': 16, 'bbxoff': 0, 'bbyoff': -2, 'swx0': 1000, 'swy0': 0, 'dwx0': 16, 'dwy0': 0, 'swx1': None, 'swy1': None, 'dwx1': None, 'dwy1': None, 'vvectorx': None, 'vvectory': None, 'hexdata': ['0000', '0000', '0000', '3ff8', '3018', '2828', '2448', '2288', '2108', '2288', '2448', '2828', '3018', '3ff8', '0000', '0000']}
