"""Gera tráfego contra a API para alimentar a análise de governança.

Dois cenários:
  baseline   tráfego limpo, como o de operação normal: todos os clientes mandam os
             headers e usam tags válidas. Serve para medir a baseline dos indicadores.
  avaliacao  tráfego misto: além das telas, entram um script de integração com mais
             concorrência, um cliente legado sem headers, chamadas com tag inexistente
             e parâmetros inválidos. É sobre ele que a conformidade é avaliada.

Cada execução é anotada em data/execucoes.json (cenário, início, fim, volume) para que
governanca/analise.py saiba qual janela de registros pertence a cada cenário.

Uso:
    python scripts/gerar_trafego.py --cenario baseline --chamadas 300 --duracao 300
    python scripts/gerar_trafego.py --cenario avaliacao --chamadas 600 --duracao 480
"""

import argparse
import json
import os
import random
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

API_URL = os.getenv("FORZY_API_URL", "http://127.0.0.1:8000")
ARQUIVO_EXECUCOES = Path(__file__).resolve().parents[1] / "data" / "execucoes.json"
TAGS = ["S1", "S2"]


def _sessoes(n: int) -> list[str]:
    return [str(uuid.uuid4()) for _ in range(n)]


def montar_plano(cenario: str, total: int, rng: random.Random) -> list[dict]:
    sessoes_tela = _sessoes(6 if cenario == "baseline" else 10)
    sessao_integracao = str(uuid.uuid4())
    plano = []
    for _ in range(total):
        tag = rng.choice(TAGS)
        sorteio = rng.random()
        chamada = {"tag": tag, "params": None, "headers": {}, "user_agent": "forzy-streamlit/1.0"}

        if cenario == "baseline" or sorteio < 0.62:
            sessao = rng.choice(sessoes_tela)
            if rng.random() < 0.6:
                chamada.update(rota="leitura-atual", feature="tela-leitura-atual")
            else:
                chamada.update(rota="historico", feature="tela-historico",
                               params={"limite": rng.choice([60, 120, 240])})
            chamada["headers"] = {"X-Session-Id": sessao, "X-Feature": chamada.pop("feature")}
        elif sorteio < 0.80:
            chamada.update(rota="leitura-atual", user_agent="forzy-integracao-mes/0.3")
            chamada["headers"] = {"X-Session-Id": sessao_integracao, "X-Feature": "integracao-mes"}
        elif sorteio < 0.88:
            # Cliente legado que nunca foi atualizado para mandar contexto.
            chamada.update(rota=rng.choice(["leitura-atual", "historico"]), user_agent="python-requests/legado")
        elif sorteio < 0.91:
            chamada.update(rota="leitura-atual")
            chamada["headers"] = {"X-Feature": "tela-leitura-atual"}
        elif sorteio < 0.97:
            chamada.update(rota=rng.choice(["leitura-atual", "historico"]),
                           tag=rng.choice(["S3", "SI", "MOTOR-2"]))
            chamada["headers"] = {"X-Session-Id": rng.choice(sessoes_tela), "X-Feature": "tela-leitura-atual"}
        else:
            chamada.update(rota="historico", params={"limite": rng.choice([0, 9000])})
            chamada["headers"] = {"X-Session-Id": rng.choice(sessoes_tela), "X-Feature": "tela-historico"}
        plano.append(chamada)
    return plano


def executar(base: str, plano: list[dict], duracao_s: float, concorrencia: int) -> Counter:
    resultados = Counter()
    trava = threading.Lock()
    intervalo = duracao_s * concorrencia / max(len(plano), 1)
    http = requests.Session()

    def disparar(i: int, chamada: dict):
        # Espalha as chamadas no tempo com um pouco de ruído para não virar um metrônomo.
        alvo = inicio + (i // concorrencia + random.uniform(-0.3, 0.3)) * intervalo
        espera = alvo - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        headers = {**chamada["headers"], "User-Agent": chamada["user_agent"]}
        url = f"{base}/v1/sensores/{chamada['tag']}/{chamada['rota']}"
        try:
            status = http.get(url, params=chamada["params"], headers=headers, timeout=10).status_code
        except requests.RequestException:
            status = "falha de conexão"
        with trava:
            resultados[status] += 1
            feitos = sum(resultados.values())
            if feitos % 50 == 0:
                print(f"  {feitos}/{len(plano)} chamadas")

    inicio = time.monotonic()
    with ThreadPoolExecutor(max_workers=concorrencia) as pool:
        for i, chamada in enumerate(plano):
            pool.submit(disparar, i, chamada)
    return resultados


def anotar_execucao(registro: dict) -> None:
    execucoes = json.loads(ARQUIVO_EXECUCOES.read_text(encoding="utf-8")) if ARQUIVO_EXECUCOES.exists() else []
    execucoes.append(registro)
    ARQUIVO_EXECUCOES.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO_EXECUCOES.write_text(json.dumps(execucoes, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera tráfego para a análise de governança.")
    parser.add_argument("--cenario", choices=["baseline", "avaliacao"], required=True)
    parser.add_argument("--chamadas", type=int, default=300)
    parser.add_argument("--duracao", type=float, default=300, help="segundos")
    parser.add_argument("--concorrencia", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--url", default=API_URL)
    args = parser.parse_args()

    base = args.url.rstrip("/")
    try:
        requests.get(f"{base}/", timeout=5)
    except requests.RequestException:
        raise SystemExit(f"A API não respondeu em {base}. Suba o uvicorn antes de gerar tráfego.")

    concorrencia = args.concorrencia or (1 if args.cenario == "baseline" else 3)
    rng = random.Random(args.seed)
    plano = montar_plano(args.cenario, args.chamadas, rng)

    # O início é marcado antes da primeira chamada e o fim depois da última, então todo
    # registro desta execução cai dentro da janela sem precisar de margem.
    inicio = datetime.now(timezone.utc)
    print(f"Cenário {args.cenario}: {args.chamadas} chamadas em ~{args.duracao:.0f} s, concorrência {concorrencia}")
    resultados = executar(base, plano, args.duracao, concorrencia)
    fim = datetime.now(timezone.utc)

    anotar_execucao({
        "cenario": args.cenario,
        "inicio": inicio.isoformat(timespec="milliseconds"),
        "fim": fim.isoformat(timespec="milliseconds"),
        "chamadas": args.chamadas,
        "concorrencia": concorrencia,
        "seed": args.seed,
        "status": {str(k): v for k, v in resultados.items()},
    })
    print("Concluído. Status recebidos:", dict(resultados))
    print(f"Janela anotada em {ARQUIVO_EXECUCOES}")


if __name__ == "__main__":
    main()
