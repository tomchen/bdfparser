"""SPEC-v3 §11 hardening decisions (cross-language parity findings K02-K17 and review)."""

import codecs
import io
import json
import sys
import time

import pytest

from bdfparser import BDFParseError, BDFParserWarning, Bitmap, Font, Glyph, cli
from bdfparser.encoding import (
    UNICODE_PREFIXES,
    canonical_charset,
    char2cp,
    charset_codec,
    charset_map,
    charset_props,
    charset_table,
    codec_name,
    cp2char,
    gb18030_ranges,
    sanitize_charset,
)
from bdfparser.pcf import PCFError, write_pcf
from bdfparser.ttf import _parse_cmap, _parse_tables, read_ttf

from .info import enctest_path, mini_bdf

pytestmark = pytest.mark.filterwarnings('ignore::bdfparser.BDFParserWarning')


def parse(text):
    return Font().load_string(text)


def bdf(props=(), glyphs=None, fbb='6 8 0 -1', size='8 75 75', version='2.1'):
    """A small BDF text with the given property lines and glyph blocks."""
    lines = [
        f'STARTFONT {version}',
        'FONT f',
        f'SIZE {size}',
        f'FONTBOUNDINGBOX {fbb}',
        f'STARTPROPERTIES {len(props)}',
        *props,
        'ENDPROPERTIES',
    ]
    if glyphs is None:
        glyphs = [glyph()]
    lines.append(f'CHARS {len(glyphs)}')
    for g in glyphs:
        lines += g
    lines.append('ENDFONT')
    return '\n'.join(lines) + '\n'


def glyph(name='A', enc='65', bbx='1 1 0 0', rows=('80',), extra=()):
    return [
        f'STARTCHAR {name}',
        f'ENCODING {enc}',
        *extra,
        f'BBX {bbx}',
        'BITMAP',
        *rows,
        'ENDCHAR',
    ]


# ---------------------------------------------------------------------------
# 11.1 charsets


class TestCharsetTable:
    NEW_KEYS = ('cp437', 'cp850', 'cp852', 'cp866', 'cp874', 'cp932', 'cp936', 'cp949', 'cp950')

    def test_new_keys(self):
        table = charset_table()
        for key in self.NEW_KEYS:
            assert table[key]['codec'] == key
            assert codec_name(key) == key
            assert charset_codec(key).known
            assert canonical_charset(key.upper()) == key
        assert table['cp437']['kind'] == 'sbcs'
        assert table['cp874']['kind'] == 'sbcs'
        assert table['cp932']['kind'] == 'dbcs'
        assert table['gb18030']['kind'] == 'gb18030'
        assert table['johab']['codec'] == 'johab'

    def test_hz_is_unknown(self):
        assert 'hz' not in charset_table()
        assert canonical_charset('HZ') == 'hz'
        assert charset_codec('hz').known is False
        assert codec_name('hz') is None

    def test_table_structure(self):
        table = charset_table()
        for key, info in table.items():
            assert set(info) == {'codec', 'kind', 'gl', 'forcegl', 'props', 'aliases'}
            assert canonical_charset(key) == key
            # the props written by charsetconvert canonicalise back to the key
            # (or to a key with the same codec)
            reg, enc = info['props']
            assert charset_codec(sanitize_charset(reg, enc)).codec == charset_codec(key).codec
            if info['kind'] == 'unicode':
                assert info['codec'] is None
            else:
                assert codec_name(key) == info['codec']
                codecs.lookup(info['codec'])  # available in every supported Python
        assert {k for k, v in table.items() if v['gl']} == {'gb2312', 'jisx0208', 'ksc5601'}
        assert [k for k, v in table.items() if v['forcegl']] == ['iso2022cn']
        assert table['shiftjis']['aliases'] == ['sjis']
        assert table['ksc5601']['aliases'] == ['ksx1001']
        assert UNICODE_PREFIXES == ('utf16', 'utf32', 'ucs2', 'ucs4')
        # a fresh copy every time
        table['gbk']['codec'] = 'x'
        assert charset_table()['gbk']['codec'] == 'gbk'

    def test_canonicalisation_cases(self):
        assert canonical_charset('ISO8859-01') == 'iso88591'  # K14
        assert canonical_charset('ISO8859-015') == 'iso885915'
        assert sanitize_charset('ISO8859', '01') == 'iso88591'
        assert sanitize_charset('ISO8859', '٣') == 'iso88591'  # no non-ASCII digits
        assert canonical_charset('KOI8-RU') == 'koi8ru'  # K14: no KOI8-RU codec: unknown
        assert charset_codec('koi8ru').known is False
        assert sanitize_charset('KOI8', 'RU') == 'koi8ru'
        assert sanitize_charset('KOI8', 'r') == 'koi8r'
        assert sanitize_charset('IBM', 'CP437') == 'cp437'
        assert canonical_charset('IBM-CP850') == 'cp850'
        assert canonical_charset('ibm-cp866') == 'cp866'
        assert canonical_charset('windows-874') == 'cp874'
        assert canonical_charset('MS932') == 'cp932'
        assert canonical_charset('microsoft-cp949') == 'cp949'
        assert canonical_charset('Windows-31J') == 'windows31j'  # not in the table
        assert sanitize_charset('microsoft', 'cp9999') == 'microsoft'
        assert sanitize_charset('cp1259') == 'cp1259'
        assert canonical_charset('Johab') == 'johab'
        assert charset_props('cp437') == ('IBM', 'CP437')
        assert charset_props('cp932') == ('MICROSOFT', 'CP932')
        assert charset_props('sjis') == ('SHIFTJIS', '0')

    def test_unicode_whitespace_is_not_stripped(self):
        assert sanitize_charset('\x1fgb2312') == '\x1fgb2312'
        assert sanitize_charset(' gb2312\t') == 'gb2312'


