"""Análise de governança sobre os registros coletados pela API.

Lê data/observabilidade.db e data/execucoes.json, calcula os indicadores da janela de
baseline e da janela de avaliação, compara a avaliação com os limiares do metric
contract e gera figuras em governanca/figuras/ e tabelas em governanca/resultados/.

Uso:
    python governanca/analise.py                    # só analisa
    python governanca/analise.py --gravar-baseline  # também grava a baseline no contrato
"""

import argparse
import json
import locale
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

from app.observability.metrics import (  # noqa: E402
    PRAZO_FRESHNESS_S, ROTA_HISTORICO, ROTA_LEITURA, avaliar_conformidade, calcular_indicadores,
    carregar_contrato,
)
from app.providers.sensores import (  # noqa: E402
    PISO_OPERACAO_MM_S, SENSORES, SensoresProvider, carregar_historico,
)

DB = RAIZ / "data" / "observabilidade.db"
EXECUCOES = RAIZ / "data" / "execucoes.json"
CONTRATO = RAIZ / "governanca" / "metric_contract.yaml"
FIGURAS = RAIZ / "governanca" / "figuras"
RESULTADOS = RAIZ / "governanca" / "resultados"

AZUL, LARANJA, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
COR_ALERTA, COR_CRITICO, COR_OK = "#fab219", "#d03b3b", "#0ca30c"
TINTA, TINTA_2, GRADE = "#0b0b0b", "#52514e", "#e4e3df"

# Vírgula decimal nos eixos, como se escreve em português.
for nome_locale in ("pt_BR.UTF-8", "Portuguese_Brazil.1252", "pt_BR"):
    try:
        locale.setlocale(locale.LC_NUMERIC, nome_locale)
        break
    except locale.Error:
        continue

plt.rcParams.update({
    "axes.formatter.use_locale": True,
    "font.family": ["Arial", "DejaVu Sans"],
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.edgecolor": TINTA_2,
    "axes.labelcolor": TINTA,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": GRADE,
    "grid.linewidth": 0.8,
    "xtick.color": TINTA_2,
    "ytick.color": TINTA_2,
    "legend.frameon": False,
    "figure.dpi": 100,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
})


def carregar_registros() -> pd.DataFrame:
    with sqlite3.connect(DB) as conn:
        df = pd.read_sql_query("SELECT * FROM chamadas ORDER BY id", conn)
    df["headers_completos"] = df["headers_completos"].astype(bool)
    df["ts"] = pd.to_datetime(df["timestamp_utc"], format="ISO8601")
    return df


def janelas_execucao() -> dict:
    execucoes = json.loads(EXECUCOES.read_text(encoding="utf-8"))
    # Se um cenário foi rodado mais de uma vez, vale a última execução.
    return {e["cenario"]: e for e in execucoes}


def recortar(df: pd.DataFrame, execucao: dict) -> pd.DataFrame:
    return df[(df["timestamp_utc"] >= execucao["inicio"]) & (df["timestamp_utc"] <= execucao["fim"])].copy()


def como_registros(df: pd.DataFrame) -> list[dict]:
    colunas = [c for c in df.columns if c != "ts"]
    return df[colunas].astype(object).where(df[colunas].notna(), None).to_dict("records")


def gravar_baseline(indicadores: dict, execucao: dict) -> None:
    """Escreve a baseline medida no YAML sem perder os comentários do arquivo."""
    texto = CONTRATO.read_text(encoding="utf-8")
    contrato = carregar_contrato(CONTRATO)
    for item in contrato["indicadores"]:
        valor = indicadores.get(item["campo_resumo"])
        if isinstance(valor, dict):
            valor = None
        bloco = re.compile(rf"(  - id: {item['id']}\n(?:    .*\n|      .*\n)*?    baseline: )[^\n]*")
        texto = bloco.sub(lambda m: m.group(1) + ("null" if valor is None else f"{valor}"), texto, count=1)
    for campo in ("inicio", "fim", "chamadas"):
        texto = re.sub(rf"(baseline_origem:\n(?:  .*\n)*?  {campo}: )[^\n]*",
                       lambda m: m.group(1) + f'"{execucao[campo]}"' if campo != "chamadas"
                       else m.group(1) + str(execucao[campo]), texto, count=1)
    CONTRATO.write_text(texto, encoding="utf-8")


