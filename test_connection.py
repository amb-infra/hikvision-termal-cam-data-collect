"""
Diagnostico de conexao - Camera Hikvision / HikMicro HM-TD2628T-7

Faz UMA UNICA tentativa (apenas Digest) contra o endpoint mais basico do ISAPI
e imprime o CORPO da resposta 401. E o corpo que distingue:

  - senha errada   -> subStatusCode "badAuthorization" / "userNameOrPassword..."
  - IP bloqueado   -> subStatusCode "userLock" (mostra ate tempo restante)

IMPORTANTE: cada tentativa de senha errada conta para o bloqueio da Hikvision
(5 tentativas -> ~30 min de bloqueio do IP). Por isso este teste faz so 1 request.
Se aparecer bloqueio, ESPERE ou reinicie a camera antes de tentar de novo.
"""

import requests
from requests.auth import HTTPDigestAuth

# ---------------------------------------------------------------------------
# Ajuste aqui
# ---------------------------------------------------------------------------
CAMERA_IP = "IP"
USERNAME = "USERNAME"
PASSWORD = "PASSWORD"
SCHEME = "http"
VERIFY_TLS = False

BASE = f"{SCHEME}://{CAMERA_IP}"


def main():
    url = f"{BASE}/ISAPI/System/deviceInfo"
    print(f"Testando {url}")
    print(f"Usuario: '{USERNAME}'  Senha: '{PASSWORD}'  (uma unica tentativa Digest)\n")

    try:
        r = requests.get(url, auth=HTTPDigestAuth(USERNAME, PASSWORD),
                         timeout=8, verify=VERIFY_TLS)
    except requests.exceptions.RequestException as e:
        print(f"FALHA DE CONEXAO: {e}")
        return

    print(f"HTTP {r.status_code}")
    print("--- Corpo da resposta ---")
    print(r.text.strip()[:1500] or "(vazio)")
    print("-------------------------\n")

    body = r.text.lower()
    if r.status_code == 200:
        print(">>> SUCESSO! Credenciais corretas. Pode rodar collect_by_areas.py")
    elif "userlock" in body or "lock" in body:
        print(">>> IP BLOQUEADO pela camera. Espere ~30 min OU reinicie a camera.")
        print("    (o corpo acima costuma trazer 'lockStatus'/'retryLoginTime'.)")
    elif "badauthorization" in body or "unauthorized" in body or r.status_code == 401:
        print(">>> SENHA/USUARIO REJEITADOS (ou ainda em bloqueio).")
        print("    Confirme a senha exata entrando no navegador: " + BASE)
        print("    Lembre: a Hikvision diferencia maiusculas/minusculas.")
    else:
        print(">>> Resposta inesperada. Veja o corpo acima.")


if __name__ == "__main__":
    main()
