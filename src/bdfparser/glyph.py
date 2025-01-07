from .bitmap import Bitmap

class Glyph(object):
    '''
    `Glyph` object

    https://font.tomchen.org/bdfparser_py/glyph
    '''

    def __init__(self, meta_dict, font):
        '''
        Initialize a `Glyph` object. Load a `dict` of meta information and the font the glyph belongs.

        https://font.tomchen.org/bdfparser_py/glyph#glyph
        '''

        self.meta = meta_dict
        self.font = font

    def __str__(self):
        '''
        Gets a human-readable (multi-line) `str` representation of the `Glyph` object.

        https://font.tomchen.org/bdfparser_py/glyph#str-and-print
        '''

        return str(self.draw())

    def __repr__(self):
        '''
        Gets a programmer-readable `str` representation of the `Glyph` object.

        https://font.tomchen.org/bdfparser_py/glyph#repr
        '''

        return 'Glyph(' + str(self.meta) + ', ' + str(self.font) + ')'

    def cp(self):
        '''
        Get the codepoint of the glyph.

        https://font.tomchen.org/bdfparser_py/glyph#cp
        '''

        return self.meta['codepoint']

    def chr(self):
        '''
        Get the character of the glyph.

        https://font.tomchen.org/bdfparser_py/glyph#chr
        '''

        return chr(self.cp())

    def draw(self, mode=0, bb=None):
        '''
        Draw the glyph to a `Bitmap` object.

        https://font.tomchen.org/bdfparser_py/glyph#draw
        '''

        if mode == 0:
            retbitmap = self.__draw_fbb()
        elif mode == 1:
            retbitmap = self.__draw_bb()
        elif mode == 2:
            retbitmap = self.__draw_original()
        elif mode == -1 and bb is not None:
            retbitmap = self.__draw_user_specified(bb)
        elif mode == -1 and bb is None:
            raise Exception(
                'Parameter bb in draw() method must be set when mode=-1')
        return retbitmap

    def __draw_user_specified(self, fbb):
        bbxoff = self.meta.get('bbxoff')
        bbyoff = self.meta.get('bbyoff')
        (fbbx, fbby, fbbxoff, fbbyoff) = fbb
        bitmap = self.__draw_bb()
        return bitmap.crop(fbbx, fbby, - bbxoff + fbbxoff, - bbyoff + fbbyoff)

    def __draw_original(self):
        return Bitmap([bin(int(h, 16))[2:].zfill(len(h) * 4) if h else '' for h in self.meta.get('hexdata')])

    def __draw_bb(self):
        bbw = self.meta.get('bbw')
        bbh = self.meta.get('bbh')
        bitmap = self.__draw_original()
        bindata = bitmap.bindata
        l = len(bindata)
        if l != bbh:
            raise Exception(
                "Glyph \"" + str(self.meta.get('glyphname')) + "\" (codepoint " + str(self.meta.get(
                    'codepoint')) + ")'s bbh, " + str(bbh) + ", does not match its hexdata line count, " + str(l)
            )
            # Use old style for Python 3.5 support. For 3.6+:
            # f"Glyph \"{str(self.meta.get('glyphname'))}\" (codepoint {str(self.meta.get('codepoint'))})'s bbh, {str(bbh)}, does not match its hexdata line count, {str(l)}"
        bitmap.bindata = [b[0:bbw] for b in bindata]
        return bitmap

    def __draw_fbb(self):
        fh = self.font.headers
        return self.__draw_user_specified((fh['fbbx'], fh['fbby'], fh['fbbxoff'], fh['fbbyoff']))

    def origin(self, mode=0, fromorigin=False, xoff=None, yoff=None):
        '''
        Get the relative position (displacement) of the origin from the left bottom corner of the bitmap drawn by the method `.draw()`, or vice versa.

        https://font.tomchen.org/bdfparser_py/glyph#origin
        '''

        bbxoff = self.meta.get('bbxoff')
        bbyoff = self.meta.get('bbyoff')
        if mode == 0:
            fh = self.font.headers
            ret = (fh['fbbxoff'], fh['fbbyoff'])
        elif mode == 1:
            ret = (bbxoff, bbyoff)
        elif mode == 2:
            ret = (bbxoff, bbyoff)
        elif mode == -1 and (xoff is not None and yoff is not None):
            ret = (xoff, yoff)
        elif mode == -1 and (xoff is None or yoff is None):
            raise Exception(
                'Parameter xoff and yoff in origin() method must be all set when mode=-1')
        return ret if fromorigin else (0 - ret[0], 0 - ret[1])
