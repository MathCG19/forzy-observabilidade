"""Provider de Sensores do Forzy Digital Twin.

Os valores são reais: vêm do histórico capturado dos dois sensores do motor WEG W22
(portas 1 e 2 do mestre IO-Link) em 19/05/2026, o mesmo arquivo que o modo demo do
forzy-api repete. O que é simulado é a coleta: um poller lê o valor corrente de cada
sensor a cada 10 s, como o forzy_poller.py do projeto, e às vezes falha (túnel do
endpoint fora do ar, poll perdido). O histórico é repetido em laço sobre o relógio atual.
"""

import bisect
import csv
import math
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

ARQUIVO_HISTORICO = Path(__file__).resolve().parent / "dados" / "historico_forzy_2026-05-19.csv"

INTERVALO_S = 10            # poll_loop do forzy_poller.py
JANELA_PARADA_S = 240
# Chance de o endpoint ficar fora do ar numa janela de 4 min. Zerar para demonstração.
PROB_PARADA = float(os.getenv("FORZY_PROB_QUEDA_ENDPOINT", "0.10"))
PROB_POLL_PERDIDO = 0.02
ATRASO_GRAVACAO_S = 0.5     # tempo entre o poll e a linha estar disponível para leitura

# Faixas físicas válidas e limiares do Metric Contract do CS3 (seções 7.4 e 7.5).
FAIXA_VALIDA = {"velocidade_mm_s": (0, 50), "aceleracao_g": (0, 20), "temperatura_c": (-10, 150)}
PISO_OPERACAO_MM_S = 0.3


@dataclass(frozen=True)
class Sensor:
    tag: str
    descricao: str
    componente_id: int
    porta: int
    limites: dict = field(default_factory=lambda: {
        "velocidade_mm_s": (1.8, 4.5),   # ISO 10816-1 Classe I, zonas C e D
        "aceleracao_g": (2.0, 4.0),
        "temperatura_c": (70.0, 90.0),
    })


SENSORES: dict[str, Sensor] = {
    "S1": Sensor("S1", "Motor WEG W22 - Unidade S1", componente_id=2, porta=1),
    "S2": Sensor("S2", "Motor WEG W22 - Unidade S2", componente_id=3, porta=2),
}

GRANDEZAS = ("velocidade_mm_s", "aceleracao_g", "temperatura_c")
CAMPOS_LEITURA = ("tag", "descricao", "timestamp_leitura", *GRANDEZAS, "severidade")
CAMPOS_HISTORICO = ("timestamp_leitura", *GRANDEZAS, "severidade")
ORDEM_SEVERIDADE = {"normal": 0, "alerta": 1, "critico": 2}


class TagNaoEncontrada(Exception):
    pass


class FonteIndisponivel(Exception):
    pass


@lru_cache(maxsize=1)
def carregar_historico() -> tuple[list[float], dict[int, list[tuple[float, float, float]]]]:
    """Segundos desde a primeira linha e, por porta, (velocidade, aceleração, temperatura)."""
    tempos, portas = [], {1: [], 2: []}
    with ARQUIVO_HISTORICO.open(encoding="utf-8") as f:
        linhas = csv.reader(f, delimiter=";")
        for _ in range(3):  # cabeçalho do exportador IO-Link tem três linhas
            next(linhas)
        inicio = None
        for linha in linhas:
            ts = datetime.fromisoformat(linha[0]).timestamp()
            inicio = inicio if inicio is not None else ts
            tempos.append(ts - inicio)
            v = [float(x) for x in linha[3:9]]
            portas[1].append((v[0], v[1], v[2]))
            portas[2].append((v[3], v[4], v[5]))
    return tempos, portas


def instante_do_historico(texto_hhmm: str) -> float:
    """Converte "13:38" (hora do histórico de 19/05) em segundos desde a primeira linha."""
    with ARQUIVO_HISTORICO.open(encoding="utf-8") as f:
        for _ in range(3):
            f.readline()
        primeira = datetime.fromisoformat(f.readline().split(";")[0])
    h, m = (int(x) for x in texto_hhmm.split(":")[:2])
    alvo = primeira.replace(hour=h, minute=m, second=0, microsecond=0)
    return max((alvo - primeira).total_seconds(), 0.0)


def _severidade(valor: float | None, limites: tuple[float, float]) -> str | None:
    if valor is None:
        return None
    alerta, critico = limites
    if valor >= critico:
        return "critico"
    if valor >= alerta:
        return "alerta"
    return "normal"


def classificar(sensor: Sensor, valores: dict) -> dict:
    por_grandeza = {g: _severidade(valores[g], sensor.limites[g]) for g in GRANDEZAS}
    validas = [s for s in por_grandeza.values() if s]
    geral = max(validas, key=ORDEM_SEVERIDADE.get) if validas else "indeterminada"
    return {"severidade": geral, "severidade_por_grandeza": por_grandeza}


def _validar(valor: float, grandeza: str) -> float | None:
    minimo, maximo = FAIXA_VALIDA[grandeza]
    return valor if minimo <= valor <= maximo else None


