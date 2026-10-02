"""Command line interface (spec section 9)."""

import gzip
import subprocess
import sys

import pytest

from bdfparser import Font, __version__
from bdfparser.cli import main

from .info import enctest_path, mini_bdf, specfont_path, unifont_path

pytestmark = pytest.mark.filterwarnings('ignore::bdfparser.BDFParserWarning')


@pytest.fixture
def mini(tmp_path):
    p = tmp_path / 'mini.bdf'
    p.write_text(mini_bdf, encoding='utf-8')
    return p


def test_info(capsys):
    assert main(['info', specfont_path]) == 0
    assert capsys.readouterr().out == (
        'fontname: Helvetica-BoldOblique\n'
        'glyphs: 2 (+ 0 unencoded)\n'
        'bbox: 9 24 -2 -6\n'
        'charset: iso10646\n'
        'properties:\n'
        '  MinSpace 4\n'
        '  Copyright "Copyright (c) 1987 Adobe Systems, Inc."\n'
    )


def test_info_comments_and_none(tmp_path, capsys):
    font = Font().load_string(mini_bdf)
    font.setprop('comment', ['a', 'b']).setprop('FLAG', None).setprop('Q', 'x"y')
    p = tmp_path / 'f.bdf'
    font.save(p)
    assert main(['info', str(p)]) == 0
    out = capsys.readouterr().out
    assert '  COMMENT a | b\n' in out
    assert '  FLAG\n' in out
    assert '  Q "x""y"\n' in out
    assert '  PIXEL_SIZE 8\n' in out


def test_info_charset(capsys):
    assert main(['info', enctest_path('big5')]) == 0
    assert 'charset: big5\n' in capsys.readouterr().out


def test_preview(capsys):
    assert main(['preview', specfont_path, "j'"]) == 0
    out = capsys.readouterr().out
    assert out == str(Font(specfont_path).draw("j'")) + '\n'
    assert set(out) <= set('.#\n')


def test_preview_non_unicode(capsys):
    assert main(['preview', enctest_path('gb2312'), '人']) == 0
    assert capsys.readouterr().out.startswith('.......#........\n')


@pytest.mark.parametrize('ext', ['bdf', 'pcf', 'ttf', 'svg'])
def test_convert(mini, tmp_path, ext):
    out = tmp_path / f'out.{ext}'
    assert main(['convert', str(mini), str(out)]) == 0
    data = out.read_bytes()
    font = Font().load_string(mini_bdf)
    if ext == 'bdf':
        assert data == mini_bdf.encode()
    elif ext == 'pcf':
        assert data == font.topcf()
    elif ext == 'ttf':
        assert data == font.tottf()
    else:
        assert data.decode() == font.tosvgfont()


def test_convert_uppercase_extension(mini, tmp_path):
    out = tmp_path / 'OUT.BDF'
    assert main(['convert', str(mini), str(out)]) == 0
    assert out.read_bytes() == mini_bdf.encode()


def test_convert_ttf_options(mini, tmp_path):
    out = tmp_path / 'o.ttf'
    args = ['convert', str(mini), str(out), '--shape', 'circle', '--dotsize', '0.8', '--ppu', '32']
    assert main(args) == 0
    font = Font().load_string(mini_bdf)
    assert out.read_bytes() == font.tottf(shape='circle', dotsize=0.8, ppu=32)


def test_convert_ttf_options_ignored_for_bdf(mini, tmp_path):
    out = tmp_path / 'o.bdf'
    assert main(['convert', str(mini), str(out), '--shape', 'circle']) == 0
    assert out.read_bytes() == mini_bdf.encode()


def test_convert_charset(tmp_path):
    out = tmp_path / 'o.bdf'
    assert main(['convert', enctest_path('utf8'), str(out), '--charset', 'gb2312']) == 0
    font = Font(str(out))
    assert font.props['charset_registry'] == 'GB2312.1980'
    assert sorted(font.glyphs) == [0x41, 0x3962, 0x484B]


def test_convert_from_pcf_gz_and_ttf(mini, tmp_path):
    font = Font().load_string(mini_bdf)
    pcfgz = tmp_path / 'm.pcf.gz'
    pcfgz.write_bytes(gzip.compress(font.topcf()))
    out = tmp_path / 'from_pcf.bdf'
    assert main(['convert', str(pcfgz), str(out)]) == 0
    assert Font(str(out)).glyphs == Font().load_bytes(font.topcf()).glyphs
    ttf = tmp_path / 'm.ttf'
    ttf.write_bytes(font.tottf())
    out2 = tmp_path / 'from_ttf.bdf'
    assert main(['convert', str(ttf), str(out2)]) == 0
    assert Font(str(out2)).glyphs == font.glyphs


def test_convert_ttf_pixelsize(mini, tmp_path):
    font = Font().load_string(mini_bdf)
    ttf = tmp_path / 'm.ttf'
    ttf.write_bytes(font.tottf(metadata=False))
    out = tmp_path / 'o.bdf'
    assert main(['convert', str(ttf), str(out), '--pixelsize', '8']) == 0
    assert sorted(Font(str(out)).glyphs) == [32, 65, 66]


def test_bad_output_extension(mini, tmp_path, capsys):
    assert main(['convert', str(mini), str(tmp_path / 'x.png')]) == 1
    assert 'cannot tell the output format' in capsys.readouterr().err


def test_missing_input(tmp_path, capsys):
    assert main(['info', str(tmp_path / 'nope.bdf')]) == 1
    assert capsys.readouterr().err.startswith('bdfparser: error: ')


def test_parse_error(tmp_path, capsys):
    p = tmp_path / 'bad.bdf'
    p.write_text('STARTFONT 2.1\nSIZE x 1 1\n')
    assert main(['info', str(p)]) == 1
    assert 'line 2' in capsys.readouterr().err


def test_truncated_gzip_input(tmp_path, capsys):
    # regression: EOFError from gzip escaped the CLI's error handling (traceback)
    p = tmp_path / 'bad.pcf.gz'
    p.write_bytes(gzip.compress(Font().load_string(mini_bdf).topcf())[:40])
    assert main(['info', str(p)]) == 1
    assert capsys.readouterr().err.startswith('bdfparser: error: Malformed gzip data')


def test_usage_errors(capsys):
    with pytest.raises(SystemExit) as e:
        main([])
    assert e.value.code == 2
    with pytest.raises(SystemExit) as e:
        main(['convert', 'a.bdf', 'b.ttf', '--shape', 'hexagon'])
    assert e.value.code == 2


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        main(['--version'])
    assert e.value.code == 0
    assert capsys.readouterr().out.strip() == f'bdfparser {__version__}'


def test_quiet_suppresses_warnings(tmp_path, recwarn):
    p = tmp_path / 'w.bdf'
    p.write_text(mini_bdf.replace('CHARS 3', 'CHARS 4'))
    assert main(['-q', 'info', str(p)]) == 0
    assert not [w for w in recwarn if 'CHARS' in str(w.message)]


def test_python_m(tmp_path):
    r = subprocess.run(
        [sys.executable, '-m', 'bdfparser', 'preview', unifont_path, 'a'],
        capture_output=True,
        text=True,
        check=True,
    )
    assert r.stdout.startswith('................\n')
