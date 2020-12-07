import bdfparser as bp

bpo = bp.BdfParser('example_fonts/bdf/unifont-9.0.06.bdf')

print(bpo.getCharBmpByUnicode(30340)) # binary representation of bitmap of the character "的"

print(bpo.getCharHexByUnicode(30340)) # hex representation of bitmap of the character "的"

print(bpo.getCharHexByUnicode(30340).hex()) # hex representation in bytes of bitmap of the character "的"

print(bpo.getGlyphInfo(30340)) # {'dwx0': 14, 'bbW': 12, 'bbH': 14, 'bbXOff': 1, 'bbYOff': -2, 'bitmap': '2100\n2100\n41F0\nFA10\n8C10\n8810\n8910\nF890\n8890\n8810\n8810\n8810\nF810\n8860', 'outputW': 14, 'outputH': 15, 'shadowedOutputW': 15, 'shadowedOutputH': 16, 'glowedOutputW': 16, 'glowedOutputH': 17}

print(bpo.getCharBmpByUnicode(65507)) # binary representation of bitmap of the character "￣"

print(bpo.getCharBmpByUnicode(169)) # binary representation of bitmap of the character "©" -- "©" does not exist in some font, and does not exist in GBK, therefore it throws an error

print(bpo.getFontName()) # name of the font from the FONT declaration
