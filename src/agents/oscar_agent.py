"""
OSCAR Agent — ODX Schema Analyst
Parses ODX/PDX files and extracts diagnostic services, DIDs, sessions.
Pure Python, uses stdlib xml.etree only. No extra dependencies.
Story: S1.1
"""

import os
import sys
import json
from dataclasses import dataclass, field, asdict
from typing import Optional
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "knowledge"))

# ── ODX Namespaces ────────────────────────────────────────
# ODX 2.0 / 2.0.1 — standard namespace
ODX_NS = {
    "odx": "http://www.asam.net/odx",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance"
}

# ── Data Classes ──────────────────────────────────────────

@dataclass
class SessionType:
    id: str
    short_name: str
    session_value: str          # hex e.g. "0x01"
    description: str = ""

@dataclass
class Parameter:
    name: str
    byte_position: int
    bit_length: int
    value: str = ""             # hex encoded default/const value
    description: str = ""

@dataclass
class DiagService:
    id: str
    short_name: str
    service_id: str             # hex e.g. "0x10"
    service_name: str           # human name e.g. "DiagnosticSessionControl"
    session: str                # which session this belongs to
    request_params: list = field(default_factory=list)
    response_params: list = field(default_factory=list)
    description: str = ""

@dataclass
class DataIdentifier:
    id: str
    short_name: str
    did_value: str              # hex e.g. "0xF190"
    did_int: int = 0
    data_length: int = 0
    data_type: str = ""
    description: str = ""
    session_access: str = "defaultSession"
    security_required: bool = False

@dataclass
class ServiceManifest:
    """Complete picture of what an ECU supports — output of OSCAR."""
    odx_file: str
    ecu_name: str
    protocol: str
    services: list = field(default_factory=list)
    data_identifiers: list = field(default_factory=list)
    sessions: list = field(default_factory=list)
    raw_service_ids: list = field(default_factory=list)   # e.g. ["0x10","0x22"]
    parse_errors: list = field(default_factory=list)


# ── OSCAR Agent ───────────────────────────────────────────

