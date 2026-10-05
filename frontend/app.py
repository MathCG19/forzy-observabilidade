"""Interface Streamlit da Sensor Monitoring API.

Rodar a partir da raiz do projeto:
    streamlit run frontend/app.py
"""

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
from api_client import API_URL_PADRAO, ApiClient, ErroApi  # noqa: E402

COR_SEVERIDADE = {
    "normal": ("#0ca30c", "Normal"),
    "alerta": ("#fab219", "Alerta"),
    "critico": ("#d03b3b", "Crítico"),
    "indeterminada": ("#8a8984", "Indeterminada"),
}
COR_STATUS = {"dentro": "Dentro", "alerta": "Alerta", "critico": "Crítico",
              "informativo": "Informativo", "sem dados": "Sem dados"}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
GRANDEZAS = [("velocidade_mm_s", "Vibração", "mm/s"), ("aceleracao_g", "Aceleração", "g"),
             ("temperatura_c", "Temperatura", "°C")]
COR_ALERTA, COR_CRITICO = "#fab219", "#d03b3b"

st.set_page_config(page_title="Forzy | Sensores", layout="wide")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

with st.sidebar:
    st.header("Sensor Monitoring API")
    api_url = st.text_input("URL da API", value=API_URL_PADRAO)
    st.caption("Sessão desta aba do navegador (enviada em X-Session-Id):")
    st.code(st.session_state.session_id, language=None)

cliente = ApiClient(api_url, st.session_state.session_id)


def chamar(funcao, *args, **kwargs):
    try:
        return funcao(*args, **kwargs)
    except ErroApi as exc:
        st.error(str(exc))
        return None


def br(valor: float, casas: int = 1) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def selo(severidade: str) -> str:
    cor, rotulo = COR_SEVERIDADE.get(severidade, ("#8a8984", severidade))
    return (f"<span style='background:{cor};color:#0b0b0b;padding:4px 12px;border-radius:4px;"
            f"font-weight:600'>{rotulo}</span>")


def linhas_limiar(alerta: float | None, critico: float | None):
    camadas = []
    for valor, cor, rotulo in ((alerta, COR_ALERTA, "alerta"), (critico, COR_CRITICO, "crítico")):
        if valor is not None:
            df = pd.DataFrame({"y": [valor], "rotulo": [f"limiar de {rotulo}"]})
            camadas.append(alt.Chart(df).mark_rule(color=cor, strokeDash=[6, 4], strokeWidth=2)
                           .encode(y="y:Q", tooltip=["rotulo", "y"]))
    return camadas


sensores = chamar(cliente.sensores, "tela-leitura-atual") or []
tags = [s["tag"] for s in sensores]
descricoes = {s["tag"]: s["descricao"] for s in sensores}

aba_leitura, aba_historico, aba_obs = st.tabs(["Leitura atual", "Histórico", "Observabilidade"])

with aba_leitura:
    if not tags:
        st.info("Sem conexão com a API. Confira a URL na barra lateral.")
    else:
        tag = st.selectbox("Sensor", tags, format_func=lambda t: f"{t} - {descricoes[t]}", key="tag_leitura")
        if st.button("Ler agora", key="btn_ler") or st.session_state.get("leitura_tag") != tag:
            st.session_state.leitura = chamar(cliente.leitura_atual, tag)
            st.session_state.leitura_tag = tag
        leitura = st.session_state.get("leitura")
        if leitura:
            sev = leitura["severidade_por_grandeza"]
            colunas = st.columns(4)
            for coluna, (campo, rotulo, unidade) in zip(colunas, GRANDEZAS):
                valor = leitura[campo]
                coluna.metric(rotulo, "inválido" if valor is None else f"{br(valor, 2)} {unidade}")
                if sev[campo]:
                    coluna.markdown(selo(sev[campo]), unsafe_allow_html=True)
            colunas[3].metric("Idade do dado", f"{leitura['idade_s']:.0f} s")
            st.markdown(f"Severidade geral: {selo(leitura['severidade'])}", unsafe_allow_html=True)
            estado = "ligado" if leitura["motor_ligado"] else "desligado (vibração abaixo de 0,3 mm/s)"
            st.caption(f"{leitura['descricao']} | componente {leitura['componente_id']} | motor {estado} | "
                       f"leitura de {leitura['timestamp_leitura']}")
            if leitura["offline"]:
                st.warning("Sensor offline: a última leitura tem mais de 30 s. Pelo circuit breaker do Metric "
                           "Contract, a severidade mostrada não deve ser usada para decisão.")
            if not leitura["motor_ligado"]:
                st.info("Motor desligado: o diagnóstico de anomalia não se aplica a esta leitura.")

