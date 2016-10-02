import os
import unittest
import ssterm

class TestInputProcessors(unittest.TestCase):
    def test_processor_newline(self):
        f = ssterm.input_processor_newline(b"abc")

        self.assertEqual(f(b""), b"")
        self.assertEqual(f(os.linesep.encode()), b"abc")
        self.assertEqual(f(b"foo" + os.linesep.encode() + b"bar"), b"fooabcbar")

    def test_processor_hexadecimal(self):
        f = ssterm.input_processor_hexadecimal()

        self.assertEqual(f(b""), b"")
        self.assertEqual(f(b"q"), b"")
        self.assertEqual(f(b"aa,bb,cc"), b"\xaa\xbb\xcc")
        self.assertEqual(f(b"aa bb cc"), b"\xaa\xbb\xcc")
        self.assertEqual(f(b"0xaa,0xbb,0xcc"), b"\xaa\xbb\xcc")
        self.assertEqual(f(b"0xaa,foo,0xbb,0xcc"), b"\xaa\xbb\xcc")
        self.assertEqual(f(b"0xaa,foo,0xbb,gar,0xcc"), b"\xaa\xbb\xcc")
        self.assertEqual(f(b"axb"), b"")
        self.assertEqual(f(b"a"), b"\xba")
        self.assertEqual(f(b"012"), b"\x01")
        self.assertEqual(f(b" "), b"")
        self.assertEqual(f(b"45"), b"\x45")

class TestOutputProcessors(unittest.TestCase):
    def test_processor_newline(self):
        f = ssterm.output_processor_newline(b"ab")

        self.assertEqual(f(b""), b"")
        self.assertEqual(f(b"ab"), os.linesep.encode())
        self.assertEqual(f(b"helloabworld"), b"hello" + os.linesep.encode() + b"world")
        self.assertEqual(f(b"abababa"), os.linesep.encode() + os.linesep.encode() + os.linesep.encode())
        self.assertEqual(f(b"f"), b"af")
        self.assertEqual(f(b"fooa"), b"foo")
        self.assertEqual(f(b"bar"), os.linesep.encode() + b"ar")
        self.assertEqual(f(b"a"), b"")
        self.assertEqual(f(b""), b"")
        self.assertEqual(f(b""), b"")
        self.assertEqual(f(b"b"), os.linesep.encode())
        self.assertEqual(f(b"a"), b"")
        self.assertEqual(f(b""), b"")
        self.assertEqual(f(b""), b"")
        self.assertEqual(f(b"r"), b"ar")

    def test_processor_raw(self):
        f = ssterm.output_processor_raw()

        self.assertEqual(f(b""), b"")
        self.assertEqual(f(b"hello world"), b"hello world")
        self.assertEqual(f(b"hello" + os.linesep.encode() + b"world"), b"hello" + os.linesep.encode() + b"world")

        f = ssterm.output_processor_raw(b"AB")

        self.assertEqual(f(b""), b"")
        self.assertEqual(f(b"hello world"), b"hello world")
        self.assertEqual(f(b"hello" + os.linesep.encode() + b"world"), b"hello" + os.linesep.encode() + b"world")
        self.assertEqual(f(b"helABlo"), b"hel" + ssterm.Color_Codes[0] + b"A" + ssterm.Color_Code_Reset + ssterm.Color_Codes[1] + b"B" + ssterm.Color_Code_Reset + b"lo")

    def test_processor_hexadecimal(self):
        f = ssterm.output_processor_hexadecimal()

        self.assertEqual(f(b""), b"")
        self.assertEqual(f(b"\xaa\xbb\xcc\xdd"), b"aa bb cc dd ")
        self.assertEqual(f(b"\xee\xff\x00\x11"), b"ee ff 00 11  ")
        self.assertEqual(f(b"\xaa\xbb\xcc\xdd"), b"aa bb cc dd ")
        self.assertEqual(f(b"\xee\xff\x00\x11"), b"ee ff 00 11" + os.linesep.encode())
        self.assertEqual(f(b"\x0a\x0a\x0a\x0a"), b"0a 0a 0a 0a ")

        if len(os.linesep.encode()) == 1:
            f = ssterm.output_processor_hexadecimal(interpret_newlines=True)

            self.assertEqual(f(b""), b"")
            self.assertEqual(f(b"\xaa" + os.linesep.encode() + b"\xbb"), b"aa " + ("%02x " % ord(os.linesep.encode())).encode() + os.linesep.encode() + b"bb ")

        f = ssterm.output_processor_hexadecimal(b"AB")

        self.assertEqual(f(b""), b"")
        self.assertEqual(f(b"\xaa\xbb\xcc\xdd"), b"aa bb cc dd ")
        self.assertEqual(f(b"AB\xee\xff"), ssterm.Color_Codes[0] + b"41" + ssterm.Color_Code_Reset + b" " + ssterm.Color_Codes[1] + b"42" + ssterm.Color_Code_Reset + b" ee ff  ")
        self.assertEqual(f(b"\xee\xff\x00\x11\xee\xff\x00\x11"), b"ee ff 00 11 ee ff 00 11" + os.linesep.encode())

    def test_processor_split(self):
        f = ssterm.output_processor_split(partial_lines=True)

        self.assertEqual(f(b""), b"")
        self.assertEqual(f(b"ABCD"), b"\r41 42 43 44                                       |ABCD            |")
        self.assertEqual(f(b"EFGH"), b"\r41 42 43 44 45 46 47 48                           |ABCDEFGH        |")
        self.assertEqual(f(b""), b"")
        self.assertEqual(f(b"IJKL"), b"\r41 42 43 44 45 46 47 48  49 4a 4b 4c              |ABCDEFGHIJKL    |")
        self.assertEqual(f(b"MNOP"), b"\r41 42 43 44 45 46 47 48  49 4a 4b 4c 4d 4e 4f 50  |ABCDEFGHIJKLMNOP|" + os.linesep.encode())
        self.assertEqual(f(b"ABCD"), b"\r41 42 43 44                                       |ABCD            |")

        f = ssterm.output_processor_split(partial_lines=False)

        self.assertEqual(f(b""), b"")
        self.assertEqual(f(b"ABCD"), b"")
        self.assertEqual(f(b"EFGH"), b"")
        self.assertEqual(f(b""), b"")
        self.assertEqual(f(b"IJKL"), b"")
        self.assertEqual(f(b"MNOP"), b"41 42 43 44 45 46 47 48  49 4a 4b 4c 4d 4e 4f 50  |ABCDEFGHIJKLMNOP|" + os.linesep.encode())

        f = ssterm.output_processor_split(b"AB", True)

        self.assertEqual(f(b""), b"")
        self.assertEqual(f(b"0ABC"), b"\r30 " + ssterm.Color_Codes[0] + b"41" + ssterm.Color_Code_Reset + b" " + ssterm.Color_Codes[1] + b"42" + ssterm.Color_Code_Reset + b" 43                                       |0" + ssterm.Color_Codes[0] + b"A" + ssterm.Color_Code_Reset + ssterm.Color_Codes[1] + b"B" + ssterm.Color_Code_Reset + b"C" + b"            |")


if __name__ == '__main__':
    unittest.main()
