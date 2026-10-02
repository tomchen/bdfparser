"""BDF parser robustness: line endings, malformed input, property typing, unencoded glyphs, ..."""

import gzip
import io
import pathlib
import warnings

import pytest

from bdfparser import BDFParseError, BDFParserWarning, Font

from .info import (
    emptylines_path,
    glyph_a_meta,
    mini_bdf,
    specfont_bad_path,
    specfont_path,
    unifont_path,
)

pytestmark = pytest.mark.filterwarnings('ignore::bdfparser.BDFParserWarning')


def parse(text):
    return Font().load_string(text)


def parse_strict(text):
    """Parse and fail on any warning."""
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        return Font().load_string(text)


def header(props='', chars=None):
    lines = [
        'STARTFONT 2.1',
        'FONT f',
        'SIZE 8 75 75',
        'FONTBOUNDINGBOX 8 8 0 -1',
    ]
    nprops = len([p for p in props.split('\n') if p and not p.startswith('COMMENT')])
    lines.append(f'STARTPROPERTIES {nprops}')
    lines += [p for p in props.split('\n') if p]
    lines.append('ENDPROPERTIES')
    if chars is not None:
        lines.append(f'CHARS {chars}')
    return '\n'.join(lines) + '\n'


def glyph(name='A', enc='65', bbx='1 1 0 0', rows=('80',), extra=()):
    lines = [
        f'STARTCHAR {name}',
        f'ENCODING {enc}',
        *extra,
        f'BBX {bbx}',
        'BITMAP',
        *rows,
        'ENDCHAR',
    ]
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# loading entry points


class TestLoadingSources:
    def test_mini_strict(self):
        font = parse_strict(mini_bdf)
        assert len(font) == 3
        assert font.headers['fbbx'] == 6
        assert font.props['pixel_size'] == 8
        assert font.glyphs[65][0] == 'A'

    def test_load_lines(self):
        font = Font().load_lines(mini_bdf.splitlines(keepends=True))
        assert font.tobdf() == mini_bdf

    def test_load_lines_generator_without_newlines(self):
        font = Font().load_lines(line for line in mini_bdf.split('\n'))
        assert font.tobdf() == mini_bdf

    def test_load_bytes(self):
        assert Font().load_bytes(mini_bdf.encode()).tobdf() == mini_bdf
        assert Font().load_bytes(bytearray(mini_bdf.encode())).tobdf() == mini_bdf
        assert Font().load_bytes(memoryview(mini_bdf.encode())).tobdf() == mini_bdf

    def test_font_bytes(self):
        assert Font(mini_bdf.encode()).tobdf() == mini_bdf

    def test_font_pathlib(self):
        assert len(Font(pathlib.Path(unifont_path))) == 849

    def test_font_text_file_obj(self):
        with open(unifont_path) as f:
            assert len(Font(f)) == 849

    def test_font_binary_file_obj(self):
        with open(unifont_path, 'rb') as f:
            assert len(Font(f)) == 849

    def test_load_file_obj_stringio_bytesio(self):
        assert Font().load_file_obj(io.StringIO(mini_bdf)).tobdf() == mini_bdf
        assert Font().load_file_obj(io.BytesIO(mini_bdf.encode())).tobdf() == mini_bdf

    def test_load_file_obj_iterable(self):
        assert Font().load_file_obj(mini_bdf.split('\n')).tobdf() == mini_bdf

    def test_read_returning_str(self):
        class Reader:
            def read(self):
                return mini_bdf

        assert Font(Reader()).tobdf() == mini_bdf

    def test_font_bad_type(self):
        with pytest.raises(TypeError):
            Font(123)

    def test_bom(self):
        assert parse_strict('﻿' + mini_bdf).tobdf() == mini_bdf
        assert Font(b'\xef\xbb\xbf' + mini_bdf.encode()).tobdf() == mini_bdf

    def test_gzip_bdf(self):
        assert Font(gzip.compress(mini_bdf.encode())).tobdf() == mini_bdf

    def test_otto_rejected(self):
        with pytest.raises(ValueError, match='CFF'):
            Font(b'OTTO' + bytes(100))

    def test_invalid_utf8_replaced(self):
        text = mini_bdf.replace('COMMENT "mini test font"', 'COMMENT "caf\xe9"')
        font = Font(text.encode('latin-1'))
        assert font.headers['comment'] == ['caf�']

    def test_reload_resets(self):
        font = Font(unifont_path)
        font.load_string(mini_bdf)
        assert len(font) == 3
        assert 'copyright' not in font.props

    def test_v2_methods_return_self(self):
        font = Font()
        assert font.load_file_path(unifont_path) is font
        with open(unifont_path) as f:
            assert font.load_file_obj(f) is font
        assert font.load_string(mini_bdf) is font
        assert font.load_lines(mini_bdf.split('\n')) is font
        assert font.load_bytes(mini_bdf.encode()) is font

    def test_empty_font_object(self):
        font = Font()
        assert (
            font.headers == {} and font.props == {} and font.glyphs == {} and font.unencoded == []
        )
        assert len(font) == 0


