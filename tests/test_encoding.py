"""Charsets / encodings (spec section 4), port of bdfparser-js test/encoding.test.ts + issue #4."""

import pytest

from bdfparser import BDFParserWarning, Font
from bdfparser.encoding import (
    CharsetCodec,
    canonical_charset,
    char2cp,
    charset_codec,
    charset_props,
    cp2char,
    is_unicode_charset,
    sanitize_charset,
)

from .info import enctest_path, mini_bdf

a_ren_guang_bitmap = [
    '0000000000000001000000000000000100000000',
    '0000000000000001000000000010000100001000',
    '0000000000000001000000000001000100001000',
    '0000000000000001000000000000100100010000',
    '0001100000000001000000000000100100100000',
    '0010010000000001000000000000000100000000',
    '0010010000000010100000001111111111111110',
    '0100001000000010100000000000010001000000',
    '0100001000000100010000000000010001000000',
    '0111111000000100010000000000010001000000',
    '0100001000001000001000000000010001000000',
    '0100001000001000001000000000100001000010',
    '0100001000010000000100000000100001000010',
    '0100001000100000000010000001000001000010',
    '0000000001000000000001000010000000111110',
    '0000000010000000000000101100000000000000',
]

examples = {
    'UTF-8': ('A', 0x41),
    'Unicode': ('A', 0x41),
    'UTF-16': ('A', 0x0041),
    'UTF-32': ('A', 0x00000041),
    'ASCII': ('A', 0x41),
    'ISO-8859-1': ('é', 0xE9),
    'Windows-1251': ('ё', 0xB8),
    'Windows-1250': ('€', 0x80),
    'Shift-JIS': ('あ', 0x82A0),
    'EUC-KR': ('가', 0xB0A1),
    'ISO-2022-CN': ('你', 0x4463),
    'GB2312': ('你', 0xC4E3),
    'GBK': ('你', 0xC4E3),
    'GB18030': ('你', 0xC4E3),
    'Big5': ('你', 0xA741),
    'KOI8-R': ('Я', 0xF1),
    'ISO-8859-5': ('Я', 0xCF),
    'ISO-8859-2': ('č', 0xE8),
    'TIS-620': ('ะ', 0xD0),
    'MacRoman': ('é', 0x8E),
}

cjks = {
    'utf8': 'utf8',
    'unicode': 'unicode',
    'iso10646': 'iso10646',
    'gb2312': 'gb2312',
    'iso2022cn': 'gb2312',  # GB2312.1980 registry, GL codes (detected)
    'big5': 'big5',
    'shiftjis': 'shiftjis',
    'euckr': 'euckr',
}


def utf8font():
    return Font(enctest_path('utf8'))


# ---------------------------------------------------------------------------
# font loading and encoding-related properties


class TestFontEncoding:
    def test_normal(self):
        font = utf8font()
        assert font.props['charset_registry'] == 'UTF-8'
        assert font.charset == 'utf8'
        assert font.draw('A人光').bindata == a_ren_guang_bitmap

    def test_override_before_loading_persists(self):
        font = Font().encoding(charset='gbk')
        font.load_file_path(enctest_path('utf8'))
        assert font.props['charset_registry'] == 'UTF-8'
        assert font.charset == 'gbk'

    def test_charset_overwritten_by_encoding(self):
        font = utf8font().encoding(charset='gb2312')
        assert font.props['charset_registry'] == 'UTF-8'
        assert font.charset == 'gb2312'
        assert font.draw('A人光').bindata != a_ren_guang_bitmap

    def test_clear_override(self):
        font = utf8font().encoding(charset='gb2312').encoding(charset='')
        assert font.charset == 'utf8'

    def test_char2cp_unicode(self):
        assert utf8font().char2cp('人') == 20154

    def test_cp2char_unicode(self):
        assert utf8font().cp2char(20154) == '人'

    def test_char2cp_gb2312(self):
        assert utf8font().encoding(charset='gb2312').char2cp('人') == 51403

    def test_cp2char_gb2312(self):
        assert utf8font().encoding(charset='gb2312').cp2char(51403) == '人'

    def test_char2cp_overwritten(self):
        font = utf8font().encoding(charset='gb2312', char2cp=lambda c: 0, cp2char=lambda cp: '一')
        assert font.char2cp('人') == 0

    def test_cp2char_overwritten(self):
        font = utf8font().encoding(charset='gb2312', char2cp=lambda c: 0, cp2char=lambda cp: '一')
        assert font.cp2char(51403) == '一'

    def test_only_one_override(self):
        font = utf8font().encoding(cp2char=lambda cp: 'x')
        assert font.cp2char(1) == 'x'
        assert font.char2cp('人') == 20154

    def test_override_used_by_draw_and_glyph(self):
        font = utf8font().encoding(char2cp=lambda c: {'a': 65, 'b': 20154}.get(c))
        assert font.glyph('b').cp() == 20154
        assert font.lacksglyphs('abz') == ['z']

    def test_default_charset(self):
        font = Font().load_string(mini_bdf.replace('STARTPROPERTIES 6', 'STARTPROPERTIES 6'))
        assert font.charset == 'iso10646'
        assert Font().charset == 'iso10646'