class TestStrictConversions:
    def test_char2cp_rejects_invalid_lengths(self):
        # K13: 3-byte JIS X 0212 and 8-byte KS X 1001 composition sequences
        assert char2cp('ß', 'jisx0208') is None
        assert char2cp('¡', 'EUC-JP') is None
        assert char2cp('갂', 'ksc5601') is None
        assert char2cp('갂', 'euckr') is None
        assert char2cp('갂', 'cp949') == 0x8141

    def test_char2cp_round_trip(self):
        # Shift_JIS encodes '¥' as 0x5C, which decodes to '\\'
        assert char2cp('¥', 'shiftjis') is None
        assert cp2char(0x5C, 'shiftjis') == '\\'
        assert char2cp('\\', 'shiftjis') == 0x5C
        assert char2cp('¥', 'jisx0201') is None

    def test_single_character_only(self):
        assert cp2char(0x8862, 'big5hkscs') is None  # two code points
        assert cp2char(0x4141, 'cp437') is None
        assert cp2char(0x41, 'cp437') == 'A'

    def test_gl_form_is_strict(self):
        # EUC-JP 0x8EB1 (half-width katakana, SS2) has no GL form
        assert cp2char(0x0E31, 'jisx0208', gl=True) is None
        assert char2cp('ｱ', 'jisx0208', gl=True) is None
        assert char2cp('ｱ', 'jisx0208') == 0x8EB1
        assert char2cp('あ', 'jisx0208', gl=True) == 0x2422
        assert cp2char(0xA4A2, 'jisx0208', gl=True) is None
        assert cp2char(0x41, 'gb2312', gl=True) == 'A'

    def test_gb18030_four_bytes(self):
        assert char2cp('😀', 'gb18030') == 0x9439FC36
        assert char2cp('\u0080', 'gb18030') == 0x81308130
        assert cp2char(0x81308130, 'gb18030') == '\u0080'
        assert cp2char(0x00813081, 'gb18030') is None  # 3 bytes
        assert cp2char(0x1_0000_0000, 'gb18030') is None

    def test_new_charsets(self):
        assert char2cp('é', 'cp437') == 0x82
        assert cp2char(0x82, 'cp437') == 'é'
        assert char2cp('Я', 'cp866') == 0x9F
        assert char2cp('ก', 'cp874') == 0xA1
        assert char2cp('あ', 'cp932') == 0x82A0
        assert char2cp('丂', 'cp936') == 0x8140
        assert char2cp('你', 'cp950') == 0xA741
        assert char2cp('가', 'johab') == 0x8861

    def test_module_level_unknown_warns_once(self):
        name = 'never-seen-charset-xyz'
        with pytest.warns(BDFParserWarning, match="Unknown charset 'neverseencharsetxyz'") as rec:
            assert char2cp('A', name) == 65
            assert cp2char(66, name) == 'B'
        assert len([w for w in rec if 'Unknown charset' in str(w.message)]) == 1

    @pytest.mark.parametrize('key', ['cp1252', 'koi8u', 'jisx0201', 'gb2312', 'big5hkscs'])
    def test_charset_map_round_trips(self, key):
        codec = charset_codec(key)
        m = charset_map(key)
        assert m == {cp: codec.cp2char(cp) for cp in m}
        chars = set(m.values())
        for ch in chars:
            cp = codec.char2cp(ch)
            assert cp is not None and m[cp] == ch

    def test_charset_map_contents(self):
        assert charset_map('gb2312')[0xB0A1] == '啊'
        assert 0x8140 not in charset_map('gb2312')
        assert len(charset_map('cp1252')) == 251
        assert max(charset_map('gb18030')) <= 0xFFFF
        with pytest.raises(ValueError):
            charset_map('utf8')
        with pytest.raises(ValueError):
            charset_map('fontspecific')

    def test_gb18030_ranges(self):
        runs = gb18030_ranges()
        assert runs[0] == (0, 0x80, 36)
        assert runs[-1] == (189000, 0x10000, 0x100000)

        def code(index):
            b3 = index % 10 + 0x30
            index //= 10
            b2 = index % 126 + 0x81
            index //= 126
            b1 = index % 10 + 0x30
            b0 = index // 10 + 0x81
            return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3

        for idx, cp, n in runs:
            for k in (0, n - 1):
                assert cp2char(code(idx + k), 'gb18030') == chr(cp + k)
                assert char2cp(chr(cp + k), 'gb18030') == code(idx + k)