def _faixas(ax, alerta, critico, maior_pior=True, rotulo_unidade=""):
    if alerta is not None:
        ax.axhline(alerta, color=COR_ALERTA, linestyle="--", linewidth=1.5,
                   label=f"limiar de alerta ({_dec_g(alerta)}{rotulo_unidade})")
    if critico is not None:
        ax.axhline(critico, color=COR_CRITICO, linestyle="--", linewidth=1.5,
                   label=f"limiar crítico ({_dec_g(critico)}{rotulo_unidade})")


def _divisor(ax, inicio_avaliacao):
    ax.axvline(inicio_avaliacao, color=TINTA_2, linewidth=1, linestyle=":")
    ax.annotate(" início da avaliação", (inicio_avaliacao, 1), xycoords=("data", "axes fraction"),
                va="top", ha="left", fontsize=8, color=TINTA_2)


def _eixo_tempo(ax):
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.set_xlabel("Horário (UTC)")


def _salvar(fig, nome: str) -> str:
    caminho = FIGURAS / nome
    fig.savefig(caminho)
    plt.close(fig)
    return caminho.name


def _dec_g(valor: float) -> str:
    return f"{valor:g}".replace(".", ",")


def _dec(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def fig_arquitetura() -> str:
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.set_axis_off()
    ax.set_xlim(0, 10.4)
    ax.set_ylim(0, 4.4)
    caixas = {
        "front": (0.1, 2.3, "Streamlit\n(frontend/app.py)\ne script requests"),
        "api": (3.8, 2.3, "FastAPI\nrotas /v1/sensores\ne /v1/observabilidade"),
        "prov": (7.5, 2.3, "Provider de Sensores\n(historiador simulado)"),
        "mw": (3.8, 0.2, "Middleware de\nobservabilidade"),
        "db": (7.5, 0.2, "SQLite\ntabela chamadas"),
    }
    for chave, (x, y, texto) in caixas.items():
        cor = "#eef4fc" if chave in ("front", "api", "prov") else "#fdf0ea"
        ax.add_patch(FancyBboxPatch((x, y), 2.7, 1.4, boxstyle="round,pad=0.02,rounding_size=0.12",
                                    facecolor=cor, edgecolor=TINTA_2, linewidth=1))
        ax.text(x + 1.35, y + 0.7, texto, ha="center", va="center", fontsize=9, color=TINTA)

    def seta(x0, y0, x1, y1):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=12,
                                     color=TINTA_2, linewidth=1.2))

    seta(2.85, 3.0, 3.75, 3.0)
    ax.text(3.3, 3.85, "GET com X-Session-Id\ne X-Feature", ha="center", va="bottom", fontsize=8, color=TINTA_2)
    seta(6.55, 3.0, 7.45, 3.0)
    ax.text(7.0, 3.85, "consulta", ha="center", va="bottom", fontsize=8, color=TINTA_2)
    seta(5.15, 2.25, 5.15, 1.65)
    ax.text(5.25, 1.95, "latência, status, idade, completude", fontsize=8, color=TINTA_2, va="center")
    seta(6.55, 0.9, 7.45, 0.9)
    ax.text(7.0, 1.0, "INSERT", ha="center", va="bottom", fontsize=8, color=TINTA_2)
    return _salvar(fig, "fig01_arquitetura.png")


