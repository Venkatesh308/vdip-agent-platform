"""
VDIP-TEST — Diagnostic Test Tool
Flask web UI on port 5000.
Imports ODX, queries STAN for ISO requirements, runs UDS tests via CAN.
Run: python3 vdip_test.py
"""
import os, sys, json, time, struct, socket, threading
from flask import Flask, request, jsonify, render_template_string

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "agents"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "knowledge"))

app = Flask(__name__)

CAN_TX = 0x757
CAN_RX = 0x75F

results_store = []
test_cases    = []
odx_manifest  = None
run_lock      = threading.Lock()

# ── CAN socket ────────────────────────────────────────────
class TestSocket:
    FMT = "=IB3x8s"; SZ = struct.calcsize("=IB3x8s")
    def __init__(self): self.s = None
    def open(self):
        try:
            self.s = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
            self.s.bind(("can0",)); self.s.settimeout(2.0); return True
        except Exception as e: print(f"CAN error: {e}"); return False
    def close(self):
        if self.s: self.s.close(); self.s = None
    def send_recv(self, payload, timeout=0.5):
        frame = bytes([len(payload)]) + payload
        frame = frame.ljust(8, b'\xAA')
        t0 = time.time()
        self.s.send(struct.pack(self.FMT, CAN_TX, 8, frame))
        self.s.settimeout(timeout)
        end = time.time() + timeout
        while time.time() < end:
            try:
                raw = self.s.recv(self.SZ)
                can_id, dlc, data = struct.unpack(self.FMT, raw)
                can_id &= 0x1FFFFFFF
                if can_id != CAN_RX: continue
                p2 = (time.time() - t0) * 1000
                data = data[:dlc]
                ft = (data[0] >> 4) & 0xF
                uds = data[1:1+(data[0]&0xF)] if ft==0 else data[2:]
                if len(uds)>=3 and uds[0]==0x7F and uds[2]==0x78:
                    time.sleep(0.05); continue
                return uds, round(p2, 2), data.hex(" ").upper()
            except socket.timeout: break
        return None, round((time.time()-t0)*1000, 2), ""

# ── Built-in test case library ─────────────────────────────
BUILTIN_TESTS = [
    {"id":"TC_001","group":"0x10","name":"Default session positive",
     "payload":[0x10,0x01],"expect_sid":0x50,"expect_sub":0x01,
     "iso":"ISO14229-1 §9.1","p2_limit":50},
    {"id":"TC_002","group":"0x10","name":"Extended session positive",
     "payload":[0x10,0x03],"expect_sid":0x50,"expect_sub":0x03,
     "iso":"ISO14229-1 §9.1","p2_limit":50},
    {"id":"TC_003","group":"0x10","name":"Return to default session",
     "payload":[0x10,0x01],"expect_sid":0x50,"expect_sub":0x01,
     "iso":"ISO14229-1 §9.3","p2_limit":50},
    {"id":"TC_004","group":"0x10","name":"Invalid session → NRC 0x12",
     "payload":[0x10,0x7F],"expect_sid":0x7F,"expect_nrc":0x12,
     "iso":"ISO14229-1 §9.4","p2_limit":50},
    {"id":"TC_005","group":"0x22","name":"Read VIN 0xF190",
     "payload":[0x22,0xF1,0x90],"expect_sid":0x62,"expect_did":0xF190,
     "iso":"ISO14229-1 §11.2","p2_limit":50},
    {"id":"TC_006","group":"0x22","name":"Read active session 0xF186",
     "payload":[0x22,0xF1,0x86],"expect_sid":0x62,"expect_did":0xF186,
     "iso":"ISO14229-1 §11.2","p2_limit":50},
    {"id":"TC_007","group":"0x22","name":"Read SW version 0xF189",
     "payload":[0x22,0xF1,0x89],"expect_sid":0x62,"expect_did":0xF189,
     "iso":"ISO14229-1 §11.2","p2_limit":50},
    {"id":"TC_008","group":"0x22","name":"Read HW number 0xF191",
     "payload":[0x22,0xF1,0x91],"expect_sid":0x62,"expect_did":0xF191,
     "iso":"ISO14229-1 §11.2","p2_limit":50},
    {"id":"TC_009","group":"0x22","name":"Invalid DID → NRC 0x31",
     "payload":[0x22,0xAB,0xCD],"expect_sid":0x7F,"expect_nrc":0x31,
     "iso":"ISO14229-1 §11.4","p2_limit":50},
    {"id":"TC_010","group":"0x22","name":"Short request → NRC 0x13",
     "payload":[0x22,0xF1],"expect_sid":0x7F,"expect_nrc":0x13,
     "iso":"ISO14229-1 §11.4","p2_limit":50},
    {"id":"TC_011","group":"0x3E","name":"TesterPresent suppress",
     "payload":[0x3E,0x80],"expect_sid":None,
     "iso":"ISO14229-1 §9.3","p2_limit":50},
    {"id":"TC_012","group":"0x11","name":"ECUReset hard reset",
     "payload":[0x11,0x01],"expect_sid":0x51,
     "iso":"ISO14229-1 §7","p2_limit":50},
]

