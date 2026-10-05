import os
from dataclasses import dataclass, field
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parents[2]


def _float_env(nome: str, padrao: float) -> float:
    valor = os.getenv(nome)
    return float(valor) if valor not in (None, "") else padrao


@dataclass
class Settings:
    db_path: Path = field(
        default_factory=lambda: Path(os.getenv("FORZY_DB_PATH", RAIZ_PROJETO / "data" / "observabilidade.db"))
    )
    contrato_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("FORZY_CONTRATO_PATH", RAIZ_PROJETO / "governanca" / "metric_contract.yaml")
        )
    )
    # Intervalo nominal de amostragem do coletor de sensores, em segundos.
    intervalo_amostragem_s: int = 30
    # Acima desta idade a leitura atual é marcada como desatualizada (ação do contrato para freshness crítico).
    limite_freshness_s: float = field(default_factory=lambda: _float_env("FORZY_LIMITE_FRESHNESS_S", 300))
    # Latência simulada da consulta ao historiador. Zerar nos testes.
    simular_latencia: bool = field(default_factory=lambda: os.getenv("FORZY_SIMULAR_LATENCIA", "1") == "1")
    # Probabilidade de a fonte de dados falhar (gera 503). Zerar nos testes.
    prob_falha_fonte: float = field(default_factory=lambda: _float_env("FORZY_PROB_FALHA", 0.004))