def fig_latencia(df, inicio_aval, contrato_idx) -> str:
    fig, ax = plt.subplots(figsize=(9, 3.8))
    por_min = df.set_index("ts").resample("1min")["latencia_ms"]
    serie = pd.DataFrame({"p50": por_min.quantile(0.5), "p95": por_min.quantile(0.95),
                          "p99": por_min.quantile(0.99)}).dropna()
    for coluna, cor in (("p50", AZUL), ("p95", LARANJA), ("p99", AQUA)):
        ax.plot(serie.index, serie[coluna], color=cor, linewidth=2, marker="o", markersize=4, label=coluna)
    c = contrato_idx["latencia_p95"]
    _faixas(ax, c["limiar_alerta"], c["limiar_critico"], rotulo_unidade=" ms, p95")
    _divisor(ax, inicio_aval)
    ax.set_ylabel("Latência (ms)")
    ax.set_title("Latência p50, p95 e p99 por janela de 1 minuto")
    _eixo_tempo(ax)
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1))
    return _salvar(fig, "fig02_latencia_percentis.png")


def fig_hist_latencia(aval, ind) -> str:
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.hist(aval["latencia_ms"], bins=60, color=AZUL, edgecolor="white", linewidth=0.5)
    ax.axvline(ind["latencia_p95_ms"], color=LARANJA, linewidth=2, label=f"p95 = {_dec(ind['latencia_p95_ms'])} ms")
    ax.axvline(ind["latencia_p50_ms"], color=TINTA_2, linewidth=1.5, linestyle=":",
               label=f"p50 = {_dec(ind['latencia_p50_ms'])} ms")
    ax.set_xlabel("Latência (ms)")
    ax.set_ylabel("Chamadas")
    ax.set_title("Distribuição da latência na janela de avaliação")
    ax.legend()
    return _salvar(fig, "fig03_histograma_latencia.png")


def fig_status(aval) -> str:
    fig, ax = plt.subplots(figsize=(8, 3.2))
    rotas = {ROTA_LEITURA: "leitura-atual", ROTA_HISTORICO: "historico"}
    tabela = aval.assign(rota_curta=aval["rota"].map(rotas).fillna(aval["rota"])) \
        .pivot_table(index="rota_curta", columns="status_code", values="id", aggfunc="count", fill_value=0)
    cores = {200: AZUL, 404: "#eda100", 422: LARANJA, 503: "#e34948"}
    esquerda = pd.Series(0, index=tabela.index)
    for status in tabela.columns:
        valores = tabela[status]
        ax.barh(tabela.index, valores, left=esquerda, color=cores.get(status, TINTA_2),
                edgecolor="white", linewidth=2, label=str(status), height=0.55)
        esquerda += valores
    ax.set_xlabel("Chamadas")
    ax.set_title("Chamadas por rota e código de status (avaliação)")
    ax.grid(axis="y", visible=False)
    ax.legend(title="Status", loc="upper left", bbox_to_anchor=(1, 1))
    return _salvar(fig, "fig04_status_por_rota.png")


def fig_disponibilidade(df, inicio_aval, c) -> str:
    fig, ax = plt.subplots(figsize=(9, 3.4))
    por_min = df.set_index("ts").resample("1min")["status_code"]
    disp = por_min.apply(lambda s: 100 * (s < 500).mean() if len(s) else None).dropna()
    ax.plot(disp.index, disp.values, color=AZUL, linewidth=2, marker="o", markersize=4, label="disponibilidade")
    _faixas(ax, c["limiar_alerta"], c["limiar_critico"], rotulo_unidade="%")
    _divisor(ax, inicio_aval)
    ax.set_ylim(min(95, disp.min() - 0.5), 100.3)
    ax.set_ylabel("Chamadas sem 5xx (%)")
    ax.set_title("Disponibilidade por janela de 1 minuto")
    _eixo_tempo(ax)
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1))
    return _salvar(fig, "fig05_disponibilidade.png")