class TestFontCodecCache:
    def gb_font(self):
        # a GB2312 font without a CHARSET_ENCODING: GL form detected from the codes
        font = Font(enctest_path('gb2312'))
        font.delprop('CHARSET_ENCODING')
        return font

    def count(self, monkeypatch):
        calls = []
        orig = Font._is_gl

        def counting(self, key):
            calls.append(key)
            return orig(self, key)

        monkeypatch.setattr(Font, '_is_gl', counting)
        return calls

    def test_cached(self, monkeypatch):
        font = self.gb_font()
        calls = self.count(monkeypatch)
        for _ in range(5):
            assert font.char2cp('啊') == 0xB0A1
            font.cp2char(0xB0A1)
        font.draw('啊啊')
        font.lacksglyphs('啊')
        assert len(calls) == 1

    def test_invalidated_by_props_and_override(self, monkeypatch):
        font = self.gb_font()
        calls = self.count(monkeypatch)
        assert font.char2cp('啊') == 0xB0A1
        font.setprop('CHARSET_ENCODING', '0')  # GL form
        assert font.char2cp('啊') == 0x3021
        font.delprop('CHARSET_ENCODING')
        assert font.char2cp('啊') == 0xB0A1
        font.encoding(charset='big5')
        assert font.charset == 'big5'
        assert font.char2cp('你') == 0xA741
        font.encoding(charset='')
        font.props['charset_registry'] = 'KOI8'  # direct assignment is noticed too
        assert font.char2cp('Я') == 0xF1
        assert len(calls) == 5

    def test_invalidated_by_glyph_set_changes(self):
        font = Font().load_string(
            mini_bdf.replace('STARTPROPERTIES 6', 'STARTPROPERTIES 7').replace(
                'DEFAULT_CHAR 65', 'DEFAULT_CHAR 65\nCHARSET_REGISTRY "GB2312.1980"'
            )
        )
        assert font.char2cp('啊') == 0xB0A1  # no 2-byte glyph: EUC form
        font.addglyph({'codepoint': 0x3021, 'bbw': 0, 'bbh': 0})
        assert font.char2cp('啊') == 0x3021  # GL form detected
        font.removeglyph(0x3021)
        assert font.char2cp('啊') == 0xB0A1
        g = font.newglyph(0x3021)
        assert font.char2cp('啊') == 0x3021
        g.setmeta(codepoint=0xB0A1)  # moves the glyph: EUC form again
        assert font.char2cp('啊') == 0xB0A1
        other = Font().load_string(mini_bdf)
        other.addglyph({'codepoint': 0x3021})
        font.merge(other)
        assert font.char2cp('啊') == 0x3021
        del font.glyphs[0x3021]  # direct dict edits that change the size are noticed
        assert font.char2cp('啊') == 0xB0A1
        font.glyphs[0x3021] = font.glyphs[65]
        assert font.char2cp('啊') == 0x3021
        font.load_string(mini_bdf)
        assert font.charset == 'iso10646'
        assert font.char2cp('啊') == 0x554A

    def test_unknown_warns_once_with_cache(self):
        font = Font().load_string(
            mini_bdf.replace('STARTPROPERTIES 6', 'STARTPROPERTIES 7').replace(
                'DEFAULT_CHAR 65', 'DEFAULT_CHAR 65\nCHARSET_REGISTRY "HZ"'
            )
        )
        with pytest.warns(BDFParserWarning) as rec:
            font.char2cp('A')
            font.addglyph({'codepoint': 70})
            font.char2cp('A')
        assert len([w for w in rec if "Unknown charset 'hz'" in str(w.message)]) == 1

    def test_charsetconvert_new_charsets(self):
        font = Font().load_string(mini_bdf)
        font.addglyph({'codepoint': 0xE9, 'glyphname': 'eacute'})
        font.charsetconvert('IBM-CP437')
        assert font.charset == 'cp437'
        assert font.getprop('CHARSET_REGISTRY') == 'IBM'
        assert sorted(font.glyphs) == [0x20, 0x41, 0x42, 0x82]
        assert font.glyphs[0x82][0] == 'eacute'
        font.charsetconvert('ISO10646-1')
        assert sorted(font.glyphs) == [0x20, 0x41, 0x42, 0xE9]

    def test_charsetconvert_drops_non_round_trip_codes(self):
        font = Font().load_string(mini_bdf)
        font.addglyph({'codepoint': 0xA5, 'glyphname': 'yen'})
        font.addglyph({'codepoint': 0xDF, 'glyphname': 'germandbls'})
        with pytest.warns(BDFParserWarning, match='2 glyph'):
            font.charsetconvert('Shift_JIS')
        assert sorted(font.glyphs) == [0x20, 0x41, 0x42]


