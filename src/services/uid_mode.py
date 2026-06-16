"""
UID-mode configuration for NXP JavaCard implants (JTaxCore / J3Rxxx).

These cards expose five proprietary config bytes via GlobalPlatform
GET DATA / STORE DATA on tag DF2B:

    10A1  ATQA byte 1
    10A2  ATQA byte 2
    10A3  SAK
    10A4  Cascade SAK
    10A5  UID mode  (0x00 randomize, 0x04 7-byte, 0x08 4-byte NUID)

This module holds the *pure* logic (no card I/O): building the GET/SET
APDUs, parsing the gp.jar `-d` APDU trace, detecting which named mode a
card is currently in, and the Randomize "preserve MFC bit" rule.

Command formats (from NXP_j3r_config_notes.txt):
    GET:  80CA00FE 06 DF2B 02 <tag> 00
    SET:  80E28800 07 DF2B 04 <tag> 01 <value>
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# --- Config tags -----------------------------------------------------------

TAG_ATQA1 = "10A1"
TAG_ATQA2 = "10A2"
TAG_SAK = "10A3"
TAG_CASCADE_SAK = "10A4"
TAG_UID = "10A5"

# Order used for reading and for display rows.
TAG_ORDER: List[str] = [TAG_ATQA1, TAG_ATQA2, TAG_SAK, TAG_CASCADE_SAK, TAG_UID]

TAG_LABELS: Dict[str, str] = {
    TAG_ATQA1: "ATQA byte 1",
    TAG_ATQA2: "ATQA byte 2",
    TAG_SAK: "SAK",
    TAG_CASCADE_SAK: "Cascade SAK",
    TAG_UID: "UID",
}

# Bit in the SAK (10A3) that indicates MIFARE Classic support.
# Basic SAK is 0x20, MFC SAK is 0x28 -> the difference is this bit.
MFC_SAK_BIT = 0x08

# UID-mode values for tag 10A5.
UID_RANDOMIZE = 0x00
UID_7BYTE = 0x04
UID_4BYTE = 0x08

# --- Named modes -----------------------------------------------------------

MODE_7BYTE_BASIC = "7byte_basic"
MODE_7BYTE_MFC = "7byte_mfc"
MODE_4BYTE_MFC = "4byte_mfc"
MODE_RANDOMIZE = "randomize"


@dataclass(frozen=True)
class UidMode:
    """A selectable UID mode.

    ``target`` is the full 5-tag config for fixed modes (used both for
    writing and for exact-match detection), or ``None`` for Randomize,
    which is computed dynamically from the card's current config.
    """

    key: str
    label: str
    target: Optional[Dict[str, int]]


# Values are the authoritative ones from the -s commands in the notes
# (10A4 = 0x24 for 7-byte modes, 0x2B for 4-byte; 4-byte UID writes 0x08).
MODES: List[UidMode] = [
    UidMode(MODE_7BYTE_BASIC, "7-byte Basic", {
        TAG_ATQA1: 0x00, TAG_ATQA2: 0x48, TAG_SAK: 0x20,
        TAG_CASCADE_SAK: 0x24, TAG_UID: UID_7BYTE,
    }),
    UidMode(MODE_7BYTE_MFC, "7-byte + MFC", {
        TAG_ATQA1: 0x00, TAG_ATQA2: 0x48, TAG_SAK: 0x28,
        TAG_CASCADE_SAK: 0x24, TAG_UID: UID_7BYTE,
    }),
    UidMode(MODE_4BYTE_MFC, "4-byte + MFC", {
        TAG_ATQA1: 0x00, TAG_ATQA2: 0x08, TAG_SAK: 0x28,
        TAG_CASCADE_SAK: 0x2B, TAG_UID: UID_4BYTE,
    }),
    UidMode(MODE_RANDOMIZE, "Randomize UID", None),
]

MODES_BY_KEY: Dict[str, UidMode] = {m.key: m for m in MODES}

# Order the notes write tags in: UID first, then SAK/cascade, then ATQA.
_WRITE_ORDER: List[str] = [TAG_UID, TAG_SAK, TAG_CASCADE_SAK, TAG_ATQA1, TAG_ATQA2]


# --- APDU construction -----------------------------------------------------

def build_get_apdu(tag: str) -> str:
    """GET DATA APDU (hex) that reads one config tag."""
    return "80CA00FE06DF2B02" + tag.upper() + "00"


def get_config_apdus() -> List[str]:
    """The five GET APDUs in :data:`TAG_ORDER` order."""
    return [build_get_apdu(t) for t in TAG_ORDER]


def build_set_apdu(tag: str, value: int) -> str:
    """STORE DATA APDU (hex) that sets one config tag to a single byte."""
    return "80E2880007DF2B04" + tag.upper() + "01" + f"{value & 0xFF:02X}"


def set_commands_for_mode(
    mode_key: str, current_config: Dict[str, int]
) -> List[Tuple[str, int]]:
    """The (tag, value) writes needed to put the card into ``mode_key``.

    Fixed modes write all five tags so the result is deterministic
    regardless of the starting state. Randomize sets the UID byte to
    0x00 and, if MFC is currently enabled, re-asserts the MFC SAK pair so
    the MFC bit is preserved.
    """
    mode = MODES_BY_KEY[mode_key]

    if mode.target is not None:
        return [(tag, mode.target[tag]) for tag in _WRITE_ORDER]

    # Randomize: preserve the MFC bit if it is currently set.
    commands: List[Tuple[str, int]] = [(TAG_UID, UID_RANDOMIZE)]
    if mfc_enabled(current_config):
        commands.append((TAG_SAK, 0x28))
        commands.append((TAG_CASCADE_SAK, 0x2B))
    return commands


def set_apdus_for_mode(
    mode_key: str, current_config: Dict[str, int]
) -> List[str]:
    """The STORE DATA APDUs (hex) to apply ``mode_key``."""
    return [
        build_set_apdu(tag, value)
        for tag, value in set_commands_for_mode(mode_key, current_config)
    ]


# --- Interpretation --------------------------------------------------------

def mfc_enabled(config: Dict[str, int]) -> bool:
    """True if the SAK currently advertises MIFARE Classic support."""
    return bool(config.get(TAG_SAK, 0) & MFC_SAK_BIT)


def detect_current_mode(config: Dict[str, int]) -> Optional[str]:
    """Return the key of the fixed mode whose full config matches exactly,
    or ``None`` (a "Custom" combination, including any Randomize state)."""
    for mode in MODES:
        if mode.target is None:
            continue
        if all(config.get(tag) == value for tag, value in mode.target.items()):
            return mode.key
    return None


def disabled_mode_keys(config: Dict[str, int]) -> set:
    """Modes that should be disabled because the card is already in them.

    A fixed mode is disabled on an exact match. Randomize is disabled
    whenever the UID byte is already 0x00, independent of the MFC bits.
    """
    disabled = set()
    current = detect_current_mode(config)
    if current is not None:
        disabled.add(current)
    if config.get(TAG_UID) == UID_RANDOMIZE:
        disabled.add(MODE_RANDOMIZE)
    return disabled


def summarize_mode(config: Dict[str, int]) -> str:
    """Human label for the current mode, or 'Custom'."""
    key = detect_current_mode(config)
    if key is not None:
        return MODES_BY_KEY[key].label
    if config.get(TAG_UID) == UID_RANDOMIZE:
        return "Randomize" + (" + MFC" if mfc_enabled(config) else "")
    return "Custom"


def describe_value(tag: str, value: int) -> str:
    """A short human meaning for a tag's value."""
    if tag == TAG_UID:
        meanings = {
            UID_RANDOMIZE: "Randomized UID",
            UID_7BYTE: "7-byte UID",
            UID_4BYTE: "4-byte NUID",
        }
        return meanings.get(value, f"Unknown UID mode (0x{value:02X})")

    if tag in (TAG_SAK, TAG_CASCADE_SAK):
        parts = []
        if value & 0x20:
            parts.append("ISO 14443-4")
        if value & MFC_SAK_BIT:
            parts.append("MIFARE Classic")
        if value & 0x04:
            parts.append("UID not complete")
        base = " + ".join(parts) if parts else "no ISO 14443-4 / no MIFARE Classic"
        if tag == TAG_CASCADE_SAK:
            return f"{base} (returned mid-cascade)"
        return base

    if tag in (TAG_ATQA1, TAG_ATQA2):
        which = "1" if tag == TAG_ATQA1 else "2"
        return f"Answer To reQuest, byte {which}"

    return ""


