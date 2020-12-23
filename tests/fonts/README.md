**unifont-13.0.04-for-test.bdf** is a reduced and altered version of **unifont-13.0.04.bdf**, the test font file:

* only includes U+0000 - U+024F (Latin) and U+0600 - U+06FF (Arabic).
* `CHARS 57086` is changed to `CHARS 848` because the actual glyph count is changed from 57086 to 848
* the glyphs are in the codepoint order, except:
  * U+0001 (1) is before U+0000 (0, originally the first one)
  * U+06FF (1791, originally the last one) is before U+06FE (1790)