# ---------------------------------------------------------------------------
# line endings / whitespace


class TestWhitespace:
    def test_crlf_cr_lf_identical(self):
        lf = parse_strict(mini_bdf)
        crlf = parse_strict(mini_bdf.replace('\n', '\r\n'))
        cr = parse_strict(mini_bdf.replace('\n', '\r'))
        for f in (crlf, cr):
            assert f.headers == lf.headers
            assert f.props == lf.props
            assert f.glyphs == lf.glyphs

    def test_crlf_bytes(self):
        assert Font(mini_bdf.replace('\n', '\r\n').encode()).tobdf() == mini_bdf

    def test_tabs_and_spaces(self):
        text = mini_bdf.replace('SIZE 8 75 75', 'SIZE\t8   75\t 75').replace(
            'BBX 5 7 0 0', '  BBX  5\t7 0  0  '
        )
        font = parse_strict(text)
        assert font.headers['xres'] == 75 and font.headers['yres'] == 75
        assert font.glyphs[65][2:6] == [5, 7, 0, 0]

    def test_blank_lines_everywhere(self):
        text = '\n\n' + '\n  \n'.join(mini_bdf.split('\n')) + '\n\n'
        assert parse_strict(text).tobdf() == mini_bdf

    def test_leading_whitespace_font(self):
        # the test font has leading whitespace and blank lines (Python repo variant)
        font = Font(unifont_path)
        assert font.headers['bdfversion'] == 2.1
        assert font.glyphbycp(97).meta == glyph_a_meta

    def test_emptylines_font(self):
        with pytest.warns(BDFParserWarning) as rec:
            font = Font(emptylines_path)
        msgs = [str(w.message) for w in rec]
        assert any("unknown header keyword 'v'" in m for m in msgs)
        assert any("unexpected line 's' ignored" in m for m in msgs)
        assert any("unexpected line 'c' ignored" in m for m in msgs)
        assert len(font) == 3
        assert font.headers['fbbx'] == 16
        assert font.props['charset_registry'] == 'ISO8859'
        assert font.charset == 'iso88591'
        assert font.glyphbycp(1).draw(2).bindata[0] == '1010101010101010'


# ---------------------------------------------------------------------------
# headers