class TestVariousEncodings:
    @pytest.mark.parametrize('encoding', list(examples))
    def test_font_char2cp_cp2char(self, encoding):
        char, cp = examples[encoding]
        font = utf8font().encoding(charset=encoding)
        assert font.char2cp(char) == cp
        assert font.cp2char(cp) == char

    @pytest.mark.parametrize('name', list(cjks))
    def test_a_ren_guang_bitmap(self, name):
        font = Font(enctest_path(name))
        assert font.charset == cjks[name]
        assert font.draw('A人光').bindata == a_ren_guang_bitmap
        assert font.lacksglyphs('A人光') is None
        assert font.glyph('人').chr() == '人'

    def test_cp1252(self):
        font = Font(enctest_path('cp1252'))
        assert font.charset == 'cp1252'
        assert font.draw('Aœ').bindata == [
            '000000000000000000000000',
            '000000000000000000000000',
            '000000000000000000000000',
            '000000000000000000000000',
            '000110000000000000000000',
            '001001000000000000000000',
            '001001000011011000000000',
            '010000100100100100000000',
            '010000100100100100000000',
            '011111100100111100000000',
            '010000100100100000000000',
            '010000100100100000000000',
            '010000100100100100000000',
            '010000100011011000000000',
            '000000000000000000000000',
            '000000000000000000000000',
        ]

    def test_cp1251(self):
        font = Font(enctest_path('cp1251'))
        assert font.charset == 'cp1251'
        assert font.draw('AЭ').bindata == [
            '000000000000000000000000',
            '000000000000000000000000',
            '000000000000000000000000',
            '000000000000000000000000',
            '000110000011100000000000',
            '001001000100010000000000',
            '001001000000001000000000',
            '010000100000001000000000',
            '010000100011111000000000',
            '011111100000001000000000',
            '010000100000001000000000',
            '010000100000001000000000',
            '010000100100010000000000',
            '010000100011100000000000',
            '000000000000000000000000',
            '000000000000000000000000',
        ]

    def test_cp1250(self):
        font = Font(enctest_path('cp1250'))
        assert font.charset == 'cp1250'
        assert font.draw('Ať').bindata == [
            '000000000010010000000000',
            '000000000001100000000000',
            '000000000000000000000000',
            '000000000000000000000000',
            '000110000001000000000000',
            '001001000001000000000000',
            '001001000001000000000000',
            '010000100111110000000000',
            '010000100001000000000000',
            '011111100001000000000000',
            '010000100001000000000000',
            '010000100001000000000000',
            '010000100001000000000000',
            '010000100000110000000000',
            '000000000000000000000000',
            '000000000000000000000000',
        ]


# ---------------------------------------------------------------------------
# issue #4: GB2312.1980-0 (GL form) font


def gb2312_gl_font(encoding='0'):
    return Font().load_string(
        '\n'.join(
            [
                'STARTFONT 2.1',
                'FONT -misc-song-medium-r-normal--4-40-75-75-c-40-gb2312.1980-0',
                'SIZE 4 75 75',
                'FONTBOUNDINGBOX 4 4 0 0',
                'STARTPROPERTIES 2',
                'CHARSET_REGISTRY "GB2312.1980"',
                f'CHARSET_ENCODING "{encoding}"',
                'ENDPROPERTIES',
                'CHARS 2',
                'STARTCHAR 3021',
                'ENCODING 12321',
                'SWIDTH 1000 0',
                'DWIDTH 4 0',
                'BBX 4 4 0 0',
                'BITMAP',
                'F0',
                '90',
                '90',
                'F0',
                'ENDCHAR',
                'STARTCHAR 4463',
                'ENCODING 17507',
                'SWIDTH 1000 0',
                'DWIDTH 4 0',
                'BBX 4 4 0 0',
                'BITMAP',
                '60',
                '60',
                '60',
                '60',
                'ENDCHAR',
                'ENDFONT',
            ]
        )
    )