def fig_freshness(df, inicio_aval, c) -> str:
    fig, ax = plt.subplots(figsize=(9, 3.8))
    fr = df[(df["rota"] == ROTA_LEITURA) & (df["status_code"] == 200)]
    topo = max(fr["idade_dado_s"].max() * 1.08, c["limiar_critico"] * 1.15)
    ax.axhspan(c["limiar_alerta"], c["limiar_critico"], color=COR_ALERTA, alpha=0.15, linewidth=0)
    ax.axhspan(c["limiar_critico"], topo, color=COR_CRITICO, alpha=0.10, linewidth=0)
    for tag, cor in (("S1", AZUL), ("S2", LARANJA)):
        parte = fr[fr["tag"] == tag]
        ax.scatter(parte["ts"], parte["idade_dado_s"], s=10, color=cor, alpha=0.6, label=f"leitura atual {tag}")
    mediana = fr.set_index("ts").resample("1min")["idade_dado_s"].median().dropna()
    ax.plot(mediana.index, mediana.values, color=TINTA, linewidth=1.5, label="mediana por minuto")
    _faixas(ax, c["limiar_alerta"], c["limiar_critico"], rotulo_unidade=" s")
    _divisor(ax, inicio_aval)
    ax.set_ylim(0, topo)
    ax.set_ylabel("Idade do dado (s)")
    ax.set_title("Freshness: idade da leitura atual no momento da resposta")
    _eixo_tempo(ax)
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1))
    return _salvar(fig, "fig06_freshness.png")


def fig_freshness_no_prazo(df, inicio_aval, c, prazo=PRAZO_FRESHNESS_S) -> str:
    fig, ax = plt.subplots(figsize=(9, 3.4))
    fr = df[(df["rota"] == ROTA_LEITURA) & (df["status_code"] == 200)].set_index("ts")
    taxa = fr.resample("2min")["idade_dado_s"].apply(lambda s: 100 * (s <= prazo).mean() if len(s) else None).dropna()
    ax.plot(taxa.index, taxa.values, color=AZUL, linewidth=2, marker="o", markersize=4, label="dentro do prazo")
    _faixas(ax, c["limiar_alerta"], c["limiar_critico"], rotulo_unidade="%")
    _divisor(ax, inicio_aval)
    ax.set_ylim(max(0, taxa.min() - 5), 101)
    ax.set_ylabel(f"Leituras com idade até {prazo} s (%)")
    ax.set_title("Taxa de completude de freshness por janela de 2 minutos")
    _eixo_tempo(ax)
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1))
    return _salvar(fig, "fig07_freshness_no_prazo.png")


def fig_completude(df, inicio_aval, c) -> str:
    fig, ax = plt.subplots(figsize=(9, 3.4))
    comp = df.set_index("ts").resample("1min")["completude"].mean().dropna() * 100
    ax.plot(comp.index, comp.values, color=AZUL, linewidth=2, marker="o", markersize=4, label="completude média")
    _faixas(ax, c["limiar_alerta"], c["limiar_critico"], rotulo_unidade="%")
    _divisor(ax, inicio_aval)
    ax.set_ylim(min(93, comp.min() - 1), 100.5)
    ax.set_ylabel("Campos preenchidos (%)")
    ax.set_title("Completude do payload por janela de 1 minuto")
    _eixo_tempo(ax)
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1))
    return _salvar(fig, "fig08_completude.png")


def intervalos_servidos(execucao) -> list[float]:
    """Reconstrói os intervalos entre leituras que o histórico devolveu na avaliação.

    O provider é determinístico, então consultar a mesma janela (a última hora antes do
    fim da avaliação, que é o padrão da rota) devolve exatamente as leituras servidas.
    """
    fim = datetime.fromisoformat(execucao["fim"])
    provider = SensoresProvider(simular_latencia=False, relogio=lambda: fim.timestamp())
    inicio = datetime.fromisoformat(execucao["inicio"]) - timedelta(hours=1)
    intervalos = []
    for tag in SENSORES:
        leituras = provider.historico(tag, inicio, fim, 5000)
        tempos = [item["timestamp_leitura"].timestamp() for item in leituras]
        intervalos += [b - a for a, b in zip(tempos, tempos[1:])]
    return intervalos