class TestHeaders:
    def test_headers(self):
        font = parse_strict(mini_bdf)
        assert font.headers == {
            'bdfversion': 2.1,
            'fontname': '-Test-Mini-Medium-R-Normal--8-80-75-75-C-60-ISO10646-1',
            'pointsize': 8,
            'xres': 75,
            'yres': 75,
            'fbbx': 6,
            'fbby': 8,
            'fbbxoff': 0,
            'fbbyoff': -1,
            'comment': ['mini test font'],
            'metricsset': 0,
        }

    def test_global_metrics(self):
        text = mini_bdf.replace(
            'COMMENT "mini test font"',
            'METRICSSET 2\nCONTENTVERSION 7\nSWIDTH 500 0\nDWIDTH 6 0\nSWIDTH1 0 1000\nDWIDTH1 0 8\nVVECTOR 3,5',
        )
        h = parse_strict(text).headers
        assert (h['metricsset'], h['contentversion']) == (2, 7)
        assert (h['swx0'], h['swy0'], h['dwx0'], h['dwy0']) == (500, 0, 6, 0)
        assert (h['swx1'], h['swy1'], h['dwx1'], h['dwy1']) == (0, 1000, 0, 8)
        assert (h['vvectorx'], h['vvectory']) == (3, 5)
        assert 'comment' not in h

    @pytest.mark.parametrize(
        'line, expected',
        [
            ('COMMENT "quoted"', 'quoted'),
            ('COMMENT plain text', 'plain text'),
            ("COMMENT 'single'", "'single'"),
            ('COMMENT "a" and "b"', 'a" and "b'),
            ('COMMENT "unbalanced', '"unbalanced'),
            ('COMMENT', ''),
            ('COMMENT    spaced   ', 'spaced'),
            ('COMMENT ""', ''),
        ],
    )
    def test_comment_quotes(self, line, expected):
        font = parse_strict(mini_bdf.replace('COMMENT "mini test font"', line))
        assert font.headers['comment'] == [expected]

    def test_spec_example_unquoted_comment(self):
        font = Font(specfont_bad_path)
        assert font.headers['comment'] == ['This is a sample font in 2.1 format.']

    def test_unknown_header_keyword(self):
        with pytest.warns(BDFParserWarning, match=r"line 2: unknown header keyword 'FOO'"):
            font = parse(mini_bdf.replace('FONT -Test', 'FOO bar\nFONT -Test'))
        assert len(font) == 3

    def test_font_without_value(self):
        font = parse_strict(
            mini_bdf.replace('FONT -Test-Mini-Medium-R-Normal--8-80-75-75-C-60-ISO10646-1', 'FONT')
        )
        assert font.headers['fontname'] == ''

    def test_fontname_with_spaces(self):
        font = parse_strict(
            mini_bdf.replace(
                'FONT -Test-Mini-Medium-R-Normal--8-80-75-75-C-60-ISO10646-1', 'FONT a b  c'
            )
        )
        assert font.headers['fontname'] == 'a b  c'


# ---------------------------------------------------------------------------
# properties


class TestProperties:
    def test_types(self):
        props = '\n'.join(
            [
                'INT_PROP 42',
                'NEG_PROP -3',
                'PLUS_PROP +5',
                'QUOTED_INT "42"',
                'STR_PROP "hello world"',
                'ESCAPED "say ""hi"" now"',
                'TRAILING "abc" ignored text',
                'EMPTY_STR ""',
                'RAW_PROP some raw value',
                'FLOATISH 1.5',
                'KEY_ONLY',
            ]
        )
        font = parse_strict(header(props) + 'CHARS 0\nENDFONT\n')
        p = font.props
        assert p['int_prop'] == 42 and isinstance(p['int_prop'], int)
        assert p['neg_prop'] == -3
        assert p['plus_prop'] == 5
        assert p['quoted_int'] == '42'
        assert p['str_prop'] == 'hello world'
        assert p['escaped'] == 'say "hi" now'
        assert p['trailing'] == 'abc'
        assert p['empty_str'] == ''
        assert p['raw_prop'] == 'some raw value'
        assert p['floatish'] == '1.5'
        assert p['key_only'] is None
        assert font.getprop('Int_Prop') == 42

    def test_non_ascii_digits_not_int(self):
        font = parse_strict(header('ARABIC_DIGITS ١٢') + 'CHARS 0\nENDFONT\n')
        assert font.props['arabic_digits'] == '١٢'

    def test_missing_closing_quote(self):
        with pytest.warns(BDFParserWarning, match='no closing quote'):
            font = parse(header('BROKEN "abc def') + 'CHARS 0\nENDFONT\n')
        assert font.props['broken'] == 'abc def'

    def test_original_case_preserved(self):
        font = Font(specfont_path)
        assert font.props['minspace'] == 4
        assert font.props['copyright'] == 'Copyright (c) 1987 Adobe Systems, Inc.'
        assert font._propnames == {'minspace': 'MinSpace', 'copyright': 'Copyright'}
        out = font.tobdf()
        assert '\nMinSpace 4\n' in out
        assert '\nCopyright "Copyright (c) 1987 Adobe Systems, Inc."\n' in out

    def test_non_adobe_properties(self):
        # XFree86 / non-Adobe style files (issue #4 class)
        props = '\n'.join(
            [
                '_XFREE86_GLYPH_RANGES "0-127"',
                'FontName "Weird"',
                'x-custom something',
                'RAW_ASCENT 800',
            ]
        )
        font = parse_strict(header(props) + 'CHARS 0\nENDFONT\n')
        assert font.props == {
            '_xfree86_glyph_ranges': '0-127',
            'fontname': 'Weird',
            'x-custom': 'something',
            'raw_ascent': 800,
        }
        assert '\nx-custom "something"\n' in font.tobdf()
        assert '\nFontName "Weird"\n' in font.tobdf()

    def test_property_comments(self):
        font = parse_strict(header('COMMENT "first"\nFOO 1\nCOMMENT second') + 'CHARS 0\nENDFONT\n')
        assert font.props == {'comment': ['first', 'second'], 'foo': 1}

    def test_property_count_mismatch(self):
        text = (
            header('FOO 1\nBAR 2').replace('STARTPROPERTIES 2', 'STARTPROPERTIES 5')
            + 'CHARS 0\nENDFONT\n'
        )
        with pytest.warns(BDFParserWarning, match='property count'):
            font = parse(text)
        assert font.props == {'foo': 1, 'bar': 2}

    def test_property_count_malformed(self):
        text = (
            header('FOO 1').replace('STARTPROPERTIES 1', 'STARTPROPERTIES x') + 'CHARS 0\nENDFONT\n'
        )
        with pytest.warns(BDFParserWarning, match='malformed property count'):
            font = parse(text)
        assert font.props == {'foo': 1}

    def test_property_count_missing(self):
        text = (
            header('FOO 1').replace('STARTPROPERTIES 1', 'STARTPROPERTIES') + 'CHARS 0\nENDFONT\n'
        )
        assert parse_strict(text).props == {'foo': 1}

    def test_duplicate_property_last_wins(self):
        font = parse_strict(header('FOO 1\nfoo "x"') + 'CHARS 0\nENDFONT\n')
        assert font.props == {'foo': 'x'}
        assert font._propnames == {'foo': 'foo'}