class TestIssue4:
    def test_gl_font_by_charset_encoding(self):
        font = gb2312_gl_font()
        assert font.charset == 'gb2312'
        g = font.glyph('啊')
        assert g is not None and g.cp() == 12321
        assert g.chr() == '啊'
        assert font.glyph('你').cp() == 0x4463
        assert font.char2cp('啊') == 0x3021
        assert font.cp2char(0x3021) == '啊'
        assert font.draw('啊你').bindata == ['11110110', '10010110', '10010110', '11110110']

    def test_gl_font_detected_from_codes(self):
        font = gb2312_gl_font('1')
        assert font.glyph('啊').chr() == '啊'

    def test_ascii_in_gl_font(self):
        font = gb2312_gl_font()
        assert font.char2cp('A') == 0x41
        assert font.cp2char(0x41) == 'A'

    def test_euc_font_not_gl(self):
        font = Font(enctest_path('gb2312'))
        assert font.char2cp('人') == 51403

    def test_gl_needs_two_byte_glyphs(self):
        font = gb2312_gl_font('1')
        font.glyphs = {65: font.glyphs[12321]}
        assert font.char2cp('啊') == 0xB0A1  # no 2-byte glyph: EUC form

    def test_jisx0208_ksc5601_gl(self):
        font = gb2312_gl_font()
        font.setprop('CHARSET_REGISTRY', 'JISX0208.1983')
        assert font.charset == 'jisx0208'
        assert font.cp2char(0x2422) == 'あ'
        assert font.char2cp('あ') == 0x2422
        font.setprop('CHARSET_REGISTRY', 'KSC5601.1987')
        assert font.charset == 'ksc5601'
        assert font.cp2char(0x3021) == '가'
        assert font.char2cp('가') == 0x3021


# ---------------------------------------------------------------------------
# module level utils


