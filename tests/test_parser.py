import unittest
from datetime import date
from pyaamva import parse, ParseError


def payload(*subfiles):
    offset = 21 + 10 * len(subfiles)
    directory = b""
    for sub in subfiles:
        directory += sub[:2] + f"{offset:04d}{len(sub):04d}".encode()
        offset += len(sub)
    return b"@\n\x1e\rANSI 6360001100" + f"{len(subfiles):02d}".encode() + directory + b"".join(subfiles)


class ParserTests(unittest.TestCase):
    def test_credential_and_jurisdiction(self):
        data = payload(b"DLDAQ123\nDCSSAMPLE\nDACJANE\nDBB01022000\nDAK12345  \nXYZunknown\nDAQ456\r", b"ZVZVA01\r")
        result = parse(data)
        self.assertEqual(result.header.issuer_id, "636000")
        self.assertEqual(result.header.aamva_version, 11)
        self.assertEqual(result.get("DAQ"), "123")
        self.assertEqual(result.credential.get_all("DAQ"), ("123", "456"))
        self.assertEqual(result.as_dict()["family_name"], "SAMPLE")
        self.assertEqual(result.get("DAK"), "12345  ")
        self.assertEqual(result.credential.get("XYZ"), "unknown")
        self.assertEqual(result.subfiles[1].get("ZVA"), "01")
        self.assertEqual(result.get_date("DBB", country="USA"), date(2000, 1, 2))
        self.assertEqual(parse(data.decode()).get("DAC"), "JANE")

    def test_canadian_date_and_invalid_date(self):
        result = parse(payload(b"IDDBB20000102\nDBA00000000\r"))
        self.assertEqual(result.get_date("DBB", country="CAN"), date(2000, 1, 2))
        self.assertIsNone(result.get_date("DBD", country="CAN"))
        with self.assertRaises(ValueError): result.get_date("DBA", country="CAN")
        with self.assertRaises(ValueError): result.get_date("DBB", country="XX")

    def test_byte_offsets_with_multibyte_values(self):
        raw = payload("DLDCSÉLAN\r".encode("utf-8"), b"ZVZVA1\r")
        result = parse(raw, encoding="utf-8")
        self.assertEqual(result.get("DCS"), "ÉLAN")
        self.assertEqual(result.subfiles[1].get("ZVA"), "1")
        self.assertEqual(parse(raw.decode("utf-8"), encoding="utf-8").get("DCS"), "ÉLAN")

    def test_opaque_subfile(self):
        result = parse(payload(b"DLDAQ1\r", b"XY\x00\xff"))
        self.assertEqual(result.subfiles[1].raw, b"XY\x00\xff")
        self.assertEqual(result.subfiles[1].elements, ())

    def test_malformed(self):
        good = payload(b"DLDAQ1\r")
        for bad in (b"", good[1:], good[:21], good[:23] + b"9999" + good[27:], good[:-1], good[:31] + b"ID" + good[33:], payload(b"DL12xvalue\r")):
            with self.subTest(bad=bad), self.assertRaises(ParseError): parse(bad)
        with self.assertRaises(TypeError): parse(None)

    def test_overlap(self):
        good = payload(b"DLDAQ1\r", b"ZVZVA1\r")
        bad = good[:33] + good[23:27] + good[37:]
        with self.assertRaises(ParseError): parse(bad)

if __name__ == "__main__": unittest.main()