# ---------------------------------------------------------------------------
# structure problems


class TestStructure:
    def test_missing_startproperties_chars(self):
        text = (
            'STARTFONT 2.1\nFONT f\nSIZE 8 75 75\nFONTBOUNDINGBOX 1 1 0 0\nCHARS 1\n'
            + glyph()
            + 'ENDFONT\n'
        )
        with pytest.warns(BDFParserWarning, match='STARTPROPERTIES'):
            font = parse(text)
        assert len(font) == 1
        assert font.props == {}
        assert font.headers['metricsset'] == 0

    def test_missing_startproperties_and_chars(self):
        text = (
            'STARTFONT 2.1\nFONT f\nSIZE 8 75 75\nFONTBOUNDINGBOX 1 1 0 0\n' + glyph() + 'ENDFONT\n'
        )
        with pytest.warns(BDFParserWarning) as rec:
            font = parse(text)
        msgs = ' | '.join(str(w.message) for w in rec)
        assert 'STARTPROPERTIES' in msgs and "Cannot find 'CHARS' line" in msgs
        assert "'CHARS' keyword does not exist" in msgs
        assert len(font) == 1

    def test_endfont_in_header(self):
        with pytest.warns(BDFParserWarning, match='does not have any glyphs'):
            font = parse('STARTFONT 2.1\nFONT f\nSIZE 8 75 75\nFONTBOUNDINGBOX 1 1 0 0\nENDFONT\n')
        assert len(font) == 0
        assert font.headers['metricsset'] == 0

    def test_endfont_after_properties(self):
        with pytest.warns(BDFParserWarning, match='does not have any glyphs'):
            font = parse(header('FOO 1') + 'ENDFONT\n')
        assert len(font) == 0 and font.props == {'foo': 1}

    def test_missing_endproperties_endfont(self):
        text = header('FOO 1').replace('ENDPROPERTIES\n', '') + 'ENDFONT\n'
        with pytest.warns(BDFParserWarning, match='ENDPROPERTIES'):
            font = parse(text)
        assert font.props == {'foo': 1} and len(font) == 0

    def test_missing_endproperties_chars(self):
        text = header('FOO 1').replace('ENDPROPERTIES\n', '') + 'CHARS 1\n' + glyph() + 'ENDFONT\n'
        with pytest.warns(BDFParserWarning, match='ENDPROPERTIES'):
            font = parse(text)
        assert font.props == {'foo': 1} and len(font) == 1

    def test_missing_endproperties_startchar(self):
        text = header('FOO 1').replace('ENDPROPERTIES\n', '') + glyph() + 'ENDFONT\n'
        with pytest.warns(BDFParserWarning, match='ENDPROPERTIES'):
            font = parse(text)
        assert font.props == {'foo': 1} and len(font) == 1

    def test_missing_chars_after_properties(self):
        with pytest.warns(
            BDFParserWarning, match="Cannot find 'CHARS' line next to 'ENDPROPERTIES' line"
        ):
            font = parse(header() + glyph() + 'ENDFONT\n')
        assert len(font) == 1

    def test_unexpected_line_after_properties(self):
        with pytest.warns(BDFParserWarning, match="unexpected line 'junk here' ignored"):
            font = parse(header(chars=None) + 'junk here\nCHARS 1\n' + glyph() + 'ENDFONT\n')
        assert len(font) == 1

    def test_chars_mismatch(self):
        with pytest.warns(
            BDFParserWarning,
            match="'CHARS' keyword is 5, which does not match the actual glyph count 1",
        ):
            parse(header(chars=5) + glyph() + 'ENDFONT\n')

    def test_chars_counts_unencoded(self):
        parse_strict(header(chars=2) + glyph() + glyph('x', '-1') + 'ENDFONT\n')

    def test_chars_between_glyphs(self):
        # a late CHARS line is accepted if none was seen yet
        with pytest.warns(BDFParserWarning, match="Cannot find 'CHARS'"):
            font = parse(header() + glyph() + 'CHARS 2\n' + glyph('B', '66') + 'ENDFONT\n')
        assert len(font) == 2

    def test_missing_endfont(self):
        with pytest.warns(BDFParserWarning, match="does not have 'ENDFONT'"):
            font = parse(header(chars=1) + glyph())
        assert len(font) == 1

    def test_content_after_endfont_ignored(self):
        font = parse_strict(mini_bdf + 'garbage\nSTARTCHAR x\n')
        assert len(font) == 3

    def test_missing_endchar_before_startchar(self):
        text = header(chars=2) + glyph().replace('ENDCHAR\n', '') + glyph('B', '66') + 'ENDFONT\n'
        with pytest.warns(BDFParserWarning, match="missing ENDCHAR for glyph 'A'"):
            font = parse(text)
        assert sorted(font.glyphs) == [65, 66]
        assert font.glyphs[65][16] == ['80']

    def test_missing_endchar_before_endfont(self):
        text = header(chars=1) + glyph().replace('ENDCHAR\n', '') + 'ENDFONT\n'
        with pytest.warns(BDFParserWarning, match="missing ENDCHAR for glyph 'A'"):
            font = parse(text)
        assert font.glyphs[65][16] == ['80']

    def test_missing_endchar_bitmap_before_eof(self):
        text = header(chars=1) + glyph().replace('ENDCHAR\n', '')
        with pytest.warns(BDFParserWarning, match='missing ENDCHAR'):
            font = parse(text)
        assert font.glyphs[65][16] == ['80']

    def test_missing_bitmap_endchar_in_glyph_header(self):
        # STARTCHAR / ENDFONT / EOF while still before BITMAP
        g = 'STARTCHAR A\nENCODING 65\nBBX 1 1 0 0\n'
        with pytest.warns(BDFParserWarning, match='missing ENDCHAR'):
            font = parse(header(chars=2) + g + glyph('B', '66') + 'ENDFONT\n')
        assert sorted(font.glyphs) == [65, 66]
        with pytest.warns(BDFParserWarning, match='missing ENDCHAR'):
            font = parse(header(chars=1) + g + 'ENDFONT\n')
        assert font.glyphs[65][16] == []
        with pytest.warns(BDFParserWarning, match='missing ENDCHAR'):
            font = parse(header(chars=1) + g)
        assert font.glyphs[65][16] == []

    def test_endchar_without_bitmap(self):
        font = parse_strict(
            header(chars=1) + 'STARTCHAR A\nENCODING 65\nBBX 0 0 0 0\nENDCHAR\nENDFONT\n'
        )
        assert font.glyphs[65][16] == []

    def test_endchar_with_trailing_token(self):
        text = header(chars=1) + glyph().replace('ENDCHAR', 'ENDCHAR x') + 'ENDFONT\n'
        assert parse_strict(text).glyphs[65][16] == ['80']

    def test_unknown_glyph_keyword(self):
        with pytest.warns(BDFParserWarning, match="unknown keyword 'ATTRIBUTES'"):
            font = parse(header(chars=1) + glyph(extra=['ATTRIBUTES 0000']) + 'ENDFONT\n')
        assert len(font) == 1

    def test_glyph_name_with_spaces_and_empty(self):
        font = parse_strict(
            header(chars=2) + glyph('my glyph  name') + glyph('', '66') + 'ENDFONT\n'
        )
        assert font.glyphs[65][0] == 'my glyph  name'
        assert font.glyphs[66][0] == ''

    def test_first_keyword_wins_in_glyph(self):
        font = parse_strict(
            header(chars=1)
            + 'STARTCHAR A\nENCODING 65\nENCODING 66\nDWIDTH 5 0\nDWIDTH 9 0\nBBX 1 1 0 0\nBBX 2 2 2 2\nBITMAP\n80\nENDCHAR\nENDFONT\n'
        )
        assert list(font.glyphs) == [65]
        assert font.glyphs[65][2:10] == [1, 1, 0, 0, None, None, 5, 0]

    def test_glyph_metrics(self):
        font = parse_strict(
            header(chars=1)
            + glyph(
                extra=[
                    'SWIDTH 500 0',
                    'DWIDTH 4 0',
                    'SWIDTH1 0 1000',
                    'DWIDTH1 0 8',
                    'VVECTOR 2, 7',
                ]
            )
            + 'ENDFONT\n'
        )
        assert font.glyphs[65][6:16] == [500, 0, 4, 0, 0, 1000, 0, 8, 2, 7]

    def test_vvector_delimiters(self):
        for v in ('2 7', '2,7', '2 , 7', '2,\t7'):
            font = parse_strict(header(chars=1) + glyph(extra=[f'VVECTOR {v}']) + 'ENDFONT\n')
            assert font.glyphs[65][14:16] == [2, 7]

    def test_hex_rows_kept_verbatim(self):
        font = parse_strict(
            header(chars=1) + glyph(bbx='12 2 0 0', rows=('aBc0', '  0f0F  ')) + 'ENDFONT\n'
        )
        assert font.glyphs[65][16] == ['aBc0', '0f0F']

    def test_duplicate_codepoint_later_wins(self):
        text = header(chars=3) + glyph('first') + glyph('B', '66') + glyph('second') + 'ENDFONT\n'
        with pytest.warns(BDFParserWarning, match='duplicate codepoint 65'):
            font = parse(text)
        assert font.glyphs[65][0] == 'second'
        assert list(font.glyphs) == [66, 65]


