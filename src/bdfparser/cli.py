"""
Command line interface: `bdfparser convert | info | preview`.

https://font.tomchen.org/bdfparser_py/cli
"""

from __future__ import annotations

import argparse
import sys
import warnings
from collections.abc import Sequence

from . import __version__
from .errors import BDFParserWarning
from .font import Font

__all__ = ['main']

_OUTPUT_FORMATS = ('bdf', 'pcf', 'ttf', 'svg')


def _load(path: str, pixelsize: int | None = None) -> Font:
    with open(path, 'rb') as f:
        data = f.read()
    opts = {'pixelsize': pixelsize} if pixelsize is not None else {}
    return Font().load_bytes(data, **opts)


def _output_format(path: str) -> str:
    lower = path.lower()
    for fmt in _OUTPUT_FORMATS:
        if lower.endswith('.' + fmt):
            return fmt
    raise ValueError(f'cannot tell the output format from {path!r} (use .bdf, .pcf, .ttf or .svg)')


def _propvalue(v: object) -> str:
    if v is None:
        return ''
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return ' | '.join(str(x) for x in v)
    return '"' + str(v).replace('"', '""') + '"'


def _cmd_convert(args: argparse.Namespace) -> int:
    fmt = _output_format(args.output)
    font = _load(args.input, args.pixelsize)
    if args.charset:
        font.charsetconvert(args.charset)
    opts = {}
    if fmt == 'ttf':
        if args.shape is not None:
            opts['shape'] = args.shape
        if args.dotsize is not None:
            opts['dotsize'] = args.dotsize
        if args.ppu is not None:
            opts['ppu'] = args.ppu
    font.save(args.output, fmt, **opts)
    return 0


def _cmd_info(args: argparse.Namespace, out) -> int:
    font = _load(args.input, args.pixelsize)
    h = font.headers
    print(f'fontname: {h.get("fontname", "")}', file=out)
    print(f'glyphs: {len(font.glyphs)} (+ {len(font.unencoded)} unencoded)', file=out)
    print(f'bbox: {h.get("fbbx")} {h.get("fbby")} {h.get("fbbxoff")} {h.get("fbbyoff")}', file=out)
    print(f'charset: {font.charset}', file=out)
    print('properties:', file=out)
    for k, v in font.props.items():
        name = 'COMMENT' if k == 'comment' else font._propnames.get(k, k.upper())
        print(f'  {name} {_propvalue(v)}'.rstrip(), file=out)
    return 0


def _cmd_preview(args: argparse.Namespace, out) -> int:
    font = _load(args.input, args.pixelsize)
    print(str(font.draw(args.text)), file=out)
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='bdfparser',
        description='BDF / PCF / TTF bitmap font parser, editor and converter',
    )
    p.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    p.add_argument('-q', '--quiet', action='store_true', help='do not print warnings')
    sub = p.add_subparsers(dest='command', required=True)

    c = sub.add_parser(
        'convert', help='convert a font (.bdf .pcf .pcf.gz .ttf) to .bdf .pcf .ttf or .svg'
    )
    c.add_argument('input')
    c.add_argument('output')
    c.add_argument(
        '--shape', choices=('square', 'circle'), help='TTF pixel dot shape (default square)'
    )
    c.add_argument(
        '--dotsize', type=float, help='TTF dot size relative to a pixel, (0, 1.5] (default 1)'
    )
    c.add_argument('--ppu', type=int, help='TTF font units per pixel (default 64)')
    c.add_argument(
        '--pixelsize', type=int, help='pixel size of a TTF input without bdfparser metadata'
    )
    c.add_argument('--charset', help='convert glyph codepoints to this charset before writing')

    i = sub.add_parser('info', help='print font information')
    i.add_argument('input')
    i.add_argument(
        '--pixelsize', type=int, help='pixel size of a TTF input without bdfparser metadata'
    )

    v = sub.add_parser('preview', help='print TEXT rendered with # and .')
    v.add_argument('input')
    v.add_argument('text')
    v.add_argument(
        '--pixelsize', type=int, help='pixel size of a TTF input without bdfparser metadata'
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    """
    Entry point of the `bdfparser` console script. Returns the exit status.

    https://font.tomchen.org/bdfparser_py/cli
    """

    args = _parser().parse_args(argv)
    out = sys.stdout
    with warnings.catch_warnings():
        if args.quiet:
            warnings.simplefilter('ignore', BDFParserWarning)
        try:
            if args.command == 'convert':
                return _cmd_convert(args)
            if args.command == 'info':
                return _cmd_info(args, out)
            return _cmd_preview(args, out)
        except (OSError, ValueError) as e:
            print(f'bdfparser: error: {e}', file=sys.stderr)
            return 1
