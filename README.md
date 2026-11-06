# pyaamva

A dependency-free Python library for parsing the decoded text or bytes from the PDF417 barcode on an AAMVA driver license or identification card. It does not read barcode images or verify that a credential is genuine.

## Installation

```powershell
python -m pip install .
```

## Usage

```python
from pyaamva import parse, ParseError

# payload is the complete output from your PDF417 reader, including control bytes.
try:
    license = parse(payload)  # bytes preferred; str also accepted
except ParseError as exc:
    print(f"Invalid or unsupported payload: {exc}")
else:
    print(license.header.issuer_id)       # six-character string, including zeros
    print(license.get("DAQ"))             # customer ID, or None
    print(license.as_dict().get("family_name"))
    print(license.get_date("DBB", country="USA"))  # datetime.date or None
    for subfile in license.subfiles:
        for element in subfile.elements:
            print(element.code, element.name, element.value)
```

The input must contain the complete `@\n\x1e\rANSI ` header, directory, and subfiles, with control characters intact. The parser uses the directory's byte offsets and lengths; pass bytes when possible. Text is encoded as ASCII by default; use `encoding=` if your reader supplies data in another known encoding. It retains field values exactly, including padding and values such as `NONE`, and does not split names or infer missing data. `get()` returns the first matching field from the first DL, ID, or EN subfile; `Subfile.get_all()` retains duplicates. `as_dict()` maps recognized fields to descriptive keys and uses the first occurrence; all fields, including unknown codes, remain accessible through `elements`. Jurisdiction-specific `Z*` subfiles are parsed into elements; other unknown subfile types are retained as raw bytes.

`get_date()` requires an explicit `country="USA"` or `"CAN"`, uses the corresponding modern AAMVA eight-digit date format, and raises `ValueError` for invalid values. Older versions and jurisdiction-specific conventions may differ; use raw fields when the format is uncertain.

This parser targets the ANSI Annex D directory-based format. It does not support every historical or alternative encoding (including the 2025 standard's Annex I), repair damaged scanner output, validate required fields or field contents, or establish compliance or identity. Parsing untrusted data successfully is not proof of authenticity. Driver license data is sensitive; avoid logging or retaining it unnecessarily.

Format reference: [AAMVA 2025 DL/ID Card Design Standard, Annex D](https://www.aamva.org/getmedia/81af105d-8b1b-45e1-aa46-f1800a259ed1/AAMVADLIDCardDesignStandard2025.pdf).

Run tests with `python -m unittest discover -s tests`.
