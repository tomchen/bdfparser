# Test fonts

**unifont-13.0.04.bdf** is GNU Unifont v13.0.04 (released on 2020-11-21), written by FontForge. The BDF writer must reproduce it byte for byte (`tests/test_bdf_write.py`).

**HanWangYanKai-26.bdf** is a FontForge-written CJK font (14160 glyphs, 190 of them unencoded, `ENCODING -1`). The BDF writer must also reproduce it byte for byte.

**unifont-13.0.04-for-test.bdf** is a reduced and altered version of **unifont-13.0.04.bdf**, the main test font file:

- only includes U+0000 - U+024F (Latin), U+0600 - U+06FF (Arabic), and U+7684 (30340, Chinese character "的").
- `CHARS 57086` is changed to `CHARS 849` because the actual glyph count is changed from 57086 to 849
- the glyphs are in the codepoint order, except:
  - U+0001 (1) is before U+0000 (0, originally the first one)
  - U+06FF (1791, "ۿ", originally the last one in the Arabic range) is before U+06FE (1790, "۾")
  - U+7684 (30340, Chinese character "的") is inserted before U+06FF (1791)
- in this Python repository the file also intentionally contains leading whitespace on some lines and blank lines (before and after `STARTFONT`, inside the properties, around `CHARS`, after the last `ENDCHAR`, and around `ENDFONT`), to test the parser's whitespace handling. Apart from that it is identical to the file of the same name in the TypeScript repository.

**unifont-13.0.04-for-test-emptylines.bdf** is an altered version of **unifont-13.0.04-for-test.bdf** with only 3 glyphs (U+0001, U+0000, U+06FE), with empty lines, whitespace, and illegal lines (single stray tokens such as `v`, `s`, `d`, `c` in the header, after `ENDPROPERTIES` and between glyphs); its CHARSET_REGISTRY is "ISO8859" and CHARSET_ENCODING is "1".

**unifont-13.0.04-2atest.bdf** contains only two glyphs, U+0002 (a control character) and U+FFFC; it is used by the SVG font tests (the expected outputs are shared with the TypeScript repository).

**unifont-13.0.04-reduced.bdf** is a reduced version of **unifont-13.0.04.bdf**. **unifont-13.0.04-reduced.bdf** includes 5441 glyphs in total:

- U+0000-U+13FF
- U+3040-U+309F (Hiragana), U+30A0-U+30FF (Katakana)
- The most commonly used Simplified and Traditional Chinese characters which are 的, 一, 是, 不, 了, 人, 我, 在, 有, 他, 这, 为, 之, 大, 来, 以, 个, 中, 上, 们, 到, 说, 国, 和, 地, 也, 子, 时, 道, 出, 而, 要, 于, 就, 下, 得, 可, 你, 年, 生, 自, 会, 那, 后, 能, 对, 着, 事, 其, 里, 所, 去, 行, 过, 家, 十, 用, 发, 天, 如, 然, 作, 方, 成, 者, 多, 日, 都, 三, 小, 军, 二, 无, 同, 么, 经, 法, 当, 起, 与, 好, 看, 学, 进, 种, 将, 还, 分, 此, 心, 前, 面, 又, 定, 见, 只, 主, 没, 公, 从, 這, 爲, 來, 個, 們, 說, 國, 時, 於, 會, 後, 對, 裏, 過, 發, 軍, 無, 麼, 經, 當, 與, 學, 進, 種, 將, 還, 見, 沒, 從

**unifont-13.0.04-enctest-???.bdf** are font files for the charset (encoding) tests. Each contains "A", "人" and "光" (only "A" and one letter for the Windows code page fonts) encoded in the charset named by the file name and declared by `CHARSET_REGISTRY` / `CHARSET_ENCODING`. **unifont-13.0.04-enctest-iso2022cn.bdf** declares `GB2312.1980` but stores its codes in GL form (both bytes 0x21-0x7E, i.e. EUC-CN minus 0x8080), which the library detects.

**spec_example_bad.bdf** is the example from BDF spec 2.2, it has an issue (the `quoteright` glyph has 5 bitmap rows while its BBX height is 6) that is fixed in **spec_example_fixed.bdf**. Both contain non-Adobe property names in mixed case (`MinSpace`, `Copyright`) and an unquoted `COMMENT`.

**golden/** contains reference PCF files generated with `bdftopcf` (see `SHA256SUMS`), used by the PCF writer tests when the `bdftopcf` binary is not available.
