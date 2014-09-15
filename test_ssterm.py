import ssterm
import os
import unittest

class TestInputProcessors(unittest.TestCase):
    def test_processor_newline(self):
        f = ssterm.input_processor_newline("abc")

        self.assertEqual(f(""), "")
        self.assertEqual(f(os.linesep), "abc")
        self.assertEqual(f("foo" + os.linesep + "bar"), "fooabcbar")

    def test_processor_hexadecimal(self):
        f = ssterm.input_processor_hexadecimal()

        self.assertEqual(f(""), "")
        self.assertEqual(f("q"), "")
        self.assertEqual(f("aa,bb,cc"), "\xaa\xbb\xcc")
        self.assertEqual(f("aa bb cc"), "\xaa\xbb\xcc")
        self.assertEqual(f("0xaa,0xbb,0xcc"), "\xaa\xbb\xcc")
        self.assertEqual(f("0xaa,foo,0xbb,0xcc"), "\xaa\xbb\xcc")
        self.assertEqual(f("0xaa,foo,0xbb,gar,0xcc"), "\xaa\xbb\xcc")
        self.assertEqual(f("axb"), "")
        self.assertEqual(f("a"), "\xba")
        self.assertEqual(f("012"), "\x01")
        self.assertEqual(f(" "), "")
        self.assertEqual(f("45"), "\x45")

class TestOutputProcessors(unittest.TestCase):
    def test_processor_newline(self):
        f = ssterm.output_processor_newline("ab")

        self.assertEqual(f(""), "")
        self.assertEqual(f("ab"), os.linesep)
        self.assertEqual(f("helloabworld"), "hello" + os.linesep + "world")
        self.assertEqual(f("abababa"), os.linesep + os.linesep + os.linesep)
        self.assertEqual(f("f"), "af")
        self.assertEqual(f("fooa"), "foo")
        self.assertEqual(f("bar"), os.linesep + "ar")
        self.assertEqual(f("a"), "")
        self.assertEqual(f(""), "")
        self.assertEqual(f(""), "")
        self.assertEqual(f("b"), os.linesep)
        self.assertEqual(f("a"), "")
        self.assertEqual(f(""), "")
        self.assertEqual(f(""), "")
        self.assertEqual(f("r"), "ar")

    def test_processor_raw(self):
        f = ssterm.output_processor_raw()

        self.assertEqual(f(""), "")
        self.assertEqual(f("hello world"), "hello world")
        self.assertEqual(f("hello" + os.linesep + "world"), "hello" + os.linesep + "world")

        f = ssterm.output_processor_raw([ord('A'), ord('B')])

        self.assertEqual(f(""), "")
        self.assertEqual(f("hello world"), "hello world")
        self.assertEqual(f("hello" + os.linesep + "world"), "hello" + os.linesep + "world")
        self.assertEqual(f("helABlo"), "hel" + ssterm.Color_Codes[0] + "A" + ssterm.Color_Code_Reset + ssterm.Color_Codes[1] + "B" + ssterm.Color_Code_Reset + "lo")

    def test_processor_hexadecimal(self):
        f = ssterm.output_processor_hexadecimal()

        self.assertEqual(f(""), "")
        self.assertEqual(f("\xaa\xbb\xcc\xdd"), "aa bb cc dd ")
        self.assertEqual(f("\xee\xff\x00\x11"), "ee ff 00 11  ")
        self.assertEqual(f("\xaa\xbb\xcc\xdd"), "aa bb cc dd ")
        self.assertEqual(f("\xee\xff\x00\x11"), "ee ff 00 11" + os.linesep)
        self.assertEqual(f("\x0a\x0a\x0a\x0a"), "0a 0a 0a 0a ")

        if len(os.linesep) == 1:
            f = ssterm.output_processor_hexadecimal(interpret_newlines=True)

            self.assertEqual(f(""), "")
            self.assertEqual(f("\xaa" + os.linesep + "\xbb"), "aa " + ("%02x " % ord(os.linesep)) + os.linesep + "bb ")

        f = ssterm.output_processor_hexadecimal([ord('A'), ord('B')])

        self.assertEqual(f(""), "")
        self.assertEqual(f("\xaa\xbb\xcc\xdd"), "aa bb cc dd ")
        self.assertEqual(f("AB\xee\xff"), ssterm.Color_Codes[0] + "41" + ssterm.Color_Code_Reset + " " + ssterm.Color_Codes[1] + "42" + ssterm.Color_Code_Reset + " ee ff  ")
        self.assertEqual(f("\xee\xff\x00\x11\xee\xff\x00\x11"), "ee ff 00 11 ee ff 00 11" + os.linesep)

    def test_processor_split(self):
        f = ssterm.output_processor_split(partial_lines=True)

        self.assertEqual(f(""), "")
        self.assertEqual(f("ABCD"), "\r41 42 43 44                                       |ABCD            |")
        self.assertEqual(f("EFGH"), "\r41 42 43 44 45 46 47 48                           |ABCDEFGH        |")
        self.assertEqual(f(""), "")
        self.assertEqual(f("IJKL"), "\r41 42 43 44 45 46 47 48  49 4a 4b 4c              |ABCDEFGHIJKL    |")
        self.assertEqual(f("MNOP"), "\r41 42 43 44 45 46 47 48  49 4a 4b 4c 4d 4e 4f 50  |ABCDEFGHIJKLMNOP|" + os.linesep)
        self.assertEqual(f("ABCD"), "\r41 42 43 44                                       |ABCD            |")

        f = ssterm.output_processor_split(partial_lines=False)

        self.assertEqual(f(""), "")
        self.assertEqual(f("ABCD"), "")
        self.assertEqual(f("EFGH"), "")
        self.assertEqual(f(""), "")
        self.assertEqual(f("IJKL"), "")
        self.assertEqual(f("MNOP"), "41 42 43 44 45 46 47 48  49 4a 4b 4c 4d 4e 4f 50  |ABCDEFGHIJKLMNOP|" + os.linesep)

        f = ssterm.output_processor_split([ord('A'), ord('B')], True)

        self.assertEqual(f(""), "")
        self.assertEqual(f("0ABC"), "\r30 " + ssterm.Color_Codes[0] + "41" + ssterm.Color_Code_Reset + " " + ssterm.Color_Codes[1] + "42" + ssterm.Color_Code_Reset + " 43                                       |0" + ssterm.Color_Codes[0] + "A" + ssterm.Color_Code_Reset + ssterm.Color_Codes[1] + "B" + ssterm.Color_Code_Reset + "C" + "            |")


if __name__ == '__main__':
    unittest.main()

