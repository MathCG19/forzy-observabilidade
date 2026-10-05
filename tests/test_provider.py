from datetime import datetime, timedelta, timezone

from app.providers.sensores import (
    SENSORES, SensoresProvider, carregar_historico, classificar, instante_do_historico,
)


def test_historico_real_carregado():
    tempos, portas = carregar_historico()
    assert len(tempos) == len(portas[1]) == len(portas[2]) > 7000
    assert tempos == sorted(tempos)


def test_zonas_iso_10816_classe_i():
    s1 = SENSORES["S1"]
    base = {"aceleracao_g": 0.1, "temperatura_c": 30.0}
    assert classificar(s1, {**base, "velocidade_mm_s": 0.57})["severidade"] == "normal"
    assert classificar(s1, {**base, "velocidade_mm_s": 1.8})["severidade"] == "alerta"
    assert classificar(s1, {**base, "velocidade_mm_s": 6.6})["severidade"] == "critico"
    quente = classificar(s1, {"velocidade_mm_s": 0.5, "aceleracao_g": 0.1, "temperatura_c": 92.0})
    assert quente["severidade"] == "critico"
    assert quente["severidade_por_grandeza"]["temperatura_c"] == "critico"
    vazio = classificar(s1, {"velocidade_mm_s": None, "aceleracao_g": None, "temperatura_c": None})
    assert vazio["severidade"] == "indeterminada"


def test_replay_comeca_no_instante_configurado():
    agora = 1_800_000_000.0
    # Entre 13:50 e 13:52 do histórico o motor está no platô de operação, perto de 6,6 mm/s.
    p = SensoresProvider(simular_latencia=False, relogio=lambda: agora,
                         inicio_replay_s=instante_do_historico("13:52"), ancora=agora)
    fim = datetime.fromtimestamp(agora, tz=timezone.utc)
    leituras = p.historico("S1", fim - timedelta(minutes=2), fim, 100)
    assert leituras
    assert all(item["velocidade_mm_s"] > 4.5 for item in leituras)
    assert all(item["motor_ligado"] for item in leituras)


def test_motor_parado_fica_desligado():
    agora = 1_800_000_000.0
    p = SensoresProvider(simular_latencia=False, relogio=lambda: agora,
                         inicio_replay_s=instante_do_historico("13:30"), ancora=agora)
    leitura = p.leitura_atual("S2")
    assert leitura["velocidade_mm_s"] < 0.3
    assert leitura["motor_ligado"] is False
