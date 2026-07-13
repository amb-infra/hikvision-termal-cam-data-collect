# Coleta de dados - Camera Termografica Hikvision / HikMicro HM-TD2628T-7

Porte do sistema originalmente feito para a camera Intelbras (API CGI estilo
Dahua) para a **Hikvision / HikMicro HM-TD2628T-7** (serie **HeatPro**), que
usa a **API ISAPI**. Os endpoints e formatos abaixo foram **confirmados na
propria camera** (firmware V5.5.326).

## Scripts

| Script | Funcao | Endpoint ISAPI (confirmado) |
|--------|--------|------------------------------|
| `collect_by_areas.py` | Monitora media/maxima/minima/diferenca de cada regra de termometria **em tempo real** | `GET /ISAPI/Thermal/channels/2/thermometry/realTimethermometry/rules?format=json` (fluxo multipart JSON) |
| `get_events.py` | Assina o fluxo de alarmes e imprime eventos de termometria (temperatura no alarme/pre-alarme, diferenca de temperatura, fogo/fumaca) | `GET /ISAPI/Event/notification/alertStream` |
| `test_connection.py` | Diagnostico: faz **uma** tentativa e valida IP/senha/canal | `GET /ISAPI/System/deviceInfo` |

## Particularidades desta camera (HeatPro)

Diferente da documentacao ISAPI generica da Hikvision, esta serie tem
peculiaridades que descobrimos ao sondar a camera:

- **Os dados de temperatura em tempo real saem no CANAL 2**, em **JSON**
  (`?format=json`), como um **fluxo multipart persistente**. A camera empurra
  continuamente blocos `ThermometryUploadList` com a leitura de todas as regras.
- A **configuracao** das regras/regioes fica no **canal 1**
  (`GET /ISAPI/Thermal/channels/1/thermometry/1/regions`), mas nao e necessaria
  para coletar: o nome de cada regra ja vem embutido no fluxo do canal 2.
- Os endpoints de *polling* avulso (`rulesTemperatureInfo`,
  `jpegPicWithAppendData`) retornam `notSupport` neste modelo -- por isso usamos
  o fluxo continuo.
- Cada leitura traz, por regra:
  - regras de **area/linha** (`LinePolygonThermCfg`): `MaxTemperature`,
    `MinTemperature`, `AverageTemperature`, `TemperatureDiff`;
  - regras de **ponto** (`PointThermCfg`): `temperature`.

### Codigos de evento (get_events.py)

| Codigo | Significado |
|--------|-------------|
| `TMA`  | Temperature Measurement Alarm (temperatura atingiu o alarme) |
| `TMPA` | Temperature Measurement Pre-Alarm (pre-alarme / alerta) |
| `TDA`  | Temperature Difference Alarm (diferenca de temperatura) |
| `fireDetection` / `smokeDetection` / `smokeAndFireDetection` | fogo / fumaca |

Eventos so sao enviados quando um **limite configurado e cruzado** (nesta
camera: alerta em 60 C, alarme em 80 C por regra). Enquanto nada dispara, o
`alertStream` envia apenas `videoloss` (batimento), que o script ignora.

## Comparacao com a versao Intelbras (Dahua/CGI)

| Item | Intelbras (Dahua) | Hikvision HeatPro (ISAPI) |
|------|-------------------|----------------------------|
| API | `/cgi-bin/*.cgi` | `/ISAPI/*` |
| Formato dos dados | texto `chave=valor` | JSON (tempo real) / XML (eventos) |
| Temperatura em tempo real | `RadiometryManager.cgi?action=getTemper` (polling) | fluxo multipart JSON `realTimethermometry/rules` (canal 2, push) |
| Eventos | `eventManager.cgi?action=attach&codes=[HeatImagingTemper]` | `Event/notification/alertStream` |
| Autenticacao | HTTP Digest | HTTP Digest |

## Configuracao

Edite o topo de cada script:

```python
CAMERA_IP = "192.168.1.64"   # IP da camera (padrao de fabrica da Hikvision)
USERNAME  = "admin"
PASSWORD  = "Amb@5888"       # sensivel a maiusculas/minusculas
CHANNEL   = 2                 # canal do fluxo de termometria em tempo real
SCHEME    = "http"           # use "https" se a camera exigir
```

## Requisitos

```bash
pip install requests
```

Somente `requests`. O parsing usa `json` e `xml.etree` (biblioteca padrao).

## Uso

```bash
# 1) (opcional) valida conexao/credenciais sem arriscar bloqueio de IP
python test_connection.py

# 2) monitora temperaturas por regra/area em tempo real
python collect_by_areas.py

# 3) monitora eventos/alarmes de termometria
python get_events.py
```

Encerre com `Ctrl+C`.

## Observacoes importantes

- **Bloqueio de IP:** a Hikvision bloqueia o IP por ~30 min apos ~5 tentativas
  de login erradas. Se comecar a receber `HTTP 401` mesmo com a senha certa,
  espere ou reinicie a camera. Evite loops de reconexao com senha errada.
- Ambos os fluxos sao **multipart persistentes** e os scripts **reconectam**
  automaticamente se a conexao cair.
- Se a camera usar HTTPS com certificado auto-assinado, mantenha
  `VERIFY_TLS = False`.
- As regras de termometria precisam estar **habilitadas** na camera (interface
  web / iVMS-4200) para gerarem dados no fluxo.