def fig_intervalos(intervalos, c_medio, c_max) -> str:
    fig, ax = plt.subplots(figsize=(8, 3.6))
    serie = pd.Series(intervalos)
    contagem = serie.value_counts().sort_index()
    ax.bar(contagem.index, contagem.values, width=8, color=AZUL, edgecolor="white", linewidth=1)
    ax.set_yscale("log")
    ax.axvline(c_max["limiar_alerta"], color=COR_ALERTA, linestyle="--", linewidth=1.5,
               label=f"alerta para maior lacuna ({_dec_g(c_max['limiar_alerta'])} s)")
    ax.axvline(c_max["limiar_critico"], color=COR_CRITICO, linestyle="--", linewidth=1.5,
               label=f"crítico para maior lacuna ({_dec_g(c_max['limiar_critico'])} s)")
    ax.set_xlabel("Intervalo entre leituras consecutivas (s)")
    ax.set_ylabel("Ocorrências (escala log)")
    ax.set_title(f"Tempo de atualização: média de {_dec(serie.mean())} s em {len(serie)} intervalos")
    ax.legend(loc="upper right")
    return _salvar(fig, "fig09_intervalo_atualizacao.png")


def fig_cobertura(aval, c) -> str:
    fig, ax = plt.subplots(figsize=(8, 3.6))
    cob = (aval.groupby("feature")["headers_completos"].mean() * 100).sort_values()
    contagem = aval["feature"].value_counts()
    ax.barh(cob.index, cob.values, color=AZUL, height=0.55, edgecolor="white", linewidth=2)
    for i, (feature, valor) in enumerate(cob.items()):
        ax.text(valor + 1, i, f"{_dec(valor, 0)}% ({contagem[feature]} chamadas)", va="center", fontsize=8, color=TINTA)
    ax.axvline(c["limiar_alerta"], color=COR_ALERTA, linestyle="--", linewidth=1.5,
               label=f"meta ({_dec_g(c['limiar_alerta'])}%)")
    ax.set_xlim(0, 135)
    ax.set_xticks(range(0, 101, 20))
    ax.set_xlabel("Chamadas com os dois headers (%)")
    ax.set_title("Cobertura de headers por valor de X-Feature (avaliação)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right")
    return _salvar(fig, "fig10_cobertura_headers.png")


def fig_throughput(df, inicio_aval, baseline) -> str:
    fig, ax = plt.subplots(figsize=(9, 3.4))
    vol = df.set_index("ts").resample("1min").size()
    vol = vol.iloc[1:-1] if len(vol) > 3 else vol  # minutos das pontas ficam incompletos
    ax.plot(vol.index, vol.values, color=AZUL, linewidth=2, marker="o", markersize=4, label="chamadas por minuto")
    if baseline:
        ax.axhline(baseline * 0.5, color=COR_ALERTA, linestyle="--", linewidth=1.5,
                   label=f"alerta: 50% da baseline ({_dec(baseline * 0.5, 0)}/min)")
    _divisor(ax, inicio_aval)
    ax.set_ylim(0, vol.max() * 1.2)
    ax.set_ylabel("Chamadas/min")
    ax.set_title("Volume de chamadas por minuto")
    _eixo_tempo(ax)
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1))
    return _salvar(fig, "fig11_throughput.png")


def fig_uso(aval) -> str:
    fig, ax = plt.subplots(figsize=(8, 3.2))
    uso = aval["feature"].value_counts().sort_values()
    ax.barh(uso.index, uso.values, color=AZUL, height=0.55, edgecolor="white", linewidth=2)
    for i, valor in enumerate(uso.values):
        ax.text(valor + 3, i, str(valor), va="center", fontsize=8, color=TINTA)
    ax.set_xlabel("Chamadas")
    ax.set_title("Uso por funcionalidade (X-Feature) na avaliação")
    ax.grid(axis="y", visible=False)
    return _salvar(fig, "fig12_uso_por_feature.png")


