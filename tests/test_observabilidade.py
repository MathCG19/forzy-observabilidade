import pytest

from app.observability.metrics import avaliar_conformidade, calcular_indicadores, classificar, percentil


def test_registro_com_headers(client, headers):
    client.get("/v1/sensores/TT-101/leitura-atual", headers=headers)
    registros = client.get("/v1/observabilidade").json()["registros"]
    assert len(registros) == 1
    r = registros[0]
    assert r["session_id"] == "sessao-teste"
    assert r["feature"] == "teste"
    assert r["headers_completos"] is True
    assert r["rota"] == "/v1/sensores/{tag}/leitura-atual"
    assert r["tag"] == "TT-101"
    assert r["status_code"] == 200
    assert r["latencia_ms"] > 0
    assert r["idade_dado_s"] is not None
    assert 0 <= r["completude"] <= 1
    assert r["tamanho_resposta_bytes"] > 0
    assert r["timestamp_utc"].endswith("+00:00")


def test_registro_sem_headers_nao_bloqueia(client):
    resp = client.get("/v1/sensores/TT-101/leitura-atual")
    assert resp.status_code == 200
    r = client.get("/v1/observabilidade").json()["registros"][0]
    assert r["session_id"] == "ausente"
    assert r["feature"] == "ausente"
    assert r["headers_completos"] is False


def test_registro_com_um_header_so(client):
    client.get("/v1/sensores/TT-101/leitura-atual", headers={"X-Feature": "parcial"})
    r = client.get("/v1/observabilidade").json()["registros"][0]
    assert r["feature"] == "parcial"
    assert r["headers_completos"] is False


def test_registro_de_erro_404(client, headers):
    client.get("/v1/sensores/XX-999/historico", headers=headers)
    r = client.get("/v1/observabilidade").json()["registros"][0]
    assert r["status_code"] == 404
    assert "XX-999" in r["erro"]


def test_registro_de_erro_422(client):
    client.get("/v1/sensores/TT-101/historico", params={"limite": "abc"})
    r = client.get("/v1/observabilidade").json()["registros"][0]
    assert r["status_code"] == 422
    assert "limite" in r["erro"]


def test_historico_registra_quantidade_e_intervalo(client, headers):
    client.get("/v1/sensores/CT-501/historico", params={"limite": 30}, headers=headers)
    r = client.get("/v1/observabilidade").json()["registros"][0]
    assert r["qtd_registros"] == 30
    assert r["intervalo_medio_s"] >= 30


def test_rotas_fora_de_sensores_nao_sao_registradas(client):
    client.get("/v1/observabilidade")
    client.get("/v1/observabilidade/resumo")
    assert client.get("/v1/observabilidade").json()["quantidade"] == 0


def test_filtros_da_observabilidade(client):
    client.get("/v1/sensores/TT-101/leitura-atual", headers={"X-Session-Id": "a", "X-Feature": "f1"})
    client.get("/v1/sensores/TT-101/leitura-atual", headers={"X-Session-Id": "b", "X-Feature": "f2"})
    client.get("/v1/sensores/TT-101/leitura-atual", headers={"X-Session-Id": "b", "X-Feature": "f1"})
    assert client.get("/v1/observabilidade", params={"feature": "f1"}).json()["quantidade"] == 2
    assert client.get("/v1/observabilidade", params={"session_id": "b"}).json()["quantidade"] == 2
    assert client.get("/v1/observabilidade", params={"limite": 1}).json()["registros"][0]["session_id"] == "b"


def test_falha_no_banco_nao_quebra_requisicao(client, app, headers):
    class StoreQuebrado:
        def inserir(self, registro):
            raise RuntimeError("disco cheio")

    app.state.store = StoreQuebrado()
    assert client.get("/v1/sensores/TT-101/leitura-atual", headers=headers).status_code == 200


def test_fonte_indisponivel_gera_503_registrado(client, app, headers):
    app.state.provider.prob_falha = 1.0
    resp = client.get("/v1/sensores/TT-101/leitura-atual", headers=headers)
    assert resp.status_code == 503
    app.state.provider.prob_falha = 0.0
    r = client.get("/v1/observabilidade").json()["registros"][0]
    assert r["status_code"] == 503


