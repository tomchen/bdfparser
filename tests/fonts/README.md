# Tests

**unifont-13.0.04-for-test.bdf** is a reduced and altered version of **unifont-13.0.04.bdf**, the test font file:

* only includes U+0000 - U+024F (Latin), U+0600 - U+06FF (Arabic), and U+7684 (30340, Chinese character "的").
* `CHARS 57086` is changed to `CHARS 849` because the actual glyph count is changed from 57086 to 849
* the glyphs are in the codepoint order, except:
  * U+0001 (1) is before U+0000 (0, originally the first one)
  * U+06FF (1791, "ۿ", originally the last one in the Arabic range) is before U+06FE (1790, "۾")
  * U+7684 (30340, Chinese character "的") is inserted before U+06FF (1791)

**unifont-reduced.bdf** is a reduced version of **unifont-13.0.04.bdf** (GNU Unifont v13.0.04 released on 2020-11-21). **unifont-reduced.bdf** includes 5441 glyphs in total:

* U+0000-U+13FF
* U+3040-U+309F (Hiragana), U+30A0-U+30FF (Katakana)
* The most commonly used Simplified and Traditional Chinese characters which are 的, 一, 是, 不, 了, 人, 我, 在, 有, 他, 这, 为, 之, 大, 来, 以, 个, 中, 上, 们, 到, 说, 国, 和, 地, 也, 子, 时, 道, 出, 而, 要, 于, 就, 下, 得, 可, 你, 年, 生, 自, 会, 那, 后, 能, 对, 着, 事, 其, 里, 所, 去, 行, 过, 家, 十, 用, 发, 天, 如, 然, 作, 方, 成, 者, 多, 日, 都, 三, 小, 军, 二, 无, 同, 么, 经, 法, 当, 起, 与, 好, 看, 学, 进, 种, 将, 还, 分, 此, 心, 前, 面, 又, 定, 见, 只, 主, 没, 公, 从, 這, 爲, 來, 個, 們, 說, 國, 時, 於, 會, 後, 對, 裏, 過, 發, 軍, 無, 麼, 經, 當, 與, 學, 進, 種, 將, 還, 見, 沒, 從