# ---------------------------------------------------------------------------
# 11.2 numbers


class TestNumbers:
    @pytest.mark.parametrize(
        'version', ['inf', 'nan', '2_1', '.5', '1e1', '0x10', 'Infinity', '2.', '+2.1', '2.1 x']
    )
    def test_bad_startfont_version(self, version):
        with pytest.raises(BDFParseError, match='STARTFONT'):
            parse(bdf(version=version))

    @pytest.mark.parametrize('version,expected', [('02.1', 2.1), ('2', 2.0), ('2.10', 2.1)])
    def test_good_startfont_version(self, version, expected):
        assert parse(bdf(version=version)).headers['bdfversion'] == expected

    @pytest.mark.parametrize(
        'text',
        [
            bdf(glyphs=[glyph(enc='1_2')]),
            bdf(glyphs=[glyph(enc='٣')]),
            bdf(glyphs=[glyph(enc='-1 1_0')]),
            bdf(glyphs=[glyph(enc='0x41')]),
            bdf(glyphs=[glyph(bbx='1_0 1 0 0')]),
            bdf(glyphs=[glyph(extra=['SWIDTH 500 0\x1f'])]),
            bdf(glyphs=[glyph(extra=['DWIDTH 1e1 0'])]),
            bdf(size='8 75 7_5'),
            bdf(fbb='6 8 0 -1.0'),
            bdf().replace('CHARS 1', 'CHARS 1_0'),
            bdf().replace('CHARS 1', 'CHARS ١'),
        ],
    )
    def test_malformed_numbers(self, text):
        with pytest.raises(BDFParseError, match='malformed number'):
            parse(text)

    @pytest.mark.parametrize(
        'text',
        [
            bdf(glyphs=[glyph(enc='2147483648')]),
            bdf(glyphs=[glyph(extra=['SWIDTH 99999999999999999999 0'])]),
            bdf(glyphs=[glyph(bbx='1 1 -2147483649 0')]),
            bdf(size='2147483648 75 75'),
            bdf().replace('CHARS 1', 'CHARS 4294967296'),
        ],
    )
    def test_int32_range(self, text):
        with pytest.raises(BDFParseError, match='out of the 32-bit range'):
            parse(text)

    def test_int32_limits_accepted(self):
        font = parse(
            bdf(glyphs=[glyph(enc='2147483647', extra=['SWIDTH -2147483648 +2147483647'])])
        )
        assert font.glyphs[2147483647][6:8] == [-2147483648, 2147483647]

    def test_property_int_range(self):
        font = parse(
            bdf(
                props=[
                    'A 4294967295',
                    'B 4294967296',
                    'C -2147483648',
                    'D -2147483649',
                    'E 99999999999999999999',
                    'F +5',
                    'G 1_0',
                    'H ٣',
                ]
            )
        )
        p = font.props
        assert p['a'] == 4294967295 and p['c'] == -2147483648 and p['f'] == 5
        assert p['b'] == '4294967296' and p['d'] == '-2147483649'
        assert p['e'] == '99999999999999999999'
        assert p['g'] == '1_0' and p['h'] == '٣'
        assert 'B "4294967296"' in font.tobdf()

    def test_property_count_strict(self):
        with pytest.warns(BDFParserWarning, match='malformed property count'):
            font = Font().load_string(
                bdf(props=['A 1']).replace('STARTPROPERTIES 1', 'STARTPROPERTIES 1_0')
            )
        assert font.props['a'] == 1

    def test_todata_zero_width_rows(self):
        b = Bitmap(['', ''])
        assert b.todata(4) == ['', '']
        assert b.todata(5) == [0, 0]
        assert Bitmap(['0101']).todata(4) == ['5']
        assert Bitmap(['1' * 60]).todata(5) == [2**60 - 1]


