# Tests

**unifont-13.0.04-for-test.bdf** is a reduced and altered version of **unifont-13.0.04.bdf**, the test font file:

* only includes U+0000 - U+024F (Latin), U+0600 - U+06FF (Arabic), and U+7684 (30340, Chinese character "的").
* `CHARS 57086` is changed to `CHARS 849` because the actual glyph count is changed from 57086 to 849
* the glyphs are in the codepoint order, except:
  * U+0001 (1) is before U+0000 (0, originally the first one)
  * U+06FF (1791, "ۿ", originally the last one in the Arabic range) is before U+06FE (1790, "۾")
  * U+7684 (30340, Chinese character "的") is inserted before U+06FF (1791)
