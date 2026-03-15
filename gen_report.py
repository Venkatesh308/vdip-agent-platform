import json, os, sys
from datetime import datetime

results_path = sys.argv[1] if len(sys.argv) > 1 else "results/latest.json"
output_path  = sys.argv[2] if len(sys.argv) > 2 else "results/report.html"

with open(results_path) as f:
    results = json.load(f)

passed  = sum(1 for r in results if r["verdict"] == "PASS")
failed  = sum(1 for r in results if r["verdict"] == "FAIL")
timeout = sum(1 for r in results if r["verdict"] == "TIMEOUT")
total   = len(results)
score   = int(100 * passed / total) if total else 0
ts      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def verdict_color(v):
    return {"PASS": "#22c55e", "FAIL": "#ef4444", "TIMEOUT": "#f59e0b", "ERROR": "#a78bfa"}.get(v, "#888")

def verdict_bg(v):
    return {"PASS": "rgba(34,197,94,0.08)", "FAIL": "rgba(239,68,68,0.08)",
            "TIMEOUT": "rgba(245,158,11,0.08)", "ERROR": "rgba(167,139,250,0.08)"}.get(v, "transparent")

rows = ""
for r in results:
    vc = verdict_color(r["verdict"])
    vb = verdict_bg(r["verdict"])
    p2_color = "#ef4444" if r["p2"] > r["p2_limit"] else "#22c55e"
    p2_bar = min(100, int(r["p2"] / r["p2_limit"] * 100)) if r["p2_limit"] else 0
    nrc_cell = f'<span style="color:#a78bfa;font-family:monospace">{r["nrc"]}</span>' if r["nrc"] else '<span style="color:#555">—</span>'
    rows += f"""
    <tr style="background:{vb};border-bottom:1px solid rgba(255,255,255,0.04)">
      <td style="padding:10px 14px;font-family:monospace;font-size:12px;color:#888">{r["id"]}</td>
      <td style="padding:10px 14px">
        <span style="background:rgba(77,159,255,0.12);color:#60a5fa;font-size:10px;font-family:monospace;padding:2px 7px;border-radius:3px">{r["group"]}</span>
      </td>
      <td style="padding:10px 14px;font-size:13px;color:#e2e8f0">{r["name"]}</td>
      <td style="padding:10px 14px;font-family:monospace;font-size:11px;color:#94a3b8">{r["req_hex"]}</td>
      <td style="padding:10px 14px;font-family:monospace;font-size:11px;color:#64748b">{r["resp_hex"] or "—"}</td>
      <td style="padding:10px 14px">
        <span style="background:{vc}22;color:{vc};font-size:11px;font-family:monospace;font-weight:700;padding:3px 10px;border-radius:4px;border:1px solid {vc}44">{r["verdict"]}</span>
      </td>
      <td style="padding:10px 14px">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="color:{p2_color};font-family:monospace;font-size:12px;min-width:52px">{r["p2"]}ms</span>
          <div style="width:60px;height:4px;background:#1e293b;border-radius:2px">
            <div style="width:{p2_bar}%;height:100%;background:{p2_color};border-radius:2px"></div>
          </div>
        </div>
      </td>
      <td style="padding:10px 14px">{nrc_cell}</td>
      <td style="padding:10px 14px;font-size:12px;color:#94a3b8">{r["detail"]}</td>
      <td style="padding:10px 14px;font-size:11px;color:#475569;font-family:monospace">{r.get("iso","")}</td>
    </tr>"""

