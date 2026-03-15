"""
VDIP-SIM — ECU Simulator
Flask web UI on port 5001.
Listens on CAN 0x757, replies on 0x75F.
Import ODX to auto-configure DID responses.
Run: python3 vdip_sim.py
"""
import os, sys, json, time, struct, socket, threading
from flask import Flask, request, jsonify, render_template_string

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)

# ── State ─────────────────────────────────────────────────
state = {
    "running": False,
    "session": "defaultSession",
    "session_byte": 0x01,
    "log": [],           # [{ts, dir, can_id, hex, decoded}]
    "did_store": {
        "F190": {"name": "VIN",                  "value": "VDIPSIM00000000001", "len": 17},
        "F189": {"name": "ecuSoftwareVersion",    "value": "SW_V01.00.00",       "len": 10},
        "F18C": {"name": "ecuSerialNumber",       "value": "SN0000001",          "len": 9},
        "F18B": {"name": "ecuManufacturingDate",  "value": "230101",             "len": 6},
        "F186": {"name": "activeDiagnosticSession","value": "01",                "len": 1},
        "F191": {"name": "ecuHardwareNumber",     "value": "HW_V01.00",          "len": 9},
    },
    "nrc_override": {},   # DID → NRC to force
    "stats": {"rx": 0, "tx": 0, "errors": 0}
}
state_lock = threading.Lock()

NRC_NAMES = {
    0x10:"generalReject", 0x11:"serviceNotSupported",
    0x12:"subFunctionNotSupported", 0x13:"incorrectMessageLength",
    0x22:"conditionsNotCorrect", 0x31:"requestOutOfRange",
    0x33:"securityAccessDenied", 0x7F:"serviceNotSupportedInSession"
}

def log_frame(direction, can_id, data, decoded=""):
    ts = time.strftime("%H:%M:%S") + f".{int(time.time()*1000)%1000:03d}"
    with state_lock:
        state["log"].insert(0, {
            "ts": ts, "dir": direction,
            "id": hex(can_id), "hex": data.hex(" ").upper(), "decoded": decoded
        })
        state["log"] = state["log"][:200]

# ── CAN Socket ────────────────────────────────────────────
class SimSocket:
    FMT = "=IB3x8s"
    SZ  = struct.calcsize("=IB3x8s")
    def __init__(self): self.s = None
    def open(self):
        try:
            self.s = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
            self.s.bind(("can0",)); self.s.settimeout(0.5); return True
        except Exception as e:
            print(f"SIM socket error: {e}"); return False
    def close(self):
        if self.s: self.s.close(); self.s = None
    def recv(self):
        try:
            raw = self.s.recv(self.SZ)
            can_id, dlc, data = struct.unpack(self.FMT, raw)
            return can_id & 0x1FFFFFFF, data[:dlc]
        except socket.timeout: return None, None
        except: return None, None
    def send(self, can_id, data):
        pad = data.ljust(8, b'\x00')[:8]
        try: self.s.send(struct.pack(self.FMT, can_id, len(data), pad)); return True
        except: return False

sim_sock = SimSocket()

# ── UDS Response Logic ────────────────────────────────────
def handle_uds(payload):
    if not payload or len(payload) < 1:
        return None
    sid = payload[0]

    # 0x10 DiagnosticSessionControl
    if sid == 0x10:
        if len(payload) < 2:
            return bytes([0x7F, 0x10, 0x13])
        sub = payload[1] & 0x7F
        session_map = {
            0x01: ("defaultSession", 0x01),
            0x02: ("programmingSession", 0x02),
            0x03: ("extendedDiagnosticSession", 0x03),
        }
        if sub not in session_map:
            return bytes([0x7F, 0x10, 0x12])
        name, byte = session_map[sub]
        with state_lock:
            state["session"] = name
            state["session_byte"] = byte
            state["did_store"]["F186"]["value"] = f"{byte:02X}"
        # P2=25ms P2*=500ms
        return bytes([0x50, sub, 0x00, 0x19, 0x01, 0xF4])

    # 0x22 ReadDataByIdentifier
    elif sid == 0x22:
        if len(payload) < 3:
            return bytes([0x7F, 0x22, 0x13])
        did_int = (payload[1] << 8) | payload[2]
        did_key = f"{did_int:04X}"
        with state_lock:
            nrc_override = state["nrc_override"].get(did_key)
            did_entry = state["did_store"].get(did_key)
        if nrc_override:
            return bytes([0x7F, 0x22, nrc_override])
        if not did_entry:
            return bytes([0x7F, 0x22, 0x31])  # requestOutOfRange
        # build response
        val_str = did_entry["value"]
        try:
            val_bytes = bytes.fromhex(val_str) if all(c in "0123456789ABCDEFabcdef" for c in val_str) and len(val_str) % 2 == 0 else val_str.encode("ascii")
        except:
            val_bytes = val_str.encode("ascii")
        return bytes([0x62, payload[1], payload[2]]) + val_bytes

    # 0x3E TesterPresent
    elif sid == 0x3E:
        sub = payload[1] if len(payload) > 1 else 0x00
        if sub & 0x80:  # suppressPositiveResponse
            return None
        return bytes([0x7E, 0x00])

    # 0x11 ECUReset
    elif sid == 0x11:
        with state_lock:
            state["session"] = "defaultSession"
            state["session_byte"] = 0x01
        return bytes([0x51, 0x01])

    # Unsupported
    else:
        return bytes([0x7F, sid, 0x11])

