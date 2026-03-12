"""
EXEC Agent — CAN Executor
Real UDS over SocketCAN using ISO-TP (python-can + can-isotp).
TBM: Request 0x757 / Response 0x75F / 500kbps
Story: S4.1
"""

import os
import sys
import time
import socket
import struct
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

# ── Config ────────────────────────────────────────────────

CAN_INTERFACE  = "can0"
CAN_TX_ID      = 0x757   # TBM Request
CAN_RX_ID      = 0x75F   # TBM Response
CAN_BITRATE    = 500000
P2_SERVER_MAX  = 0.050   # 50ms default ISO 14229
P2_STAR_MAX    = 5.000   # 5000ms extended

# ── Data Classes ──────────────────────────────────────────

class TestVerdict(Enum):
    PASS    = "PASS"
    FAIL    = "FAIL"
    ERROR   = "ERROR"
    TIMEOUT = "TIMEOUT"
    SKIP    = "SKIP"

@dataclass
class UDSFrame:
    direction: str          # TX or RX
    can_id: int
    data: bytes
    timestamp: float = 0.0

    def hex(self):
        return self.data.hex(" ").upper()

    def sid(self):
        # ISO-TP single frame: byte0=length, byte1=SID
        if len(self.data) >= 2:
            return self.data[1]
        return 0

@dataclass
class TestResult:
    test_id: str
    description: str
    request_hex: str
    response_hex: str = ""
    verdict: TestVerdict = TestVerdict.ERROR
    p2_measured_ms: float = 0.0
    p2_limit_ms: float = 50.0
    nrc: Optional[str] = None
    iso_clause: str = ""
    detail: str = ""
    frames: list = field(default_factory=list)


# ── Raw ISO-TP via SocketCAN ──────────────────────────────

class RawCANSocket:
    """
    Minimal ISO-TP single-frame sender/receiver using raw AF_CAN socket.
    Works without python-can or can-isotp — stdlib only.
    Handles UDS messages up to 7 bytes (single CAN frame).
    """
    CAN_FRAME_FMT = "=IB3x8s"
    CAN_FRAME_SIZE = struct.calcsize(CAN_FRAME_FMT)

    def __init__(self, interface=CAN_INTERFACE):
        self.interface = interface
        self.sock = None

    def open(self):
        try:
            self.sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
            self.sock.bind((self.interface,))
            self.sock.settimeout(2.0)
            return True
        except Exception as e:
            print(f"CAN socket error: {e}")
            return False

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _build_frame(self, can_id: int, data: bytes) -> bytes:
        # Pad to 8 bytes
        padded = data.ljust(8, b'\x00')[:8]
        return struct.pack(self.CAN_FRAME_FMT, can_id, len(data), padded)

    def _parse_frame(self, raw: bytes):
        can_id, dlc, data = struct.unpack(self.CAN_FRAME_FMT, raw)
        can_id &= 0x1FFFFFFF   # strip flags
        return can_id, data[:dlc]

    def send(self, can_id: int, data: bytes) -> bool:
        try:
            frame = self._build_frame(can_id, data)
            self.sock.send(frame)
            return True
        except Exception as e:
            print(f"CAN send error: {e}")
            return False

    def recv(self, expected_id: int, timeout: float = 2.0) -> Optional[bytes]:
        self.sock.settimeout(timeout)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = self.sock.recv(self.CAN_FRAME_SIZE)
                can_id, data = self._parse_frame(raw)
                if can_id == expected_id:
                    return data
                # Also accept functional response IDs
                if can_id == 0x7FF or can_id == (expected_id | 0x008):
                    return data
            except socket.timeout:
                break
            except Exception as e:
                print(f"CAN recv error: {e}")
                break
        return None


# ── ISO-TP Frame Builder ───────────────────────────────────

def build_isotp_single(payload: bytes) -> bytes:
    """
    ISO 15765-2 Single Frame.
    Byte 0: 0x0N where N = payload length (max 7 bytes)
    """
    assert len(payload) <= 7, "Use multi-frame for payloads > 7 bytes"
    frame = bytes([len(payload)]) + payload
    return frame.ljust(8, b'\xAA')   # pad with 0xAA


