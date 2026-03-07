from src.execution.can_executor import CANExecutor, TestCase

def test_simulator_mode():
    ex = CANExecutor(channel="can0")
    assert ex.simulator_mode() is True

def test_testcase_creation():
    tc = TestCase(
        tc_id="TC_0x22_F190_001",
        service_sid=0x22,
        request_payload=bytes([0x22, 0xF1, 0x90]),
        expected_sid=0x62,
        p2_max_ms=50.0,
        standard_ref="ISO14229-1 S11.4.2"
    )
    assert tc.service_sid == 0x22
    assert tc.expected_sid == 0x62