def run_test(tc, sock):
    payload = bytes(tc["payload"])
    uds, p2, raw_hex = sock.send_recv(payload)

    req_hex = payload.hex(" ").upper()
    verdict = "ERROR"
    detail  = ""
    nrc     = ""
    resp_hex = raw_hex

    if uds is None:
        verdict = "TIMEOUT"
        detail  = f"No response after {p2}ms"
    else:
        expect = tc.get("expect_sid")
        if expect is None:
            verdict = "PASS"
            detail  = "suppress — no response expected"
        elif uds[0] == expect:
            # positive response checks
            if expect == 0x50:
                sub = uds[1] if len(uds)>1 else 0
                if sub == tc.get("expect_sub", sub):
                    verdict = "PASS" if p2 <= tc["p2_limit"] else "FAIL"
                    detail  = f"P2={p2}ms limit={tc['p2_limit']}ms"
                    if len(uds)>=6:
                        detail += f" ECU_P2={(uds[2]<<8|uds[3])}ms"
                else:
                    verdict = "FAIL"; detail = f"sub echo {hex(sub)} != {hex(tc['expect_sub'])}"
            elif expect == 0x62:
                resp_did = (uds[1]<<8|uds[2]) if len(uds)>=3 else 0
                if resp_did == tc.get("expect_did", resp_did):
                    verdict = "PASS" if p2 <= tc["p2_limit"] else "FAIL"
                    data = uds[3:]
                    try: val = data.decode("ascii").strip()
                    except: val = data.hex().upper()
                    detail = f"P2={p2}ms  val={val}"
                else:
                    verdict = "FAIL"; detail = f"DID echo mismatch"
            elif expect == 0x7F:
                got_nrc = uds[2] if len(uds)>=3 else 0
                exp_nrc = tc.get("expect_nrc", got_nrc)
                nrc = hex(got_nrc)
                verdict = "PASS" if got_nrc == exp_nrc else "FAIL"
                detail  = f"NRC={hex(got_nrc)} expected={hex(exp_nrc)}"
            else:
                verdict = "PASS" if p2 <= tc["p2_limit"] else "FAIL"
                detail  = f"P2={p2}ms"
        elif uds[0] == 0x7F:
            got_nrc = uds[2] if len(uds)>=3 else 0
            nrc = hex(got_nrc)
            if tc.get("expect_sid") == 0x7F:
                exp_nrc = tc.get("expect_nrc", got_nrc)
                verdict = "PASS" if got_nrc == exp_nrc else "FAIL"
                detail  = f"NRC={hex(got_nrc)} expected={hex(exp_nrc)}"
            else:
                verdict = "FAIL"
                detail  = f"Unexpected NRC={hex(got_nrc)}"
        else:
            verdict = "FAIL"
            detail  = f"Unexpected SID={hex(uds[0])}"

    return {
        "id": tc["id"], "group": tc["group"], "name": tc["name"],
        "iso": tc.get("iso",""), "req_hex": req_hex, "resp_hex": resp_hex,
        "verdict": verdict, "p2": p2, "p2_limit": tc["p2_limit"],
        "detail": detail, "nrc": nrc,
        "ts": time.strftime("%H:%M:%S")
    }

