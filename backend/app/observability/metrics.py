"""Cálculo dos indicadores do metric contract a partir dos registros de chamada."""

from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

ROTA_LEITURA = "/v1/sensores/{tag}/leitura-atual"
ROTA_HISTORICO = "/v1/sensores/{tag}/historico"
PRAZO_FRESHNESS_S = 30


def percentil(valores: list[float], p: float) -> float | None:
    """Percentil com interpolação linear entre vizinhos (mesmo método padrão do numpy)."""
    if not valores:
        return None
    ordenados = sorted(valores)
    pos = (len(ordenados) - 1) * p / 100
    baixo = int(pos)
    alto = min(baixo + 1, len(ordenados) - 1)
    return ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * (pos - baixo)


def _pct(parte: int, total: int) -> float | None:
    return round(100 * parte / total, 2) if total else None


def _media(valores: list[float]) -> float | None:
    return round(sum(valores) / len(valores), 3) if valores else None


def _arred(valor: float | None, casas: int = 2) -> float | None:
    return round(valor, casas) if valor is not None else None


def calcular_indicadores(registros: list[dict], prazo_freshness_s: float = PRAZO_FRESHNESS_S) -> dict:
    total = len(registros)
    latencias = [r["latencia_ms"] for r in registros]
    status = [r["status_code"] for r in registros]

    leituras_ok = [r for r in registros if r["rota"] == ROTA_LEITURA and r["status_code"] == 200]
    historicos_ok = [r for r in registros if r["rota"] == ROTA_HISTORICO and r["status_code"] == 200]
    idades = [r["idade_dado_s"] for r in leituras_ok if r["idade_dado_s"] is not None]
    completudes = [r["completude"] for r in registros if r["completude"] is not None]
    intervalos = [r["intervalo_medio_s"] for r in historicos_ok if r["intervalo_medio_s"] is not None]
    intervalos_max = [r["intervalo_max_s"] for r in historicos_ok if r["intervalo_max_s"] is not None]

    duracao_min = None
    if total >= 2:
        t0 = datetime.fromisoformat(registros[0]["timestamp_utc"])
        t1 = datetime.fromisoformat(registros[-1]["timestamp_utc"])
        duracao_min = max((t1 - t0).total_seconds() / 60, 1 / 60)

    sessoes = {r["session_id"] for r in registros if r["session_id"] != "ausente"}

    return {
        "total_chamadas": total,
        "periodo_inicio": registros[0]["timestamp_utc"] if registros else None,
        "periodo_fim": registros[-1]["timestamp_utc"] if registros else None,
        "latencia_p50_ms": _arred(percentil(latencias, 50)),
        "latencia_p95_ms": _arred(percentil(latencias, 95)),
        "latencia_p99_ms": _arred(percentil(latencias, 99)),
        "taxa_erro_4xx_pct": _pct(sum(400 <= s < 500 for s in status), total),
        "taxa_erro_5xx_pct": _pct(sum(s >= 500 for s in status), total),
        "disponibilidade_pct": _pct(sum(s < 500 for s in status), total),
        "freshness_p95_s": _arred(percentil(idades, 95), 1),
        "freshness_media_s": _arred(_media(idades), 1),
        "taxa_freshness_no_prazo_pct": _pct(sum(i <= prazo_freshness_s for i in idades), len(idades)),
        "completude_media_pct": _arred(100 * _media(completudes)) if completudes else None,
        "intervalo_atualizacao_medio_s": _arred(_media(intervalos), 1),
        "intervalo_atualizacao_max_s": max(intervalos_max) if intervalos_max else None,
        "cobertura_headers_pct": _pct(sum(r["headers_completos"] for r in registros), total),
        "throughput_por_min": _arred(total / duracao_min) if duracao_min else None,
        "sessoes_unicas": len(sessoes),
        "proporcao_critica_pct": _pct(sum(r["severidade"] == "critico" for r in leituras_ok), len(leituras_ok)),
        "uso_por_feature": dict(Counter(r["feature"] for r in registros).most_common()),
    }


def carregar_contrato(caminho: Path | str) -> dict | None:
    caminho = Path(caminho)
    if not caminho.exists():
        return None
    with caminho.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def classificar(valor: float | None, alerta: float | None, critico: float | None, direcao: str) -> str:
    if valor is None:
        return "sem dados"
    if alerta is None and critico is None:
        return "informativo"
    pior = (lambda v, lim: v > lim) if direcao == "maior_pior" else (lambda v, lim: v < lim)
    if critico is not None and pior(valor, critico):
        return "critico"
    if alerta is not None and pior(valor, alerta):
        return "alerta"
    return "dentro"


def avaliar_conformidade(indicadores: dict, contrato: dict) -> list[dict]:
    linhas = []
    for item in contrato.get("indicadores", []):
        campo = item["campo_resumo"]
        valor = indicadores.get(campo)
        alerta, critico = item.get("limiar_alerta"), item.get("limiar_critico")
        if item.get("limiar_relativo_baseline") and item.get("baseline") is not None:
            alerta = item["baseline"] * alerta if alerta is not None else None
            critico = item["baseline"] * critico if critico is not None else None
        linhas.append({
            "id": item["id"],
            "indicador": item["nome"],
            "valor": valor,
            "unidade": item.get("unidade", ""),
            "baseline": item.get("baseline"),
            "limiar_alerta": alerta,
            "limiar_critico": critico,
            "direcao": item.get("direcao", "maior_pior"),
            "status": classificar(valor, alerta, critico, item.get("direcao", "maior_pior")),
        })
    return linhas
