"""CAN test execution engine - stub, implemented in S4.1"""
from dataclasses import dataclass, field
from enum import Enum

class TestResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"

@dataclass
class TestCase:
    tc_id: str
    service_sid: int
    request_payload: bytes
    expected_sid: int
    p2_max_ms: float = 50.0
    p2_star_max_ms: float = 5000.0
    standard_ref: str = ""

@dataclass
class TestExecution:
    tc: TestCase
    result: TestResult
    measured_p2_ms: float
    response_payload: bytes
    raw_frames: list = field(default_factory=list)

class CANExecutor:
    def __init__(self, channel: str = "can0", bitrate: int = 500000):
        self.channel = channel
        self.bitrate = bitrate

    def execute(self, tc: TestCase) -> TestExecution:
        raise NotImplementedError("Implemented in S4.1")

    def simulator_mode(self) -> bool:
        return True
