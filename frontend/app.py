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
import requests
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
from api_client import API_URL_PADRAO, ApiClient, ErroApi  # noqa: E402

FUSO = "America/Sao_Paulo"
ALTURA = 280
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
COR_ALERTA, COR_CRITICO, COR_OK, COR_NEUTRA = "#fab219", "#d03b3b", "#0ca30c", "#8a8984"
SEVERIDADE = {
    "normal": (COR_OK, "Normal"),
    "alerta": (COR_ALERTA, "Alerta"),
    "critico": (COR_CRITICO, "Crítico"),
    "indeterminada": (COR_NEUTRA, "Indeterminada"),
}
OFFLINE = (COR_NEUTRA, "Sem decisão (offline)")
STATUS_CONTRATO = {"dentro": (COR_OK, "Dentro"), "alerta": (COR_ALERTA, "Alerta"),
                   "critico": (COR_CRITICO, "Crítico"), "sem dados": (COR_NEUTRA, "Sem dados")}
GRANDEZAS = [("velocidade_mm_s", "Vibração", "mm/s"), ("aceleracao_g", "Aceleração", "g"),
             ("temperatura_c", "Temperatura", "°C")]
ROTAS_CURTAS = {"/v1/sensores/{tag}/leitura-atual": "leitura-atual",
                "/v1/sensores/{tag}/historico": "historico", "/v1/sensores": "lista de sensores"}
COMANDO_TRAFEGO = "python scripts/gerar_trafego.py --cenario avaliacao --chamadas 200 --duracao 90"

st.set_page_config(page_title="Forzy | Sensores", layout="wide")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())


# ---------------------------------------------------------------- utilitários

def br(valor, casas: int = 1) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def em_brasilia(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, utc=True, format="ISO8601").dt.tz_convert(FUSO)


def eixo_grafico(serie_brasilia: pd.Series) -> pd.Series:
    # O Vega-Lite converte datas para o fuso do navegador. Rotulando a hora de Brasília como
    # UTC e usando escala utc, o eixo mostra a hora de Brasília em qualquer máquina.
    return serie_brasilia.dt.tz_localize(None).dt.tz_localize("UTC")


def texto_hora(serie_brasilia: pd.Series) -> pd.Series:
    return serie_brasilia.dt.strftime("%d/%m %H:%M:%S")


def eixo_x(campo: str) -> alt.X:
    return alt.X(f"{campo}:T", title="Horário (Brasília)", scale=alt.Scale(type="utc"),
                 axis=alt.Axis(format="%H:%M", grid=False))


def selo(cor_rotulo: tuple[str, str], grande: bool = False) -> str:
    cor, rotulo = cor_rotulo
    tamanho = "1.05rem;padding:6px 16px" if grande else "0.85rem;padding:3px 10px"
    return (f"<span style='background:{cor};color:#0b0b0b;border-radius:4px;font-weight:600;"
            f"font-size:{tamanho}'>{rotulo}</span>")


def linhas_limiar(alerta, critico):
    camadas = []
    for valor, cor, rotulo in ((alerta, COR_ALERTA, "Limiar de alerta"), (critico, COR_CRITICO, "Limiar crítico")):
        if valor is not None:
            df = pd.DataFrame({"y": [valor], "rotulo": [rotulo], "valor": [br(valor, 1)]})
            camadas.append(alt.Chart(df).mark_rule(color=cor, strokeDash=[6, 4], strokeWidth=2)
                           .encode(y="y:Q", tooltip=[alt.Tooltip("rotulo:N", title="Linha"),
                                                     alt.Tooltip("valor:N", title="Valor")]))
    return camadas


def grafico(camadas) -> None:
    st.altair_chart(alt.layer(*camadas).properties(height=ALTURA), width="stretch")


def chamar(funcao, *args, **kwargs):
    try:
        return funcao(*args, **kwargs)
    except ErroApi as exc:
        st.error(str(exc))
        return None


def api_online(url: str) -> bool:
    try:
        return requests.get(f"{url.rstrip('/')}/", timeout=1.5).ok
    except requests.RequestException:
        return False


# ---------------------------------------------------------------- cabeçalho e barra lateral

st.title("Forzy Digital Twin | Monitoramento de Sensores")
st.caption("Motor WEG W22, sensores S1 e S2. Valores do histórico real de 19/05/2026, coleta simulada.")