class TestUtils:
    @pytest.mark.parametrize('encoding', list(examples))
    def test_char2cp_cp2char(self, encoding):
        char, cp = examples[encoding]
        assert char2cp(char, encoding) == cp
        assert cp2char(cp, encoding) == char

    def test_sanitize_charset(self):
        assert sanitize_charset('utf8') == 'utf8'
        assert sanitize_charset('UTF-8') == 'utf8'
        assert sanitize_charset('_utf32') == 'utf32'
        assert sanitize_charset('-_utf32-') == 'utf32'
        assert sanitize_charset('GB2312.1980') == 'gb2312'
        assert sanitize_charset('GB2312.1980', '0') == 'gb2312'
        assert sanitize_charset(None) == 'iso10646'
        assert sanitize_charset('') == 'iso10646'
        assert sanitize_charset('  ISO10646 ', 1) == 'iso10646'
        assert sanitize_charset('ISO8859', '5') == 'iso88595'
        assert sanitize_charset('ISO8859') == 'iso88591'
        assert sanitize_charset('ISO8859', '0') == 'iso88591'
        assert sanitize_charset('ISO8859', 'x') == 'iso88591'
        assert sanitize_charset('KOI8', 'R') == 'koi8r'
        assert sanitize_charset('KOI8', 'U') == 'koi8u'
        assert sanitize_charset('KOI8') == 'koi8r'
        assert sanitize_charset('MICROSOFT', 'CP1252') == 'cp1252'
        assert sanitize_charset('microsoft', 'win1251') == 'cp1251'
        assert sanitize_charset('microsoft', 'symbol') == 'microsoft'
        assert sanitize_charset('Windows-1250') == 'cp1250'
        assert sanitize_charset('1252') == '1252'
        assert sanitize_charset('SJIS') == 'shiftjis'
        assert sanitize_charset('KSX1001') == 'ksc5601'
        assert sanitize_charset('Big5.ETen', '0') == 'big5'
        assert sanitize_charset('Adobe-FontSpecific') == 'adobefontspecific'

    def test_canonical_charset(self):
        assert canonical_charset('ISO10646-1') == 'iso10646'
        assert canonical_charset('ISO-8859-1') == 'iso88591'
        assert canonical_charset('iso8859-15') == 'iso885915'
        assert canonical_charset('microsoft-cp1252') == 'cp1252'
        assert canonical_charset('big5-0') == 'big5'
        assert canonical_charset('GB2312.1980-0') == 'gb2312'
        assert canonical_charset('jisx0208.1983-0') == 'jisx0208'
        assert canonical_charset('KOI8-R') == 'koi8r'
        assert canonical_charset('fontspecific') == 'fontspecific'
        assert canonical_charset('foo-bar') == 'foobar'

    def test_is_unicode(self):
        for k in ('iso10646', 'unicode', 'utf8', 'utf16le', 'utf32be', 'ucs2', 'ucs4'):
            assert is_unicode_charset(k)
        for k in ('gb2312', 'iso88591', 'fontspecific'):
            assert not is_unicode_charset(k)

    def test_charset_props(self):
        assert charset_props('utf8') == ('ISO10646', '1')
        assert charset_props('iso88595') == ('ISO8859', '5')
        assert charset_props('cp1252') == ('MICROSOFT', 'CP1252')
        assert charset_props('koi8u') == ('KOI8', 'U')
        assert charset_props('gb2312') == ('GB2312.1980', '0')
        assert charset_props('big5') == ('BIG5', '0')
        assert charset_props('ascii') == ('ISO646.1991', 'IRV')
        for key in (
            'utf8',
            'iso88595',
            'cp1252',
            'koi8u',
            'koi8r',
            'gb2312',
            'big5',
            'ascii',
            'jisx0201',
            'jisx0208',
        ):
            reg, enc = charset_props(key)
            canon = sanitize_charset(reg, enc)
            assert charset_codec(canon).codec == charset_codec(key).codec

    def test_unrepresentable(self):
        assert char2cp('人', 'ISO-8859-1') is None
        assert char2cp('é', 'ascii') is None
        assert cp2char(0xFFFF, 'gb2312') is None
        assert cp2char(0xC4, 'gb2312') is None
        assert cp2char(-1, 'utf8') is None
        assert cp2char(-1, 'gb2312') is None
        assert cp2char(0x110000, 'utf8') is None
        assert cp2char(0x1_0000_0000, 'gb18030') is None

    def test_multibyte_code_in_single_byte_charset(self):
        assert cp2char(0x06FE, 'ISO8859-1') is None
        assert cp2char(0x4141, 'cp1252') is None
        assert cp2char(0x41, 'cp1252') == 'A'
        assert cp2char(0x8140, 'gb2312') is None  # invalid in GB2312 (valid in GBK)
        assert cp2char(0x8140, 'gbk') == '丂'

    def test_code_decoding_to_several_characters(self):
        # Big5-HKSCS 0x8862 is one code for two Unicode characters
        assert cp2char(0x8862, 'big5hkscs') == '\u00ca\u0304'

    def test_gb18030_four_bytes(self):
        assert char2cp('😀', 'gb18030') == 0x9439FC36
        assert cp2char(0x9439FC36, 'gb18030') == '😀'

    def test_jisx0201(self):
        assert char2cp('A', 'JISX0201.1976-0') == 0x41
        assert char2cp('ｱ', 'jisx0201') == 0xB1
        assert char2cp('あ', 'jisx0201') is None
        assert char2cp('é', 'jisx0201') is None
        assert cp2char(0x41, 'jisx0201') == 'A'
        assert cp2char(0xB1, 'jisx0201') == 'ｱ'
        assert cp2char(0x90, 'jisx0201') is None

    def test_char2cp_requires_one_char(self):
        with pytest.raises(TypeError):
            char2cp('ab', 'utf8')
        with pytest.raises(TypeError):
            char2cp('', 'gb2312')

    def test_gl_forced_and_ignored(self):
        assert charset_codec('iso2022cn').gl is True
        assert charset_codec('gb2312', gl=True).gl is True
        assert charset_codec('big5', gl=True).gl is False
        assert char2cp('你', 'gb2312', gl=True) == 0x4463

    def test_unknown_iso8859_part(self):
        codec = charset_codec('iso885912')  # no ISO-8859-12 codec
        assert codec.known is False and codec.codec is None
        assert charset_codec('cp1259').known is False

    def test_codec_dataclass(self):
        c = CharsetCodec('utf8')
        assert c.char2cp('人') == 20154 and c.cp2char(20154) == '人'
        assert charset_codec('gb2312') == CharsetCodec('gb2312', 'gb2312', False)


# ---------------------------------------------------------------------------
# unknown charsets, charsetconvert