class TestPcfGuards:
    def font(self, props=()):
        return parse(bdf(props=list(props)))

    def test_huge_ascent_rejected_before_allocation(self):
        font = self.font(['FONT_ASCENT 300000000', 'FONT_DESCENT 1'])
        t = time.monotonic()
        with pytest.raises(
            PCFError,
            match=r'^PCF: FONT_ASCENT 300000000 / FONT_DESCENT 1 do not fit in 16 bits$',
        ):
            font.topcf()
        assert time.monotonic() - t < 1

    @pytest.mark.parametrize(
        'asc,desc',
        [(32768, 0), (0, -32769), (20000, 20000), (-32768, -1), (40000, -39990)],
    )
    def test_ascent_descent_16_bits(self, asc, desc):
        font = self.font([f'FONT_ASCENT {asc}', f'FONT_DESCENT {desc}'])
        with pytest.raises(PCFError, match='do not fit in 16 bits'):
            write_pcf(font)

    def test_ascent_descent_limits_ok(self):
        font = self.font(['FONT_ASCENT 32767', 'FONT_DESCENT 0'])
        assert font.topcf()[:4] == b'\x01fcp'

    def test_derived_ascent_from_fbb(self):
        font = self.font()
        font.headers['fbby'] = 40000
        with pytest.raises(PCFError, match='FONT_ASCENT 39999 / FONT_DESCENT 1'):
            font.topcf()

    def test_property_32_bits(self):
        font = self.font(['A 4294967295', 'B -2147483648'])
        assert font.topcf()
        font.setprop('Big', 2**32)
        with pytest.raises(
            PCFError, match=r'^PCF: property Big value 4294967296 does not fit in 32 bits$'
        ):
            font.topcf()
        font.delprop('Big')
        font.setprop('FONT_ASCENT', -(2**31) - 1)
        with pytest.raises(PCFError, match='property FONT_ASCENT value -2147483649 does not fit'):
            font.topcf()

    def test_generated_property_32_bits(self):
        font = self.font()
        font.headers['pointsize'] = 2**31 - 1  # POINT_SIZE = float32(pointsize) * 10
        with pytest.raises(PCFError, match='property POINT_SIZE value 21474836480 does not fit'):
            font.topcf()

    def test_glyph_messages(self):
        font = self.font()
        font.glyphs[65][8] = 40000
        with pytest.raises(
            PCFError, match=r'^Glyph "A": metric value 40000 does not fit in 16 bits$'
        ):
            font.topcf()
        font.glyphs[65][8] = 1
        font.glyphs[65][2] = -1
        with pytest.raises(PCFError, match=r'^Glyph "A" has a negative sized bitmap, -1x1$'):
            font.topcf()


# ---------------------------------------------------------------------------
# 11.3 properties


class TestCommentLikeProperties:
    def test_lowercase_comment_property(self):
        text = bdf(props=['FOO 1', 'comment "abc"', 'Comment x y', 'COMMENT z', 'BAR 2'])
        with pytest.warns(BDFParserWarning, match="property 'comment' treated as a COMMENT"):
            font = Font().load_string(text)
        assert font.props['comment'] == ['abc', 'x y', 'z']
        assert list(font.props) == ['foo', 'comment', 'bar']
        out = font.tobdf()
        assert 'STARTPROPERTIES 2\nCOMMENT "abc"\nCOMMENT "x y"\nCOMMENT "z"\nFOO 1\nBAR 2\n' in out

    def test_comment_int_then_comment(self):
        # K06d: used to crash with AttributeError
        font = parse(bdf(props=['comment 5', 'COMMENT x']))
        assert font.props['comment'] == ['5', 'x']

    def test_non_ascii_lookalike_is_a_property(self):
        font = parse(bdf(props=['сomment 1']))  # Cyrillic 'с'
        assert font.props['сomment'] == 1


# ---------------------------------------------------------------------------
# 11.4 parsing and drawing robustness