with aba_historico:
    if tags:
        c1, c2, c3, c4 = st.columns(4)
        tag_h = c1.selectbox("Sensor", tags, key="tag_hist")
        grandeza = c2.selectbox("Grandeza", GRANDEZAS, format_func=lambda g: g[1], key="grandeza_hist")
        horas = c3.selectbox("Período", [1, 6, 24], format_func=lambda h: f"últimas {h} h")
        limite = c4.number_input("Máximo de leituras", 10, 5000, value=360, step=10)
        chave = (tag_h, horas, limite)
        if st.button("Consultar", key="btn_hist") or st.session_state.get("hist_chave") != chave:
            fim = datetime.now(timezone.utc)
            st.session_state.hist = chamar(cliente.historico, tag_h, fim - timedelta(hours=horas), fim, int(limite))
            st.session_state.hist_chave = chave
        hist = st.session_state.get("hist")
        if hist and hist["leituras"]:
            df = pd.DataFrame(hist["leituras"]).drop(columns=["severidade_por_grandeza"])
            df["timestamp_leitura"] = pd.to_datetime(df["timestamp_leitura"])
            campo, rotulo, unidade = grandeza
            limites = next(s for s in sensores if s["tag"] == hist["tag"])["limites"][campo]
            linha = (alt.Chart(df).mark_line(color=SERIES[0], strokeWidth=2)
                     .encode(x=alt.X("timestamp_leitura:T", title="Horário (UTC)"),
                             y=alt.Y(f"{campo}:Q", title=f"{rotulo} ({unidade})"),
                             tooltip=["timestamp_leitura:T", f"{campo}:Q", "severidade:N"]))
            st.altair_chart(alt.layer(linha, *linhas_limiar(limites["alerta"], limites["critico"])),
                            width="stretch")
            st.caption(f"{hist['quantidade']} leituras, uma a cada 10 s quando o poller consegue ler. Linhas "
                       "tracejadas: limiar de alerta (amarelo) e crítico (vermelho) do Metric Contract.")
            st.dataframe(df, width="stretch", hide_index=True)
        elif hist:
            st.info("Nenhuma leitura no período.")


def janela(df: pd.DataFrame, freq: str):
    return df.set_index("timestamp_utc").resample(freq)