# ── Flask routes ──────────────────────────────────────────
@app.route("/")
def index():
    return render_template_string(HTML_TEST)

@app.route("/api/tests")
def get_tests():
    return jsonify(BUILTIN_TESTS)

@app.route("/api/run", methods=["POST"])
def run_all():
    if not run_lock.acquire(blocking=False):
        return jsonify({"ok": False, "msg": "run in progress"})
    try:
        data = request.json or {}
        selected_ids = data.get("ids", [tc["id"] for tc in BUILTIN_TESTS])
        to_run = [tc for tc in BUILTIN_TESTS if tc["id"] in selected_ids]
        sock = TestSocket()
        if not sock.open():
            return jsonify({"ok": False, "msg": "Cannot open CAN socket. Check: sudo ip link set can0 up type can bitrate 500000"})
        results = []
        try:
            for tc in to_run:
                r = run_test(tc, sock)
                results.append(r)
                time.sleep(0.08)
        finally:
            sock.close()
        global results_store
        results_store = results
        passed  = sum(1 for r in results if r["verdict"]=="PASS")
        failed  = sum(1 for r in results if r["verdict"]=="FAIL")
        timeout = sum(1 for r in results if r["verdict"]=="TIMEOUT")
        os.makedirs("results", exist_ok=True)
        with open("results/latest.json","w") as f:
            json.dump(results, f, indent=2)
        return jsonify({"ok":True,"results":results,"summary":{"total":len(results),"passed":passed,"failed":failed,"timeout":timeout}})
    finally:
        run_lock.release()

@app.route("/api/results")
def get_results():
    return jsonify(results_store)

@app.route("/api/stan", methods=["POST"])
def query_stan():
    data = request.json or {}
    q = data.get("q","")
    try:
        from stan_agent import STANAgent
        stan = STANAgent()
        stan.setup()
        stan.ingest_knowledge()
        r = stan.query(q)
        return jsonify({"ok":True,"answer":r.answer,"sources":r.sources,"confidence":r.confidence})
    except Exception as e:
        return jsonify({"ok":False,"msg":str(e)})