def test_percentil():
    valores = [10, 20, 30, 40, 50]
    assert percentil(valores, 50) == 30
    assert percentil(valores, 95) == pytest.approx(48)
    assert percentil([7], 99) == 7
    assert percentil([], 50) is None


def _registro(**kw):
    base = {
        "timestamp_utc": "2026-10-04T12:00:00.000+00:00", "session_id": "s1", "feature": "f",
        "rota": "/v1/sensores/{tag}/leitura-atual", "status_code": 200, "latencia_ms": 10.0,
        "headers_completos": True, "idade_dado_s": 30.0, "completude": 1.0, "severidade": "normal",
        "intervalo_medio_s": None, "intervalo_max_s": None,
    }
    return {**base, **kw}


def test_calculo_do_resumo():
    registros = [
        _registro(latencia_ms=10),
        _registro(timestamp_utc="2026-10-04T12:01:00.000+00:00", latencia_ms=20, idade_dado_s=120,
                  severidade="critico", session_id="s2"),
        _registro(timestamp_utc="2026-10-04T12:02:00.000+00:00", latencia_ms=30, status_code=404,
                  idade_dado_s=None, completude=None, headers_completos=False, session_id="ausente",
                  feature="ausente"),
        _registro(timestamp_utc="2026-10-04T12:02:00.000+00:00", latencia_ms=40, status_code=503,
                  idade_dado_s=None, completude=None),
    ]
    ind = calcular_indicadores(registros)
    assert ind["total_chamadas"] == 4
    assert ind["latencia_p50_ms"] == 25
    assert ind["taxa_erro_4xx_pct"] == 25
    assert ind["taxa_erro_5xx_pct"] == 25
    assert ind["disponibilidade_pct"] == 75
    assert ind["cobertura_headers_pct"] == 75
    assert ind["taxa_freshness_no_prazo_pct"] == 50
    assert ind["proporcao_critica_pct"] == 50
    assert ind["sessoes_unicas"] == 2
    assert ind["throughput_por_min"] == 2
    assert ind["uso_por_feature"] == {"f": 3, "ausente": 1}


def test_resumo_vazio_nao_quebra(client):
    corpo = client.get("/v1/observabilidade/resumo").json()
    assert corpo["indicadores"]["total_chamadas"] == 0
    assert corpo["indicadores"]["latencia_p95_ms"] is None


def test_resumo_pela_api(client, headers):
    for _ in range(5):
        client.get("/v1/sensores/TT-101/leitura-atual", headers=headers)
    client.get("/v1/sensores/TT-101/leitura-atual")
    ind = client.get("/v1/observabilidade/resumo").json()["indicadores"]
    assert ind["total_chamadas"] == 6
    assert ind["cobertura_headers_pct"] == pytest.approx(83.33)
    assert ind["latencia_p95_ms"] > 0


def test_classificacao_dos_limiares():
    assert classificar(100, 250, 1000, "maior_pior") == "dentro"
    assert classificar(300, 250, 1000, "maior_pior") == "alerta"
    assert classificar(1200, 250, 1000, "maior_pior") == "critico"
    assert classificar(99.9, 99.5, 99.0, "menor_pior") == "dentro"
    assert classificar(98.0, 99.5, 99.0, "menor_pior") == "critico"
    assert classificar(None, 1, 2, "maior_pior") == "sem dados"


def test_conformidade_com_limiar_relativo():
    contrato = {"indicadores": [{
        "id": "throughput", "nome": "Volume", "campo_resumo": "throughput_por_min", "direcao": "menor_pior",
        "baseline": 40, "limiar_alerta": 0.5, "limiar_critico": 0.2, "limiar_relativo_baseline": True,
    }]}
    linha = avaliar_conformidade({"throughput_por_min": 15}, contrato)[0]
    assert linha["limiar_alerta"] == 20
    assert linha["status"] == "alerta"
