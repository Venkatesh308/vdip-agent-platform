"""
STAN Agent — Built-in ISO 14229 Knowledge Base
All critical UDS clauses for 0x10 and 0x22 pre-loaded as structured text.
No PDF required — knowledge is embedded directly.
"""

ISO_14229_KNOWLEDGE = [

    # ─────────────────────────────────────────────
    # SERVICE 0x10 — DiagnosticSessionControl
    # ─────────────────────────────────────────────
    {
        "id": "ISO14229-1_S9.1_0x10_overview",
        "standard": "ISO14229-1",
        "section": "9.1",
        "service_sid": "0x10",
        "service_name": "DiagnosticSessionControl",
        "topic": "Service Overview",
        "content": """
ISO 14229-1 Section 9.1 — DiagnosticSessionControl (SID 0x10)

The DiagnosticSessionControl service is used by a client (tester) to enable different 
diagnostic sessions in the server (ECU). A diagnostic session enables a specific set 
of diagnostic services and/or functionality in the server.

Service ID (SID): 0x10
Positive Response SID: 0x50

The service request contains:
- SID: 0x10 (1 byte)
- diagnosticSessionType: subfunction byte (1 byte)
  Bit 7: suppressPosRspMsgIndicationBit (SPRMIB)
  Bits 6-0: sessionType value

Standard session types:
- 0x01: defaultSession
- 0x02: programmingSession  
- 0x03: extendedDiagnosticSession
- 0x04-0x3F: ISOSAEreserved
- 0x40-0x5F: vehicleManufacturerSpecific
- 0x60-0x7E: systemSupplierSpecific
- 0x7F: ISOSAEreserved

The positive response (0x50) contains:
- Response SID: 0x50 (1 byte)
- sessionType echo: (1 byte)
- sessionParameterRecord: P2ServerMax (2 bytes) + P2StarServerMax (2 bytes)
"""
    },

    {
        "id": "ISO14229-1_S9.3_0x10_behavior",
        "standard": "ISO14229-1",
        "section": "9.3",
        "service_sid": "0x10",
        "service_name": "DiagnosticSessionControl",
        "topic": "Server Behaviour",
        "content": """
ISO 14229-1 Section 9.3 — DiagnosticSessionControl Server Behaviour

9.3.1 defaultSession (0x01):
- The server shall always support the defaultSession.
- Upon receiving a request to enter defaultSession, the server shall:
  - Enable all diagnostic services supported in defaultSession
  - Reset all session-specific parameters to their default values
  - Respond with positive response 0x50 containing timing parameters
- The server shall respond to defaultSession request even if already in defaultSession.
- The ECUReset service (0x11) is NOT required to transition to defaultSession.

9.3.2 programmingSession (0x02):
- Used for ECU reprogramming (flash download).
- Server may impose security access requirements before entering this session.
- NRC 0x22 (conditionsNotCorrect) if vehicle conditions not met (e.g. vehicle moving).

9.3.3 extendedDiagnosticSession (0x03):
- Enables extended diagnostic functionality not available in defaultSession.
- Server shall transition from defaultSession to extendedDiagnosticSession upon request.
- Server shall maintain extendedDiagnosticSession as long as S3Server timer not expired.
- If S3Server timer expires, server shall transition back to defaultSession automatically.

Session transition rules:
- defaultSession → extendedDiagnosticSession: ALLOWED (NRC 0x22 if conditions not met)
- defaultSession → programmingSession: ALLOWED (NRC 0x22 if conditions not met)  
- extendedDiagnosticSession → defaultSession: ALLOWED always
- extendedDiagnosticSession → programmingSession: ALLOWED
- Any session → defaultSession: ALWAYS ALLOWED
"""
    },

    {
        "id": "ISO14229-1_S9.4_0x10_nrc",
        "standard": "ISO14229-1",
        "section": "9.4",
        "service_sid": "0x10",
        "service_name": "DiagnosticSessionControl",
        "topic": "Negative Response Codes",
        "content": """
ISO 14229-1 Section 9.4 — DiagnosticSessionControl Negative Response Codes

NRC 0x12 (subFunctionNotSupported):
- Sent when the requested sessionType is not supported by the server.
- Example: Server does not support programmingSession → returns NRC 0x12.
- MANDATORY: Server must send this NRC for unsupported session types.

NRC 0x22 (conditionsNotCorrect):
- Sent when the server cannot perform the session transition due to current conditions.
- Example: Vehicle speed > 0 km/h when programmingSession requested.
- Example: Engine running when certain sessions require engine off.

NRC 0x31 (requestOutOfRange):
- Sent when the sessionType value is in the ISOSAEreserved range and not supported.

NRC 0x25 (requestSequenceError):  
- Sent when the session transition sequence is not valid.

suppressPosRspMsgIndicationBit (SPRMIB) rules:
- If bit 7 of subfunction = 1: Server shall NOT send positive response.
- If bit 7 of subfunction = 0: Server SHALL send positive response.
- NRC responses are ALWAYS sent regardless of SPRMIB bit.

NRC 0x78 (requestCorrectlyReceivedResponsePending):
- Server sends this if processing will exceed P2ServerMax.
- Server can send multiple 0x78 responses but must complete within P2StarServerMax.
"""
    },

    {
        "id": "ISO14229-1_S9.5_0x10_timing",
        "standard": "ISO14229-1",
        "section": "9.5",
        "service_sid": "0x10",
        "service_name": "DiagnosticSessionControl",
        "topic": "Timing Parameters",
        "content": """
ISO 14229-1 Section 9.5 — DiagnosticSessionControl Timing Parameters

P2Server timing (response time):
- P2ServerMax DEFAULT value: 50ms (0x0019 in response = 25 units × 2ms = 50ms)
- P2ServerMax is the maximum time between request and first response.
- Unit: 1ms per bit in the sessionParameterRecord.
- Encoding in response: 2 bytes, value in ms.

P2*Server timing (extended response time after 0x78 NRC):
- P2StarServerMax DEFAULT value: 5000ms (0x01F4 in response = 500 units × 10ms = 5000ms)
- P2*ServerMax is the maximum time between 0x78 NRC and final response.
- Unit: 10ms per bit in the sessionParameterRecord.
- Encoding in response: 2 bytes, value in 10ms units.

S3Server timing (session timeout):
- S3Server DEFAULT value: 5000ms (5 seconds)
- If no diagnostic request received within S3Server time, server returns to defaultSession.
- S3Server timer restarts on every valid diagnostic request.
- S3Server only applies to non-default sessions.

Timing validation rules for test cases:
- PASS condition: response received within P2ServerMax from request timestamp.
- FAIL condition: response received AFTER P2ServerMax (timing violation).
- FAIL condition: no response received within P2StarServerMax after 0x78 NRC.
- P2ServerMax from response bytes: bytes[3:5] value in ms.
- P2StarServerMax from response bytes: bytes[5:7] value × 10 in ms.

Example positive response decode for 0x10 0x01:
Response: 06 50 01 00 19 01 F4
- 0x50: positive response SID
- 0x01: defaultSession echo
- 0x0019: P2ServerMax = 25ms (raw) → 25ms
- 0x01F4: P2StarServerMax = 500 (raw) × 10ms = 5000ms
"""
    },

    # ─────────────────────────────────────────────
    # SERVICE 0x22 — ReadDataByIdentifier
    # ─────────────────────────────────────────────
    {
        "id": "ISO14229-1_S11.1_0x22_overview",
        "standard": "ISO14229-1",
        "section": "11.1",
        "service_sid": "0x22",
        "service_name": "ReadDataByIdentifier",
        "topic": "Service Overview",
        "content": """
ISO 14229-1 Section 11.1 — ReadDataByIdentifier (SID 0x22)

The ReadDataByIdentifier service allows the client to request data record values 
from the server identified by one or more dataIdentifiers (DIDs).

Service ID (SID): 0x22
Positive Response SID: 0x62

Request format:
- SID: 0x22 (1 byte)
- dataIdentifier: 2 bytes (MSB first)
- Multiple DIDs can be requested in one message (if server supports it)

Positive Response format:
- Response SID: 0x62 (1 byte)
- dataIdentifier echo: 2 bytes
- dataRecord: variable length (DID-specific)

DID ranges per ISO 14229-1:
- 0x0000-0x00FF: ISOSAEreserved
- 0x0100-0xA5FF: vehicleManufacturerSpecific
- 0xA600-0xA7FF: ISOSAEreserved  
- 0xA800-0xACFF: vehicleManufacturerSpecific
- 0xAD00-0xAFFF: ISOSAEreserved
- 0xB000-0xB1FF: systemSupplierSpecific
- 0xB200-0xBFFF: ISOSAEreserved
- 0xC000-0xCEFF: vehicleManufacturerSpecific
- 0xCF00-0xCFFF: ISOSAEreserved
- 0xD000-0xDFFF: vehicleManufacturerSpecific
- 0xE000-0xE1FF: ISOSAEreserved
- 0xE200-0xEFFF: systemSupplierSpecific
- 0xF000-0xF0FF: ISOSAEreserved
- 0xF100-0xF1FF: ISO/SAE standardized (mandatory DIDs)
- 0xF200-0xF2FF: ISOSAEreserved
- 0xF300-0xFEFF: vehicleManufacturerSpecific
- 0xFF00-0xFFFF: ISOSAEreserved
"""
    },

    {
        "id": "ISO14229-1_S11.2_0x22_standardized_dids",
        "standard": "ISO14229-1",
        "section": "11.2",
        "service_sid": "0x22",
        "service_name": "ReadDataByIdentifier",
        "topic": "Standardized DIDs F1xx",
        "content": """
ISO 14229-1 Section 11.2 — Standardized Data Identifiers (0xF100-0xF1FF)

MANDATORY DIDs (server must support these in all sessions):

0xF186 — activeDiagnosticSessionDataIdentifier
- Returns current active session type (1 byte)
- 0x01=default, 0x02=programming, 0x03=extended
- MANDATORY in all sessions, no security access required.

0xF187 — vehicleManufacturerSparePartNumberDataIdentifier
- Spare part number assigned by vehicle manufacturer.

0xF188 — vehicleManufacturerECUSoftwareNumberDataIdentifier  
- ECU software number.

0xF189 — vehicleManufacturerECUSoftwareVersionNumberDataIdentifier
- ECU software version number.
- Typical format: ASCII string (e.g. "V1.0.0")

0xF18A — systemSupplierIdentifierDataIdentifier
- System supplier identifier (CAGE code or similar).

0xF18B — ECUManufacturingDateDataIdentifier
- ECU manufacturing date: 3 bytes (year, month, day BCD encoded).

0xF18C — ECUSerialNumberDataIdentifier
- ECU serial number: ASCII string.

0xF190 — VINDataIdentifier (Vehicle Identification Number)
- MANDATORY: Must be readable in defaultSession WITHOUT security access.
- Length: EXACTLY 17 bytes ASCII (ISO 3779).
- If VIN not programmed: return 17 × 0x00 or 17 × space characters.
- NRC 0x33 (securityAccessDenied) for VIN is a VIOLATION of ISO 14229-1.

0xF191 — vehicleManufacturerECUHardwareNumberDataIdentifier
- ECU hardware number.

0xF192-0xF194 — system supplier ECU hardware/software numbers.

0xF195 — systemSupplierECUSoftwareVersionNumberDataIdentifier

0xF197 — systemNameOrEngineTypeDataIdentifier

0xF1A0-0xF1EF — vehicleManufacturerSpecific in F1xx range.
"""
    },

    {
        "id": "ISO14229-1_S11.4_0x22_nrc",
        "standard": "ISO14229-1",
        "section": "11.4",
        "service_sid": "0x22",
        "service_name": "ReadDataByIdentifier",
        "topic": "Negative Response Codes",
        "content": """
ISO 14229-1 Section 11.4 — ReadDataByIdentifier Negative Response Codes

NRC 0x13 (incorrectMessageLengthOrInvalidFormat):
- Request length is not valid (e.g. odd number of bytes for DID list).
- DID field is not exactly 2 bytes.

NRC 0x14 (responseTooLong):
- Response data exceeds the maximum PDU length for the transport layer.
- Applies when multiple DIDs requested and combined response is too large.

NRC 0x22 (conditionsNotCorrect):
- Server cannot read the DID due to current operating conditions.
- Example: DID only readable when engine running, but engine is off.

NRC 0x31 (requestOutOfRange):
- The requested DID is not supported by the server.
- The DID is in a reserved range not implemented.
- MANDATORY: Server must return this NRC for unsupported DIDs.

NRC 0x33 (securityAccessDenied):
- The requested DID requires a security level not currently active.
- VIOLATION if returned for 0xF190 (VIN) in defaultSession.
- Valid for manufacturer-specific DIDs that require unlocked security.

NRC 0x35 (invalidKey):
- Not applicable to ReadDataByIdentifier directly.

Session and security requirements per DID:
- 0xF190 (VIN): readable in ALL sessions, NO security required.
- 0xF186 (activeSession): readable in ALL sessions, NO security required.
- 0xF18B (ECU date): readable in defaultSession, NO security required.
- Manufacturer DIDs: session and security requirements defined by OEM.

Multiple DID request rules:
- If ANY requested DID returns NRC, entire request returns that NRC.
- Server may support reading multiple DIDs in one request (optional).
- If multiple DIDs and one not supported: NRC 0x31 for entire request.
"""
    },

    {
        "id": "ISO14229-1_S11.4_0x22_timing",
        "standard": "ISO14229-1",
        "section": "11.4.2",
        "service_sid": "0x22",
        "service_name": "ReadDataByIdentifier",
        "topic": "Timing Requirements",
        "content": """
ISO 14229-1 Section 11.4.2 — ReadDataByIdentifier Timing Requirements

P2Server timing applies to ReadDataByIdentifier same as all UDS services:
- P2ServerMax DEFAULT: 50ms from request to first response.
- P2StarServerMax DEFAULT: 5000ms from 0x78 NRC to final response.

Response time measurement:
- Start: timestamp of last byte of request frame received by server.
- End: timestamp of first byte of response frame sent by server.
- Measurement: tester side measures from last TX frame to first RX frame.

NRC 0x78 (requestCorrectlyReceivedResponsePending):
- Server may send 0x78 if data retrieval will exceed P2ServerMax.
- After 0x78: server has P2StarServerMax (default 5000ms) to send final response.
- Server may send multiple 0x78 responses within P2StarServerMax window.
- Test validation: if P2 measured > P2ServerMax AND no 0x78 received → TIMING FAIL.
- Test validation: if 0x78 received AND final response > P2StarServerMax → TIMING FAIL.

Typical P2 values observed in ECUs:
- Body ECUs: 25-50ms
- Powertrain ECUs: 30-50ms  
- Safety ECUs (ASIL-D): may use P2StarServer with 0x78 for complex reads.

Test case timing assertions:
- TC PASS: response_time_ms <= p2_server_max_ms
- TC FAIL: response_time_ms > p2_server_max_ms (no 0x78 pending)
- TC PASS (with pending): 0x78 received AND final_response_time <= p2_star_server_max_ms
"""
    },

    # ─────────────────────────────────────────────
    # ISO 15765-2 — CAN Transport Layer
    # ─────────────────────────────────────────────
    {
        "id": "ISO15765-2_S8_transport_overview",
        "standard": "ISO15765-2",
        "section": "8",
        "service_sid": "ALL",
        "service_name": "CAN Transport Layer",
        "topic": "ISO-TP Frame Types",
        "content": """
ISO 15765-2 Section 8 — Network Layer Protocol Data Units (N_PDU)

Frame types for CAN transport (ISO-TP):

Single Frame (SF) — PCI byte 0x0N where N = data length:
- Used when UDS message fits in one CAN frame (≤7 bytes for CAN 2.0).
- Byte 0: 0x0N (N = payload length 1-7)
- Bytes 1-N: UDS payload
- Example: 02 10 01 = Single Frame, 2 bytes, SID 0x10, session 0x01

First Frame (FF) — PCI bytes 0x1H 0xLL:
- Used when UDS message > 7 bytes (multi-frame).
- Byte 0: 0x1H (H = high nibble of length)
- Byte 1: 0xLL (low byte of length)
- Bytes 2-7: first 6 bytes of UDS payload

Consecutive Frame (CF) — PCI byte 0x2N where N = sequence number:
- Carries remaining bytes of multi-frame message.
- Sequence number 0x21, 0x22, ... 0x2F, 0x20, 0x21 (wraps)

Flow Control (FC) — PCI byte 0x3N:
- Sent by receiver to control transmission of CF frames.
- 0x30: ContinueToSend (BS=0 means no limit, STmin=0 means send immediately)
- 0x31: Wait
- 0x32: Overflow

CAN addressing modes:
- Normal (11-bit): Tester TX ID = 0x7E0, ECU RX ID = 0x7E8 (typical)
- Extended (29-bit): used in some OEM implementations

UDS over CAN addressing for 0x22 VIN (17 bytes = multi-frame):
Request:  03 22 F1 90 (single frame — 3 bytes fits in SF)
Response: 14 62 F1 90 [17 VIN bytes] (first frame — 20 bytes total)
          Server sends FF then waits for FC from tester
          21 [bytes 7-13 of VIN]  (CF sequence 1)
          22 [bytes 14-17 of VIN] (CF sequence 2)
"""
    },

    {
        "id": "ISO15765-2_S9_addressing",
        "standard": "ISO15765-2",
        "section": "9",
        "service_sid": "ALL",
        "service_name": "CAN Transport Layer",
        "topic": "CAN IDs and Addressing",
        "content": """
ISO 15765-2 Section 9 — CAN Addressing

Standard OBD/UDS CAN addressing (11-bit):
- Tester physical request: 0x7E0
- ECU physical response: 0x7E8
- Tester functional request: 0x7DF (broadcasts to all ECUs)
- ECU 1 response: 0x7E8
- ECU 2 response: 0x7E9
- ECU N response: 0x7E0 + N + 8

Multi-ECU addressing:
- 0x7E0/0x7E8: ECU 0 (engine/main ECU)
- 0x7E1/0x7E9: ECU 1
- 0x7E2/0x7EA: ECU 2
- up to 0x7E7/0x7EF: ECU 7

Functional addressing (0x7DF):
- Broadcasts to all ECUs on the bus.
- All ECUs that support the requested service shall respond.
- Used for: DiagnosticSessionControl defaultSession, TesterPresent.
- Should NOT be used for physical addressing services.

CAN frame DLC rules for UDS:
- Single Frame: DLC = 3-8 (SF_DL + payload)
- First Frame: DLC = 8 (always full frame)
- Consecutive Frame: DLC = 8 (always full frame, padded with 0xCC or 0xAA)
- Flow Control: DLC = 3-8

Padding byte:
- ISO 15765-2 recommends padding unused bytes with 0xCC.
- Some OEMs use 0xAA or 0x00.
- Padding does not affect UDS message content.
"""
    },

    # ─────────────────────────────────────────────
    # GENERAL UDS — NRC Reference
    # ─────────────────────────────────────────────
    {
        "id": "ISO14229-1_S7.4_nrc_reference",
        "standard": "ISO14229-1",
        "section": "7.4",
        "service_sid": "ALL",
        "service_name": "All Services",
        "topic": "Negative Response Code Reference",
        "content": """
ISO 14229-1 Section 7.4 — Negative Response Codes (NRC) Complete Reference

Negative Response format:
- Byte 0: 0x7F (Negative Response SID)
- Byte 1: SID of service that failed (e.g. 0x10, 0x22)
- Byte 2: NRC value

NRC values:
0x10: generalReject — server cannot perform request, unspecified reason.
0x11: serviceNotSupported — SID not supported in any session.
0x12: subFunctionNotSupported — subfunction not supported (0x10 session types).
0x13: incorrectMessageLengthOrInvalidFormat — wrong request length.
0x14: responseTooLong — response exceeds PDU size.
0x21: busyRepeatRequest — server busy, client should retry.
0x22: conditionsNotCorrect — preconditions for service not met.
0x24: requestSequenceError — wrong order of service requests.
0x25: noResponseFromSubnetComponent — gateway cannot reach subnet ECU.
0x26: failurePreventsExecutionOfRequestedAction — hardware fault.
0x31: requestOutOfRange — DID/parameter not supported.
0x33: securityAccessDenied — security level insufficient.
0x35: invalidKey — wrong security key provided (0x27 service).
0x36: exceededNumberOfAttempts — too many failed security attempts.
0x37: requiredTimeDelayNotExpired — security delay not elapsed.
0x70: uploadDownloadNotAccepted — transfer not accepted.
0x71: transferDataSuspended — data transfer suspended.
0x72: generalProgrammingFailure — flash programming failed.
0x73: wrongBlockSequenceCounter — wrong block number in transfer.
0x78: requestCorrectlyReceivedResponsePending — still processing, wait.
0x7E: subFunctionNotSupportedInActiveSession — subfunction not in current session.
0x7F: serviceNotSupportedInActiveSession — service not in current session.
0x81: rpmTooHigh — RPM condition not met.
0x82: rpmTooLow — RPM condition not met.
0x83: engineIsRunning — engine must be off.
0x84: engineIsNotRunning — engine must be running.
0x85: engineRunTimeTooLow — engine not running long enough.
0x86: temperatureTooHigh — temperature condition not met.
0x87: temperatureTooLow — temperature condition not met.
0x88: vehicleSpeedTooHigh — vehicle must be stationary.
0x89: vehicleSpeedTooLow — vehicle speed condition not met.
0x8A: throttlePedalTooHigh — throttle condition not met.
0x8B: throttlePedalTooLow — throttle condition not met.
0x8C: transmissionRangeNotInNeutral — must be in neutral.
0x8D: transmissionRangeNotInGear — must be in gear.
0x8F: brakeNotApplied — brake must be applied.
0x90: shifterLeverNotInPark — must be in park.
"""
    },

    # ─────────────────────────────────────────────
    # TEST REQUIREMENTS — Summary for TARA
    # ─────────────────────────────────────────────
    {
        "id": "ISO14229-1_TEST_REQUIREMENTS_0x10",
        "standard": "ISO14229-1",
        "section": "9",
        "service_sid": "0x10",
        "service_name": "DiagnosticSessionControl",
        "topic": "Test Requirements Summary",
        "content": """
ISO 14229-1 Test Requirements for DiagnosticSessionControl (0x10)

MANDATORY test cases per ISO 14229-1:

TC_0x10_001: Default Session Positive
- Request: 02 10 01
- Expected: 0x50 positive response with P2/P2* timing params
- P2 assertion: response within P2ServerMax (default 50ms)
- PASS criteria: SID=0x50, session echo=0x01, timing params present

TC_0x10_002: Extended Session Positive  
- Request: 02 10 03
- Expected: 0x50 positive response
- PASS criteria: SID=0x50, session echo=0x03

TC_0x10_003: Invalid Session Type
- Request: 02 10 FF (or any unsupported session type)
- Expected: NRC 0x12 (subFunctionNotSupported)
- PASS criteria: SID=0x7F, failed SID=0x10, NRC=0x12

TC_0x10_004: Timing Boundary Check
- Request: 02 10 01
- Measure: actual response time vs P2ServerMax from response bytes
- PASS criteria: measured_p2_ms <= p2_server_max_ms

TC_0x10_005: SPRMIB bit set (suppress positive response)
- Request: 02 10 81 (0x80 | 0x01 = suppress + defaultSession)
- Expected: NO positive response (server suppresses it)
- PASS criteria: no 0x50 response received within 2 × P2ServerMax

TC_0x10_006: Session timeout (S3Server)
- Enter extendedSession, wait > S3Server (5000ms) without sending request
- Expected: server returns to defaultSession automatically
- Verify: send 0x22 F1 86 (read active session) → should return 0x01

TC_0x10_007: NRC 0x7F (serviceNotSupportedInActiveSession)
- If programmingSession (0x02) requested in conditions that prevent it
- Expected: NRC 0x22 (conditionsNotCorrect)
"""
    },

    {
        "id": "ISO14229-1_TEST_REQUIREMENTS_0x22",
        "standard": "ISO14229-1",
        "section": "11",
        "service_sid": "0x22",
        "service_name": "ReadDataByIdentifier",
        "topic": "Test Requirements Summary",
        "content": """
ISO 14229-1 Test Requirements for ReadDataByIdentifier (0x22)

MANDATORY test cases per ISO 14229-1:

TC_0x22_001: Read VIN (0xF190) Positive
- Request: 03 22 F1 90
- Expected: 0x62 positive response with 17-byte VIN
- PASS criteria: SID=0x62, DID echo=0xF190, data length=17 bytes ASCII
- Note: Must pass in defaultSession WITHOUT security access

TC_0x22_002: Read Active Session (0xF186) Positive
- Request: 03 22 F1 86
- Expected: 0x62 with 1 byte session value
- PASS criteria: SID=0x62, DID=0xF186, value=0x01 (in defaultSession)

TC_0x22_003: Read SW Version (0xF189) Positive
- Request: 03 22 F1 89
- Expected: 0x62 with ASCII version string
- PASS criteria: SID=0x62, DID=0xF189, data is valid ASCII

TC_0x22_004: Unsupported DID — NRC 0x31
- Request: 03 22 FF FF (unsupported DID)
- Expected: NRC 0x31 (requestOutOfRange)
- PASS criteria: SID=0x7F, failed SID=0x22, NRC=0x31

TC_0x22_005: VIN Security Denied Violation Check
- Request: 03 22 F1 90 in defaultSession
- If response is NRC 0x33: TEST FAILS (violation of ISO 14229-1 §11.2)
- VIN MUST be readable without security access

TC_0x22_006: Timing Check
- Request: 03 22 F1 90
- Measure: actual P2 response time
- PASS criteria: measured_p2_ms <= p2_server_max_ms (from 0x10 response params)

TC_0x22_007: Invalid DID length
- Request: 02 22 F1 (only 1 byte DID, should be 2)
- Expected: NRC 0x13 (incorrectMessageLengthOrInvalidFormat)
- PASS criteria: SID=0x7F, NRC=0x13

TC_0x22_008: Multi-frame response handling (VIN)
- VIN response is 20 bytes → requires ISO-TP multi-frame
- Verify: First Frame received, Flow Control sent, Consecutive Frames received
- Verify: Complete VIN assembled correctly from all frames
"""
    },
]