with st.sidebar:
    st.subheader("Conexão")
    api_url = st.text_input("URL da API", value=API_URL_PADRAO)
    if api_online(api_url):
        st.markdown(f"<span style='color:{COR_OK}'>●</span> API online", unsafe_allow_html=True)
    else:
        st.markdown(f"<span style='color:{COR_CRITICO}'>●</span> API fora do ar", unsafe_allow_html=True)
    sid = st.session_state.session_id
    st.caption(f"Sessão (X-Session-Id): {sid[:8]}", help=sid)
    st.divider()
    st.caption("Matheus Cardoso Gomes, RM 564898  \nCaique Sousa, RM 563621  \nFIAP, Tecnólogo em IA, 2026")

cliente = ApiClient(api_url, st.session_state.session_id)
sensores = chamar(cliente.sensores, "tela-leitura-atual") or []
tags = [s["tag"] for s in sensores]
descricoes = {s["tag"]: s["descricao"] for s in sensores}
limites_por_tag = {s["tag"]: s["limites"] for s in sensores}

aba_leitura, aba_historico, aba_obs = st.tabs([
    ":material/sensors: Leitura atual", ":material/show_chart: Histórico", ":material/monitoring: Observabilidade",
])


# ---------------------------------------------------------------- leitura atual

with aba_leitura:
    if not tags:
        st.info("Sem conexão com a API. Confira a URL na barra lateral.")
    else:
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        tag = c1.selectbox("Sensor", tags, format_func=lambda t: f"{t} | {descricoes[t]}", key="tag_leitura")
        if c2.button("Ler agora", key="btn_ler", width="stretch") or st.session_state.get("leitura_tag") != tag:
            st.session_state.leitura = chamar(cliente.leitura_atual, tag)
            st.session_state.leitura_tag = tag
        leitura = st.session_state.get("leitura")
        if leitura:
            offline = leitura["offline"]
            geral = OFFLINE if offline else SEVERIDADE.get(leitura["severidade"], SEVERIDADE["indeterminada"])
            motor = "Motor ligado" if leitura["motor_ligado"] else "Motor desligado"
            st.markdown(f"{selo(geral, grande=True)} &nbsp; <span style='font-size:1.05rem'>{motor}</span>",
                        unsafe_allow_html=True)
            if offline:
                st.warning("Sensor offline: a última leitura tem mais de 30 s. Pelo circuit breaker do Metric "
                           "Contract, a severidade não é usada para decisão até o dado voltar.")
            if not leitura["motor_ligado"]:
                st.info("Motor desligado (vibração abaixo de 0,3 mm/s): o diagnóstico de anomalia não se aplica.")

            hora = pd.Timestamp(leitura["timestamp_leitura"]).tz_convert(FUSO).strftime("%d/%m %H:%M:%S")
            colunas = st.columns(4)
            for coluna, (campo, rotulo, unidade) in zip(colunas, GRANDEZAS):
                with coluna.container(border=True):
                    valor = leitura[campo]
                    st.metric(rotulo, "inválido" if valor is None else f"{br(valor, 2)} {unidade}")
                    sev = leitura["severidade_por_grandeza"][campo]
                    if offline:
                        st.markdown(selo(OFFLINE), unsafe_allow_html=True)
                    elif sev:
                        st.markdown(selo(SEVERIDADE[sev]), unsafe_allow_html=True)
                    lim = limites_por_tag[leitura["tag"]][campo]
                    st.caption(f"alerta {br(lim['alerta'])} | crítico {br(lim['critico'])} {unidade}")
            with colunas[3].container(border=True):
                st.metric("Idade do dado", f"{leitura['idade_s']:.0f} s")
                st.caption(f"atualizado há {leitura['idade_s']:.0f} s  \nleitura de {hora} (Brasília)")
            st.caption(f"{leitura['descricao']} | componente {leitura['componente_id']}")


