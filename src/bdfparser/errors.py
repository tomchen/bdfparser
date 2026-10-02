"""
Warning and exception classes used by bdfparser.

https://font.tomchen.org/bdfparser_py/
"""

from __future__ import annotations

import warnings

__all__ = ['BDFParserWarning', 'BDFParseError']


class BDFParserWarning(UserWarning):
    """
    Category of every warning emitted by bdfparser (non-fatal problems in a font,
    missing glyphs, unknown charsets, ...).

    Filter them with the standard `warnings` machinery, e.g.
    `warnings.simplefilter('ignore', BDFParserWarning)`.
    """


class BDFParseError(ValueError):
    """
    Raised on fatal BDF parse errors (unexpected end of file inside the headers,
    malformed numbers in required fields, glyph without `BBX`, ...).

    `lineno` is the 1-based line number where the problem was detected (or `None`).
    """

    def __init__(self, message: str, lineno: int | None = None) -> None:
        self.lineno = lineno
        self.msg = message
        super().__init__(f'line {lineno}: {message}' if lineno is not None else message)


def _warn(message: str) -> None:
    # stacklevel=3 here == stacklevel=2 at the call site of `_warn`
    warnings.warn(message, BDFParserWarning, stacklevel=3)
