# BDF Parser

BDF (Glyph Bitmap Distribution Format) Bitmap Font File Parser (Python).

## Usage

```python
BdfParserObject = BdfParser(<font_file_path>)
BdfParserObject.{getCharBmpByUnicode|getCharHexByUnicode|getCharHexByUnicode|getGlyphInfo}(<unicode_decimal>)
```

## Example

(see also [example.py](https://github.com/tomchen/bdfparser/blob/master/example.py)):

Import library and instantiation:

```python
import bdfparser as bp
bpo = bp.BdfParser('example_fonts/bdf/SimSun-14.bdf')
```

Get binary representation string of bitmap of the character "的":

```python
print(bpo.getCharBmpByUnicode(30340))
```

Get hex representation string of bitmap of the character "的":

```python
print(bpo.getCharHexByUnicode(30340))
```

Get hex representation string in bytes of bitmap of the character "的":

```python
print(bpo.getCharHexByUnicode(30340).hex())
```

Get glyph information:

```python
print(bpo.getGlyphInfo(30340))
```

The above script returns:

```python
{'dwx0': 14, 'bbW': 12, 'bbH': 14, 'bbXOff': 1, 'bbYOff': -2, 'bitmap': '2100\n2100\n41F0\nFA10\n8C10\n8810\n8910\nF890\n8890\n8810\n8810\n8810\nF810\n8860', 'outputW': 14, 'outputH': 15, 'shadowedOutputW': 15, 'shadowedOutputH': 16, 'glowedOutputW': 16, 'glowedOutputH': 17}
```

Get binary representation of bitmap of the character "￣"

```python
print(bpo.getCharBmpByUnicode(65507))
```

Get binary representation of bitmap of the character "©" -- "©" does not exist in some font, and does not exist in GBK, therefore it throws an error:

```python
print(bpo.getCharBmpByUnicode(169))
```

## Projects that use this library

[FNT Generator](https://github.com/might-and-magic/fnt-generator): Might and Magic 6 7 8 and Heroes 3 font File Generator in Python. Another project of mine