# ---------------------------------------------------------------------------
# unencoded glyphs


class TestUnencoded:
    def test_unencoded(self):
        text = header(chars=3) + glyph('u1', '-1') + glyph() + glyph('u2', '-1 123') + 'ENDFONT\n'
        font = parse_strict(text)
        assert len(font) == 1
        assert [e['altcode'] for e in font.unencoded] == [None, 123]
        assert [e['meta'][0] for e in font.unencoded] == ['u1', 'u2']
        assert all(e['meta'][1] == -1 for e in font.unencoded)
        assert len(font.unencoded[0]['meta']) == 17

    def test_other_negative_encoding(self):
        with pytest.warns(BDFParserWarning, match='negative ENCODING -5'):
            font = parse(header(chars=1) + glyph('n', '-5') + 'ENDFONT\n')
        assert font.unencoded[0]['meta'][1] == -1

    def test_missing_encoding(self):
        text = header(chars=1) + 'STARTCHAR x\nBBX 1 1 0 0\nBITMAP\n80\nENDCHAR\nENDFONT\n'
        with pytest.warns(BDFParserWarning, match='no ENCODING'):
            font = parse(text)
        assert len(font) == 0 and len(font.unencoded) == 1

    def test_hanwang_unencoded(self):
        font = Font('tests/fonts/HanWangYanKai-26.bdf')
        assert len(font.unencoded) == 190
        assert len(font) + len(font.unencoded) == 14160
        assert all(e['meta'][1] == -1 and e['altcode'] is None for e in font.unencoded)

    def test_unencoded_not_drawn_by_codepoint(self):
        font = parse_strict(header(chars=1) + glyph('u1', '-1') + 'ENDFONT\n')
        with pytest.warns(BDFParserWarning):
            assert font.glyphbycp(-1) is None
        assert list(font.itercps()) == []


