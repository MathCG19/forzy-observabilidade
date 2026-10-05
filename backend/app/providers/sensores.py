"""Provider de Sensores do Forzy Digital Twin.

As leituras são simuladas de forma determinística: a mesma tag no mesmo instante
sempre gera o mesmo valor, então o histórico é estável entre chamadas. O simulador
reproduz problemas reais de coleta (amostras perdidas, coletor parado por alguns
minutos, campos nulos) para que os indicadores de qualidade de dado tenham o que medir.
"""

import math
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache


@dataclass(frozen=True)
class Sensor:
    tag: str
    descricao: str
    unidade: str
    base: float
    amplitude: float
    limite_alerta: float
    limite_critico: float


SENSORES: dict[str, Sensor] = {
    s.tag: s
    for s in [
        Sensor("TT-101", "Temperatura do mancal do motor M-01", "°C", 68.0, 5.0, 80.0, 90.0),
        Sensor("PT-201", "Pressão de descarga da bomba B-02", "bar", 6.2, 0.45, 7.5, 8.2),
        Sensor("VT-301", "Vibração do redutor R-03", "mm/s", 3.0, 0.9, 4.5, 7.1),
        Sensor("CT-501", "Corrente do motor M-05", "A", 42.0, 3.0, 50.0, 55.0),
    ]
}

INTERVALO_S = 30
JANELA_PARADA_S = 240
PROB_PARADA = 0.10
PROB_AMOSTRA_PERDIDA = 0.02
PROB_QUALIDADE_NULA = 0.03
PROB_VALOR_NULO = 0.01

CAMPOS_LEITURA = (
    "tag", "descricao", "unidade", "valor", "timestamp_leitura",
    "severidade", "qualidade", "limite_alerta", "limite_critico",
)
CAMPOS_HISTORICO = ("timestamp_leitura", "valor", "severidade", "qualidade")


class TagNaoEncontrada(Exception):
    pass


class FonteIndisponivel(Exception):
    pass


def classificar(sensor: Sensor, valor: float | None) -> str:
    if valor is None:
        return "indeterminada"
    if valor >= sensor.limite_critico:
        return "critico"
    if valor >= sensor.limite_alerta:
        return "alerta"
    return "normal"


@lru_cache(maxsize=4096)
def _parada(tag: str, janela: int) -> tuple[int, int] | None:
    """Intervalo [inicio, fim) em que o coletor ficou parado dentro da janela, se ficou."""
    rng = random.Random(f"{tag}:parada:{janela}")
    if rng.random() >= PROB_PARADA:
        return None
    inicio = janela * JANELA_PARADA_S + rng.randint(0, JANELA_PARADA_S - 60)
    return inicio, inicio + rng.randint(60, 420)


def _existe(tag: str, slot: int) -> bool:
    ts = slot * INTERVALO_S
    janela = ts // JANELA_PARADA_S
    # Uma parada pode começar numa janela e invadir as duas seguintes.
    for j in (janela, janela - 1, janela - 2):
        parada = _parada(tag, j)
        if parada and parada[0] <= ts < parada[1]:
            return False
    return random.Random(f"{tag}:perda:{slot}").random() >= PROB_AMOSTRA_PERDIDA


def _publicada(tag: str, slot: int, agora: float) -> bool:
    # Cada amostra leva de 3 a 20 s para sair do coletor e ficar disponível.
    atraso = random.Random(f"{tag}:atraso:{slot}").uniform(3, 20)
    return slot * INTERVALO_S + atraso <= agora


def _gerar(sensor: Sensor, slot: int) -> dict:
    rng = random.Random(f"{sensor.tag}:valor:{slot}")
    valor = sensor.base + sensor.amplitude * math.sin(2 * math.pi * slot / 120)
    valor += rng.gauss(0, sensor.amplitude * 0.2)
    sorteio = rng.random()
    if sorteio < 0.015:
        valor += sensor.amplitude * rng.uniform(4.0, 5.0)
    elif sorteio < 0.07:
        valor += sensor.amplitude * rng.uniform(2.0, 3.0)

    valor_final: float | None = round(valor, 2)
    if rng.random() < PROB_VALOR_NULO:
        valor_final = None
    qualidade: str | None = "boa" if valor_final is not None else "ruim"
    if rng.random() < PROB_QUALIDADE_NULA:
        qualidade = None

    return {
        "timestamp_leitura": datetime.fromtimestamp(slot * INTERVALO_S, tz=timezone.utc),
        "valor": valor_final,
        "severidade": classificar(sensor, valor_final),
        "qualidade": qualidade,
    }


def completude(payload: dict, campos: tuple[str, ...]) -> float:
    return sum(payload.get(c) is not None for c in campos) / len(campos)


class SensoresProvider:
    def __init__(self, simular_latencia: bool = True, prob_falha: float = 0.0, relogio=time.time):
        self.simular_latencia = simular_latencia
        self.prob_falha = prob_falha
        self.relogio = relogio
        self._rng = random.Random()

    def listar(self) -> list[Sensor]:
        return list(SENSORES.values())

    def _sensor(self, tag: str) -> Sensor:
        sensor = SENSORES.get(tag.upper())
        if sensor is None:
            raise TagNaoEncontrada(tag)
        return sensor

    def _consultar_fonte(self, peso: float = 1.0) -> None:
        """Simula o custo de ir ao historiador: tempo de resposta variável e falha ocasional."""
        if self.simular_latencia:
            espera = self._rng.lognormvariate(math.log(12), 0.5) * peso
            if self._rng.random() < 0.02:
                espera += self._rng.uniform(250, 600)
            time.sleep(espera / 1000)
        if self._rng.random() < self.prob_falha:
            raise FonteIndisponivel("historiador de sensores não respondeu")

    def leitura_atual(self, tag: str) -> dict:
        sensor = self._sensor(tag)
        self._consultar_fonte()
        agora = self.relogio()
        slot = int(agora // INTERVALO_S)
        for _ in range(2880):
            if _existe(sensor.tag, slot) and _publicada(sensor.tag, slot, agora):
                break
            slot -= 1
        leitura = _gerar(sensor, slot)
        return {
            "tag": sensor.tag,
            "descricao": sensor.descricao,
            "unidade": sensor.unidade,
            **leitura,
            "limite_alerta": sensor.limite_alerta,
            "limite_critico": sensor.limite_critico,
        }

    def historico(self, tag: str, inicio: datetime, fim: datetime, limite: int) -> list[dict]:
        """Devolve as `limite` leituras mais recentes dentro de [inicio, fim], em ordem cronológica."""
        sensor = self._sensor(tag)
        self._consultar_fonte(peso=1.6)
        agora = self.relogio()
        ts_fim = min(fim.timestamp(), agora)
        slot = int(ts_fim // INTERVALO_S)
        slot_inicio = math.ceil(inicio.timestamp() / INTERVALO_S)
        leituras = []
        while slot >= slot_inicio and len(leituras) < limite:
            if _existe(sensor.tag, slot) and _publicada(sensor.tag, slot, agora):
                leituras.append(_gerar(sensor, slot))
            slot -= 1
        leituras.reverse()
        return leituras
