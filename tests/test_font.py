import unittest

from bdfparser import Font


class TestFont(unittest.TestCase):

    def test_font(self):
        self.assertIsInstance(Font('tests/fonts/unifont-13.0.04-for-test.bdf'), Font)
    
if __name__ == '__main__':
    unittest.main()
