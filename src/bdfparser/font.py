from .bitmap import Bitmap
from .glyph import Glyph
import re
import io
import pathlib
import warnings
from sys import version_info as python_version

def format_warning(message, category, filename, lineno, file=None, line=None):
    return '%s:%s\n%s: %s\n' % (filename, lineno, 'bdfparser warning', message)

warnings.formatwarning = format_warning

class Font(object):
    '''
    `Font` object

    https://font.tomchen.org/bdfparser_py/font
    '''

    __PATTERN_VVECTOR_DELIMITER = re.compile(r'[,\s]+')

    __META_TITLES = [
        'glyphname',
        'codepoint',
        'bbw',
        'bbh',
        'bbxoff',
        'bbyoff',
        'swx0',
        'swy0',
        'dwx0',
        'dwy0',
        'swx1',
        'swy1',
        'dwx1',
        'dwy1',
        'vvectorx',
        'vvectory',
        'hexdata',
    ]

    __EMPTY_GLYPH = {
        'glyphname': 'empty',
        'codepoint': 8203,  # zero-width space's codepoint
        'bbw': 0,
        'bbh': 0,
        'bbxoff': 0,
        'bbyoff': 0,
        'swx0': 0,
        'swy0': 0,
        'dwx0': 0,
        'dwy0': 0,
        'swx1': 0,
        'swy1': 0,
        'dwx1': 0,
        'dwy1': 0,
        'vvectorx': 0,
        'vvectory': 0,
        'hexdata': [],
    }

    def __init__(self, *argv):
        '''
        Initialize a `Font` object. Load the BDF font file if a file path string or a file object is present.

        https://font.tomchen.org/bdfparser_py/font#font
        '''

        if python_version < (3, 7, 0):
            from collections import OrderedDict as ordered_dict
        else:
            ordered_dict = dict

        self.headers = ordered_dict()
        self.props = ordered_dict()
        self.glyphs = ordered_dict()
        self.unencoded = []
        self._propnames = {}

        self.__glyph_count_to_check = None
        self.__curline_startchar = None
        self.__curline_chars = None

        l = len(argv)
        if l == 1:
            arg = argv[0]
            if isinstance(arg, str) or isinstance(arg, pathlib.Path):
                self.load_file_path(arg)
            elif isinstance(arg, io.IOBase):
                self.load_file_obj(arg)

    def load_file_path(self, file_path):
        '''
        Load the BDF font file in the file path.

        https://font.tomchen.org/bdfparser_py/font#load_file_path
        '''

        with open(file_path) as file_obj:
            self.load_file_obj(file_obj)
        return self

    def load_file_obj(self, file_obj):
        '''
        Load the BDF font file object.

        https://font.tomchen.org/bdfparser_py/font#load_file_obj
        '''

        self.__f = file_obj
        self.__parse_headers()
        return self

    def __parse_headers(self):

        while 1:

            line = next(self.__f).strip()
            while len(line) == 0:
                line = next(self.__f).strip()
            kvlist = line.split(None, 1)
            l = len(kvlist)

            if l == 2:
                key = kvlist[0]
                value = kvlist[1].strip()
                if key == 'STARTFONT':
                    self.headers['bdfversion'] = float(value)
                elif key == 'FONT':
                    self.headers['fontname'] = value
                elif key == 'SIZE':
                    nlist = value.split()
                    self.headers['pointsize'] = int(nlist[0])
                    self.headers['xres'] = int(nlist[1])
                    self.headers['yres'] = int(nlist[2])
                elif key == 'FONTBOUNDINGBOX':
                    nlist = value.split()
                    self.headers['fbbx'] = int(nlist[0])
                    self.headers['fbby'] = int(nlist[1])
                    self.headers['fbbxoff'] = int(nlist[2])
                    self.headers['fbbyoff'] = int(nlist[3])
                elif key == 'STARTPROPERTIES':
                    self.__parse_headers_after()
                    self.__parse_props()
                    return
                elif key == 'COMMENT':
                    comment = 'comment'
                    if comment not in self.headers:
                        self.headers[comment] = []
                    self.headers[comment].append(value.strip(' "\'\t\r\n'))
                elif key == 'SWIDTH':
                    nlist = value.split()
                    self.headers['swx0'] = int(nlist[0])
                    self.headers['swy0'] = int(nlist[1])
                elif key == 'DWIDTH':
                    nlist = value.split()
                    self.headers['dwx0'] = int(nlist[0])
                    self.headers['dwy0'] = int(nlist[1])
                elif key == 'SWIDTH1':
                    nlist = value.split()
                    self.headers['swx1'] = int(nlist[0])
                    self.headers['swy1'] = int(nlist[1])
                elif key == 'DWIDTH1':
                    nlist = value.split()
                    self.headers['dwx1'] = int(nlist[0])
                    self.headers['dwy1'] = int(nlist[1])
                elif key == 'VVECTOR':
                    nlist = self.__PATTERN_VVECTOR_DELIMITER.split(value)
                    self.headers['vvectorx'] = int(nlist[0])
                    self.headers['vvectory'] = int(nlist[1])
                elif key == 'METRICSSET' or key == 'CONTENTVERSION':
                    self.headers[key.lower()] = int(value)
                elif key == 'CHARS':
                    warnings.warn(
                        "It looks like the font does not have property block beginning with 'STARTPROPERTIES' keyword")
                    self.__parse_headers_after()
                    self.__curline_chars = line
                    self.__parse_glyph_count()
                    return
                elif key == 'STARTCHAR':
                    warnings.warn(
                        "It looks like the font does not have property block beginning with 'STARTPROPERTIES' keyword")
                    warnings.warn("Cannot find 'CHARS' line")
                    self.__parse_headers_after()
                    self.__curline_startchar = line
                    self.__prepare_glyphs()
                    return

            if l == 1 and kvlist[0].strip() == 'ENDFONT':
                warnings.warn(
                    "It looks like the font does not have property block beginning with 'STARTPROPERTIES' keyword")
                warnings.warn("This font does not have any glyphs")
                return

    def __parse_headers_after(self):
        if 'metricsset' not in self.headers:
            self.headers['metricsset'] = 0

    def __parse_props(self):

        while 1:

            line = next(self.__f).strip()
            while len(line) == 0:
                line = next(self.__f).strip()
            kvlist = line.split(None, 1)
            l = len(kvlist)

            if l == 2:
                key = kvlist[0]
                value = kvlist[1].strip(' "\'\t\r\n')
                if key == 'COMMENT':
                    comment = 'comment'
                    if comment not in self.props:
                        self.props[comment] = []
                    self.props[comment].append(value.strip(' "\'\t\r\n'))
                else:
                    self.props[key.lower()] = value.replace('""', '"')
            elif l == 1:
                key = kvlist[0].strip()
                if key == 'ENDPROPERTIES':
                    self.__parse_glyph_count()
                    return
                if key == 'ENDFONT':
                    warnings.warn("This font does not have any glyphs")
                    return
                else:
                    self.props[key] = None

    def __parse_glyph_count(self):

        if self.__curline_chars is None:
            line = next(self.__f).strip()
            while len(line) == 0:
                line = next(self.__f).strip()
        else:
            line = self.__curline_chars
            self.__curline_chars = None

        if line.strip() == 'ENDFONT':
            warnings.warn("This font does not have any glyphs")
            return

        kvlist = line.split(None, 1)
        if kvlist[0] == 'CHARS':
            self.__glyph_count_to_check = int(kvlist[1].strip())
        else:
            self.__curline_startchar = line
            warnings.warn(
                "Cannot find 'CHARS' line next to 'ENDPROPERTIES' line")
        self.__prepare_glyphs()

    def __prepare_glyphs(self):

        glyph_meta = []
        glyph_bitmap = []
        glyph_bitmap_is_on = False

        STARTCHAR_used = ENCODING_used = BBX_used = SWIDTH_used = DWIDTH_used = SWIDTH1_used = DWIDTH1_used = VVECTOR_used = BITMAP_used = glyph_end = False

        while 1:
            if self.__curline_startchar is None:
                line = next(self.__f, None)
            else:
                line = self.__curline_startchar
                self.__curline_startchar = None

            if line is None:
                warnings.warn("This font does not have 'ENDFONT' keyword")
                self.__prepare_glyphs_after()
                return

            kvlist = line.split(None, 1)
            l = len(kvlist)

            if l == 2:
                key = kvlist[0]
                value = kvlist[1].strip()
                if not STARTCHAR_used and key == 'STARTCHAR':
                    glyph_meta = [None] * 17
                    glyph_meta[0] = value
                    STARTCHAR_used = True
                    glyph_end = False
                elif not ENCODING_used and key == 'ENCODING':
                    glyph_codepoint = int(value)
                    glyph_meta[1] = glyph_codepoint
                    ENCODING_used = True
                elif not BBX_used and key == 'BBX':
                    nlist = value.split()
                    glyph_meta[2] = int(nlist[0])
                    glyph_meta[3] = int(nlist[1])
                    glyph_meta[4] = int(nlist[2])
                    glyph_meta[5] = int(nlist[3])
                    BBX_used = True
                elif not SWIDTH_used and key == 'SWIDTH':
                    nlist = value.split()
                    glyph_meta[6] = int(nlist[0])
                    glyph_meta[7] = int(nlist[1])
                    SWIDTH_used = True
                elif not DWIDTH_used and key == 'DWIDTH':
                    nlist = value.split()
                    glyph_meta[8] = int(nlist[0])
                    glyph_meta[9] = int(nlist[1])
                    DWIDTH_used = True
                elif not SWIDTH1_used and key == 'SWIDTH1':
                    nlist = value.split()
                    glyph_meta[10] = int(nlist[0])
                    glyph_meta[11] = int(nlist[1])
                    SWIDTH1_used = True
                elif not DWIDTH1_used and key == 'DWIDTH1':
                    nlist = value.split()
                    glyph_meta[12] = int(nlist[0])
                    glyph_meta[13] = int(nlist[1])
                    DWIDTH1_used = True
                elif not VVECTOR_used and key == 'VVECTOR':
                    nlist = self.__PATTERN_VVECTOR_DELIMITER.split(value)
                    glyph_meta[14] = int(nlist[0])
                    glyph_meta[15] = int(nlist[1])
                    VVECTOR_used = True

            elif l == 1:
                key = kvlist[0].strip()
                if not BITMAP_used and key == 'BITMAP':
                    glyph_bitmap = []
                    glyph_bitmap_is_on = True
                    BITMAP_used = True
                elif key == 'ENDCHAR':
                    glyph_bitmap_is_on = False
                    glyph_meta[16] = glyph_bitmap
                    self.glyphs[glyph_codepoint] = glyph_meta
                    STARTCHAR_used = ENCODING_used = BBX_used = SWIDTH_used = DWIDTH_used = SWIDTH1_used = DWIDTH1_used = VVECTOR_used = BITMAP_used = False
                    glyph_end = True
                elif glyph_end and key == 'ENDFONT':
                    self.__prepare_glyphs_after()
                    return
                elif glyph_bitmap_is_on:
                    glyph_bitmap.append(key)

    def __prepare_glyphs_after(self):
        l = len(self.glyphs)
        if self.__glyph_count_to_check != l:
            if self.__glyph_count_to_check is None:
                warnings.warn(
                    "The glyph count next to 'CHARS' keyword does not exist")
            else:
                warnings.warn(
                    "The glyph count next to 'CHARS' keyword is " +
                    str(self.__glyph_count_to_check) +
                    ", which does not match the actual glyph count " + str(l)
                )
                # Use old style for Python 3.5 support. For 3.6+:
                # f"The glyph count next to 'CHARS' keyword is {str(self.__glyph_count_to_check)}, which does not match the actual glyph count {str(l)}"

    def setprop(self, key, value):
        '''
        Set a property (case-insensitive key). Remembers the given spelling of a new key.
        '''

        k = key.lower()
        if k not in self._propnames and k != 'comment':
            self._propnames[k] = key
        self.props[k] = value
        return self

    def swidth(self, dwx):
        '''
        Compute SWIDTH (scalable width, 1/1000 em) from DWIDTH (pixels).
        '''

        import math
        pointsize = self.headers.get('pointsize')
        xres = self.headers.get('xres')
        if pointsize and xres:
            return math.floor(dwx * 72000 / (pointsize * xres) + 0.5)
        return math.floor(dwx * 1000 / max(self.headers.get('fbbx') or 1, 1) + 0.5)

    def length(self):
        '''
        Returns how many glyphs actually exist in the font.

        https://font.tomchen.org/bdfparser_py/font#length
        '''

        return len(self.glyphs)

    def __len__(self):
        '''
        Same as `.length()`
        '''
        return self.length()

    def itercps(self, order=1, r=None):
        '''
        Almost identical to `.iterglyphs()`, except it returns an `iterator` of glyph codepoints instead of an `iterator` of `Glyph` objects.

        https://font.tomchen.org/bdfparser_py/font#itercps
        '''

        ks = self.glyphs.keys()
        if order == 1:
            retiterator = iter(sorted(ks))
        elif order == 0:
            retiterator = iter(ks)
        elif order == 2:
            retiterator = iter(sorted(ks, reverse=True))
        elif order == -1:
            try:
                retiterator = reversed(ks)
            except TypeError:
                retiterator = reversed(list(ks))  # Python <=3.7
        if r is not None:
            def f(cp):
                if isinstance(r, int):
                    return cp < r
                elif isinstance(r, tuple):
                    return cp <= r[1] and cp >= r[0]
                elif isinstance(r, list):
                    for t in r:
                        if cp <= t[1] and cp >= t[0]:
                            return True
                    return False
            retiterator = filter(f, retiterator)
        return retiterator

    def iterglyphs(self, order=1, r=None):
        '''
        Returns an iterator of all the glyphs (as `Glyph` objects) in the font (default) or in the specified codepoint range in the font, sorted by the specified order (or by the ascending codepoint order by default).

        https://font.tomchen.org/bdfparser_py/font#iterglyphs
        '''

        for cp in self.itercps(order, r):
            yield self.glyphbycp(cp)

    def glyphbycp(self, codepoint):
        '''
        Get a glyph (as Glyph object) by its codepoint.

        https://font.tomchen.org/bdfparser_py/font#glyphbycp
        '''

        if codepoint not in self.glyphs:
            warnings.warn(
                "Glyph \"" + chr(codepoint) + "\" (codepoint " +
                str(codepoint) + ") does not exist in the font. Will return `None`"
            )
            # Use old style for Python 3.5 support. For 3.6+:
            # f"Glyph \"{chr(codepoint)}\" (codepoint {str(codepoint)}) does not exist in the font. Will return `None`"
            return None
        return Glyph(dict(zip(self.__META_TITLES, self.glyphs[codepoint])), self)

    def glyph(self, character):
        '''
        Get a glyph (as `Glyph` object) by its character.

        https://font.tomchen.org/bdfparser_py/font#glyph
        '''

        return self.glyphbycp(ord(character))

    def lacksglyphs(self, string):
        '''
        Check if there is any missing glyph and gets these glyphs' character.

        https://font.tomchen.org/bdfparser_py/font#lacksglyphs
        '''

        l = []
        for cp, char in ((ord(char), char) for char in string):
            if cp not in self.glyphs:
                l.append(char)
        return l if len(l) != 0 else None

    def drawcps(self, cps, linelimit=512, mode=1, direction='lrtb', usecurrentglyphspacing=False, missing=None):
        '''
        Draw the glyphs of the specified codepoints, to a `Bitmap` object.

        https://font.tomchen.org/bdfparser_py/font#drawcps
        '''

        dire_shortcut_dict = {
            'lr': 'lrtb',
            'rl': 'rltb',
            'tb': 'tbrl',
            'bt': 'btrl',
        }
        dire = dire_shortcut_dict.get(direction) or direction
        dire_dict = {
            'lr': 1,
            'rl': 2,
            'tb': 0,
            'bt': -1,
        }
        dire_glyph_str = dire[0:2]
        dire_line_str = dire[2:4]
        if dire_glyph_str in dire_dict and dire_line_str in dire_dict:
            dire_glyph = dire_dict[dire_glyph_str]
            dire_line = dire_dict[dire_line_str]
        else:
            dire_glyph = 1
            dire_line = 0

        if dire_line == 0 or dire_line == 2:  # 'xxtb' or 'xxrl'
            align_glyph = 1  # bottom or left
        elif dire_line == 1 or dire_line == -1:  # 'xxlr' or 'xxbt'
            align_glyph = 0  # right or top

        if dire_glyph == 1 or dire_glyph == -1:  # 'lrxx' or 'btxx'
            align_line = 1  # left or bottom
        elif dire_glyph == 2 or dire_glyph == 0:  # 'rlxx' or 'tbxx'
            align_line = 0  # right or top

        if mode == 1:  # dwidth / dwidth1 mode
            # 'lrxx'/'rlxx' else 'tbxx'/'btxx'
            fbbsize = self.headers['fbbx'] if dire_glyph > 0 else self.headers['fbby']

            if dire_glyph > 0:  # 'lrxx'/'rlxx'
                # interglyph_keyword = 'DWIDTH'
                interglyph_str = 'dwx0'
                interglyph_str2 = 'dwy0'
            else:  # 'tbxx'/'btxx'
                # interglyph_keyword = 'DWIDTH1'
                interglyph_str = 'dwx1'
                interglyph_str2 = 'dwy1'

            if interglyph_str in self.headers:
                interglyph_global = self.headers[interglyph_str]
            elif interglyph_str2 in self.headers:
                interglyph_global = self.headers[interglyph_str2]
            else:
                interglyph_global = None
                # warnings.warn("The font do not have `" + interglyph_keyword + "`, glyph spacing adjustment could be skipped unless present in individual glyphs")
                # # Use old style for Python 3.5 support. For 3.6+:
                # # warnings.warn(f"The font do not have `{interglyph_keyword}`, glyph spacing adjustment could be skipped unless present in individual glyphs")

        list_of_bitmaplist = []
        bitmaplist = []
        list_of_offsetlist = []
        offsetlist = []
        size = 0

        def append_bitmaplist_and_offsetlist():
            list_of_bitmaplist.append(bitmaplist)
            if usecurrentglyphspacing:
                offsetlist.pop(0)
            else:  # use previous glyph spacing (default)
                offsetlist.pop()
            list_of_offsetlist.append(offsetlist)

        cpsiter = iter(cps)
        skip = False
        while 1:
            if skip:
                skip = False
            else:
                cp = next(cpsiter, None)
                if cp is None:
                    break

                if cp in self.glyphs:
                    glyph = self.glyphbycp(cp)
                elif missing:
                    if isinstance(missing, Glyph):
                        glyph = missing
                    else:  # isinstance(missing, dict):
                        glyph = Glyph(missing, self)
                else:
                    glyph = Glyph(self.__EMPTY_GLYPH, self)

                bitmap = glyph.draw()
                w = bitmap.width()

                offset = 0
                if mode == 1:
                    interglyph = glyph.meta[interglyph_str] or glyph.meta[interglyph_str2]
                    if interglyph is None:
                        interglyph = interglyph_global
                    if interglyph is not None:
                        offset = interglyph - fbbsize

            size += w + offset
            if size <= linelimit:
                bitmaplist.append(bitmap)
                offsetlist.append(offset)
            else:
                if len(bitmaplist) == 0:
                    raise Exception(
                        "`linelimit` (" + linelimit + ") is too small the line can't even contain one glyph: \"" +
                        glyph.chr() + "\" (codepoint " + cp + ", width: " + w + ")"
                    )
                    # Use old style for Python 3.5 support. For 3.6+:
                    # f"`linelimit` ({linelimit}) is too small the line can't even contain one glyph: \"{glyph.chr()}\" (codepoint {cp}, width: {w})"
                append_bitmaplist_and_offsetlist()
                size = 0
                bitmaplist = []
                offsetlist = []
                skip = True
        if len(bitmaplist) != 0:
            append_bitmaplist_and_offsetlist()

        list_of_bitmap_line_lists = [Bitmap.concatall(bitmaplist, direction=dire_glyph, align=align_glyph,
                                                      offsetlist=list_of_offsetlist[i]) for i, bitmaplist in enumerate(list_of_bitmaplist)]

        return Bitmap.concatall(list_of_bitmap_line_lists, direction=dire_line, align=align_line)

    def draw(self, string, linelimit=512, mode=1, direction='lrtb', usecurrentglyphspacing=False, missing=None):
        '''
        Draw (render) the glyphs of the specified words / setences / paragraphs (as a `str`), to a `Bitmap` object.

        https://font.tomchen.org/bdfparser_py/font#draw
        '''

        return self.drawcps((ord(char) for char in string), linelimit, mode, direction, usecurrentglyphspacing, missing)

    def drawall(self, order=1, r=None, linelimit=512, mode=0, direction='lrtb', usecurrentglyphspacing=False):
        '''
        Draw all the glyphs in the font (default) or in the specified codepoint range in the font, sorted by the specified order (or by the ascending codepoint order by default), to a `Bitmap` object.

        https://font.tomchen.org/bdfparser_py/font#drawall
        '''

        return self.drawcps(self.itercps(order, r), linelimit, mode, direction, usecurrentglyphspacing)