class TestWhitespace:
    def test_ascii_whitespace_separators(self):
        text = bdf(glyphs=[glyph(extra=['SWIDTH\t500\v0', 'DWIDTH\f6 0'])]).replace(
            'SIZE 8 75 75', 'SIZE\x0b8\t75  75'
        )
        font = parse(text)
        assert font.headers['pointsize'] == 8
        assert font.glyphs[65][6:10] == [500, 0, 6, 0]

    def test_unicode_whitespace_is_ordinary(self):
        font = parse(bdf().replace('FONT f', 'FONT f\x85\nCOMMENT hello\x85\nCOMMENT y﻿'))
        assert font.headers['fontname'] == 'f\x85'
        assert font.headers['comment'] == ['hello\x85', 'y﻿']

    def test_feff_line_is_unknown_keyword(self):
        with pytest.warns(BDFParserWarning, match='unknown header keyword'):
            font = Font().load_string(bdf().replace('FONT f', 'FONT f\n﻿COMMENT x'))
        assert 'comment' not in font.headers

    def test_leading_bom_skipped(self):
        assert parse('﻿' + bdf()).headers['fontname'] == 'f'

    def test_x1f_glyph_name_kept(self):
        font = parse(bdf(glyphs=[glyph(name='A\x1f')]))
        assert font.glyphs[65][0] == 'A\x1f'

    def test_x1c_separator_is_not_whitespace(self):
        with pytest.raises(BDFParseError):
            parse(bdf(glyphs=[glyph(bbx='1\x1c1 0 0')]))


class TestBitmapBlock:
    def test_comment_inside_bitmap_ignored(self):
        font = parse(
            bdf(glyphs=[glyph(bbx='8 2 0 0', rows=('FF', 'COMMENT hello', 'COMMENT', '81'))])
        )
        assert font.glyphs[65][16] == ['FF', '81']

    def test_hex_rows_starting_with_keyword_letters(self):
        font = parse(bdf(glyphs=[glyph(bbx='8 3 0 0', rows=('C0', 'E1', 'Ab'))]))
        assert font.glyphs[65][16] == ['C0', 'E1', 'Ab']


class TestNegativeSizes:
    @pytest.mark.parametrize('bbx', ['-1 1 0 0', '1 -1 0 0'])
    def test_negative_bbx(self, bbx):
        with pytest.raises(BDFParseError, match='negative BBX'):
            parse(bdf(glyphs=[glyph(bbx=bbx)]))

    @pytest.mark.parametrize('fbb', ['-1 2 0 0', '2 -1 0 0'])
    def test_negative_fbb(self, fbb):
        with pytest.raises(BDFParseError, match='negative FONTBOUNDINGBOX'):
            parse(bdf(fbb=fbb))

    def test_negative_offsets_fine(self):
        assert parse(bdf(fbb='6 8 -3 -2', glyphs=[glyph(bbx='1 1 -1 -2')]))

    def test_crop_negative(self):
        with pytest.raises(ValueError, match=r'^Bitmap.crop: negative width or height \(-1, 2\)$'):
            Bitmap(['101']).crop(-1, 2, 0, 0)
        with pytest.raises(ValueError, match=r'\(1, -2\)'):
            Bitmap(['101']).crop(1, -2)
        assert Bitmap(['101']).crop(0, 0).bindata == []

    def test_draw_with_negative_headers(self):
        font = parse(bdf())
        font.headers['fbbx'] = -1
        with pytest.raises(ValueError, match='negative width'):
            font.glyphbycp(65).draw()


class TestNonHexRows:
    @pytest.mark.parametrize('row', ['XY', 'F_F', '0x', '+F', 'F F', 'ＦＦ'])
    def test_draw_raises(self, row):
        font = parse(bdf(glyphs=[glyph(bbx='8 2 0 0', rows=('FF', row))]))
        g = font.glyphbycp(65)
        expected = f'Glyph "A" (codepoint 65): bitmap row 1 {json.dumps(row, ensure_ascii=False)} contains a non-hex character'
        for mode in (0, 1, 2):
            with pytest.raises(ValueError) as exc:
                g.draw(mode)
            assert str(exc.value) == expected
        with pytest.raises(ValueError, match='non-hex'):
            font.draw('A')
        with pytest.raises(ValueError, match='non-hex'):
            font.tottf()
        # the PCF writer keeps bdftopcf's lenient behaviour
        assert font.topcf()

    def test_message_quotes(self):
        font = parse(bdf(glyphs=[glyph(name='my "A"', bbx='8 1 0 0', rows=('"G',))]))
        with pytest.raises(ValueError) as exc:
            font.glyphbycp(65).draw()
        assert str(exc.value) == (
            'Glyph "my "A"" (codepoint 65): bitmap row 0 "\\"G" contains a non-hex character'
        )


