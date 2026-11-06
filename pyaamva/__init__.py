"""Parse the decoded contents of AAMVA DL/ID PDF417 barcodes.

This module does not scan images or authenticate credentials.
"""
from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, Optional, Tuple, Union
import re

__all__ = ["ParseError", "Element", "Header", "Subfile", "License", "parse", "FIELD_NAMES"]

FIELD_NAMES = {
    "DAQ": "customer_id", "DCS": "family_name", "DAC": "given_names",
    "DAD": "middle_names", "DCU": "name_suffix", "DAA": "full_name",
    "DBA": "expiration_date", "DBB": "date_of_birth", "DBD": "issue_date",
    "DBC": "sex", "DAU": "height", "DAY": "eye_color", "DAZ": "hair_color",
    "DAG": "street_address", "DAH": "street_address_2", "DAI": "city",
    "DAJ": "jurisdiction", "DAK": "postal_code", "DCG": "country",
    "DCF": "document_discriminator", "DCK": "inventory_control_number",
    "DCA": "vehicle_class", "DCB": "restriction_codes", "DCD": "endorsement_codes",
    "DDE": "family_name_truncation", "DDF": "given_names_truncation",
    "DDG": "middle_names_truncation", "DDA": "compliance_type",
    "DDB": "card_revision_date", "DDC": "hazmat_endorsement_expiration_date",
    "DDH": "under_18_until", "DDI": "under_19_until", "DDJ": "under_21_until",
    "DAW": "weight_pounds", "DAX": "weight_kilograms", "DCI": "place_of_birth",
    "DCJ": "audit_information", "DCE": "weight_range", "DDK": "organ_donor_indicator",
    "DDL": "veteran_indicator",
}

class ParseError(ValueError):
    """The input is not a supported or structurally valid AAMVA payload."""

@dataclass(frozen=True)
class Header:
    issuer_id: str
    aamva_version: int
    jurisdiction_version: int
    number_of_entries: int

@dataclass(frozen=True)
class Element:
    code: str
    value: str

    @property
    def name(self) -> Optional[str]:
        return FIELD_NAMES.get(self.code)

@dataclass(frozen=True)
class Subfile:
    type: str
    offset: int
    length: int
    raw: bytes
    elements: Tuple[Element, ...]

    def get_all(self, code: str) -> Tuple[str, ...]:
        return tuple(element.value for element in self.elements if element.code == code)

    def get(self, code: str, default: Optional[str] = None) -> Optional[str]:
        values = self.get_all(code)
        return values[0] if values else default

@dataclass(frozen=True)
class License:
    header: Header
    subfiles: Tuple[Subfile, ...]

    @property
    def credential(self) -> Optional[Subfile]:
        return next((s for s in self.subfiles if s.type in ("DL", "ID", "EN")), None)

    def get(self, code: str, default: Optional[str] = None) -> Optional[str]:
        """Get the first field in the credential subfile, preserving its original value."""
        subfile = self.credential
        return subfile.get(code, default) if subfile else default

    def as_dict(self) -> Dict[str, str]:
        """Return known credential fields under descriptive names; first occurrence wins."""
        result: Dict[str, str] = {}
        if self.credential:
            for element in self.credential.elements:
                if element.name is not None:
                    result.setdefault(element.name, element.value)
        return result

    def get_date(self, code: str, *, country: str) -> Optional[date]:
        """Parse an eight-digit date using USA (MMDDYYYY) or CAN (YYYYMMDD).

        Raises ValueError for an invalid date or unsupported country. No country is inferred.
        """
        if country not in ("USA", "CAN"):
            raise ValueError("country must be 'USA' or 'CAN'")
        value = self.get(code)
        if value is None:
            return None
        if not re.fullmatch(r"[0-9]{8}", value):
            raise ValueError("date must contain exactly eight digits")
        return datetime.strptime(value, "%m%d%Y" if country == "USA" else "%Y%m%d").date()

def parse(data: Union[str, bytes], *, encoding: str = "ascii") -> License:
    """Parse a complete Annex D payload, preserving duplicate and unknown fields.

    Offsets and lengths are byte positions, so bytes are preferred. Strings are
    encoded with *encoding* before parsing. Malformed structure raises ParseError.
    """
    if isinstance(data, str):
        try:
            data = data.encode(encoding)
        except (UnicodeError, LookupError) as exc:
            raise ParseError("input cannot be encoded with the specified encoding") from exc
    elif not isinstance(data, bytes):
        raise TypeError("data must be str or bytes")
    if len(data) < 21 or data[:4] != b"@\n\x1e\r" or data[4:9] != b"ANSI ":
        raise ParseError("expected an AAMVA ANSI header with control characters")
    fixed = data[9:21]
    if not re.fullmatch(rb"[0-9]{12}", fixed):
        raise ParseError("invalid numeric header fields")
    count = int(fixed[10:12])
    header = Header(fixed[:6].decode("ascii"), int(fixed[6:8]), int(fixed[8:10]), count)
    directory_end = 21 + 10 * count
    if not count or directory_end > len(data):
        raise ParseError("missing or truncated subfile directory")
    entries = []
    for i in range(count):
        entry = data[21 + 10*i:31 + 10*i]
        if not re.fullmatch(rb"[A-Z]{2}[0-9]{8}", entry):
            raise ParseError("invalid subfile designator")
        kind = entry[:2].decode("ascii")
        offset, length = int(entry[2:6]), int(entry[6:10])
        if offset < directory_end or length < 2 or offset + length > len(data):
            raise ParseError("subfile range is outside the payload")
        if any(offset < end and start < offset + length for start, end in entries):
            raise ParseError("overlapping subfile ranges")
        entries.append((offset, offset + length))
        raw = data[offset:offset + length]
        if raw[:2] != entry[:2]:
            raise ParseError("subfile type does not match its designator")
        elements = []
        # Annex D credential and jurisdiction subfiles contain LF-separated elements.
        if kind in ("DL", "ID", "EN") or kind.startswith("Z"):
            body = raw[2:]
            if body.endswith(b"\r"):
                body = body[:-1]
            for item in body.split(b"\n"):
                if not item:
                    continue
                if len(item) < 3 or not re.fullmatch(rb"[A-Z]{3}", item[:3]):
                    raise ParseError("invalid data element identifier")
                try:
                    value = item[3:].decode(encoding)
                except (UnicodeError, LookupError) as exc:
                    raise ParseError("data element cannot be decoded with the specified encoding") from exc
                elements.append(Element(item[:3].decode("ascii"), value))
        # Unknown subfiles may use other structures; retain their bytes unchanged.
        entries_subfile = Subfile(kind, offset, length, raw, tuple(elements))
        if i == 0:
            subfiles = []
        subfiles.append(entries_subfile)
    return License(header, tuple(subfiles))