# ---------------------------------------------------------------------------
# fatal errors


class TestFatal:
    @pytest.mark.parametrize('text', ['', '\n\n', 'STARTFONT 2.1\nFONT f\n', 'random text\nmore\n'])
    def test_eof_in_headers(self, text):
        with pytest.raises(
            BDFParseError, match='Unexpected end of file before the end of the headers'
        ):
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                parse(text)

    def test_eof_in_properties(self):
        with pytest.raises(BDFParseError) as exc:
            parse('STARTFONT 2.1\nSTARTPROPERTIES 1\nFOO 1\n')
        assert exc.value.lineno == 4

    @pytest.mark.parametrize(
        'old, new, lineno',
        [
            ('STARTFONT 2.1', 'STARTFONT x', 1),
            ('SIZE 8 75 75', 'SIZE 8 a 75', 3),
            ('SIZE 8 75 75', 'SIZE 8 75', 3),
            ('FONTBOUNDINGBOX 6 8 0 -1', 'FONTBOUNDINGBOX 6 8 0 -1.5', 4),
            ('ENCODING 65', 'ENCODING A', 23),
            ('ENCODING 65', 'ENCODING', 23),
            ('BBX 5 7 0 0', 'BBX 5 7 0', 26),
            ('DWIDTH 6 0\nBBX 5 7', 'DWIDTH six 0\nBBX 5 7', 25),
            ('CHARS 3', 'CHARS three', 14),
        ],
    )
    def test_malformed_numbers(self, old, new, lineno):
        assert old in mini_bdf
        text = (
            mini_bdf.replace(old, new, 1)
            if old != 'ENCODING 65'
            else mini_bdf.replace('ENCODING 65', new)
        )
        with pytest.raises(BDFParseError) as exc:
            parse(text)
        assert exc.value.lineno == lineno
        assert str(exc.value).startswith(f'line {lineno}: ')
        assert isinstance(exc.value, ValueError)

    def test_missing_bbx(self):
        text = header(chars=1) + 'STARTCHAR nobbx\nENCODING 65\nBITMAP\n80\nENDCHAR\nENDFONT\n'
        with pytest.raises(
            BDFParseError, match="glyph 'nobbx' \\(starting at line 8\\) has no BBX"
        ) as exc:
            parse(text)
        assert exc.value.lineno == 12

    def test_error_without_lineno(self):
        e = BDFParseError('boom')
        assert str(e) == 'boom' and e.lineno is None and e.msg == 'boom'


