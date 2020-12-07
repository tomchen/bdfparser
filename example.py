import bdfparser as bp

bpo = bp.BdfParser('example_fonts/bdf/unifont-9.0.06.bdf')

print(bpo.getCharBmpByUnicode(30340)) # binary representation of bitmap of the character "的"

print(bpo.getCharHexByUnicode(30340)) # hex representation of bitmap of the character "的"

print(bpo.getCharHexByUnicode(30340).hex()) # hex representation in bytes of bitmap of the character "的"

print(bpo.getGlyphInfo(30340)) # {'dwx0': 16, 'bbW': 16, 'bbH': 16, 'bbXOff': 0, 'bbYOff': -2, 'bitmap': '1040\n1040\n2040\n7E7C\n4284\n4284\n4304\n4244\n7E24\n4224\n4204\n4204\n4204\n7E04\n4228\n0010', 'outputW': 16, 'outputH': 16, 'shadowedOutputW': 17, 'shadowedOutputH': 17, 'glowedOutputW': 18, 'glowedOutputH': 18}

print(bpo.getCharBmpByUnicode(65507)) # binary representation of bitmap of the character "￣"

print(bpo.getCharBmpByUnicode(169)) # binary representation of bitmap of the character "©"

# However, if you use HanWangYanKai font which covers Big5 characters, because "©" does not exist in Big5 and HanWangYanKai font, it throws an error in the following example:
bpo = bp.BdfParser('example_fonts/bdf/HanWangYanKai-26.bdf')
print(bpo.getCharBmpByUnicode(169))

print(bpo.getFontName()) # name of the font (from the "FONT" declaration in the BDF file)