class OSCARAgent:
    """
    OSCAR — ODX Schema Analyst.
    Parses ODX/PDX XML and returns a ServiceManifest
    that STAN, TARA and EXEC can consume.
    """

    # Known SID → human name mapping
    SID_NAMES = {
        "0x10": "DiagnosticSessionControl",
        "0x11": "ECUReset",
        "0x14": "ClearDiagnosticInformation",
        "0x19": "ReadDTCInformation",
        "0x22": "ReadDataByIdentifier",
        "0x23": "ReadMemoryByAddress",
        "0x27": "SecurityAccess",
        "0x28": "CommunicationControl",
        "0x2A": "ReadDataByPeriodicIdentifier",
        "0x2C": "DynamicallyDefineDataIdentifier",
        "0x2E": "WriteDataByIdentifier",
        "0x2F": "InputOutputControlByIdentifier",
        "0x31": "RoutineControl",
        "0x34": "RequestDownload",
        "0x35": "RequestUpload",
        "0x36": "TransferData",
        "0x37": "RequestTransferExit",
        "0x3D": "WriteMemoryByAddress",
        "0x3E": "TesterPresent",
        "0x85": "ControlDTCSetting",
        "0x86": "ResponseOnEvent",
        "0x87": "LinkControl",
    }

    # Known DID → human name mapping
    DID_NAMES = {
        0xF186: "activeDiagnosticSession",
        0xF187: "sparePartNumber",
        0xF188: "ecuSoftwareNumber",
        0xF189: "ecuSoftwareVersion",
        0xF18A: "systemSupplierIdentifier",
        0xF18B: "ecuManufacturingDate",
        0xF18C: "ecuSerialNumber",
        0xF190: "VIN",
        0xF191: "ecuHardwareNumber",
        0xF192: "systemSupplierECUHardwareNumber",
        0xF193: "systemSupplierECUHardwareVersionNumber",
        0xF194: "systemSupplierECUSoftwareNumber",
        0xF195: "systemSupplierECUSoftwareVersionNumber",
        0xF197: "systemNameOrEngineType",
    }

    def __init__(self):
        self.last_manifest = None

    # ── Public API ────────────────────────────────────────

    def parse(self, odx_file_path: str) -> ServiceManifest:
        """
        Parse an ODX file and return a ServiceManifest.
        Main entry point — called by pipeline and GUI.
        """
        manifest = ServiceManifest(
            odx_file=os.path.basename(odx_file_path),
            ecu_name="Unknown",
            protocol="ISO14229-1 (UDS)"
        )

        if not os.path.exists(odx_file_path):
            manifest.parse_errors.append(f"File not found: {odx_file_path}")
            return manifest

        try:
            tree = ET.parse(odx_file_path)
            root = tree.getroot()
        except ET.ParseError as e:
            manifest.parse_errors.append(f"XML parse error: {e}")
            return manifest

        # Strip namespace for easier xpath
        self._strip_ns(root)

        # Extract ECU name
        manifest.ecu_name = self._get_ecu_name(root)

        # Extract sessions
        manifest.sessions = self._extract_sessions(root)

        # Extract DIAG-SERVICEs
        manifest.services = self._extract_services(root)
        manifest.raw_service_ids = sorted(set(
            s.service_id for s in manifest.services
        ))

        # Extract DIDs from 0x22 services
        manifest.data_identifiers = self._extract_dids(root, manifest.services)

        self.last_manifest = manifest
        return manifest

    def decode_request(self, hex_bytes: str) -> dict:
        """
        Decode a UDS request hex string.
        e.g. "03 22 F1 90" → {SID: 0x22, DID: 0xF190, name: VIN}
        """
        try:
            raw = bytes.fromhex(hex_bytes.replace(" ", ""))
        except ValueError:
            return {"error": "Invalid hex string"}

        if len(raw) < 2:
            return {"error": "Too short"}

        length = raw[0]
        sid = raw[1]
        sid_hex = hex(sid)
        result = {
            "length": length,
            "SID": sid_hex,
            "service": self.SID_NAMES.get(sid_hex, "Unknown"),
            "raw": hex_bytes
        }

        # 0x10 — DiagnosticSessionControl
        if sid == 0x10 and len(raw) >= 3:
            subf = raw[2] & 0x7F
            sprmib = bool(raw[2] & 0x80)
            sessions = {0x01:"defaultSession", 0x02:"programmingSession",
                        0x03:"extendedDiagnosticSession"}
            result["subFunction"] = hex(raw[2])
            result["sessionType"] = sessions.get(subf, hex(subf))
            result["suppressPositiveResponse"] = sprmib

        # 0x22 — ReadDataByIdentifier
        elif sid == 0x22 and len(raw) >= 4:
            did = (raw[2] << 8) | raw[3]
            did_hex = f"0x{did:04X}"
            result["DID"] = did_hex
            result["DID_name"] = self.DID_NAMES.get(did, "ManufacturerSpecific")

        # 0x7F — Negative Response
        elif sid == 0x7F and len(raw) >= 4:
            failed_sid = raw[2]
            nrc = raw[3]
            result["failedSID"] = hex(failed_sid)
            result["NRC"] = hex(nrc)
            result["NRC_meaning"] = self._nrc_name(nrc)

        return result

    def decode_response(self, hex_bytes: str) -> dict:
        """
        Decode a UDS response hex string.
        e.g. "14 62 F1 90 ..." → {SID: 0x62, DID: 0xF190, data: ...}
        """
        try:
            raw = bytes.fromhex(hex_bytes.replace(" ", ""))
        except ValueError:
            return {"error": "Invalid hex string"}

        if len(raw) < 2:
            return {"error": "Too short"}

        sid = raw[0]
        sid_hex = hex(sid)
        result = {"SID": sid_hex, "raw": hex_bytes}

        # 0x50 — Positive response to 0x10
        if sid == 0x50 and len(raw) >= 6:
            session = raw[1]
            p2_max = (raw[2] << 8) | raw[3]
            p2star = ((raw[4] << 8) | raw[5]) * 10
            result["sessionType"] = hex(session)
            result["P2ServerMax_ms"] = p2_max
            result["P2StarServerMax_ms"] = p2star

        # 0x62 — Positive response to 0x22
        elif sid == 0x62 and len(raw) >= 4:
            did = (raw[1] << 8) | raw[2]
            did_hex = f"0x{did:04X}"
            data = raw[3:]
            result["DID"] = did_hex
            result["DID_name"] = self.DID_NAMES.get(did, "ManufacturerSpecific")
            result["data_length"] = len(data)
            result["data_hex"] = data.hex().upper()
            # Try ASCII decode for string DIDs
            try:
                result["data_ascii"] = data.decode("ascii").strip()
            except Exception:
                result["data_ascii"] = None

        # 0x7F — Negative Response
        elif sid == 0x7F and len(raw) >= 3:
            failed_sid = raw[1]
            nrc = raw[2]
            result["type"] = "NegativeResponse"
            result["failedSID"] = hex(failed_sid)
            result["NRC"] = hex(nrc)
            result["NRC_meaning"] = self._nrc_name(nrc)

        return result

    def to_json(self, manifest: ServiceManifest) -> str:
        """Serialise ServiceManifest to JSON for inter-agent sharing."""
        return json.dumps(asdict(manifest), indent=2)

    def print_manifest(self, manifest: ServiceManifest):
        """Pretty print the parsed manifest."""
        print("\n" + "="*60)
        print(f"ECU:      {manifest.ecu_name}")
        print(f"File:     {manifest.odx_file}")
        print(f"Protocol: {manifest.protocol}")
        print(f"\nSessions ({len(manifest.sessions)}):")
        for s in manifest.sessions:
            print(f"  [{s.session_value}] {s.short_name}")
        print(f"\nServices ({len(manifest.services)}):")
        for svc in manifest.services:
            print(f"  {svc.service_id} — {svc.service_name} ({svc.short_name})")
        print(f"\nData Identifiers ({len(manifest.data_identifiers)}):")
        for did in manifest.data_identifiers:
            sec = " [SECURITY]" if did.security_required else ""
            print(f"  {did.did_value} — {did.short_name}{sec} ({did.data_length} bytes)")
        if manifest.parse_errors:
            print(f"\nWarnings:")
            for e in manifest.parse_errors:
                print(f"  ! {e}")
        print("="*60)

    # ── Private Helpers ───────────────────────────────────

    def _strip_ns(self, root):
        """Remove XML namespaces for simpler xpath queries."""
        for elem in root.iter():
            if "}" in elem.tag:
                elem.tag = elem.tag.split("}")[1]
            elem.attrib = {
                k.split("}")[-1]: v for k, v in elem.attrib.items()
            }

    def _get_ecu_name(self, root) -> str:
        for path in [".//ECU-SHARED-DATA/SHORT-NAME",
                     ".//DIAG-LAYER/SHORT-NAME",
                     ".//BASE-VARIANT/SHORT-NAME",
                     ".//ECU-VARIANT/SHORT-NAME"]:
            el = root.find(path)
            if el is not None and el.text:
                return el.text.strip()
        # Try root tag SHORT-NAME
        el = root.find("SHORT-NAME")
        if el is not None and el.text:
            return el.text.strip()
        return "UnknownECU"

    def _extract_sessions(self, root) -> list:
        sessions = []
        seen = set()
        for elem in root.iter("DIAG-SERVICE"):
            # Check for session-related services
            sn = self._text(elem, "SHORT-NAME")
            if not sn:
                continue
            # Look for session values in request params
            for param in elem.iter("CODED-CONST"):
                parent = self._text(param, "../SHORT-NAME")
                val = self._text(param, "CODED-VALUE")
                if val and sn not in seen:
                    try:
                        int_val = int(val)
                        hex_val = hex(int_val)
                        if hex_val in ("0x1","0x2","0x3") or int_val in (1,2,3):
                            session_map = {
                                "0x1":"defaultSession",
                                "0x2":"programmingSession",
                                "0x3":"extendedDiagnosticSession",
                                "1":"defaultSession",
                                "2":"programmingSession",
                                "3":"extendedDiagnosticSession"
                            }
                            s_name = session_map.get(str(int_val),
                                     session_map.get(hex_val, sn))
                            if s_name not in seen:
                                seen.add(s_name)
                                sessions.append(SessionType(
                                    id=sn,
                                    short_name=s_name,
                                    session_value=hex(int_val)
                                ))
                    except (ValueError, TypeError):
                        pass

        # Always add defaultSession if missing
        if not any(s.session_value in ("0x1","0x01") for s in sessions):
            sessions.insert(0, SessionType(
                id="DS_default",
                short_name="defaultSession",
                session_value="0x01"
            ))
        return sessions

    def _extract_services(self, root) -> list:
        services = []
        seen_ids = set()

        for elem in root.iter("DIAG-SERVICE"):
            sn = self._text(elem, "SHORT-NAME") or ""
            sid_val = None

            # Find SID from REQUEST coded params
            req = elem.find(".//REQUEST")
            if req is None:
                req = elem

            for param in req.iter("CODED-CONST"):
                val = self._text(param, "CODED-VALUE")
                if val:
                    try:
                        int_val = int(val)
                        # UDS SIDs are 0x10-0x87
                        if 0x10 <= int_val <= 0xFF:
                            sid_val = hex(int_val)
                            break
                    except (ValueError, TypeError):
                        # Try hex string
                        try:
                            if val.startswith("0x") or val.startswith("0X"):
                                int_val = int(val, 16)
                                if 0x10 <= int_val <= 0xFF:
                                    sid_val = hex(int_val)
                                    break
                        except (ValueError, TypeError):
                            pass

            if not sid_val:
                # Infer from SHORT-NAME
                sid_val = self._infer_sid_from_name(sn)

            if not sid_val:
                continue

            key = sn + sid_val
            if key in seen_ids:
                continue
            seen_ids.add(key)

            # Extract request params
            req_params = self._extract_params(elem, ".//REQUEST//PARAM")
            # Extract response params
            res_params = self._extract_params(elem, ".//POS-RESPONSE//PARAM")

            services.append(DiagService(
                id=elem.get("ID", sn),
                short_name=sn,
                service_id=sid_val,
                service_name=self.SID_NAMES.get(sid_val, "UnknownService"),
                session=self._infer_session(sn),
                request_params=req_params,
                response_params=res_params,
                description=self._text(elem, "DESC/p") or ""
            ))

        return services

    def _extract_dids(self, root, services: list) -> list:
        dids = []
        seen = set()

        # Find DIDs from DATA-OBJECT-PROP or DIAG-SERVICE with 0x22
        for elem in root.iter("DIAG-SERVICE"):
            sn = self._text(elem, "SHORT-NAME") or ""
            sid = self._infer_sid_from_name(sn)
            if sid != "0x22":
                # check coded params
                found_22 = False
                for param in elem.iter("CODED-CONST"):
                    try:
                        if int(self._text(param, "CODED-VALUE") or "0") == 0x22:
                            found_22 = True
                            break
                    except (ValueError, TypeError):
                        pass
                if not found_22:
                    continue

            # Find DID value — look for 2-byte param after SID
            did_val = None
            did_int = 0
            params = list(elem.iter("CODED-CONST"))
            for i, param in enumerate(params):
                try:
                    val = int(self._text(param, "CODED-VALUE") or "0")
                    # DID range 0x0000-0xFFFF but skip SID values
                    if val > 0xFF or (val >= 0xF100 and val <= 0xFFFF):
                        did_val = f"0x{val:04X}"
                        did_int = val
                        break
                except (ValueError, TypeError):
                    pass

            # Fallback: infer DID from SHORT-NAME
            if not did_val:
                did_val, did_int = self._infer_did_from_name(sn)

            if not did_val or did_val in seen:
                continue
            seen.add(did_val)

            # Data length from response
            data_len = self._infer_data_length(did_int, elem)

            dids.append(DataIdentifier(
                id=elem.get("ID", sn),
                short_name=sn,
                did_value=did_val,
                did_int=did_int,
                data_length=data_len,
                data_type="ASCII" if did_int in (0xF190, 0xF189, 0xF18C) else "bytes",
                description=self.DID_NAMES.get(did_int, "ManufacturerSpecific"),
                session_access="defaultSession",
                security_required=(did_int < 0xF100)
            ))

        return dids

    def _extract_params(self, elem, xpath: str) -> list:
        params = []
        for p in elem.findall(xpath):
            sn = self._text(p, "SHORT-NAME") or ""
            bp = 0
            bl = 8
            try:
                bp = int(self._text(p, "BYTE-POSITION") or "0")
                bl = int(self._text(p, "BIT-LENGTH") or "8")
            except (ValueError, TypeError):
                pass
            val = self._text(p, "CODED-CONST/CODED-VALUE") or ""
            params.append(Parameter(
                name=sn, byte_position=bp,
                bit_length=bl, value=val
            ))
        return params

    def _infer_sid_from_name(self, name: str) -> Optional[str]:
        name_up = name.upper()
        if "0X10" in name_up or "DSC" in name_up or "SESSION" in name_up:
            return "0x10"
        if "0X22" in name_up or "RDBI" in name_up or "READDATA" in name_up:
            return "0x22"
        if "0X27" in name_up or "SECURITY" in name_up:
            return "0x27"
        if "0X3E" in name_up or "TESTERPRESENT" in name_up:
            return "0x3e"
        if "0X11" in name_up or "RESET" in name_up:
            return "0x11"
        if "0X19" in name_up or "DTC" in name_up:
            return "0x19"
        if "0X2E" in name_up or "WRITEDATA" in name_up:
            return "0x2e"
        return None

    def _infer_did_from_name(self, name: str):
        name_up = name.upper()
        did_map = {
            "VIN":    (0xF190, "0xF190"),
            "F190":   (0xF190, "0xF190"),
            "F189":   (0xF189, "0xF189"),
            "SWVER":  (0xF189, "0xF189"),
            "F186":   (0xF186, "0xF186"),
            "SESSION":(0xF186, "0xF186"),
            "F18C":   (0xF18C, "0xF18C"),
            "SERIAL": (0xF18C, "0xF18C"),
            "F18B":   (0xF18B, "0xF18B"),
            "DATE":   (0xF18B, "0xF18B"),
            "F191":   (0xF191, "0xF191"),
        }
        for key, (int_val, hex_val) in did_map.items():
            if key in name_up:
                return hex_val, int_val
        return None, 0

    def _infer_session(self, name: str) -> str:
        name_up = name.upper()
        if "PROG" in name_up:
            return "programmingSession"
        if "EXT" in name_up:
            return "extendedDiagnosticSession"
        return "defaultSession"

    def _infer_data_length(self, did_int: int, elem) -> int:
        known = {0xF190: 17, 0xF186: 1, 0xF189: 10,
                 0xF18C: 10, 0xF18B: 3,  0xF191: 10}
        if did_int in known:
            return known[did_int]
        # Try to find from response params
        try:
            bl = int(self._text(elem, ".//POS-RESPONSE//BIT-LENGTH") or "0")
            return bl // 8 if bl > 0 else 0
        except (ValueError, TypeError):
            return 0

    def _text(self, elem, xpath: str) -> Optional[str]:
        try:
            found = elem.find(xpath)
            if found is not None and found.text:
                return found.text.strip()
        except Exception:
            pass
        return None

    def _nrc_name(self, nrc: int) -> str:
        nrc_map = {
            0x10:"generalReject", 0x11:"serviceNotSupported",
            0x12:"subFunctionNotSupported", 0x13:"incorrectMessageLength",
            0x14:"responseTooLong", 0x21:"busyRepeatRequest",
            0x22:"conditionsNotCorrect", 0x24:"requestSequenceError",
            0x31:"requestOutOfRange", 0x33:"securityAccessDenied",
            0x35:"invalidKey", 0x36:"exceededNumberOfAttempts",
            0x37:"requiredTimeDelayNotExpired", 0x78:"responsePending",
            0x7E:"subFunctionNotSupportedInActiveSession",
            0x7F:"serviceNotSupportedInActiveSession"
        }
        return nrc_map.get(nrc, f"unknown_0x{nrc:02X}")