@st.fragment(run_every=timedelta(seconds=5) if st.session_state.get("auto_obs") else None)
def painel_observabilidade():
    c1, c2, c3, c4 = st.columns(4)
    minutos = c1.selectbox("Janela", [15, 60, 360, 1440, 0],
                           format_func=lambda m: "tudo" if m == 0 else f"últimos {m} min", index=4)
    filtro_feature = c2.text_input("Feature (X-Feature)")
    filtro_sessao = c3.text_input("Sessão (X-Session-Id)")
    limite = c4.number_input("Máximo de registros", 50, 10000, value=2000, step=50)

    desde = datetime.now(timezone.utc) - timedelta(minutes=minutos) if minutos else None
    resumo = chamar(cliente.resumo, desde=desde)
    dados = chamar(cliente.observabilidade, filtro_feature=filtro_feature or None,
                   session_id=filtro_sessao or None, desde=desde, limite=int(limite))
    if not resumo or not dados:
        return
    ind = resumo["indicadores"]
    if not ind["total_chamadas"]:
        st.info("Ainda não há chamadas registradas. Use as outras abas ou rode scripts/gerar_trafego.py.")
        return

    def fmt(valor, sufixo=""):
        return "-" if valor is None else f"{br(valor, 2)}{sufixo}"

    k = st.columns(6)
    k[0].metric("Chamadas", ind["total_chamadas"])
    k[1].metric("Latência p95", fmt(ind["latencia_p95_ms"], " ms"))
    k[2].metric("Disponibilidade", fmt(ind["disponibilidade_pct"], "%"))
    k[3].metric("Cobertura de headers", fmt(ind["cobertura_headers_pct"], "%"))
    k[4].metric("Freshness no prazo", fmt(ind["taxa_freshness_no_prazo_pct"], "%"))
    k[5].metric("Sessões únicas", ind["sessoes_unicas"])

    if resumo["conformidade"]:
        st.subheader("Conformidade com o metric contract")
        conf = pd.DataFrame(resumo["conformidade"])
        conf = conf[conf["status"] != "informativo"]
        conf["status"] = conf["status"].map(COR_STATUS)
        st.dataframe(conf[["indicador", "valor", "unidade", "limiar_alerta", "limiar_critico", "status"]],
                     width="stretch", hide_index=True)

    df = pd.DataFrame(dados["registros"])
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], format="ISO8601")
    st.caption(f"Gráficos sobre os {len(df)} registros filtrados abaixo.")

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("Latência por minuto (ms)")
        lat = janela(df, "1min")["latencia_ms"].quantile([0.5, 0.95]).unstack().dropna().reset_index()
        lat.columns = ["minuto", "p50", "p95"]
        lat = lat.melt("minuto", var_name="percentil", value_name="ms")
        linha = (alt.Chart(lat).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=40))
                 .encode(x=alt.X("minuto:T", title="Horário (UTC)"), y=alt.Y("ms:Q", title="Latência (ms)"),
                         color=alt.Color("percentil:N", scale=alt.Scale(range=SERIES[:2]), title=None),
                         tooltip=["minuto:T", "percentil:N", alt.Tooltip("ms:Q", format=".1f")]))
        st.altair_chart(alt.layer(linha, *linhas_limiar(250, 1000)), width="stretch")
    with g2:
        st.markdown("Chamadas por minuto")
        vol = janela(df, "1min").size().reset_index(name="chamadas")
        st.altair_chart(alt.Chart(vol).mark_line(color=SERIES[0], strokeWidth=2)
                        .encode(x=alt.X("timestamp_utc:T", title="Horário (UTC)"),
                                y=alt.Y("chamadas:Q", title="Chamadas/min"),
                                tooltip=["timestamp_utc:T", "chamadas:Q"]), width="stretch")

    g3, g4 = st.columns(2)
    with g3:
        st.markdown("Status HTTP por rota")
        status = df.groupby(["rota", "status_code"]).size().reset_index(name="chamadas")
        status["status_code"] = status["status_code"].astype(str)
        st.altair_chart(alt.Chart(status).mark_bar()
                        .encode(y=alt.Y("rota:N", title=None), x=alt.X("chamadas:Q", title="Chamadas"),
                                color=alt.Color("status_code:N", title="Status",
                                                scale=alt.Scale(range=["#2a78d6", "#eda100", "#eb6834", "#e34948"])),
                                tooltip=["rota", "status_code", "chamadas"]), width="stretch")
    with g4:
        st.markdown("Cobertura de headers por feature (%)")
        cob = (df.groupby("feature")["headers_completos"].mean() * 100).reset_index(name="cobertura")
        st.altair_chart(alt.layer(
            alt.Chart(cob).mark_bar(color=SERIES[0])
            .encode(y=alt.Y("feature:N", sort="-x", title=None), x=alt.X("cobertura:Q", title="Cobertura (%)"),
                    tooltip=["feature", alt.Tooltip("cobertura:Q", format=".1f")]),
            alt.Chart(pd.DataFrame({"x": [95]})).mark_rule(color=COR_ALERTA, strokeDash=[6, 4], strokeWidth=2)
            .encode(x="x:Q")), width="stretch")

    g5, g6 = st.columns(2)
    with g5:
        st.markdown("Idade do dado na leitura atual (s)")
        fr = df[df["idade_dado_s"].notna()]
        if not fr.empty:
            pontos = (alt.Chart(fr).mark_circle(size=40, color=SERIES[0])
                      .encode(x=alt.X("timestamp_utc:T", title="Horário (UTC)"),
                              y=alt.Y("idade_dado_s:Q", title="Idade (s)"),
                              tooltip=["timestamp_utc:T", "tag", alt.Tooltip("idade_dado_s:Q", format=".0f")]))
            st.altair_chart(alt.layer(pontos, *linhas_limiar(30, 300)), width="stretch")
    with g6:
        st.markdown("Uso por feature")
        uso = df["feature"].value_counts().reset_index()
        uso.columns = ["feature", "chamadas"]
        st.altair_chart(alt.Chart(uso).mark_bar(color=SERIES[0])
                        .encode(y=alt.Y("feature:N", sort="-x", title=None), x=alt.X("chamadas:Q", title="Chamadas"),
                                tooltip=["feature", "chamadas"]), width="stretch")

    st.subheader("Registros")
    st.dataframe(df.sort_values("id", ascending=False), width="stretch", hide_index=True)


with aba_obs:
    st.toggle("Atualizar a cada 5 s", key="auto_obs")
    painel_observabilidade()
