"""
Monitor de Temperatura - Camera Termografica Hikvision / HikMicro HM-TD2628T-7
(serie HeatPro - firmware V5.5.x)

Le, em tempo real, as temperaturas media/maxima/minima de cada regra de
termometria configurada na camera (pontos, linhas e areas/regioes).

Endpoint usado (confirmado nesta camera):
  GET /ISAPI/Thermal/channels/2/thermometry/realTimethermometry/rules?format=json

E um fluxo multipart PERSISTENTE: a camera empurra continuamente blocos JSON
(ThermometryUploadList), cada um com a leitura atual de todas as regras.
Autenticacao: HTTP Digest.
"""

import requests
from requests.auth import HTTPDigestAuth
import time
from datetime import datetime
import json

# ---------------------------------------------------------------------------
# Configuracoes da camera
# ---------------------------------------------------------------------------
CAMERA_IP = "192.168.1.64"
USERNAME = "admin"
PASSWORD = "Amb@5888"

# Nesta serie (HeatPro) a saida de termometria em tempo real esta no canal 2.
# (A configuracao das regras/regioes fica no canal 1, mas os dados ao vivo
#  sao publicados no canal 2.)
CHANNEL = 2

SCHEME = "http"          # use "https" se a camera exigir
VERIFY_TLS = False       # ISAPI normalmente usa certificado auto-assinado

AUTH = HTTPDigestAuth(USERNAME, PASSWORD)

# thermometryUnit -> simbolo
UNIT = {0: "C", 1: "F", 2: "K"}


def _stream_url():
    return (f"{SCHEME}://{CAMERA_IP}/ISAPI/Thermal/channels/{CHANNEL}"
            f"/thermometry/realTimethermometry/rules?format=json")


def _iter_json_objects(response):
    """
    Le um fluxo multipart e vai devolvendo (yield) cada objeto JSON completo.

    O corpo multipart intercala cabecalhos de parte (Content-Type,
    Content-Length, linhas em branco e delimitadores --boundary) com blocos
    JSON. Em vez de depender do formato exato do multipart, acumulamos os
    bytes e extraimos cada JSON contando chaves { } balanceadas -- robusto
    a variacoes de firmware e a JSON "pretty printed".
    """
    buffer = ""
    pos = 0            # proxima posicao AINDA nao lida (persiste entre chunks)
    depth = 0
    start = -1
    in_string = False
    escape = False

    for chunk in response.iter_content(chunk_size=1024):
        if not chunk:
            continue
        buffer += chunk.decode("utf-8", errors="ignore")

        while pos < len(buffer):
            c = buffer[pos]

            if in_string:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"':
                    in_string = False
            elif c == '"':
                in_string = True
            elif c == "{":
                if depth == 0:
                    start = pos
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = buffer[start:pos + 1]
                    try:
                        obj = json.loads(candidate)
                    except json.JSONDecodeError:
                        obj = None
                    # descarta tudo que ja foi consumido e reinicia o ponteiro
                    buffer = buffer[pos + 1:]
                    pos = 0
                    start = -1
                    if obj is not None:
                        yield obj
                    continue  # nao incrementa pos: ja aponta para o resto

            pos += 1


def _extract_readings(obj):
    """Converte um bloco ThermometryUploadList em uma lista de leituras."""
    readings = []

    upload_list = obj.get("ThermometryUploadList", obj)
    items = upload_list.get("ThermometryUpload", [])
    if isinstance(items, dict):
        items = [items]

    for it in items:
        name = it.get("ruleName") or f"rule {it.get('ruleID')}"
        unit = UNIT.get(it.get("thermometryUnit", 0), "?")
        data = {}
        rtype = "unknown"

        # Regra de linha/area/poligono: max/min/media/diferenca
        region = it.get("LinePolygonThermCfg")
        if isinstance(region, dict):
            rtype = "region/line"
            if "MaxTemperature" in region:
                data["max"] = region["MaxTemperature"]
            if "MinTemperature" in region:
                data["min"] = region["MinTemperature"]
            if "AverageTemperature" in region:
                data["avg"] = region["AverageTemperature"]
            if "TemperatureDiff" in region:
                data["diff"] = region["TemperatureDiff"]

        # Regra de ponto: temperatura unica
        point = it.get("PointThermCfg")
        if isinstance(point, dict) and "temperature" in point:
            rtype = "point"
            data["temp"] = point["temperature"]

        if data:
            readings.append({
                "id": it.get("ruleID"),
                "name": name,
                "type": rtype,
                "unit": unit,
                "data": data,
            })

    return readings


def monitor_areas(reconnect_delay=3):
    print(f"Conectando ao fluxo de termometria (canal {CHANNEL}) em {CAMERA_IP}...")

    while True:
        try:
            response = requests.get(_stream_url(), auth=AUTH, stream=True,
                                    timeout=(5, None), verify=VERIFY_TLS)

            if response.status_code != 200:
                print(f"Erro HTTP {response.status_code}. "
                      f"Tentando novamente em {reconnect_delay}s...")
                time.sleep(reconnect_delay)
                continue

            print("Conectado. Recebendo temperaturas em tempo real...\n")

            for obj in _iter_json_objects(response):
                if "ThermometryUploadList" not in obj and "ThermometryUpload" not in obj:
                    continue

                readings = _extract_readings(obj)
                if not readings:
                    continue

                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for r in readings:
                    print(json.dumps({
                        "timestamp": ts,
                        "area": r["name"],
                        "type": r["type"],
                        "unit": r["unit"],
                        "data": r["data"],
                    }, indent=2, ensure_ascii=False))

        except KeyboardInterrupt:
            print("\nMonitoramento encerrado.")
            return
        except requests.exceptions.RequestException as e:
            print(f"Falha de conexao: {e}. Reconectando em {reconnect_delay}s...")
            time.sleep(reconnect_delay)


if __name__ == "__main__":
    monitor_areas()