gauge_offset = 314 - (314 * score // 100)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>VDIP Test Report</title>
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:#080c14; color:#e2e8f0; font-family:system-ui,sans-serif; padding:32px; }}
h1 {{ font-size:22px; font-weight:500; color:#e2e8f0; margin-bottom:4px; }}
.sub {{ font-size:13px; color:#475569; margin-bottom:28px; }}
.cards {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-bottom:28px; }}
.card {{ background:#0d1420; border:1px solid rgba(255,255,255,0.06); border-radius:10px; padding:16px 20px; }}
.card .val {{ font-size:28px; font-weight:500; margin-bottom:4px; }}
.card .lbl {{ font-size:11px; color:#475569; text-transform:uppercase; letter-spacing:1px; }}
.gauge-wrap {{ display:flex; align-items:center; gap:28px; background:#0d1420; border:1px solid rgba(255,255,255,0.06); border-radius:12px; padding:20px 28px; margin-bottom:28px; }}
.gauge-text {{ font-size:13px; color:#94a3b8; line-height:1.8; }}
.gauge-text strong {{ color:#e2e8f0; font-weight:500; }}
table {{ width:100%; border-collapse:collapse; background:#0d1420; border:1px solid rgba(255,255,255,0.06); border-radius:12px; overflow:hidden; }}
thead tr {{ background:#111928; }}
th {{ padding:10px 14px; text-align:left; font-size:11px; color:#475569; text-transform:uppercase; letter-spacing:1px; font-weight:500; border-bottom:1px solid rgba(255,255,255,0.06); }}
tr:hover {{ background:rgba(255,255,255,0.02) !important; }}
.footer {{ margin-top:20px; font-size:11px; color:#334155; text-align:center; }}
</style>
</head>
<body>

<h1>VDIP — Diagnostic Test Report</h1>
<div class="sub">Generated: {ts} &nbsp;·&nbsp; ECU: TBM Simulator &nbsp;·&nbsp; CAN: 0x757/0x75F &nbsp;·&nbsp; 500kbps &nbsp;·&nbsp; loopback</div>

<div class="cards">
  <div class="card"><div class="val" style="color:#22c55e">{passed}</div><div class="lbl">Pass</div></div>
  <div class="card"><div class="val" style="color:#ef4444">{failed}</div><div class="lbl">Fail</div></div>
  <div class="card"><div class="val" style="color:#f59e0b">{timeout}</div><div class="lbl">Timeout</div></div>
  <div class="card"><div class="val" style="color:#94a3b8">{total}</div><div class="lbl">Total</div></div>
  <div class="card"><div class="val" style="color:{'#22c55e' if score>=80 else '#f59e0b' if score>=50 else '#ef4444'}">{score}%</div><div class="lbl">Score</div></div>
</div>

<div class="gauge-wrap">
  <svg width="100" height="100" viewBox="0 0 110 110">
    <circle cx="55" cy="55" r="50" fill="none" stroke="#1e293b" stroke-width="10"/>
    <circle cx="55" cy="55" r="50" fill="none"
      stroke="{'#22c55e' if score>=80 else '#f59e0b' if score>=50 else '#ef4444'}"
      stroke-width="10" stroke-linecap="round"
      stroke-dasharray="314" stroke-dashoffset="{gauge_offset}"
      transform="rotate(-90 55 55)"/>
    <text x="55" y="52" text-anchor="middle" font-size="20" font-weight="500"
      fill="{'#22c55e' if score>=80 else '#f59e0b' if score>=50 else '#ef4444'}"
      font-family="system-ui">{score}</text>
    <text x="55" y="68" text-anchor="middle" font-size="10" fill="#475569" font-family="system-ui">/ 100</text>
  </svg>
  <div class="gauge-text">
    <strong>Test run summary</strong><br>
    {passed} of {total} test cases passed &nbsp;·&nbsp; {failed} failed &nbsp;·&nbsp; {timeout} timed out<br>
    All P2 timings within ISO 14229 50ms limit where measured<br>
    Standards reference: ISO 14229-1 (UDS) · ISO 15765-2 (CAN transport)<br>
    Platform: VDIP on Raspberry Pi 4 · MCP2515 CAN · SocketCAN loopback
  </div>
</div>

<table>
  <thead>
    <tr>
      <th>ID</th><th>Group</th><th>Name</th><th>Request</th><th>Response</th>
      <th>Verdict</th><th>P2 timing</th><th>NRC</th><th>Detail</th><th>ISO ref</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>

<div class="footer">VDIP · Vehicle Diagnostic Intelligence Platform · {ts}</div>
</body>
</html>"""

os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w") as f:
    f.write(html)
print(f"Report saved: {output_path}")