# ---------------------------------------------------------------------------
# hex rows vs BBX height


class TestHexRows:
    def test_fewer_rows_padded(self):
        font = parse_strict(header(chars=1) + glyph(bbx='4 3 0 0', rows=('F0',)) + 'ENDFONT\n')
        g = font.glyphbycp(65)
        with pytest.warns(BDFParserWarning, match='has 1 bitmap rows but its BBX height is 3'):
            bm = g.draw(1)
        assert bm.bindata == ['1111', '0000', '0000']

    def test_more_rows_ignored(self):
        font = parse_strict(
            header(chars=1) + glyph(bbx='4 1 0 0', rows=('F0', 'A0', '50')) + 'ENDFONT\n'
        )
        assert font.glyphbycp(65).draw(1).bindata == ['1111']
        assert font.glyphbycp(65).draw(2).bindata == ['11110000', '10100000', '01010000']

    def test_short_hex_row_padded(self):
        font = parse_strict(header(chars=1) + glyph(bbx='8 1 0 0', rows=('F',)) + 'ENDFONT\n')
        assert font.glyphbycp(65).draw(1).bindata == ['11110000']


# ---------------------------------------------------------------------------
# warnings behaviour (issue #8 / PR #9)


class TestWarnings:
    def test_formatwarning_not_patched(self):
        import bdfparser.font

        assert warnings.formatwarning.__module__ in ('warnings', '_py_warnings')
        assert not hasattr(bdfparser.font, 'format_warning')

    def test_warning_category(self):
        font = Font(unifont_path)
        with pytest.warns(BDFParserWarning):
            font.glyphbycp(0x10FFFF)
        assert issubclass(BDFParserWarning, UserWarning)

    def test_can_be_silenced(self):
        font = Font(unifont_path)
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            warnings.simplefilter('ignore', BDFParserWarning)
            assert font.glyphbycp(22909) is None

    def test_stacklevel_points_to_caller(self):
        font = Font(unifont_path)
        with pytest.warns(BDFParserWarning) as rec:
            font.glyphbycp(22909)
        assert rec[0].filename == __file__