def decode_uds(payload, direction):
    if not payload: return ""
    sid = payload[0]
    if sid == 0x10: return f"DSC sub={hex(payload[1]&0x7F) if len(payload)>1 else '?'}"
    if sid == 0x22 and len(payload)>=3: return f"RDBI DID=0x{payload[1]:02X}{payload[2]:02X}"
    if sid == 0x3E: return "TesterPresent"
    if sid == 0x50: return f"DSC+pos session={hex(payload[1])}" if len(payload)>1 else "DSC+pos"
    if sid == 0x62 and len(payload)>=3:
        did = f"0x{payload[1]:02X}{payload[2]:02X}"
        try: val = payload[3:].decode("ascii").strip()
        except: val = payload[3:].hex().upper()
        return f"RDBI+pos DID={did} val={val}"
    if sid == 0x7F and len(payload)>=3:
        return f"NRC 0x{payload[2]:02X} {NRC_NAMES.get(payload[2],'?')} for SID=0x{payload[1]:02X}"
    return f"SID=0x{sid:02X}"

# ── Background CAN thread ─────────────────────────────────
def sim_thread():
    print("SIM thread starting...")
    if not sim_sock.open():
        print("SIM: cannot open CAN socket"); return
    print("SIM: listening on can0 TX_ID=0x757 RX_ID=0x75F")

    while state["running"]:
        can_id, raw_data = sim_sock.recv()
        if can_id is None: continue
        if can_id != 0x757: continue

        with state_lock: state["stats"]["rx"] += 1

        # Parse ISO-TP
        if len(raw_data) < 2: continue
        frame_type = (raw_data[0] >> 4) & 0xF
        if frame_type == 0:
            length = raw_data[0] & 0x0F
            payload = raw_data[1:1+length]
        else:
            payload = raw_data[1:]

        decoded_rx = decode_uds(payload, "RX")
        log_frame("RX", can_id, raw_data, decoded_rx)

        # Build UDS response
        uds_resp = handle_uds(payload)
        if uds_resp is None: continue

        # Wrap in ISO-TP single frame
        resp_frame = bytes([len(uds_resp)]) + uds_resp
        resp_frame = resp_frame.ljust(8, b'\xAA')

        ok = sim_sock.send(0x75F, resp_frame)
        if ok:
            decoded_tx = decode_uds(uds_resp, "TX")
            log_frame("TX", 0x75F, resp_frame, decoded_tx)
            with state_lock: state["stats"]["tx"] += 1
        else:
            with state_lock: state["stats"]["errors"] += 1

    sim_sock.close()
    print("SIM thread stopped")

sim_thread_obj = None

# ── Flask Routes ──────────────────────────────────────────
@app.route("/")
def index():
    return render_template_string(HTML_SIM)

@app.route("/api/start", methods=["POST"])
def start():
    global sim_thread_obj
    if state["running"]:
        return jsonify({"ok": False, "msg": "already running"})
    state["running"] = True
    sim_thread_obj = threading.Thread(target=sim_thread, daemon=True)
    sim_thread_obj.start()
    return jsonify({"ok": True, "msg": "simulator started"})

@app.route("/api/stop", methods=["POST"])
def stop():
    state["running"] = False
    return jsonify({"ok": True, "msg": "simulator stopped"})

@app.route("/api/status")
def status():
    with state_lock:
        return jsonify({
            "running": state["running"],
            "session": state["session"],
            "stats": state["stats"],
            "log": state["log"][:50]
        })

@app.route("/api/dids")
def get_dids():
    with state_lock:
        return jsonify(state["did_store"])

@app.route("/api/did/<did_key>", methods=["POST"])
def set_did(did_key):
    data = request.json or {}
    with state_lock:
        if did_key in state["did_store"]:
            state["did_store"][did_key]["value"] = data.get("value", "")
    return jsonify({"ok": True})

@app.route("/api/nrc/<did_key>", methods=["POST"])
def set_nrc(did_key):
    data = request.json or {}
    nrc = data.get("nrc", 0)
    with state_lock:
        if nrc:
            state["nrc_override"][did_key] = nrc
        else:
            state["nrc_override"].pop(did_key, None)
    return jsonify({"ok": True})

