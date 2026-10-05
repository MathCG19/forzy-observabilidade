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
    # Intervalo do poller de sensores, em segundos (forzy_poller.py).
    intervalo_amostragem_s: int = 10
    # Acima desta idade a leitura é marcada como offline e não deve ser usada para decisão (CS3, seção 7.5).
    limite_freshness_s: float = field(default_factory=lambda: _float_env("FORZY_LIMITE_FRESHNESS_S", 30))
    # Ponto do histórico de 19/05 em que o replay começa quando a API sobe. O padrão cai logo antes
    # de uma partida do motor, então os primeiros minutos têm motor parado, partida e operação.
    inicio_replay: str = field(default_factory=lambda: os.getenv("FORZY_REPLAY_INICIO", "13:38"))
    # Latência simulada da consulta ao historiador. Zerar nos testes.
    simular_latencia: bool = field(default_factory=lambda: os.getenv("FORZY_SIMULAR_LATENCIA", "1") == "1")
    # Probabilidade de a fonte de dados falhar (gera 503). Zerar nos testes.
    prob_falha_fonte: float = field(default_factory=lambda: _float_env("FORZY_PROB_FALHA", 0.004))