def fig_critica(df, inicio_aval, c) -> str:
    fig, ax = plt.subplots(figsize=(9, 3.4))
    lt = df[(df["rota"] == ROTA_LEITURA) & (df["status_code"] == 200)].set_index("ts")
    prop = lt.resample("2min")["severidade"].apply(lambda s: 100 * (s == "critico").mean() if len(s) else None).dropna()
    ax.plot(prop.index, prop.values, color=AZUL, linewidth=2, marker="o", markersize=4, label="leituras críticas")
    _faixas(ax, c["limiar_alerta"], c["limiar_critico"], rotulo_unidade="%")
    _divisor(ax, inicio_aval)
    ax.set_ylim(0, max(prop.max(), c["limiar_critico"]) * 1.2)
    ax.set_ylabel("Leituras críticas (%)")
    ax.set_title("Proporção de leituras críticas por janela de 2 minutos")
    _eixo_tempo(ax)
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1))
    return _salvar(fig, "fig13_proporcao_critica.png")


def estatisticas_historico_real() -> dict:
    """Distribuição do histórico real de 19/05 pelas zonas da ISO 10816-1 Classe I."""
    tempos, portas = carregar_historico()
    saida = {"linhas": len(tempos), "duracao_h": round(tempos[-1] / 3600, 2)}
    for porta, tag in ((1, "S1"), (2, "S2")):
        vel = pd.Series([v for v, _, _ in portas[porta]])
        temp = pd.Series([t for _, _, t in portas[porta]])
        acel = pd.Series([a for _, a, _ in portas[porta]])
        ligado = vel[vel >= PISO_OPERACAO_MM_S]
        plato = vel[vel >= 4.5]
        saida[tag] = {
            "desligado_pct": round(100 * (vel < PISO_OPERACAO_MM_S).mean(), 1),
            "zona_c_pct": round(100 * ((vel >= 1.8) & (vel < 4.5)).mean(), 1),
            "zona_d_pct": round(100 * (vel >= 4.5).mean(), 1),
            "zona_d_entre_ligado_pct": round(100 * (ligado >= 4.5).mean(), 1),
            "mediana_plato_mm_s": round(float(plato.median()), 2),
            "velocidade_max_mm_s": float(vel.max()),
            "temperatura_max_c": float(temp.max()),
            "aceleracao_max_g": float(acel.max()),
        }
    return saida


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gravar-baseline", action="store_true")
    args = parser.parse_args()

    FIGURAS.mkdir(parents=True, exist_ok=True)
    RESULTADOS.mkdir(parents=True, exist_ok=True)

    df = carregar_registros()
    execucoes = janelas_execucao()
    base_df = recortar(df, execucoes["baseline"])
    aval_df = recortar(df, execucoes["avaliacao"])
    ind_base = calcular_indicadores(como_registros(base_df))
    ind_aval = calcular_indicadores(como_registros(aval_df))

    if args.gravar_baseline:
        gravar_baseline(ind_base, execucoes["baseline"])
        print("Baseline gravada em", CONTRATO.relative_to(RAIZ))

    contrato = carregar_contrato(CONTRATO)
    idx = {i["id"]: i for i in contrato["indicadores"]}
    conformidade = avaliar_conformidade(ind_aval, contrato)

    periodo = pd.concat([base_df, aval_df])
    inicio_aval = aval_df["ts"].min()
    intervalos = intervalos_servidos(execucoes["avaliacao"])

    figuras = [
        fig_arquitetura(),
        fig_latencia(periodo, inicio_aval, idx),
        fig_hist_latencia(aval_df, ind_aval),
        fig_status(aval_df),
        fig_disponibilidade(periodo, inicio_aval, idx["disponibilidade"]),
        fig_freshness(periodo, inicio_aval, idx["freshness_p95"]),
        fig_freshness_no_prazo(periodo, inicio_aval, idx["freshness_no_prazo"]),
        fig_completude(periodo, inicio_aval, idx["completude_payload"]),
        fig_intervalos(intervalos, idx["intervalo_atualizacao"], idx["maior_lacuna"]),
        fig_cobertura(aval_df, idx["cobertura_headers"]),
        fig_throughput(periodo, inicio_aval, idx["throughput"].get("baseline")),
        fig_uso(aval_df),
        fig_critica(periodo, inicio_aval, idx["proporcao_critica"]),
    ]

    tabela = pd.DataFrame(conformidade)
    tabela.to_csv(RESULTADOS / "tabela_conformidade.csv", index=False, encoding="utf-8")

    sem_header = aval_df[~aval_df["headers_completos"]]
    erros_4xx = aval_df[(aval_df["status_code"] >= 400) & (aval_df["status_code"] < 500)]
    lat_rota = aval_df.groupby("rota")["latencia_ms"].quantile(0.95).round(1).to_dict()
    detalhes = {
        "registros_total_banco": len(df),
        "chamadas_baseline": len(base_df),
        "chamadas_avaliacao": len(aval_df),
        "sem_header_por_user_agent": sem_header["user_agent"].value_counts().to_dict(),
        "erros_4xx_por_status": erros_4xx["status_code"].value_counts().to_dict(),
        "erros_4xx_por_feature": erros_4xx["feature"].value_counts().to_dict(),
        "erros_5xx": int((aval_df["status_code"] >= 500).sum()),
        "latencia_p95_por_rota": lat_rota,
        "leituras_desatualizadas_300s": int((aval_df["idade_dado_s"] > 300).sum()),
        "leituras_offline_30s": int((aval_df["idade_dado_s"] > PRAZO_FRESHNESS_S).sum()),
        "leituras_atuais_ok": int(((aval_df["rota"] == ROTA_LEITURA) & (aval_df["status_code"] == 200)).sum()),
        "intervalos_reconstruidos": len(intervalos),
        "intervalo_medio_reconstruido_s": round(sum(intervalos) / len(intervalos), 2),
        "chamadas_lentas_acima_250ms": int((aval_df["latencia_ms"] > 250).sum()),
        "offline_por_tag": aval_df[aval_df["idade_dado_s"] > PRAZO_FRESHNESS_S].groupby("tag").agg(
            leituras=("id", "count"), idade_max_s=("idade_dado_s", "max"),
            primeira=("timestamp_utc", "min")).round(0).to_dict("index"),
        "maior_lacuna_por_tag_avaliacao": aval_df.groupby("tag")["intervalo_max_s"].max().dropna().to_dict(),
        "maior_lacuna_por_tag_baseline": base_df.groupby("tag")["intervalo_max_s"].max().dropna().to_dict(),
        "sem_header_por_feature_e_user_agent": {
            f"{f} | {ua}": n for (f, ua), n in sem_header.groupby(["feature", "user_agent"]).size().items()},
        "erros_404_por_tag": erros_4xx[erros_4xx["status_code"] == 404]["tag"].value_counts().to_dict(),
        "erros_5xx_baseline": int((base_df["status_code"] >= 500).sum()),
        "severidade_leitura_atual_baseline": base_df[base_df["rota"] == ROTA_LEITURA]["severidade"]
        .value_counts().to_dict(),
        "severidade_leitura_atual_avaliacao": aval_df[aval_df["rota"] == ROTA_LEITURA]["severidade"]
        .value_counts().to_dict(),
        "historico_real": estatisticas_historico_real(),
    }
    resultados = {
        "gerado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "execucoes": execucoes,
        "baseline": ind_base,
        "avaliacao": ind_aval,
        "conformidade": conformidade,
        "detalhes": detalhes,
        "figuras": figuras,
    }
    (RESULTADOS / "resultados.json").write_text(
        json.dumps(resultados, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"Baseline: {len(base_df)} chamadas | Avaliação: {len(aval_df)} chamadas")
    print(tabela[["indicador", "valor", "baseline", "limiar_alerta", "limiar_critico", "status"]].to_string(index=False))
    print(f"\n{len(figuras)} figuras em {FIGURAS.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