@app.route("/api/import-odx", methods=["POST"])
def import_odx():
    f = request.files.get("file")
    if not f: return jsonify({"ok": False, "msg": "no file"})
    xml = f.read().decode("utf-8", errors="ignore")
    # Simple ODX DID extraction
    import re
    dids_found = re.findall(r'SHORT-NAME[^>]*>([^<]*(?:VIN|F1[0-9A-F]{2}|RDBI|ReadData)[^<]*)<', xml, re.I)
    return jsonify({"ok": True, "msg": f"ODX parsed, {len(dids_found)} services found"})

HTML_SIM = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>VDIP-SIM — ECU Simulator</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; font-family: monospace; }
body { background: #0f0f0f; color: #d4d4d4; padding: 16px; font-size: 13px; }
h1 { color: #4ec9b0; font-size: 16px; margin-bottom: 4px; }
.sub { color: #888; font-size: 11px; margin-bottom: 16px; }
.row { display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.card { background: #1e1e1e; border: 1px solid #333; border-radius: 6px; padding: 12px; flex: 1; min-width: 240px; }
.card h2 { color: #9cdcfe; font-size: 12px; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: bold; }
.badge-green { background: #1b3a1b; color: #4ec9b0; border: 1px solid #2d6a2d; }
.badge-gray  { background: #2a2a2a; color: #888;    border: 1px solid #444; }
.badge-red   { background: #3a1b1b; color: #f48771; border: 1px solid #6a2d2d; }
btn, .btn { padding: 6px 14px; border: 1px solid #555; background: #2d2d2d; color: #d4d4d4; border-radius: 4px; cursor: pointer; font-size: 12px; font-family: monospace; }
.btn:hover { background: #3d3d3d; }
.btn-green { border-color: #2d6a2d; color: #4ec9b0; }
.btn-red   { border-color: #6a2d2d; color: #f48771; }
.stat { text-align: center; }
.stat .val { font-size: 22px; color: #4ec9b0; font-weight: bold; }
.stat .lbl { font-size: 10px; color: #666; margin-top: 2px; }
.did-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.did-key { color: #ce9178; width: 44px; }
.did-name { color: #888; width: 150px; font-size: 11px; overflow: hidden; }
.did-val { background: #0f0f0f; border: 1px solid #333; color: #d4d4d4; padding: 3px 6px; border-radius: 3px; font-family: monospace; font-size: 12px; width: 180px; }
.nrc-sel { background: #0f0f0f; border: 1px solid #333; color: #d4d4d4; padding: 3px 4px; border-radius: 3px; font-size: 11px; }
.log-box { height: 260px; overflow-y: auto; background: #0a0a0a; border-radius: 4px; padding: 8px; }
.log-entry { margin-bottom: 4px; line-height: 1.5; }
.ts { color: #555; }
.rx { color: #569cd6; }
.tx { color: #4ec9b0; }
.hex { color: #ce9178; }
.dec { color: #888; font-size: 11px; margin-left: 4px; }
.session-default  { color: #4ec9b0; }
.session-extended { color: #dcdcaa; }
.session-prog     { color: #f48771; }
#status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #555; margin-right: 6px; }
#status-dot.on { background: #4ec9b0; box-shadow: 0 0 6px #4ec9b0; }
</style>
</head>
<body>
<h1>&#9679; VDIP-SIM <span style="color:#888;font-size:13px;">— ECU Simulator</span></h1>
<div class="sub">CAN RX: 0x757 &nbsp;|&nbsp; CAN TX: 0x75F &nbsp;|&nbsp; 500kbps &nbsp;|&nbsp; can0</div>

<div class="row">
  <div class="card" style="flex:0 0 auto;">
    <h2>Control</h2>
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
      <span id="status-dot"></span>
      <span id="status-txt" style="color:#888;">stopped</span>
    </div>
    <div style="display:flex;gap:8px;">
      <button class="btn btn-green" onclick="startSim()">&#9654; Start</button>
      <button class="btn btn-red"   onclick="stopSim()">&#9632; Stop</button>
    </div>
  </div>
  <div class="card" style="flex:0 0 auto;">
    <h2>Session</h2>
    <div id="session-badge" class="badge badge-gray">defaultSession</div>
  </div>
  <div class="card" style="flex:0 0 auto;">
    <h2>Stats</h2>
    <div style="display:flex;gap:20px;">
      <div class="stat"><div class="val" id="stat-rx">0</div><div class="lbl">RX</div></div>
      <div class="stat"><div class="val" id="stat-tx">0</div><div class="lbl">TX</div></div>
      <div class="stat"><div class="val" id="stat-err" style="color:#f48771;">0</div><div class="lbl">ERR</div></div>
    </div>
  </div>
  <div class="card" style="flex:0 0 auto;">
    <h2>Import ODX</h2>
    <input type="file" id="odx-file" accept=".odx,.pdx" style="display:none" onchange="importODX()">
    <button class="btn" onclick="document.getElementById('odx-file').click()">&#128196; Load ODX</button>
    <div id="odx-msg" style="color:#888;font-size:11px;margin-top:6px;"></div>
  </div>
</div>

<div class="row">
  <div class="card" style="min-width:520px;">
    <h2>DID Store &nbsp;<span style="color:#555;font-weight:normal;font-size:10px;">— edit values then press Enter</span></h2>
    <div id="did-table"></div>
  </div>
</div>

<div class="row">
  <div class="card">
    <h2>Bus Activity Log &nbsp;<button class="btn" style="font-size:10px;padding:2px 8px;" onclick="clearLog()">clear</button></h2>
    <div class="log-box" id="log-box">
      <div style="color:#555;">Waiting for frames...</div>
    </div>
  </div>
</div>

<script>
let logData = [];
let didData = {};

async function startSim() {
  const r = await fetch('/api/start', {method:'POST'});
  const d = await r.json();
  if (!d.ok) alert(d.msg);
}
async function stopSim() {
  await fetch('/api/stop', {method:'POST'});
}
async function importODX() {
  const f = document.getElementById('odx-file').files[0];
  if (!f) return;
  const fd = new FormData(); fd.append('file', f);
  const r = await fetch('/api/import-odx', {method:'POST', body:fd});
  const d = await r.json();
  document.getElementById('odx-msg').textContent = d.msg || '';
}
function clearLog() {
  logData = [];
  renderLog();
}
function renderLog() {
  const box = document.getElementById('log-box');
  if (!logData.length) { box.innerHTML='<div style="color:#555;">No frames yet...</div>'; return; }
  box.innerHTML = logData.slice(0,80).map(e => {
    const dir_cls = e.dir==='RX' ? 'rx' : 'tx';
    return '<div class="log-entry"><span class="ts">'+e.ts+'</span> ' +
      '<span class="'+dir_cls+'">'+e.dir+'</span> ' +
      '<span style="color:#555;">'+e.id+'</span> ' +
      '<span class="hex">'+e.hex+'</span>' +
      (e.decoded ? '<span class="dec">'+e.decoded+'</span>' : '') +
      '</div>';
  }).join('');
}
function renderDIDs() {
  const t = document.getElementById('did-table');
  const nrcOpts = '<option value="">OK</option>' +
    '<option value="22">0x22 condNotCorrect</option>' +
    '<option value="31">0x31 outOfRange</option>' +
    '<option value="33">0x33 secAccDenied</option>' +
    '<option value="7F">0x7F notInSession</option>';
  t.innerHTML = Object.entries(didData).map(([key, d]) =>
    '<div class="did-row">' +
    '<span class="did-key">0x'+key+'</span>' +
    '<span class="did-name">'+d.name+'</span>' +
    '<input class="did-val" value="'+d.value+'" onchange="saveDID(\''+key+'\',this.value)">' +
    '<select class="nrc-sel" onchange="saveNRC(\''+key+'\',this.value)">'+nrcOpts+'</select>' +
    '</div>'
  ).join('');
}
async function saveDID(key, val) {
  await fetch('/api/did/'+key, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({value:val})});
}
async function saveNRC(key, nrc) {
  await fetch('/api/nrc/'+key, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nrc:parseInt(nrc,16)||0})});
}
async function poll() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    const dot = document.getElementById('status-dot');
    const txt = document.getElementById('status-txt');
    dot.className = d.running ? 'on' : '';
    txt.textContent = d.running ? 'running' : 'stopped';
    txt.style.color = d.running ? '#4ec9b0' : '#888';
    document.getElementById('stat-rx').textContent = d.stats.rx;
    document.getElementById('stat-tx').textContent = d.stats.tx;
    document.getElementById('stat-err').textContent = d.stats.errors;
    const sess = d.session || 'defaultSession';
    const sess_el = document.getElementById('session-badge');
    sess_el.textContent = sess;
    sess_el.className = 'badge ' + (sess.includes('extended')?'badge badge-gray':sess.includes('prog')?'badge badge-red':'badge badge-green');
    if (d.log && d.log.length) { logData = d.log; renderLog(); }
  } catch(e) {}
  // DIDs poll less frequently
}
async function pollDIDs() {
  try {
    const r = await fetch('/api/dids');
    didData = await r.json();
    renderDIDs();
  } catch(e) {}
}
setInterval(poll, 800);
setInterval(pollDIDs, 3000);
pollDIDs();
poll();
</script>
</body>
</html>"""

if __name__ == "__main__":
    print("VDIP-SIM starting on http://0.0.0.0:5001")
    print("CAN: RX=0x757  TX=0x75F  iface=can0")
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
