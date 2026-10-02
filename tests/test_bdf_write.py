"""BDF writer (spec section 5): exact format and byte-identical round trips."""

import pytest

from bdfparser import Font
from bdfparser.font import fmtver

from .info import (
    hanwang_path,
    mini_bdf,
    specfont_bad_path,
    specfont_path,
    unifont_full_path,
    unifont_path,
    unifont_reduced_path,
)

pytestmark = pytest.mark.filterwarnings('ignore::bdfparser.BDFParserWarning')


def read(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8')


# ---------------------------------------------------------------------------
# byte-identical round trips of FontForge-written files


@pytest.mark.parametrize('path', [hanwang_path, unifont_full_path, unifont_reduced_path])
def test_fontforge_round_trip(path):
    src = read(path)
    out = Font(path).tobdf()
    assert out == src
    assert out.encode('utf-8') == open(path, 'rb').read()


def test_hanwang_unencoded_written_last():
    font = Font(hanwang_path)
    out = font.tobdf()
    assert out.count('\nENCODING -1\n') == 190
    assert 'CHARS 14160\n' in out


def test_round_trip_is_stable():
    once = Font(unifont_path).tobdf()
    assert Font().load_string(once).tobdf() == once


def test_leading_whitespace_font_normalised():
    # the Python repo test font has leading whitespace / blank lines; the writer normalises them
    src = read(unifont_path)
    out = Font(unifont_path).tobdf()
    normalised = '\n'.join(line.strip() for line in src.split('\n') if line.strip()) + '\n'
    assert out == normalised


def test_mini_round_trip():
    assert Font().load_string(mini_bdf).tobdf() == mini_bdf


def test_spec_example():
    out = Font(specfont_path).tobdf()
    assert out.startswith(
        'STARTFONT 2.1\n'
        'FONT Helvetica-BoldOblique\n'
        'SIZE 8 200 200\n'
        'FONTBOUNDINGBOX 9 24 -2 -6\n'
        'COMMENT "This is a sample font in 2.1 format."\n'
        'STARTPROPERTIES 2\n'
        'MinSpace 4\n'
        'Copyright "Copyright (c) 1987 Adobe Systems, Inc."\n'
        'ENDPROPERTIES\n'
        'CHARS 2\n'
        'STARTCHAR j\n'
        'ENCODING 106\n'
        'SWIDTH 355 0\n'
        'DWIDTH 8 0\n'
        'BBX 9 22 -2 -6\n'
        'BITMAP\n'
        '0380\n'
    )
    assert out.endswith('BBX 4 6 2 12\nBITMAP\n70\n70\n70\n60\nE0\nC0\nENDCHAR\nENDFONT\n')


def test_spec_example_bad_bitmap_kept_verbatim():
    out = Font(specfont_bad_path).tobdf()
    assert 'BBX 4 6 2 12\nBITMAP\n70\n70\n60\nE0\nC0\nENDCHAR\n' in out


# ---------------------------------------------------------------------------
# exact format details


def test_fmtver():
    assert fmtver(2.1) == '2.1'
    assert fmtver(2) == '2.0'
    assert fmtver(2.0) == '2.0'
    assert fmtver(2.2) == '2.2'
    assert fmtver(10.25) == '10.25'


def test_full_format():
    font = Font()
    font.headers = {
        'bdfversion': 2.2,
        'fontname': 'x',
        'pointsize': 8,
        'xres': 72,
        'yres': 72,
        'fbbx': 8,
        'fbby': 8,
        'fbbxoff': 0,
        'fbbyoff': -1,
        'swx0': 500,
        'swy0': 0,
        'dwx0': 4,
        'dwy0': 0,
        'swx1': 0,
        'swy1': 1000,
        'dwx1': 0,
        'dwy1': 8,
        'vvectorx': 4,
        'vvectory': 7,
        'metricsset': 2,
        'contentversion': 3,
        'comment': ['c "q"', ''],
    }
    font.setprop('comment', ['p1'])
    font.setprop('Mixed_Case', 'say "hi"')
    font.setprop('NUM', -3)
    font.setprop('FLAG', None)
    font.setprop('BOOL', True)
    font.setprop('FLOAT', 1.5)
    font.addglyph(
        {
            'glyphname': 'A',
            'codepoint': 65,
            'bbw': 1,
            'bbh': 1,
            'bbxoff': 0,
            'bbyoff': 0,
            'swx0': 500,
            'swy0': 0,
            'dwx0': 4,
            'dwy0': 0,
            'swx1': 0,
            'swy1': 1000,
            'dwx1': 0,
            'dwy1': 8,
            'vvectorx': 4,
            'vvectory': 7,
            'hexdata': ['80'],
        }
    )
    font.addglyph({'glyphname': 'u', 'codepoint': -1, 'bbw': 1, 'bbh': 1, 'hexdata': ['80']})
    font.unencoded.append({'altcode': 42, 'meta': ['v', -1, 0, 0, 0, 0] + [None] * 10 + [[]]})
    font.addglyph(
        {'glyphname': 'half', 'codepoint': 66, 'swx0': 1, 'swy0': None, 'dwx0': 2, 'dwy0': 0}
    )
    assert font.tobdf() == (
        'STARTFONT 2.2\n'
        'FONT x\n'
        'SIZE 8 72 72\n'
        'FONTBOUNDINGBOX 8 8 0 -1\n'
        'METRICSSET 2\n'
        'CONTENTVERSION 3\n'
        'SWIDTH 500 0\n'
        'DWIDTH 4 0\n'
        'SWIDTH1 0 1000\n'
        'DWIDTH1 0 8\n'
        'VVECTOR 4 7\n'
        'COMMENT "c "q""\n'
        'COMMENT ""\n'
        'STARTPROPERTIES 5\n'
        'COMMENT "p1"\n'
        'Mixed_Case "say ""hi"""\n'
        'NUM -3\n'
        'FLAG\n'
        'BOOL 1\n'
        'FLOAT "1.5"\n'
        'ENDPROPERTIES\n'
        'CHARS 4\n'
        'STARTCHAR A\n'
        'ENCODING 65\n'
        'SWIDTH 500 0\n'
        'DWIDTH 4 0\n'
        'SWIDTH1 0 1000\n'
        'DWIDTH1 0 8\n'
        'VVECTOR 4 7\n'
        'BBX 1 1 0 0\n'
        'BITMAP\n'
        '80\n'
        'ENDCHAR\n'
        'STARTCHAR half\n'
        'ENCODING 66\n'
        'DWIDTH 2 0\n'
        'BBX 0 0 0 0\n'
        'BITMAP\n'
        'ENDCHAR\n'
        'STARTCHAR u\n'
        'ENCODING -1\n'
        'BBX 1 1 0 0\n'
        'BITMAP\n'
        '80\n'
        'ENDCHAR\n'
        'STARTCHAR v\n'
        'ENCODING -1 42\n'
        'BBX 0 0 0 0\n'
        'BITMAP\n'
        'ENDCHAR\n'
        'ENDFONT\n'
    )


def test_metricsset_zero_and_no_props():
    font = Font()
    font.headers = {
        'bdfversion': 2.1,
        'fontname': 'n',
        'pointsize': 1,
        'xres': 1,
        'yres': 1,
        'fbbx': 1,
        'fbby': 1,
        'fbbxoff': 0,
        'fbbyoff': 0,
        'metricsset': 0,
    }
    assert font.tobdf() == (
        'STARTFONT 2.1\nFONT n\nSIZE 1 1 1\nFONTBOUNDINGBOX 1 1 0 0\nCHARS 0\nENDFONT\n'
    )


def test_only_prop_comments():
    font = Font.create()
    font.props = {'comment': ['only']}
    assert '\nSTARTPROPERTIES 0\nCOMMENT "only"\nENDPROPERTIES\n' in font.tobdf()


def test_unloaded_font_raises():
    with pytest.raises(ValueError, match='missing header'):
        Font().tobdf()
    font = Font.create()
    del font.headers['fbbyoff']
    with pytest.raises(ValueError, match='fbbyoff'):
        font.tobdf()


def test_missing_optional_headers_defaults():
    font = Font.create()
    del font.headers['bdfversion'], font.headers['fontname']
    assert font.tobdf().startswith('STARTFONT 2.1\nFONT \nSIZE 16 75 75\n')


def test_glyph_order_is_dict_order():
    font = Font(unifont_path)
    out = font.tobdf()
    i1 = out.index('STARTCHAR U+0001\n')
    i0 = out.index('STARTCHAR U+0000\n')
    assert i1 < i0


def test_edit_then_write_then_read():
    font = Font().load_string(mini_bdf)
    font.glyphbycp(65).shift(1, 1)
    font.setprop('Custom', 'v')
    font.newglyph(67)
    again = Font().load_string(font.tobdf())
    assert again.glyphs == font.glyphs
    assert again.props == font.props
    assert again._propnames == font._propnames
    assert again.headers == font.headers


def test_round_trip_unencoded_and_altcode():
    font = Font().load_string(mini_bdf)
    font.unencoded.append({'altcode': 7, 'meta': ['alt', -1, 1, 1, 0, 0] + [None] * 10 + [['80']]})
    again = Font().load_string(font.tobdf())
    assert again.unencoded == font.unencoded
