"""
Monitor de Eventos - Camera Termografica Hikvision / HikMicro HM-TD2628T-7

Assina o fluxo de alarmes da camera (alertStream) e imprime os eventos de
termometria (temperatura acima/abaixo do limite, diferenca de temperatura, etc.).

API: Hikvision ISAPI - GET /ISAPI/Event/notification/alertStream
(fluxo multipart continuo, autenticacao Digest)
"""

import requests
from requests.auth import HTTPDigestAuth
from datetime import datetime
import json
import time
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Configuracoes da camera
# ---------------------------------------------------------------------------
CAMERA_IP = "IP"
USERNAME = "USERNAME"
PASSWORD = "PASSWORD"

SCHEME = "http"
VERIFY_TLS = False

# Tipos de evento de interesse (termometria) - codigos usados pela serie
# HeatPro (HM-TD2628T-7). Deixe a lista VAZIA (set()) para imprimir TODOS os
# eventos que a camera enviar.
EVENT_TYPES = {
    "TMA",                   # Temperature Measurement Alarm (temperatura no alarme)
    "TMPA",                  # Temperature Measurement Pre-Alarm (pre-alarme/alerta)
    "TDA",                   # Temperature Difference Alarm (diferenca de temperatura)
    "fireDetection",         # deteccao de fogo
    "smokeDetection",        # deteccao de fumaca
    "smokeAndFireDetection", # fogo + fumaca
}

# Eventos de "manutencao" que nao interessam (batimento/heartbeat do stream).
IGNORED_TYPES = {"videoloss"}

AUTH = HTTPDigestAuth(USERNAME, PASSWORD)


def _local(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def parse_event_message(xml_text):
    """Interpreta um bloco <EventNotificationAlert> em um dicionario plano."""
    event = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    for node in root.iter():
        name = _local(node.tag)
        text = (node.text or "").strip()
        if text and name != _local(root.tag):
            # Nao sobrescreve campos ja preenchidos com listas aninhadas
            event.setdefault(name, text)

    # Normaliza os campos principais
    normalized = {
        "eventType": event.get("eventType"),
        "eventState": event.get("eventState"),
        "channelID": event.get("channelID") or event.get("dynChannelID"),
        "ruleName": event.get("ruleName"),
        "currTemperature": event.get("currTemperature"),
        "ruleTemperature": event.get("RuleTemperature") or event.get("ruleTemperature"),
        "alarmRule": event.get("alarmRule"),
        "dateTime": event.get("dateTime"),
    }
    normalized = {k: v for k, v in normalized.items() if v is not None}
    normalized["raw"] = event
    return normalized


def monitor_events():
    url = f"{SCHEME}://{CAMERA_IP}/ISAPI/Event/notification/alertStream"

    while True:
        try:
            response = requests.get(url, auth=AUTH, stream=True,
                                    timeout=(5, None), verify=VERIFY_TLS)

            if response.status_code != 200:
                print(f"Erro HTTP {response.status_code}. Tentando novamente em 5s...")
                time.sleep(5)
                continue

            print("Conectado ao alertStream. Aguardando eventos...")

            buffer = []
            for raw in response.iter_lines():
                if raw is None:
                    continue
                line = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else raw

                # Delimitador de parte multipart -> processa o bloco acumulado
                if line.startswith("--"):
                    if buffer:
                        _handle_block("\n".join(buffer))
                    buffer = []
                    continue

                if line.startswith("Content-") or not line.strip():
                    continue

                buffer.append(line)

            # Se o fluxo cair, reconecta
            if buffer:
                _handle_block("\n".join(buffer))

        except KeyboardInterrupt:
            print("\n\nMonitoramento encerrado.")
            return
        except requests.exceptions.RequestException as e:
            print(f"Falha de conexao: {e}. Reconectando em 5s...")
            time.sleep(5)


def _handle_block(block):
    if "EventNotificationAlert" not in block:
        return

    event = parse_event_message(block)
    if not event:
        return

    etype = event.get("eventType")
    # Ignora batimentos/eventos de manutencao (ex.: videoloss)
    if etype in IGNORED_TYPES:
        return
    # Filtra por tipo de evento, se configurado
    if EVENT_TYPES and etype not in EVENT_TYPES:
        return

    event["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(json.dumps(event, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    monitor_events()