class TestUnknownCharset:
    def test_unknown_warns_once(self):
        font = Font().load_string(
            mini_bdf.replace('STARTPROPERTIES 6', 'STARTPROPERTIES 7').replace(
                'DEFAULT_CHAR 65', 'DEFAULT_CHAR 65\nCHARSET_REGISTRY "FontSpecific"'
            )
        )
        with pytest.warns(BDFParserWarning, match="Unknown charset 'fontspecific'") as rec:
            assert font.char2cp('A') == 65
            assert font.cp2char(66) == 'B'
            font.draw('AB')
        assert len([w for w in rec if 'Unknown charset' in str(w.message)]) == 1

    def test_unrepresentable_glyph_lookup(self):
        font = Font(enctest_path('gb2312'))
        with pytest.warns(BDFParserWarning, match='cannot be encoded'):
            assert font.glyph('😀') is None
        assert font.lacksglyphs('A😀') == ['😀']
        with pytest.warns(BDFParserWarning, match=r'Glyph \(codepoint 65535\) does not exist'):
            assert font.glyphbycp(0xFFFF) is None
        # unrepresentable characters are drawn as missing glyphs
        assert font.draw('A😀').width() == 8 + 16


class TestCharsetConvert:
    def test_unicode_to_gb2312_and_back(self):
        font = utf8font()
        font.charsetconvert('GB2312')
        assert font.props['charset_registry'] == 'GB2312.1980'
        assert font.props['charset_encoding'] == '0'
        assert font.charset == 'gb2312'
        assert sorted(font.glyphs) == [0x41, 0x3962, 0x484B]  # GL form
        assert font.draw('A人光').bindata == a_ren_guang_bitmap
        assert font.glyph('人').chr() == '人'
        font.charsetconvert('ISO10646-1')
        assert font.props['charset_registry'] == 'ISO10646'
        assert font.props['charset_encoding'] == '1'
        assert sorted(font.glyphs) == [65, 20154, 20809]
        assert font.draw('A人光').bindata == a_ren_guang_bitmap

    def test_big5_to_unicode(self):
        font = Font(enctest_path('big5'))
        font.charsetconvert('iso10646')
        assert sorted(font.glyphs) == [65, 20154, 20809]
        assert font.glyphs[20154][1] == 20154

    def test_drop_unrepresentable(self):
        font = utf8font()
        with pytest.warns(
            BDFParserWarning, match=r"2 glyph\(s\) could not be converted to the charset 'iso88591'"
        ):
            font.charsetconvert('ISO8859-1')
        assert list(font.glyphs) == [65]
        assert font.props['charset_registry'] == 'ISO8859'
        assert font.props['charset_encoding'] == '1'

    def test_clears_override(self):
        font = utf8font().encoding(charset='utf8', cp2char=lambda cp: chr(cp))
        font.charsetconvert('big5')
        assert font._charset_override is None and font._cp2char_override is None
        assert font.charset == 'big5'
        assert font.draw('A人光').bindata == a_ren_guang_bitmap

    def test_unknown_target(self):
        font = utf8font()
        with pytest.warns(BDFParserWarning, match="Unknown charset 'weird'"):
            font.charsetconvert('weird')
        assert sorted(font.glyphs) == [65, 20154, 20809]
        assert font.props['charset_registry'] == 'WEIRD'

    def test_collision_dropped(self):
        font = utf8font().encoding(cp2char=lambda cp: 'A')
        with pytest.warns(BDFParserWarning, match='2 glyph'):
            font.charsetconvert('utf8')
        assert list(font.glyphs) == [65]

    def test_collision_later_wins_at_later_position(self):
        # regression: the later glyph replaced the earlier one IN PLACE, so tobdf()
        # wrote a different glyph order than bdfparser-js (and than a duplicate
        # ENCODING in a BDF file, where the later glyph also takes the later position)
        font = Font.create(8)
        for cp in (0x41, 0x42, 0x43):
            font.newglyph(cp, name=f'g{cp:X}')
        font.encoding(cp2char=lambda cp: 'A' if cp in (0x41, 0x43) else chr(cp))
        with pytest.warns(BDFParserWarning, match='1 glyph'):
            font.charsetconvert('utf8')
        assert list(font.glyphs) == [0x42, 0x41]
        assert font.glyphs[0x41][0] == 'g43'
        assert font.tobdf().index('STARTCHAR g42') < font.tobdf().index('STARTCHAR g43')


def test_tottf_resolves_charset_once(monkeypatch):
    # regression: write_ttf called font.cp2char per glyph, which re-ran the GL-form
    # detection (a scan of all glyphs) every time: quadratic for GB2312/JIS/KSC fonts
    font = Font(enctest_path('gb2312'))
    calls = []
    orig = Font._is_gl

    def counting(self, key):
        calls.append(key)
        return orig(self, key)

    monkeypatch.setattr(Font, '_is_gl', counting)
    data = font.tottf()
    assert len(calls) == 1
    assert sorted(Font(data).glyphs) == sorted(font.glyphs)