HTML_TEST = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>VDIP-TEST — Diagnostic Test Tool</title>
<style>
* { box-sizing:border-box; margin:0; padding:0; font-family:monospace; }
body { background:#0f0f0f; color:#d4d4d4; padding:16px; font-size:13px; }
h1 { color:#569cd6; font-size:16px; margin-bottom:4px; }
.sub { color:#888; font-size:11px; margin-bottom:16px; }
.row { display:flex; gap:12px; margin-bottom:12px; flex-wrap:wrap; }
.card { background:#1e1e1e; border:1px solid #333; border-radius:6px; padding:12px; flex:1; min-width:200px; }
.card h2 { color:#9cdcfe; font-size:12px; margin-bottom:10px; text-transform:uppercase; letter-spacing:1px; }
.btn { padding:6px 14px; border:1px solid #555; background:#2d2d2d; color:#d4d4d4; border-radius:4px; cursor:pointer; font-size:12px; font-family:monospace; }
.btn:hover { background:#3d3d3d; }
.btn:disabled { opacity:0.4; cursor:not-allowed; }
.btn-blue { border-color:#1e3a5f; color:#569cd6; }
.btn-green { border-color:#2d6a2d; color:#4ec9b0; }
.stat .val { font-size:22px; font-weight:bold; }
.stat .lbl { font-size:10px; color:#666; margin-top:2px; }
table { width:100%; border-collapse:collapse; }
th { text-align:left; padding:6px 8px; color:#888; font-size:11px; border-bottom:1px solid #333; white-space:nowrap; }
td { padding:5px 8px; border-bottom:1px solid #222; vertical-align:top; }
tr:hover td { background:#252525; }
.v-PASS    { color:#4ec9b0; font-weight:bold; }
.v-FAIL    { color:#f48771; font-weight:bold; }
.v-TIMEOUT { color:#dcdcaa; font-weight:bold; }
.v-ERROR   { color:#f48771; }
.v-PENDING { color:#555; }
.group-tag { display:inline-block; padding:1px 5px; border-radius:2px; font-size:10px; background:#1a2a3a; color:#569cd6; border:1px solid #1e3a5f; }
.cb { width:13px; height:13px; cursor:pointer; }
.hex-sm { color:#ce9178; font-size:11px; }
.iso-ref { color:#888; font-size:10px; }
.detail-td { color:#888; font-size:11px; max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.stan-box { background:#0a0a0a; border:1px solid #333; border-radius:4px; padding:10px; margin-top:8px; font-size:12px; color:#d4d4d4; white-space:pre-wrap; max-height:200px; overflow-y:auto; }
#progress { height:3px; background:#1e3a5f; border-radius:2px; margin:8px 0; transition:width 0.3s; }
</style>
</head>
<body>
<h1>&#9654; VDIP-TEST <span style="color:#888;font-size:13px;">— Diagnostic Test Tool</span></h1>
<div class="sub">CAN TX: 0x757 &nbsp;|&nbsp; CAN RX: 0x75F &nbsp;|&nbsp; 500kbps &nbsp;|&nbsp; can0 &nbsp;|&nbsp; Target: VDIP-SIM or real TBM</div>

<div class="row">
  <div class="card" style="flex:0 0 auto;">
    <h2>Run</h2>
    <div style="display:flex;gap:8px;align-items:center;">
      <button class="btn btn-green" id="btn-run" onclick="runTests()">&#9654; Run Selected</button>
      <button class="btn btn-blue"  onclick="selectAll()">All</button>
      <button class="btn"           onclick="selectNone()">None</button>
    </div>
    <div id="progress" style="width:0%"></div>
    <div id="run-msg" style="color:#888;font-size:11px;margin-top:4px;"></div>
  </div>
  <div class="card" style="flex:0 0 auto;">
    <h2>Summary</h2>
    <div style="display:flex;gap:20px;">
      <div class="stat"><div class="val" id="s-pass" style="color:#4ec9b0;">–</div><div class="lbl">PASS</div></div>
      <div class="stat"><div class="val" id="s-fail" style="color:#f48771;">–</div><div class="lbl">FAIL</div></div>
      <div class="stat"><div class="val" id="s-time" style="color:#dcdcaa;">–</div><div class="lbl">TIMEOUT</div></div>
      <div class="stat"><div class="val" id="s-total" style="color:#888;">–</div><div class="lbl">TOTAL</div></div>
    </div>
  </div>
  <div class="card">
    <h2>STAN — ISO Query</h2>
    <div style="display:flex;gap:8px;">
      <input type="text" id="stan-q" placeholder="e.g. P2ServerMax timing for 0x10" style="flex:1;background:#0f0f0f;border:1px solid #333;color:#d4d4d4;padding:5px 8px;border-radius:3px;font-family:monospace;font-size:12px;">
      <button class="btn btn-blue" onclick="querySTAN()">Ask STAN</button>
    </div>
    <div id="stan-ans" class="stan-box" style="display:none;"></div>
  </div>
</div>

<div class="card">
  <h2>Test Cases</h2>
  <table>
    <thead>
      <tr>
        <th><input type="checkbox" class="cb" id="cb-all" onchange="toggleAll(this.checked)"></th>
        <th>ID</th><th>Group</th><th>Name</th><th>Request</th>
        <th>Verdict</th><th>P2 (ms)</th><th>Response</th><th>Detail</th><th>ISO ref</th>
      </tr>
    </thead>
    <tbody id="test-tbody"></tbody>
  </table>
</div>

<script>
let testMeta = {};

async function loadTests() {
  const r = await fetch('/api/tests');
  const tests = await r.json();
  const tbody = document.getElementById('test-tbody');
  tbody.innerHTML = tests.map(t => {
    testMeta[t.id] = t;
    return '<tr id="row-'+t.id+'">' +
      '<td><input type="checkbox" class="cb tc-cb" value="'+t.id+'" checked></td>' +
      '<td style="color:#888;font-size:11px;">'+t.id+'</td>' +
      '<td><span class="group-tag">'+t.group+'</span></td>' +
      '<td>'+t.name+'</td>' +
      '<td class="hex-sm">'+t.payload.map(b=>(b<16?'0':'')+b.toString(16).toUpperCase()).join(' ')+'</td>' +
      '<td class="v-PENDING" id="v-'+t.id+'">–</td>' +
      '<td id="p2-'+t.id+'" style="color:#888;">–</td>' +
      '<td class="hex-sm" id="res-'+t.id+'">–</td>' +
      '<td class="detail-td" id="det-'+t.id+'">–</td>' +
      '<td class="iso-ref">'+t.iso+'</td>' +
      '</tr>';
  }).join('');
}

async function runTests() {
  const selected = [...document.querySelectorAll('.tc-cb:checked')].map(c=>c.value);
  if (!selected.length) { alert('Select at least one test'); return; }
  const btn = document.getElementById('btn-run');
  btn.disabled = true; btn.textContent = '⏳ Running...';
  document.getElementById('run-msg').textContent = 'Sending frames to CAN...';
  document.getElementById('progress').style.width = '20%';

  try {
    const r = await fetch('/api/run', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ids:selected})
    });
    document.getElementById('progress').style.width = '80%';
    const d = await r.json();
    if (!d.ok) { alert(d.msg); return; }
    d.results.forEach(res => {
      const vEl = document.getElementById('v-'+res.id);
      if (vEl) { vEl.textContent=res.verdict; vEl.className='v-'+res.verdict; }
      const p2El = document.getElementById('p2-'+res.id);
      if (p2El) {
        const over = res.p2 > res.p2_limit;
        p2El.innerHTML = '<span style="color:'+(over?'#f48771':'#4ec9b0')+'">'+res.p2+'</span>';
      }
      const resEl = document.getElementById('res-'+res.id);
      if (resEl) resEl.textContent = res.resp_hex ? res.resp_hex.slice(0,24)+(res.resp_hex.length>24?'…':'') : 'none';
      const detEl = document.getElementById('det-'+res.id);
      if (detEl) { detEl.textContent=res.detail; detEl.title=res.detail; }
    });
    const s = d.summary;
    document.getElementById('s-pass').textContent  = s.passed;
    document.getElementById('s-fail').textContent  = s.failed;
    document.getElementById('s-time').textContent  = s.timeout;
    document.getElementById('s-total').textContent = s.total;
    document.getElementById('run-msg').textContent = 'Done — results/latest.json saved';
    document.getElementById('progress').style.width = '100%';
  } catch(e) {
    document.getElementById('run-msg').textContent = 'Error: '+e.message;
  } finally {
    btn.disabled=false; btn.textContent='▶ Run Selected';
  }
}

async function querySTAN() {
  const q = document.getElementById('stan-q').value;
  if (!q) return;
  const box = document.getElementById('stan-ans');
  box.style.display='block'; box.textContent='Querying STAN...';
  try {
    const r = await fetch('/api/stan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q})});
    const d = await r.json();
    if (d.ok) {
      box.textContent = '['+d.confidence+'] '+d.sources.join(', ')+'\n\n'+d.answer;
    } else {
      box.textContent = 'STAN error: '+d.msg+'\n(Start STAN agent first or check imports)';
    }
  } catch(e) { box.textContent='Error: '+e.message; }
}

function selectAll()  { document.querySelectorAll('.tc-cb').forEach(c=>c.checked=true);  document.getElementById('cb-all').checked=true; }
function selectNone() { document.querySelectorAll('.tc-cb').forEach(c=>c.checked=false); document.getElementById('cb-all').checked=false; }
function toggleAll(v) { document.querySelectorAll('.tc-cb').forEach(c=>c.checked=v); }

loadTests();
</script>
</body>
</html>"""

if __name__ == "__main__":
    print("VDIP-TEST starting on http://0.0.0.0:5000")
    print("CAN: TX=0x757  RX=0x75F  iface=can0")
    print("STAN integration: will try to import from src/agents/")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