class TestTransformOrder:
    def test_glyphs_then_unencoded(self):
        font = parse(
            bdf(
                glyphs=[
                    glyph('u1', enc='-1'),
                    glyph('B', enc='66'),
                    glyph('u2', enc='-1'),
                    glyph('A', enc='65'),
                ]
            )
        )
        seen = []

        def fn(bm):
            seen.append(bm)
            if len(seen) == 3:
                raise RuntimeError('stop')
            return bm.invert()

        with pytest.raises(RuntimeError):
            font.transform(fn)
        # B and A (font.glyphs order) were changed, u1 (first unencoded) was not
        assert font.glyphs[66][16] != ['80']
        assert font.glyphs[65][16] != ['80']
        assert font.unencoded[0]['meta'][16] == ['80']


class TestOverlay:
    def test_keeps_own_size(self):
        with pytest.warns(BDFParserWarning):
            assert Bitmap(['1001110']).overlay(Bitmap([])).bindata == ['1001110']  # K04
        with pytest.warns(BDFParserWarning):
            assert Bitmap(['000', '000']).overlay(Bitmap(['1'])).bindata == ['100', '000']
        with pytest.warns(BDFParserWarning):
            assert Bitmap(['00', '00']).overlay(Bitmap(['0111', '1111', '1111'])).bindata == [
                '01',
                '11',
            ]
        assert Bitmap(['10', '01']).overlay(Bitmap(['02', '00'])).bindata == ['12', '01']


class TestConcatallVertical:
    def test_k16(self):
        r = Bitmap.concatall(
            [Bitmap([]), Bitmap([]), Bitmap(['0110', '0010'])],
            direction=-1,
            align=0,
            offsetlist=[-2, 3],
        )
        assert r.bindata == ['0110', '0010']

    def test_skips_empty_and_their_offsets(self):
        a = Bitmap(['11'])
        b = Bitmap(['1'])
        r = Bitmap.concatall([a, Bitmap(['', '']), b], direction=0, offsetlist=[5, 1])
        assert r.bindata == ['11', '00', '10']
        r = Bitmap.concatall([Bitmap(['000']), Bitmap([]), b], direction=0, align=0)
        assert r.bindata == ['000', '001']
        r = Bitmap.concatall([Bitmap(['', '']), b], direction=-1, offsetlist=[4])
        assert r.bindata == ['1']

    def test_all_empty(self):
        assert Bitmap.concatall([Bitmap([]), Bitmap(['', ''])], direction=0).bindata == []

    def test_equal_row_lengths(self):
        r = Bitmap.concatall(
            [Bitmap(['1']), Bitmap(['0110', '0010'])], direction=0, offsetlist=[-3]
        )
        assert len({len(row) for row in r.bindata}) == 1


def test_removeglyph_stale_glyph_noop():
    font = parse(bdf(glyphs=[glyph('A', '65'), glyph('B', '66')]))
    g = font.glyphbycp(65)
    font.removeglyph(g)
    font.addglyph({'codepoint': 65, 'glyphname': 'new'}, replace=False)
    font.removeglyph(g)
    assert font.glyphs[65][0] == 'new'


# ---------------------------------------------------------------------------
# 11.5 outputs


class TestTtfCmap:
    def test_surrogates_and_out_of_range_unmapped(self):
        font = parse(
            bdf(
                glyphs=[
                    glyph('A', '65'),
                    glyph('hs', str(0xD800)),
                    glyph('ls', str(0xDFFF)),
                    glyph('big', str(0x110000)),
                    glyph('last', str(0x10FFFF)),
                ]
            )
        )
        data = font.tottf()
        cmap = _parse_cmap(_parse_tables(data)['cmap'])
        assert sorted(cmap) == [65, 0x10FFFF]
        back = Font(data)
        assert sorted(back.glyphs) == sorted(font.glyphs)  # glyphs kept (BDFP)
        plain = read_ttf(font.tottf(metadata=False), pixelsize=8)
        assert sorted(plain.glyphs) == [65, 0x10FFFF]
        assert len(plain.unencoded) == 3


