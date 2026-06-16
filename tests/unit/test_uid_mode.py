"""
Unit tests for the UID-mode configuration logic (src/services/uid_mode.py).

Covers the NXP config tags 10A1-10A5 (ATQA1/ATQA2/SAK/Cascade SAK/UID):
APDU construction, parsing of the gp.jar -d trace, mode detection, the
"disabled current mode" logic, and the Randomize "preserve MFC bit" rule.
"""

from src.services import uid_mode as um


class TestApduBuilders:
    def test_build_get_apdu(self):
        assert um.build_get_apdu("10A5") == "80CA00FE06DF2B0210A500"
        assert um.build_get_apdu("10A1") == "80CA00FE06DF2B0210A100"

    def test_get_config_apdus_order(self):
        apdus = um.get_config_apdus()
        assert len(apdus) == 5
        assert apdus[0] == um.build_get_apdu("10A1")
        assert apdus[-1] == um.build_get_apdu("10A5")

    def test_build_set_apdu(self):
        # Matches the authoritative -s commands in NXP_j3r_config_notes.txt
        assert um.build_set_apdu("10A5", 0x04) == "80E2880007DF2B0410A50104"
        assert um.build_set_apdu("10A3", 0x28) == "80E2880007DF2B0410A30128"
        assert um.build_set_apdu("10A1", 0x00) == "80E2880007DF2B0410A10100"


class TestSetCommandsForMode:
    def test_7byte_basic_writes_all_five(self):
        cmds = um.set_commands_for_mode(um.MODE_7BYTE_BASIC, {})
        assert len(cmds) == 5
        assert dict(cmds) == {
            "10A1": 0x00, "10A2": 0x48, "10A3": 0x20, "10A4": 0x24, "10A5": 0x04,
        }

    def test_7byte_mfc(self):
        cmds = um.set_commands_for_mode(um.MODE_7BYTE_MFC, {})
        assert dict(cmds) == {
            "10A1": 0x00, "10A2": 0x48, "10A3": 0x28, "10A4": 0x24, "10A5": 0x04,
        }

    def test_4byte_mfc(self):
        cmds = um.set_commands_for_mode(um.MODE_4BYTE_MFC, {})
        assert dict(cmds) == {
            "10A1": 0x00, "10A2": 0x08, "10A3": 0x28, "10A4": 0x2B, "10A5": 0x08,
        }

    def test_write_order_starts_with_uid_tag(self):
        # Notes write 10A5 first; matters because SAK/cascade follow.
        cmds = um.set_commands_for_mode(um.MODE_7BYTE_MFC, {})
        assert cmds[0][0] == "10A5"

    def test_randomize_preserves_mfc_when_set(self):
        current = {"10A1": 0x00, "10A2": 0x48, "10A3": 0x28, "10A4": 0x24, "10A5": 0x04}
        cmds = um.set_commands_for_mode(um.MODE_RANDOMIZE, current)
        d = dict(cmds)
        assert d["10A5"] == 0x00
        assert d["10A3"] == 0x28
        assert d["10A4"] == 0x2B

    def test_randomize_without_mfc_only_sets_uid(self):
        current = {"10A1": 0x00, "10A2": 0x48, "10A3": 0x20, "10A4": 0x24, "10A5": 0x04}
        cmds = um.set_commands_for_mode(um.MODE_RANDOMIZE, current)
        assert cmds == [("10A5", 0x00)]

    def test_set_apdus_for_mode(self):
        apdus = um.set_apdus_for_mode(um.MODE_7BYTE_BASIC, {})
        assert apdus[0] == um.build_set_apdu("10A5", 0x04)
        assert len(apdus) == 5


class TestMfcEnabled:
    def test_mfc_on(self):
        assert um.mfc_enabled({"10A3": 0x28}) is True

    def test_mfc_off(self):
        assert um.mfc_enabled({"10A3": 0x20}) is False

    def test_missing(self):
        assert um.mfc_enabled({}) is False


class TestModeDetection:
    BASIC = {"10A1": 0x00, "10A2": 0x48, "10A3": 0x20, "10A4": 0x24, "10A5": 0x04}
    MFC7 = {"10A1": 0x00, "10A2": 0x48, "10A3": 0x28, "10A4": 0x24, "10A5": 0x04}
    MFC4 = {"10A1": 0x00, "10A2": 0x08, "10A3": 0x28, "10A4": 0x2B, "10A5": 0x08}
    # The real card captured from hardware: 4-byte UID but basic SAK -> Custom
    CUSTOM = {"10A1": 0x00, "10A2": 0x48, "10A3": 0x20, "10A4": 0x24, "10A5": 0x08}
    RAND = {"10A1": 0x00, "10A2": 0x48, "10A3": 0x28, "10A4": 0x2B, "10A5": 0x00}

    def test_detect_basic(self):
        assert um.detect_current_mode(self.BASIC) == um.MODE_7BYTE_BASIC

    def test_detect_mfc7(self):
        assert um.detect_current_mode(self.MFC7) == um.MODE_7BYTE_MFC

    def test_detect_mfc4(self):
        assert um.detect_current_mode(self.MFC4) == um.MODE_4BYTE_MFC

    def test_custom_is_none(self):
        assert um.detect_current_mode(self.CUSTOM) is None

    def test_randomize_is_not_a_fixed_mode(self):
        assert um.detect_current_mode(self.RAND) is None

    def test_partial_config_no_match(self):
        assert um.detect_current_mode({"10A5": 0x04}) is None

    def test_disabled_for_basic(self):
        assert um.disabled_mode_keys(self.BASIC) == {um.MODE_7BYTE_BASIC}

    def test_disabled_for_mfc4(self):
        assert um.disabled_mode_keys(self.MFC4) == {um.MODE_4BYTE_MFC}

    def test_disabled_for_custom_is_empty(self):
        assert um.disabled_mode_keys(self.CUSTOM) == set()

    def test_disabled_for_randomize_when_uid_zero(self):
        assert um.disabled_mode_keys(self.RAND) == {um.MODE_RANDOMIZE}


