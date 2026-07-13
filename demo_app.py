"""
Aplicacao de demonstracao - Camera Termografica Hikvision / HikMicro HM-TD2628T-7

Sobe um pequeno servidor web (Flask) que mostra, em uma unica pagina:
  - o VIDEO da camera ao vivo (termico ou visual), via proxy MJPEG;
  - as TEMPERATURAS de cada zona em tempo real (mesmo fluxo do collect_by_areas),
    transmitidas ao navegador por SSE (Server-Sent Events).

O servidor faz a ponte com a camera (que usa autenticacao Digest e nao e
acessivel direto pelo navegador). Nenhuma dependencia alem de flask + requests.

Uso:
    pip install flask requests
    python demo_app.py
    # abra http://127.0.0.1:5000 no navegador
"""

import time
import json
import requests
from requests.auth import HTTPDigestAuth
from flask import Flask, Response, request

# Reaproveita o parser de fluxo JSON ja validado do coletor
import collect_by_areas as C

# ---------------------------------------------------------------------------
# Configuracoes da camera (iguais aos outros scripts)
# ---------------------------------------------------------------------------
CAMERA_IP = "192.168.1.64"
USERNAME = "admin"
PASSWORD = "Amb@5888"
THERM_CHANNEL = 2        # canal do fluxo de termometria em tempo real
SCHEME = "http"
VERIFY_TLS = False

AUTH = HTTPDigestAuth(USERNAME, PASSWORD)
BASE = f"{SCHEME}://{CAMERA_IP}"
THERM_URL = (f"{BASE}/ISAPI/Thermal/channels/{THERM_CHANNEL}"
             f"/thermometry/realTimethermometry/rules?format=json")

# Canais de video/snapshot: 201=termico, 101=visual (confirmados na camera)
VIDEO_CHANNELS = {"thermal": 201, "optical": 101}

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Backend: fluxo de temperaturas (SSE) e video (MJPEG)
# ---------------------------------------------------------------------------
@app.route("/stream/temps")
def stream_temps():
    """Encaminha o fluxo de termometria da camera ao navegador como SSE."""
    def gen():
        min_interval = 0.25   # nao inunda o navegador: no maximo ~4 updates/s
        last = 0.0
        while True:
            try:
                r = requests.get(THERM_URL, auth=AUTH, stream=True,
                                 timeout=(5, None), verify=VERIFY_TLS)
                if r.status_code != 200:
                    yield _sse({"error": f"HTTP {r.status_code}"})
                    time.sleep(3)
                    continue

                yield _sse({"status": "connected"})

                for obj in C._iter_json_objects(r):
                    if "ThermometryUploadList" not in obj and "ThermometryUpload" not in obj:
                        continue
                    zones = C._extract_readings(obj)
                    if not zones:
                        continue
                    now = time.time()
                    if now - last < min_interval:
                        continue
                    last = now
                    yield _sse({
                        "ts": time.strftime("%H:%M:%S"),
                        "zones": zones,
                    })
            except requests.exceptions.RequestException as e:
                yield _sse({"error": str(e)})
                time.sleep(3)

    return Response(gen(), mimetype="text/event-stream")