# ── Standalone Test ───────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Default to the POC fixture
    odx_path = sys.argv[1] if len(sys.argv) > 1 else \
               "/home/minu/vdip-agent-platform/data/samples/poc_ecu.odx"

    oscar = OSCARAgent()

    print(f"\nOSCAR parsing: {odx_path}")
    manifest = oscar.parse(odx_path)
    oscar.print_manifest(manifest)

    # Test request/response decoding
    print("\n── Decode Test ──────────────────────────────")
    test_frames = [
        ("REQUEST  0x10 default session", "02 10 01"),
        ("REQUEST  0x10 extended session", "02 10 03"),
        ("REQUEST  0x22 VIN",             "03 22 F1 90"),
        ("REQUEST  0x22 SW version",      "03 22 F1 89"),
        ("RESPONSE 0x50 default session", "06 50 01 00 19 01 F4"),
        ("RESPONSE 0x62 VIN",             "14 62 F1 90 57 56 57 5A 5A 5A 31 32 33 34 35 36 37 38 39 30 31"),
        ("RESPONSE NRC 0x12",             "03 7F 10 12"),
        ("RESPONSE NRC 0x31",             "03 7F 22 31"),
    ]

    for label, hex_str in test_frames:
        if "REQUEST" in label:
            result = oscar.decode_request(hex_str)
        else:
            result = oscar.decode_response(hex_str)
        print(f"\n{label}: {hex_str}")
        for k, v in result.items():
            print(f"  {k}: {v}")

    # Output JSON manifest for inter-agent use
    print("\n── ServiceManifest JSON (first 500 chars) ──")
    print(oscar.to_json(manifest)[:500])
    print("\n✓ OSCAR ready.")