@lru_cache(maxsize=4096)
def _parada(janela: int) -> tuple[int, int] | None:
    # A parada é do endpoint, então derruba os dois sensores ao mesmo tempo.
    rng = random.Random(f"parada:{janela}")
    if rng.random() >= PROB_PARADA:
        return None
    inicio = janela * JANELA_PARADA_S + rng.randint(0, JANELA_PARADA_S - 60)
    return inicio, inicio + rng.randint(60, 420)


def _poll_ok(tag: str, slot: int) -> bool:
    ts = slot * INTERVALO_S
    janela = ts // JANELA_PARADA_S
    for j in (janela, janela - 1, janela - 2):
        parada = _parada(j)
        if parada and parada[0] <= ts < parada[1]:
            return False
    return random.Random(f"{tag}:poll:{slot}").random() >= PROB_POLL_PERDIDO


def completude(payload: dict, campos: tuple[str, ...]) -> float:
    return sum(payload.get(c) is not None for c in campos) / len(campos)


class SensoresProvider:
    def __init__(self, simular_latencia: bool = True, prob_falha: float = 0.0, relogio=time.time,
                 inicio_replay_s: float = 0.0, ancora: float | None = None):
        self.simular_latencia = simular_latencia
        self.prob_falha = prob_falha
        self.relogio = relogio
        self._rng = random.Random()
        self.tempos, self.portas = carregar_historico()
        self.periodo = math.ceil(self.tempos[-1] / INTERVALO_S) * INTERVALO_S + INTERVALO_S
        # No instante `ancora` o replay está em `inicio_replay_s` do histórico.
        ancora = relogio() if ancora is None else ancora
        self.origem = ancora - inicio_replay_s

    def listar(self) -> list[Sensor]:
        return list(SENSORES.values())

    def sensor(self, tag: str) -> Sensor:
        sensor = SENSORES.get(tag.upper())
        if sensor is None:
            raise TagNaoEncontrada(tag)
        return sensor

    def _consultar_fonte(self, peso: float = 1.0) -> None:
        """Simula o custo da consulta ao banco: tempo variável e falha ocasional."""
        if self.simular_latencia:
            espera = self._rng.lognormvariate(math.log(12), 0.5) * peso
            if self._rng.random() < 0.02:
                espera += self._rng.uniform(250, 600)
            time.sleep(espera / 1000)
        if self._rng.random() < self.prob_falha:
            raise FonteIndisponivel("banco de leituras não respondeu")

    def _valores(self, sensor: Sensor, slot: int) -> dict:
        """Valor corrente do sensor no instante do poll (última linha do histórico até ali)."""
        posicao = (slot * INTERVALO_S - self.origem) % self.periodo
        i = bisect.bisect_right(self.tempos, posicao) - 1
        v, a, t = self.portas[sensor.porta][i]  # i = -1 cai na última linha, fechando o laço
        return {
            "velocidade_mm_s": _validar(v, "velocidade_mm_s"),
            "aceleracao_g": _validar(a, "aceleracao_g"),
            "temperatura_c": _validar(t, "temperatura_c"),
        }

    def _leitura(self, sensor: Sensor, slot: int) -> dict:
        valores = self._valores(sensor, slot)
        vel = valores["velocidade_mm_s"]
        return {
            "timestamp_leitura": datetime.fromtimestamp(slot * INTERVALO_S, tz=timezone.utc),
            **valores,
            "motor_ligado": None if vel is None else vel >= PISO_OPERACAO_MM_S,
            **classificar(sensor, valores),
        }

    def _disponivel(self, sensor: Sensor, slot: int, agora: float) -> bool:
        return slot * INTERVALO_S + ATRASO_GRAVACAO_S <= agora and _poll_ok(sensor.tag, slot)

    def leitura_atual(self, tag: str) -> dict:
        sensor = self.sensor(tag)
        self._consultar_fonte()
        agora = self.relogio()
        slot = int(agora // INTERVALO_S)
        for _ in range(8640):
            if self._disponivel(sensor, slot, agora):
                break
            slot -= 1
        return {"tag": sensor.tag, "descricao": sensor.descricao, "componente_id": sensor.componente_id,
                **self._leitura(sensor, slot)}

    def historico(self, tag: str, inicio: datetime, fim: datetime, limite: int) -> list[dict]:
        """As `limite` leituras mais recentes dentro de [inicio, fim], em ordem cronológica."""
        sensor = self.sensor(tag)
        self._consultar_fonte(peso=1.6)
        agora = self.relogio()
        slot = int(min(fim.timestamp(), agora) // INTERVALO_S)
        slot_inicio = math.ceil(inicio.timestamp() / INTERVALO_S)
        leituras = []
        while slot >= slot_inicio and len(leituras) < limite:
            if self._disponivel(sensor, slot, agora):
                leituras.append(self._leitura(sensor, slot))
            slot -= 1
        leituras.reverse()
        return leituras