@app.route("/video")
def video():
    """Proxy MJPEG: busca snapshots da camera e serve como stream continuo."""
    kind = request.args.get("kind", "thermal")
    ch = VIDEO_CHANNELS.get(kind, VIDEO_CHANNELS["thermal"])
    url = f"{BASE}/ISAPI/Streaming/channels/{ch}/picture"

    def gen():
        while True:
            try:
                r = requests.get(url, auth=AUTH, timeout=8, verify=VERIFY_TLS)
                if r.status_code == 200 and r.content:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                           + r.content + b"\r\n")
                time.sleep(0.15)   # ~6-7 quadros por segundo
            except requests.exceptions.RequestException:
                time.sleep(1)

    return Response(gen(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/")
def index():
    return Response(PAGE, mimetype="text/html")


def _sse(payload):
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Frontend (HTML + CSS + JS embutidos)
# ---------------------------------------------------------------------------
PAGE = """<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Camera Termografica - Demonstracao</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    background: #0d1117; color: #e6edf3;
  }
  header {
    padding: 14px 20px; border-bottom: 1px solid #21262d;
    display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  }
  header h1 { font-size: 16px; margin: 0; font-weight: 600; }
  header .model { color: #7d8590; font-size: 13px; }
  .status { margin-left: auto; display: flex; align-items: center; gap: 8px; font-size: 13px; }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: #f85149; }
  .dot.on { background: #3fb950; box-shadow: 0 0 8px #3fb950; }
  main { display: grid; grid-template-columns: minmax(360px, 1fr) minmax(320px, 1fr); gap: 18px; padding: 18px; }
  @media (max-width: 860px) { main { grid-template-columns: 1fr; } }
  .panel { background: #161b22; border: 1px solid #21262d; border-radius: 10px; overflow: hidden; }
  .panel h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .5px;
    color: #7d8590; margin: 0; padding: 12px 14px; border-bottom: 1px solid #21262d; }
  .videowrap { position: relative; background: #000; aspect-ratio: 16/9; display: flex; }
  .videowrap img { width: 100%; height: 100%; object-fit: contain; }
  .vidbtns { display: flex; gap: 8px; padding: 10px 14px; }
  .vidbtns button {
    background: #21262d; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px;
    padding: 6px 12px; cursor: pointer; font-size: 13px;
  }
  .vidbtns button.active { background: #1f6feb; border-color: #1f6feb; }
  .zones { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 10px; padding: 14px; }
  .zone {
    background: #0d1117; border: 1px solid #21262d; border-left: 4px solid #3fb950;
    border-radius: 8px; padding: 10px 12px;
  }
  .zone .name { font-size: 12px; color: #7d8590; margin-bottom: 6px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .zone .big { font-size: 26px; font-weight: 700; line-height: 1; }
  .zone .big span { font-size: 14px; color: #7d8590; font-weight: 400; }
  .zone .row { display: flex; justify-content: space-between; margin-top: 8px;
    font-size: 11px; color: #8b949e; }
  .zone .row b { color: #c9d1d9; font-weight: 600; }
  footer { text-align: center; color: #484f58; font-size: 12px; padding: 8px; }
</style>
</head>
<body>
<header>
  <h1>Camera Termografica</h1>
  <span class="model">HikMicro HM-TD2628T-7 (HeatPro)</span>
  <div class="status"><span id="dot" class="dot"></span><span id="stxt">conectando...</span>
    <span id="clock" style="color:#7d8590"></span></div>
</header>

<main>
  <section class="panel">
    <h2>Video ao vivo</h2>
    <div class="videowrap"><img id="vid" src="/video?kind=thermal" alt="video"></div>
    <div class="vidbtns">
      <button id="b-thermal" class="active" onclick="setVideo('thermal')">Termico</button>
      <button id="b-optical" onclick="setVideo('optical')">Visual</button>
    </div>
  </section>

  <section class="panel">
    <h2>Temperaturas por zona (tempo real)</h2>
    <div id="zones" class="zones"></div>
  </section>
</main>

<footer>Dados via ISAPI /realTimethermometry (canal 2) &middot; video via proxy MJPEG</footer>

<script>
function tempColor(t) {
  // azul (frio) -> verde -> amarelo -> vermelho (quente), faixa 0..80C
  if (t == null) return '#3fb950';
  const stops = [[0,'#2f81f7'],[25,'#3fb950'],[45,'#d29922'],[60,'#db6d28'],[80,'#f85149']];
  let c = stops[0][1];
  for (const [v,col] of stops) { if (t >= v) c = col; }
  return c;
}
function fmt(v){ return (v==null)?'--':Number(v).toFixed(1); }

function setVideo(kind){
  document.getElementById('vid').src = '/video?kind='+kind+'&t='+Date.now();
  document.getElementById('b-thermal').classList.toggle('active', kind==='thermal');
  document.getElementById('b-optical').classList.toggle('active', kind==='optical');
}

const zonesEl = document.getElementById('zones');
const dot = document.getElementById('dot'), stxt = document.getElementById('stxt');
const clock = document.getElementById('clock');

function render(zones){
  for (const z of zones){
    const d = z.data || {};
    const main = (d.max != null) ? d.max : (d.temp != null ? d.temp : d.avg);
    const id = 'z'+z.id;
    let el = document.getElementById(id);
    if (!el){
      el = document.createElement('div');
      el.className = 'zone'; el.id = id;
      zonesEl.appendChild(el);
    }
    el.style.borderLeftColor = tempColor(main);
    const isPoint = (d.temp != null);
    el.innerHTML =
      '<div class="name" title="'+z.name+'">'+z.name+'</div>' +
      '<div class="big" style="color:'+tempColor(main)+'">'+fmt(main)+'<span> &deg;'+(z.unit||'C')+'</span></div>' +
      (isPoint ? '' :
        '<div class="row"><span>min <b>'+fmt(d.min)+'</b></span><span>med <b>'+fmt(d.avg)+'</b></span></div>' +
        '<div class="row"><span>max <b>'+fmt(d.max)+'</b></span><span>&Delta; <b>'+fmt(d.diff)+'</b></span></div>');
  }
}

function connect(){
  const es = new EventSource('/stream/temps');
  es.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.error){ dot.classList.remove('on'); stxt.textContent = 'erro: '+msg.error; return; }
    if (msg.status === 'connected'){ dot.classList.add('on'); stxt.textContent = 'conectado'; return; }
    if (msg.zones){ dot.classList.add('on'); stxt.textContent = 'conectado';
      clock.textContent = msg.ts; render(msg.zones); }
  };
  es.onerror = () => { dot.classList.remove('on'); stxt.textContent = 'reconectando...'; };
}
connect();
</script>
</body>
</html>"""


if __name__ == "__main__":
    print("Servidor de demonstracao em http://127.0.0.1:5000")
    print("(Ctrl+C para encerrar)")
    app.run(host="0.0.0.0", port=5000, threaded=True)
