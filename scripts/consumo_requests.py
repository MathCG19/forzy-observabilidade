"""Consome os três endpoints da Sensor Monitoring API com requests.

Uso:
    python scripts/consumo_requests.py [--url http://127.0.0.1:8000] [--tag S1]
"""

import argparse
import os
import sys
import uuid

import requests

API_URL = os.getenv("FORZY_API_URL", "http://127.0.0.1:8000")
TIMEOUT_S = 10


def chamar(url: str, session_id: str, feature: str, params: dict | None = None) -> dict | None:
    headers = {"X-Session-Id": session_id, "X-Feature": feature}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT_S)
    except requests.ConnectionError:
        print(f"Erro: não foi possível conectar em {url}. Suba a API com uvicorn antes de rodar o script.")
        sys.exit(1)
    except requests.Timeout:
        print(f"Erro: {url} não respondeu em {TIMEOUT_S} s.")
        return None
    print(f"GET {resp.url}")
    print(f"  status {resp.status_code}, latência informada pela API: {resp.headers.get('X-Latencia-Ms', '-')} ms")
    if resp.status_code >= 400:
        print(f"  erro: {resp.json().get('detail')}")
        return None
    return resp.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Consome leitura atual, histórico e observabilidade.")
    parser.add_argument("--url", default=API_URL)
    parser.add_argument("--tag", default="S1")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    session_id = str(uuid.uuid4())
    print(f"Sessão: {session_id}\n")

    print("1) Leitura atual")
    leitura = chamar(f"{base}/v1/sensores/{args.tag}/leitura-atual", session_id, "script-leitura-atual")
    if leitura:
        aviso = "  (offline: não usar para decisão)" if leitura["offline"] else ""
        estado = "ligado" if leitura["motor_ligado"] else "desligado"
        print(f"  {leitura['tag']} - {leitura['descricao']} (motor {estado})")
        print(f"  vibração {leitura['velocidade_mm_s']} mm/s | aceleração {leitura['aceleracao_g']} g | "
              f"temperatura {leitura['temperatura_c']} °C")
        print(f"  severidade: {leitura['severidade']}{aviso}")
        print(f"  lida em {leitura['timestamp_leitura']} (há {leitura['idade_s']} s)")
    print()

    print("2) Histórico (últimas 10 leituras)")
    hist = chamar(f"{base}/v1/sensores/{args.tag}/historico", session_id, "script-historico", {"limite": 10})
    if hist:
        print(f"  {hist['quantidade']} leituras entre {hist['inicio']} e {hist['fim']}")
        for item in hist["leituras"]:
            print(f"  {item['timestamp_leitura']}  {str(item['velocidade_mm_s']):>5} mm/s  {str(item['aceleracao_g']):>5} g  "
                  f"{str(item['temperatura_c']):>5} °C  {item['severidade']}")
    print()

    print("3) Observabilidade (registros desta sessão)")
    obs = chamar(f"{base}/v1/observabilidade", session_id, "script-observabilidade", {"session_id": session_id})
    if obs:
        print(f"  {obs['quantidade']} registros")
        for r in obs["registros"]:
            print(f"  {r['timestamp_utc']}  {r['feature']:<22} {r['rota']:<36} "
                  f"{r['status_code']}  {r['latencia_ms']:.1f} ms")


if __name__ == "__main__":
    main()