# --- gp.jar -d trace parsing ----------------------------------------------

_HEX = set("0123456789ABCDEF")


def _extract_response_value(a_line: str) -> Optional[int]:
    """Pull the config byte out of an ``A<<`` trace line.

    Expected data layout (verified on hardware): ``FE 04 DF2B 01 <value>``
    with status word 9000. Returns the value, or ``None`` for a
    non-success status / unparseable line.
    """
    tokens = a_line.split()
    if len(tokens) < 2:
        return None

    sw = tokens[-1].upper()
    if sw != "9000":
        return None

    data = tokens[-2].upper()
    if not data or len(data) % 2 or any(c not in _HEX for c in data):
        return None

    # Locate the DF2B TLV and read its (single-byte) value.
    idx = data.find("DF2B")
    if idx != -1 and idx + 6 <= len(data):
        length = int(data[idx + 4:idx + 6], 16)
        val_hex = data[idx + 6:idx + 6 + length * 2]
        if length >= 1 and len(val_hex) >= 2:
            return int(val_hex[:2], 16)

    # Fallback: the value is the last data byte before the status word.
    return int(data[-2:], 16)


def store_data_succeeded(trace: str) -> bool:
    """True if the trace shows at least one STORE DATA (config write) and
    every STORE DATA response returned status word 9000."""
    saw_write = False
    pending = False
    for raw in trace.splitlines():
        line = raw.strip()
        compact = line.replace(" ", "").upper()
        if "A>>" in line:
            pending = "E28800" in compact  # STORE DATA, CLA 80/84 E2 P1=88 P2=00
            if pending:
                saw_write = True
        elif "A<<" in line and pending:
            tokens = line.split()
            sw = tokens[-1].upper() if tokens else ""
            if sw != "9000":
                return False
            pending = False
    return saw_write


def parse_config_response(trace: str) -> Dict[str, int]:
    """Parse a gp.jar ``-d`` trace into ``{tag: value}``.

    Pairs each GET DATA request (``A>>`` containing ``DF2B02<tag>``) with
    the immediately following ``A<<`` response, ignoring the secure-channel
    setup APDUs (SELECT / INITIALIZE UPDATE / EXTERNAL AUTHENTICATE).
    """
    config: Dict[str, int] = {}
    pending_tag: Optional[str] = None

    for raw in trace.splitlines():
        line = raw.strip()
        compact = line.replace(" ", "").upper()

        if "A>>" in line:
            pending_tag = None
            if "CA00FE" in compact:
                for tag in TAG_ORDER:
                    if ("DF2B02" + tag) in compact:
                        pending_tag = tag
                        break
        elif "A<<" in line and pending_tag is not None:
            value = _extract_response_value(line)
            if value is not None:
                config[pending_tag] = value
            pending_tag = None

    return config