# ---------------------------------------------------------------- histórico

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
            campo, rotulo, unidade = grandeza
            lim = limites_por_tag[hist["tag"]][campo]
            df = pd.DataFrame(hist["leituras"])
            df["sev"] = df["severidade_por_grandeza"].map(lambda s: s.get(campo) or "indeterminada")
            brasilia = em_brasilia(df["timestamp_leitura"])
            df["eixo"] = eixo_grafico(brasilia)
            df["horario"] = texto_hora(brasilia)
            df["valor_txt"] = df[campo].map(lambda v: f"{br(v, 2)} {unidade}")
            df["sev_txt"] = df["sev"].map(lambda s: SEVERIDADE[s][1])

            m1, m2, m3 = st.columns(3)
            m1.metric("Mínimo no período", f"{br(df[campo].min(), 2)} {unidade}")
            m2.metric("Máximo no período", f"{br(df[campo].max(), 2)} {unidade}")
            m3.metric("Leituras em zona crítica", f"{br(100 * (df['sev'] == 'critico').mean(), 1)}%")

            topo = max(float(df[campo].max()) * 1.15, lim["critico"] * 1.15)
            zonas = pd.DataFrame({"y": [0, lim["alerta"], lim["critico"]],
                                  "y2": [lim["alerta"], lim["critico"], topo],
                                  "zona": ["normal", "alerta", "critico"]})
            cores_sev = alt.Scale(domain=["normal", "alerta", "critico", "indeterminada"],
                                  range=[COR_OK, COR_ALERTA, COR_CRITICO, COR_NEUTRA])
            faixa = (alt.Chart(zonas).mark_rect(opacity=0.1)
                     .encode(y=alt.Y("y:Q", scale=alt.Scale(domain=[0, topo])), y2="y2:Q",
                             color=alt.Color("zona:N", scale=cores_sev, legend=None)))
            tooltip = [alt.Tooltip("horario:N", title="Horário"), alt.Tooltip("valor_txt:N", title=rotulo),
                       alt.Tooltip("sev_txt:N", title="Severidade")]
            base = alt.Chart(df).encode(x=eixo_x("eixo"),
                                        y=alt.Y(f"{campo}:Q", title=f"{rotulo} ({unidade})",
                                                scale=alt.Scale(domain=[0, topo])))
            linha = base.mark_line(color=SERIES[0], strokeWidth=1.5)
            pontos = base.mark_circle(size=22, opacity=0.9).encode(
                color=alt.Color("sev:N", scale=cores_sev, legend=None), tooltip=tooltip)
            grafico([faixa, linha, pontos, *linhas_limiar(lim["alerta"], lim["critico"])])
            st.caption(f"{hist['quantidade']} leituras, uma a cada 10 s quando o poller consegue ler. Faixas: "
                       "verde normal, amarelo alerta, vermelho crítico, pelos limiares do Metric Contract.")

            with st.expander("Ver leituras"):
                tabela = pd.DataFrame({
                    "Horário": df["horario"],
                    "Vibração (mm/s)": df["velocidade_mm_s"].map(lambda v: br(v, 2)),
                    "Aceleração (g)": df["aceleracao_g"].map(lambda v: br(v, 2)),
                    "Temperatura (°C)": df["temperatura_c"].map(lambda v: br(v, 0)),
                    "Motor ligado": df["motor_ligado"].map({True: "Sim", False: "Não"}).fillna(""),
                    "Severidade": df["severidade"].map(lambda s: SEVERIDADE.get(s, (None, s))[1]),
                }).iloc[::-1]
                st.dataframe(tabela, width="stretch", hide_index=True)
        elif hist:
            st.info("Nenhuma leitura no período.")


# ---------------------------------------------------------------- observabilidade

def delta_baseline(conf: dict, ident: str, unidade: str) -> str | None:
    linha = conf.get(ident)
    if not linha or linha["valor"] is None or linha["baseline"] is None:
        return None
    diferenca = linha["valor"] - linha["baseline"]
    if abs(diferenca) < 0.05:
        return None
    sinal = "-" if diferenca < 0 else "+"
    return f"{sinal}{br(abs(diferenca), 1)}{unidade} vs baseline"


def tabela_conformidade(conformidade: list[dict]) -> None:
    linhas = [c for c in conformidade if c["status"] != "informativo"]
    contagem = {s: sum(c["status"] == s for c in linhas) for s in ("dentro", "alerta", "critico")}
    st.markdown(f"{contagem['dentro']} dentro, {contagem['alerta']} em alerta, {contagem['critico']} críticos")
    tabela = pd.DataFrame({
        "Indicador": [c["indicador"] for c in linhas],
        "Medido": [br(c["valor"], 2) for c in linhas],
        "Unidade": [c["unidade"] for c in linhas],
        "Alerta": [br(c["limiar_alerta"], 1) for c in linhas],
        "Crítico": [br(c["limiar_critico"], 1) for c in linhas],
        "Status": [STATUS_CONTRATO.get(c["status"], (COR_NEUTRA, c["status"]))[1] for c in linhas],
    })
    cor_por_rotulo = {rotulo: cor for cor, rotulo in STATUS_CONTRATO.values()}
    estilo = tabela.style.map(
        lambda v: f"background-color: {cor_por_rotulo.get(v, COR_NEUTRA)}; color: #0b0b0b; font-weight: 600",
        subset=["Status"])
    st.dataframe(estilo, width="stretch", hide_index=True)