def parse_isotp_response(data: bytes) -> Optional[bytes]:
    """
    Parse ISO-TP response frame.
    Returns UDS payload bytes or None if not a valid single frame.
    """
    if not data or len(data) < 2:
        return None
    frame_type = (data[0] >> 4) & 0x0F
    if frame_type == 0:   # Single Frame
        length = data[0] & 0x0F
        return data[1:1+length]
    # First Frame — return what we have (simplified, no FC handling)
    if frame_type == 1:
        length = ((data[0] & 0x0F) << 8) | data[1]
        return data[2:2+min(length, 6)]
    return data[1:]


# ── EXEC Agent ────────────────────────────────────────────

class EXECAgent:
    """
    EXEC — CAN/UDS Executor.
    Sends UDS requests to TBM, measures P2, validates responses.
    TX: 0x757  RX: 0x75F  500kbps
    """

    def __init__(self,
                 interface=CAN_INTERFACE,
                 tx_id=CAN_TX_ID,
                 rx_id=CAN_RX_ID):
        self.interface = interface
        self.tx_id = tx_id
        self.rx_id = rx_id
        self.can = RawCANSocket(interface)
        self.connected = False
        self.session_results = []

    # ── Connection ────────────────────────────────────────

    def connect(self) -> bool:
        self.connected = self.can.open()
        if self.connected:
            print(f"EXEC connected: {self.interface}  TX={hex(self.tx_id)}  RX={hex(self.rx_id)}")
        else:
            print(f"EXEC: CAN socket failed — check 'ip link show {self.interface}'")
        return self.connected

    def disconnect(self):
        self.can.close()
        self.connected = False

    # ── Core Send/Receive ─────────────────────────────────

    def send_uds(self, payload: bytes, timeout: float = P2_SERVER_MAX * 4) -> tuple:
        """
        Send UDS payload, return (response_payload, p2_ms, frames).
        """
        frames = []
        isotp_frame = build_isotp_single(payload)

        # Log TX
        frames.append(UDSFrame("TX", self.tx_id, isotp_frame, time.time()))
        print(f"  TX [{hex(self.tx_id)}]: {isotp_frame.hex(' ').upper()}")

        t_start = time.time()
        ok = self.can.send(self.tx_id, isotp_frame)
        if not ok:
            return None, 0.0, frames

        # Wait for response — handle 0x78 responsePending loop
        response_payload = None
        for attempt in range(5):
            raw = self.can.recv(self.rx_id, timeout=timeout)
            t_end = time.time()
            p2_ms = (t_end - t_start) * 1000.0

            if raw is None:
                print(f"  RX: TIMEOUT after {p2_ms:.1f}ms")
                break

            frames.append(UDSFrame("RX", self.rx_id, raw, t_end))
            print(f"  RX [{hex(self.rx_id)}]: {raw.hex(' ').upper()}  ({p2_ms:.1f}ms)")

            uds_data = parse_isotp_response(raw)
            if uds_data and len(uds_data) >= 1:
                # 0x7F 0xSID 0x78 = responsePending — wait and retry recv
                if len(uds_data) >= 3 and uds_data[0] == 0x7F and uds_data[2] == 0x78:
                    print(f"  RX: responsePending (0x78) — waiting P2*...")
                    time.sleep(0.1)
                    continue
                response_payload = uds_data
                break

        return response_payload, p2_ms, frames

    # ── UDS Services ──────────────────────────────────────

    def diagnostic_session_control(self, session: int = 0x01) -> TestResult:
        """
        SID 0x10 — DiagnosticSessionControl
        session: 0x01=default, 0x02=programming, 0x03=extended
        """
        session_names = {0x01:"defaultSession", 0x02:"programmingSession",
                         0x03:"extendedDiagnosticSession"}
        s_name = session_names.get(session, hex(session))
        req = bytes([0x10, session])
        result = TestResult(
            test_id=f"TC_0x10_{session:03d}",
            description=f"DiagnosticSessionControl → {s_name}",
            request_hex=req.hex(" ").upper(),
            p2_limit_ms=P2_SERVER_MAX * 1000,
            iso_clause="ISO14229-1 §9"
        )

        resp, p2, frames = self.send_uds(req)
        result.p2_measured_ms = round(p2, 2)
        result.frames = [asdict(f) if hasattr(f,'__dataclass_fields__') else str(f) for f in frames]

        if resp is None:
            result.verdict = TestVerdict.TIMEOUT
            result.detail = "No response within timeout"
            return result

        result.response_hex = resp.hex(" ").upper()

        # Positive response: 0x50 + session echo
        if resp[0] == 0x50:
            if resp[1] == session:
                result.verdict = TestVerdict.PASS if p2 <= (P2_SERVER_MAX * 1000) else TestVerdict.FAIL
                result.detail = f"P2={p2:.1f}ms limit={P2_SERVER_MAX*1000}ms"
                if len(resp) >= 6:
                    p2_max = (resp[2] << 8) | resp[3]
                    p2_star = ((resp[4] << 8) | resp[5]) * 10
                    result.detail += f" ECU_P2={p2_max}ms ECU_P2*={p2_star}ms"
            else:
                result.verdict = TestVerdict.FAIL
                result.detail = f"Session echo mismatch: got {hex(resp[1])} expected {hex(session)}"
        # Negative response: 0x7F
        elif resp[0] == 0x7F and len(resp) >= 3:
            nrc = resp[2]
            result.nrc = hex(nrc)
            result.verdict = TestVerdict.FAIL
            result.detail = f"NRC {hex(nrc)}"
        else:
            result.verdict = TestVerdict.ERROR
            result.detail = f"Unexpected response: {result.response_hex}"

        return result

    def read_data_by_identifier(self, did: int) -> TestResult:
        """
        SID 0x22 — ReadDataByIdentifier
        did: e.g. 0xF190 (VIN), 0xF189 (SW version)
        """
        did_names = {
            0xF190:"VIN", 0xF189:"ecuSoftwareVersion",
            0xF186:"activeDiagnosticSession", 0xF18C:"ecuSerialNumber",
            0xF18B:"ecuManufacturingDate", 0xF191:"ecuHardwareNumber"
        }
        d_name = did_names.get(did, f"DID_{did:04X}")
        req = bytes([0x22, (did >> 8) & 0xFF, did & 0xFF])
        result = TestResult(
            test_id=f"TC_0x22_{did:04X}",
            description=f"ReadDataByIdentifier {hex(did)} ({d_name})",
            request_hex=req.hex(" ").upper(),
            p2_limit_ms=P2_SERVER_MAX * 1000,
            iso_clause="ISO14229-1 §11"
        )

        resp, p2, frames = self.send_uds(req)
        result.p2_measured_ms = round(p2, 2)
        result.frames = [str(f) for f in frames]

        if resp is None:
            result.verdict = TestVerdict.TIMEOUT
            result.detail = "No response within timeout"
            return result

        result.response_hex = resp.hex(" ").upper()

        # Positive: 0x62 + DID echo + data
        if resp[0] == 0x62 and len(resp) >= 3:
            resp_did = (resp[1] << 8) | resp[2]
            if resp_did == did:
                data = resp[3:]
                result.verdict = TestVerdict.PASS if p2 <= (P2_SERVER_MAX * 1000) else TestVerdict.FAIL
                result.detail = f"P2={p2:.1f}ms  data={data.hex().upper()}  len={len(data)}"
                try:
                    result.detail += f"  ascii='{data.decode('ascii').strip()}'"
                except Exception:
                    pass
            else:
                result.verdict = TestVerdict.FAIL
                result.detail = f"DID echo mismatch: got {hex(resp_did)} expected {hex(did)}"
        elif resp[0] == 0x7F and len(resp) >= 3:
            nrc = resp[2]
            result.nrc = hex(nrc)
            nrc_names = {
                0x13:"incorrectMessageLength", 0x22:"conditionsNotCorrect",
                0x31:"requestOutOfRange", 0x33:"securityAccessDenied",
                0x7F:"serviceNotSupportedInActiveSession"
            }
            result.verdict = TestVerdict.FAIL
            result.detail = f"NRC {hex(nrc)} ({nrc_names.get(nrc,'unknown')})"
        else:
            result.verdict = TestVerdict.ERROR
            result.detail = f"Unexpected: {result.response_hex}"

        return result

    def tester_present(self, suppress=True) -> bool:
        """SID 0x3E — keep session alive."""
        sub = 0x80 if suppress else 0x00
        req = bytes([0x3E, sub])
        resp, p2, _ = self.send_uds(req, timeout=0.1)
        if suppress:
            return True   # no response expected
        return resp is not None and resp[0] == 0x7E

    # ── POC Test Suite ────────────────────────────────────

    def run_poc_suite(self) -> list:
        """
        POC test suite — 0x10 and 0x22 against TBM.
        Covers mandatory ISO 14229-1 test cases.
        """
        results = []
        print("\n" + "="*60)
        print("EXEC: Starting POC Test Suite")
        print(f"  ECU:  TBM")
        print(f"  TX:   {hex(self.tx_id)}  RX: {hex(self.rx_id)}")
        print(f"  BUS:  {self.interface} @ 500kbps")
        print("="*60)

        # ── 0x10 DiagnosticSessionControl ─────────────────
        print("\n[0x10] DiagnosticSessionControl")

        # TC1: Default session
        print("\nTC1: Default Session")
        r = self.diagnostic_session_control(0x01)
        self._print_result(r)
        results.append(r)
        time.sleep(0.1)

        # TC2: Extended session
        print("\nTC2: Extended Diagnostic Session")
        r = self.diagnostic_session_control(0x03)
        self._print_result(r)
        results.append(r)
        time.sleep(0.1)

        # TC3: Return to default
        print("\nTC3: Return to Default Session")
        r = self.diagnostic_session_control(0x01)
        self._print_result(r)
        results.append(r)
        time.sleep(0.1)

        # ── 0x22 ReadDataByIdentifier ──────────────────────
        print("\n[0x22] ReadDataByIdentifier")

        # TC4: VIN
        print("\nTC4: Read VIN (0xF190)")
        r = self.read_data_by_identifier(0xF190)
        self._print_result(r)
        results.append(r)
        time.sleep(0.1)

        # TC5: Active session DID
        print("\nTC5: Active Diagnostic Session (0xF186)")
        r = self.read_data_by_identifier(0xF186)
        self._print_result(r)
        results.append(r)
        time.sleep(0.1)

        # TC6: SW Version
        print("\nTC6: ECU Software Version (0xF189)")
        r = self.read_data_by_identifier(0xF189)
        self._print_result(r)
        results.append(r)
        time.sleep(0.1)

        # ── Summary ───────────────────────────────────────
        self._print_summary(results)
        self.session_results = results
        return results

    def _print_result(self, r: TestResult):
        icon = {"PASS":"✓","FAIL":"✗","TIMEOUT":"⏱","ERROR":"!","SKIP":"-"}
        v = r.verdict.value
        print(f"  [{icon.get(v,'?')} {v}] {r.test_id}: {r.description}")
        print(f"    REQ: {r.request_hex}")
        print(f"    RES: {r.response_hex or 'none'}")
        print(f"    P2:  {r.p2_measured_ms}ms / {r.p2_limit_ms}ms limit")
        if r.detail:
            print(f"    {r.detail}")

    def _print_summary(self, results: list):
        passed  = sum(1 for r in results if r.verdict == TestVerdict.PASS)
        failed  = sum(1 for r in results if r.verdict == TestVerdict.FAIL)
        timeout = sum(1 for r in results if r.verdict == TestVerdict.TIMEOUT)
        error   = sum(1 for r in results if r.verdict == TestVerdict.ERROR)
        total   = len(results)
        print("\n" + "="*60)
        print(f"POC RESULTS: {total} tests")
        print(f"  PASS:    {passed}")
        print(f"  FAIL:    {failed}")
        print(f"  TIMEOUT: {timeout}")
        print(f"  ERROR:   {error}")
        print(f"  SCORE:   {passed}/{total} ({100*passed//total if total else 0}%)")
        print("="*60)

    def save_results(self, results: list, path: str = "results/poc_results.json"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        out = []
        for r in results:
            d = asdict(r) if hasattr(r, '__dataclass_fields__') else r.__dict__
            d['verdict'] = r.verdict.value
            out.append(d)
        with open(path, "w") as f:
            json.dump(out, f, indent=2, default=str)
        print(f"Results saved: {path}")


# ── Entry Point ───────────────────────────────────────────

if __name__ == "__main__":
    exec_agent = EXECAgent(
        interface=CAN_INTERFACE,
        tx_id=CAN_TX_ID,
        rx_id=CAN_RX_ID
    )

    if not exec_agent.connect():
        print("Cannot connect to CAN. Check:")
        print("  sudo ip link show can0")
        print("  sudo ip link set can0 up type can bitrate 500000")
        sys.exit(1)

    try:
        results = exec_agent.run_poc_suite()
        exec_agent.save_results(results)
    finally:
        exec_agent.disconnect()