class TestParseConfigResponse:
    # Verbatim gp.jar -d trace captured from the JTaxCore card in the reader.
    REAL = """# gp -d -s 80CA00FE06DF2B0210A100 ...
# SCardConnect(...) -> T=1, 3BFA1800...
A>> T=1 (4+0000) 00A40400 00
A<< (0018+2) (24ms) 6F108408A000000151000000A5049F6501FF 9000
A>> T=1 (4+0008) 80500000 08 F0C86A8D6E451E9E 00
A<< (0032+2) (50ms) 00005110288880212732010370CA256EE20E464E397F691932C02B4E0E000064 9000
A>> T=1 (4+0016) 84820100 10 29CD5CF9E14D385B4702BB3801D431E3 00
A<< (0000+2) (20ms) 9000
A>> T=1 (4+0014) 84CA00FE 0E DF2B0210A1003DA5F0E29845BB1C 00
A<< (0006+2) (16ms) FE04DF2B0100 9000
A>> T=1 (4+0014) 84CA00FE 0E DF2B0210A20079414326F9A5DEF7 00
A<< (0006+2) (16ms) FE04DF2B0148 9000
A>> T=1 (4+0014) 84CA00FE 0E DF2B0210A3009C70A09F2B475598 00
A<< (0006+2) (17ms) FE04DF2B0120 9000
A>> T=1 (4+0014) 84CA00FE 0E DF2B0210A400EECF5496A8063C77 00
A<< (0006+2) (18ms) FE04DF2B0124 9000
A>> T=1 (4+0014) 84CA00FE 0E DF2B0210A500497C12C7E55A9253 00
A<< (0006+2) (17ms) FE04DF2B0108 9000
"""

    def test_parse_real_trace(self):
        cfg = um.parse_config_response(self.REAL)
        assert cfg == {
            "10A1": 0x00, "10A2": 0x48, "10A3": 0x20, "10A4": 0x24, "10A5": 0x08,
        }

    def test_parse_single_tag(self):
        out = (
            "A>> T=1 (4+0014) 84CA00FE 0E DF2B0210A500AA 00\n"
            "A<< (0006+2) (1ms) FE04DF2B0104 9000\n"
        )
        assert um.parse_config_response(out) == {"10A5": 0x04}

    def test_parse_skips_error_status(self):
        out = (
            "A>> T=1 (4+0014) 84CA00FE 0E DF2B0210A500AA 00\n"
            "A<< (0000+2) (1ms) 6985\n"
        )
        assert um.parse_config_response(out) == {}

    def test_parse_empty(self):
        assert um.parse_config_response("") == {}


class TestStoreDataSucceeded:
    OK = (
        "A>> T=1 (4+0014) 84E28800 0E DF2B0410A50104AABB 00\n"
        "A<< (0000+2) (5ms) 9000\n"
        "A>> T=1 (4+0014) 84E28800 0E DF2B0410A30128CCDD 00\n"
        "A<< (0000+2) (5ms) 9000\n"
    )

    def test_all_ok(self):
        assert um.store_data_succeeded(self.OK) is True

    def test_one_failure(self):
        bad = self.OK + (
            "A>> T=1 (4+0014) 84E28800 0E DF2B0410A40124EEFF 00\n"
            "A<< (0000+2) (5ms) 6985\n"
        )
        assert um.store_data_succeeded(bad) is False

    def test_no_writes(self):
        # A read-only trace has no STORE DATA -> not a successful write.
        assert um.store_data_succeeded(TestParseConfigResponse.REAL) is False


class TestDescribeValue:
    def test_uid_known(self):
        assert "7-byte" in um.describe_value("10A5", 0x04)
        assert "4-byte" in um.describe_value("10A5", 0x08)
        assert "andom" in um.describe_value("10A5", 0x00)

    def test_uid_unknown(self):
        desc = um.describe_value("10A5", 0x99)
        assert "0x99" in desc

    def test_sak_mfc(self):
        assert "MIFARE Classic" in um.describe_value("10A3", 0x28)
        assert "MIFARE Classic" not in um.describe_value("10A3", 0x20)
