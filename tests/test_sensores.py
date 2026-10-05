from datetime import datetime, timedelta, timezone


def test_lista_sensores(client):
    resp = client.get("/v1/sensores")
    assert resp.status_code == 200
    assert {s["tag"] for s in resp.json()} == {"S1", "S2"}


def test_leitura_atual(client, headers):
    resp = client.get("/v1/sensores/S1/leitura-atual", headers=headers)
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["tag"] == "S1"
    assert corpo["severidade"] in {"normal", "alerta", "critico", "indeterminada"}
    assert corpo["idade_s"] >= 0
    assert "X-Latencia-Ms" in resp.headers


def test_leitura_atual_aceita_tag_minuscula(client):
    assert client.get("/v1/sensores/s1/leitura-atual").json()["tag"] == "S1"


def test_historico(client, headers):
    resp = client.get("/v1/sensores/S2/historico", params={"limite": 50}, headers=headers)
    assert resp.status_code == 200
    corpo = resp.json()
    assert 0 < corpo["quantidade"] <= 50
    tempos = [item["timestamp_leitura"] for item in corpo["leituras"]]
    assert tempos == sorted(tempos)


def test_historico_respeita_intervalo(client):
    fim = datetime.now(timezone.utc) - timedelta(hours=2)
    inicio = fim - timedelta(minutes=10)
    resp = client.get("/v1/sensores/S1/historico",
                      params={"inicio": inicio.isoformat(), "fim": fim.isoformat(), "limite": 1000})
    assert resp.status_code == 200
    for item in resp.json()["leituras"]:
        ts = datetime.fromisoformat(item["timestamp_leitura"])
        assert inicio <= ts <= fim
    # 10 minutos com poll a cada 10 s dão no máximo 61 leituras
    assert resp.json()["quantidade"] <= 61


def test_historico_inicio_depois_do_fim(client):
    agora = datetime.now(timezone.utc)
    resp = client.get("/v1/sensores/S1/historico",
                      params={"inicio": agora.isoformat(), "fim": (agora - timedelta(hours=1)).isoformat()})
    assert resp.status_code == 422


def test_historico_limite_invalido(client):
    assert client.get("/v1/sensores/S1/historico", params={"limite": 0}).status_code == 422


def test_tag_inexistente_retorna_404(client):
    for rota in ("leitura-atual", "historico"):
        resp = client.get(f"/v1/sensores/S9/{rota}")
        assert resp.status_code == 404
        assert "S9" in resp.json()["detail"]


def test_lista_traz_limites_do_contrato(client):
    s1 = client.get("/v1/sensores").json()[0]
    assert s1["limites"]["velocidade_mm_s"] == {"alerta": 1.8, "critico": 4.5}
    assert s1["limites"]["temperatura_c"] == {"alerta": 70.0, "critico": 90.0}


def test_leitura_atual_traz_as_tres_grandezas(client):
    corpo = client.get("/v1/sensores/S2/leitura-atual").json()
    for campo in ("velocidade_mm_s", "aceleracao_g", "temperatura_c", "motor_ligado", "offline"):
        assert campo in corpo
    assert set(corpo["severidade_por_grandeza"]) == {"velocidade_mm_s", "aceleracao_g", "temperatura_c"}