@st.fragment(run_every=timedelta(seconds=5) if st.session_state.get("auto_obs") else None)
def painel_observabilidade(minutos: int, filtro_feature: str, filtro_sessao: str, limite: int):
    desde = datetime.now(timezone.utc) - timedelta(minutes=minutos) if minutos else None
    resumo = chamar(cliente.resumo, desde=desde)
    dados = chamar(cliente.observabilidade, filtro_feature=filtro_feature or None,
                   session_id=filtro_sessao or None, desde=desde, limite=int(limite))
    if not resumo or not dados:
        return
    ind = resumo["indicadores"]
    if not ind["total_chamadas"] or not dados["registros"]:
        st.info("Ainda não há chamadas registradas nesta janela. Use as abas Leitura atual e Histórico ou gere "
                "tráfego de teste com o comando abaixo, num terminal com o venv ativado.")
        st.code(COMANDO_TRAFEGO, language="bash")
        return
    conf = {c["id"]: c for c in resumo["conformidade"]}

    st.subheader("Visão geral")
    k = st.columns(6)
    k[0].metric("Chamadas", br(ind["total_chamadas"], 0))
    k[1].metric("Latência p95", f"{br(ind['latencia_p95_ms'], 1)} ms",
                delta_baseline(conf, "latencia_p95", " ms"), delta_color="inverse")
    k[2].metric("Disponibilidade", f"{br(ind['disponibilidade_pct'], 2)}%",
                delta_baseline(conf, "disponibilidade", " p.p."))
    k[3].metric("Cobertura de headers", f"{br(ind['cobertura_headers_pct'], 2)}%",
                delta_baseline(conf, "cobertura_headers", " p.p."))
    k[4].metric("Freshness no prazo", f"{br(ind['taxa_freshness_no_prazo_pct'], 1)}%",
                delta_baseline(conf, "freshness_no_prazo", " p.p."))
    k[5].metric("Sessões únicas", br(ind["sessoes_unicas"], 0))

    if resumo["conformidade"]:
        st.divider()
        st.subheader("Conformidade")
        tabela_conformidade(resumo["conformidade"])

    df = pd.DataFrame(dados["registros"])
    brasilia = em_brasilia(df["timestamp_utc"])
    df["eixo"] = eixo_grafico(brasilia)
    df["horario"] = texto_hora(brasilia)
    por_minuto = df.set_index("eixo").resample("1min")

    st.divider()
    st.subheader("Desempenho")
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("Latência por minuto")
        lat = por_minuto["latencia_ms"].quantile([0.5, 0.95]).unstack().dropna().reset_index()
        lat.columns = ["minuto", "p50", "p95"]
        lat = lat.melt("minuto", var_name="percentil", value_name="ms")
        lat["hora_txt"] = lat["minuto"].dt.strftime("%H:%M")
        lat["ms_txt"] = lat["ms"].map(lambda v: f"{br(v, 1)} ms")
        linha = (alt.Chart(lat).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=30))
                 .encode(x=eixo_x("minuto"), y=alt.Y("ms:Q", title="Latência (ms)"),
                         color=alt.Color("percentil:N", scale=alt.Scale(range=SERIES[:2]), title=None),
                         tooltip=[alt.Tooltip("hora_txt:N", title="Minuto"), alt.Tooltip("percentil:N", title="Percentil"),
                                  alt.Tooltip("ms_txt:N", title="Latência")]))
        grafico([linha, *linhas_limiar(250, 1000)])
    with g2:
        st.markdown("Chamadas por minuto")
        vol = por_minuto.size().reset_index(name="chamadas")
        vol["hora_txt"] = vol["eixo"].dt.strftime("%H:%M")
        grafico([alt.Chart(vol).mark_line(color=SERIES[0], strokeWidth=2)
                 .encode(x=eixo_x("eixo"), y=alt.Y("chamadas:Q", title="Chamadas por minuto"),
                         tooltip=[alt.Tooltip("hora_txt:N", title="Minuto"),
                                  alt.Tooltip("chamadas:Q", title="Chamadas")])])

    st.divider()
    st.subheader("Qualidade do dado")
    g3, g4 = st.columns(2)
    with g3:
        st.markdown("Idade do dado na leitura atual")
        fr = df[df["idade_dado_s"].notna()].copy()
        if fr.empty:
            st.caption("Sem leituras atuais na janela.")
        else:
            fr["idade_txt"] = fr["idade_dado_s"].map(lambda v: f"{br(v, 1)} s")
            pontos = (alt.Chart(fr).mark_circle(size=30)
                      .encode(x=eixo_x("eixo"), y=alt.Y("idade_dado_s:Q", title="Idade do dado (s)"),
                              color=alt.Color("tag:N", scale=alt.Scale(range=SERIES[:2]), title="Sensor"),
                              tooltip=[alt.Tooltip("horario:N", title="Horário"), alt.Tooltip("tag:N", title="Sensor"),
                                       alt.Tooltip("idade_txt:N", title="Idade")]))
            grafico([pontos, *linhas_limiar(30, 300)])
    with g4:
        st.markdown("Cobertura de headers por feature")
        cob = (df.groupby("feature")["headers_completos"].mean() * 100).reset_index(name="cobertura")
        cob["cob_txt"] = cob["cobertura"].map(lambda v: f"{br(v, 1)}%")
        barras = (alt.Chart(cob).mark_bar(color=SERIES[0])
                  .encode(y=alt.Y("feature:N", sort="-x", title=None),
                          x=alt.X("cobertura:Q", title="Chamadas com os dois headers (%)",
                                  scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(grid=False)),
                          tooltip=[alt.Tooltip("feature:N", title="Feature"), alt.Tooltip("cob_txt:N", title="Cobertura")]))
        meta = (alt.Chart(pd.DataFrame({"x": [95]})).mark_rule(color=COR_ALERTA, strokeDash=[6, 4], strokeWidth=2)
                .encode(x="x:Q"))
        grafico([barras, meta])

    st.divider()
    st.subheader("Uso")
    g5, g6 = st.columns(2)
    with g5:
        st.markdown("Status HTTP por rota")
        status = df.assign(rota_curta=df["rota"].map(ROTAS_CURTAS).fillna(df["rota"]))
        status = status.groupby(["rota_curta", "status_code"]).size().reset_index(name="chamadas")
        status["status_code"] = status["status_code"].astype(str)
        grafico([alt.Chart(status).mark_bar()
                 .encode(y=alt.Y("rota_curta:N", title=None), x=alt.X("chamadas:Q", title="Chamadas",
                                                                       axis=alt.Axis(grid=False)),
                         color=alt.Color("status_code:N", title="Status HTTP",
                                         scale=alt.Scale(range=[SERIES[0], "#eda100", SERIES[1], "#e34948"])),
                         tooltip=[alt.Tooltip("rota_curta:N", title="Rota"),
                                  alt.Tooltip("status_code:N", title="Status"),
                                  alt.Tooltip("chamadas:Q", title="Chamadas")])])
    with g6:
        st.markdown("Uso por feature")
        uso = df["feature"].value_counts().reset_index()
        uso.columns = ["feature", "chamadas"]
        grafico([alt.Chart(uso).mark_bar(color=SERIES[0])
                 .encode(y=alt.Y("feature:N", sort="-x", title=None),
                         x=alt.X("chamadas:Q", title="Chamadas", axis=alt.Axis(grid=False)),
                         tooltip=[alt.Tooltip("feature:N", title="Feature"),
                                  alt.Tooltip("chamadas:Q", title="Chamadas")])])

    st.divider()
    st.subheader("Registros")
    recentes = df.sort_values("id", ascending=False).head(200)
    registros = pd.DataFrame({
        "Horário": recentes["horario"],
        "Feature": recentes["feature"],
        "Rota": recentes["rota"].map(ROTAS_CURTAS).fillna(recentes["rota"]),
        "Sensor": recentes["tag"].fillna(""),
        "Status HTTP": recentes["status_code"].astype(str),
        "Latência (ms)": recentes["latencia_ms"].map(lambda v: br(v, 1)),
        "Headers completos": recentes["headers_completos"].map({True: "Sim", False: "Não"}),
        "Idade do dado (s)": recentes["idade_dado_s"].map(lambda v: br(v, 1)),
        "Sessão": recentes["session_id"].str[:8],
    })
    with st.expander(f"Ver registros ({len(registros)} mais recentes de {len(df)})"):
        st.dataframe(registros, width="stretch", hide_index=True)


with aba_obs:
    with st.expander("Filtros", expanded=True):
        f1, f2, f3, f4 = st.columns(4)
        minutos = f1.selectbox("Janela", [15, 60, 360, 1440, 0],
                               format_func=lambda m: "tudo" if m == 0 else f"últimos {m} min", index=4)
        filtro_feature = f2.text_input("Feature (X-Feature)")
        filtro_sessao = f3.text_input("Sessão (X-Session-Id)")
        limite_registros = f4.number_input("Máximo de registros", 50, 10000, value=2000, step=50)
        st.toggle("Atualizar a cada 5 s", key="auto_obs")
    painel_observabilidade(minutos, filtro_feature, filtro_sessao, int(limite_registros))