class TestSvgFont:
    def gb_font(self):
        return Font(enctest_path('gb2312'))

    def test_unicode_values_for_non_unicode_font(self):
        font = self.gb_font()
        svg = font.tosvgfont()
        uni = font.cp2char(0xC8CB)
        assert uni == '人'
        assert f'unicode="&#x{ord(uni):x};"' in svg
        assert 'unicode="&#xc8cb;"' not in svg
        rng = svg.split('unicode-range="')[1].split('"')[0]
        cps = sorted({ord(font.cp2char(cp)) for cp in font.glyphs})
        assert rng.startswith(f'U+{cps[0]:04X}')
        assert font.tosvgfont(unicodeformat='char').count('unicode="人"') == 1
        assert f'unicode="&#{ord(uni)};"' in font.tosvgfont(unicodeformat='decncr')

    def test_unicode_font_unchanged(self):
        font = Font().load_string(mini_bdf)
        svg = font.tosvgfont()
        assert 'unicode="&#x41;"' in svg and 'unicode-range="U+0041-0042"' not in svg
        assert 'unicode-range="U+0020, U+0041-0042"' in svg

    def test_unmappable_glyphs_have_no_unicode(self):
        font = parse(
            bdf(
                props=['CHARSET_REGISTRY "ISO8859"', 'CHARSET_ENCODING "1"'],
                glyphs=[glyph('A', '65'), glyph('wide', '300'), glyph('hs', str(0xD800))],
            )
        )
        for fmt in ('hexncr', 'decncr', 'char'):
            svg = font.tosvgfont(unicodeformat=fmt)
            assert svg.count('unicode=') == 1
            assert 'unicode-range="U+0041"' in svg
            svg.encode('utf-8')  # never contains a lone surrogate
        uni = parse(bdf(glyphs=[glyph('hs', str(0xD800)), glyph('big', str(0x110000))]))
        svg = uni.tosvgfont(unicodeformat='char')
        assert 'unicode="' not in svg and 'unicode-range=""' in svg
        svg.encode('utf-8')

    def test_control_chars_use_unicode_value(self):
        font = parse(
            bdf(
                props=['CHARSET_REGISTRY "KOI8"', 'CHARSET_ENCODING "R"'],
                glyphs=[glyph('ctl', '1'), glyph('ya', str(0xF1))],
            )
        )
        svg = font.tosvgfont()
        assert 'unicode="&#x42f;"' in svg and 'unicode="&#x1;"' not in svg
        assert 'unicode="&#x1;"' in font.tosvgfont(controlcharnoskip=True)


class TestReadTtfGuard:
    def test_huge_glyph_rejected(self):
        font = Font.create(pixelsize=8)
        font.newglyph(65, Bitmap(['1' * 8] * 8))
        data = font.tottf(metadata=False)
        t = time.monotonic()
        with pytest.raises(ValueError) as exc:
            read_ttf(data, pixelsize=8 * 600)
        assert time.monotonic() - t < 2
        assert str(exc.value) == (
            'Malformed TrueType font: glyph 1 bounding box too large (4800x4800 pixels)'
        )
        assert read_ttf(data, pixelsize=8 * 500).glyphs  # 4000x4000 < 2**24

    def test_huge_bdfp_box_rejected(self):
        font = Font.create(pixelsize=8, fontname='long font name')
        font.newglyph(65, Bitmap(['1' * 8] * 8))
        data = bytearray(font.tottf())
        tables = _parse_tables(bytes(data))
        raw = tables['BDFP']
        obj = json.loads(raw.decode('utf-8'))
        entry = obj['glyphs'][0]
        assert len(entry) == 18
        entry[3], entry[4] = 5000, 4000
        obj['headers']['fontname'] = ''  # make room for the longer numbers
        new = json.dumps(obj, separators=(',', ':')).encode('utf-8')
        # same length: patch in place (pad with spaces inside the JSON)
        assert len(new) <= len(raw)
        new = new + b' ' * (len(raw) - len(new))
        start = bytes(data).index(raw)
        data[start : start + len(raw)] = new
        with pytest.raises(
            ValueError, match=r'glyph 1 bounding box too large \(5000x4000 pixels\)'
        ):
            read_ttf(bytes(data))


# ---------------------------------------------------------------------------
# CLI on consoles that cannot encode every character


def test_cli_info_non_encodable(monkeypatch, tmp_path):
    font = Font().load_string(mini_bdf.replace('FAMILY_NAME "Mini"', 'FAMILY_NAME "宋体 Ω"'))
    font.headers['fontname'] = '宋体'
    path = tmp_path / 'f.bdf'
    font.save(path)
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding='cp1252', errors='strict')
    monkeypatch.setattr(sys, 'stdout', stream)
    assert cli.main(['info', str(path)]) == 0
    stream.flush()
    out = raw.getvalue().decode('cp1252')
    assert 'fontname: ??' in out
    assert 'FAMILY_NAME "?? ?"' in out


def test_cli_print_fallback():
    class Strict(io.StringIO):
        encoding = 'ascii'

        def write(self, s):
            s.encode('ascii')
            return super().write(s)

    out = Strict()
    cli._print('a 宋 b', out)
    assert out.getvalue() == 'a ? b\n'


def test_glyph_detached_hexrow_error_uses_meta():
    g = Glyph({'glyphname': 'x', 'codepoint': None, 'bbw': 4, 'bbh': 1, 'hexdata': ['G']}, None)
    with pytest.raises(ValueError, match=r'Glyph "x" \(codepoint None\): bitmap row 0 "G"'):
        g.draw(1)
