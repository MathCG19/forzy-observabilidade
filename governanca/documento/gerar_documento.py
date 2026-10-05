"""Gera o documento ABNT do checkpoint a partir do contrato e dos resultados da análise.

Rodar depois de governanca/analise.py:
    python governanca/documento/gerar_documento.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from abnt import (  # noqa: E402
    WD_ALIGN_PARAGRAPH, Cm, Contador, campo_indice, destaque_amarelo, figura, grade, nova_secao,
    novo_documento, paragrafo, quebra_pagina, texto_com_italico,
)

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "backend"))
from app.observability.metrics import classificar  # noqa: E402
FIG = RAIZ / "governanca" / "figuras"
SAIDA = RAIZ / "governanca" / "documento" / "Checkpoint_Governanca_Observabilidade.docx"

R = json.loads((RAIZ / "governanca" / "resultados" / "resultados.json").read_text(encoding="utf-8"))
CONTRATO = yaml.safe_load((RAIZ / "governanca" / "metric_contract.yaml").read_text(encoding="utf-8"))
IND = {i["id"]: i for i in CONTRATO["indicadores"]}
CONF = {c["id"]: c for c in R["conformidade"]}
BASE, AVAL, DET = R["baseline"], R["avaliacao"], R["detalhes"]
EXEC_B, EXEC_A = R["execucoes"]["baseline"], R["execucoes"]["avaliacao"]

STATUS_PT = {"dentro": "Dentro", "alerta": "Alerta", "critico": "Crítico", "informativo": "Informativo",
             "sem dados": "Sem dados"}


def br(valor, casas=1):
    if valor is None:
        return "-"
    if isinstance(valor, int) or float(valor).is_integer() and casas == 0:
        return f"{int(round(valor)):,}".replace(",", ".")
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def hora(iso):
    return datetime.fromisoformat(iso).strftime("%H:%M:%S")


def data_br(iso):
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y")


def contagem_status():
    linhas = [c for c in R["conformidade"] if c["status"] in ("dentro", "alerta", "critico")]
    return {s: [c for c in linhas if c["status"] == s] for s in ("dentro", "alerta", "critico")}


H = []  # títulos para o sumário (nível, texto)


def titulo(doc, texto, nivel=1):
    doc.add_heading(texto, level=nivel)
    H.append((nivel, texto.upper() if nivel <= 2 else texto))


def p(doc, texto):
    return paragrafo(doc, texto)


# ---------------------------------------------------------------- pré-textuais

def capa(doc):
    c = WD_ALIGN_PARAGRAPH.CENTER
    for linha in ("FACULDADE DE INFORMÁTICA E ADMINISTRAÇÃO PAULISTA (FIAP)",
                  "TECNÓLOGO EM INTELIGÊNCIA ARTIFICIAL"):
        paragrafo(doc, linha, negrito=True, alinhamento=c, recuo=Cm(0))
    for _ in range(3):
        paragrafo(doc)
    for nome in ("MATHEUS CARDOSO GOMES", "CAIQUE SOUSA"):
        paragrafo(doc, nome, alinhamento=c, recuo=Cm(0))
    for _ in range(6):
        paragrafo(doc)
    pt = paragrafo(doc, "OBSERVABILIDADE DE UM ENDPOINT DE IA:", negrito=True, alinhamento=c, recuo=Cm(0))
    pt.add_run(" Sensor Monitoring API do Forzy Digital Twin")
    for _ in range(11):
        paragrafo(doc)
    paragrafo(doc, "SÃO PAULO", alinhamento=c, recuo=Cm(0))
    paragrafo(doc, "2026", alinhamento=c, recuo=Cm(0))


def folha_rosto(doc):
    c = WD_ALIGN_PARAGRAPH.CENTER
    for nome in ("MATHEUS CARDOSO GOMES (RM 564898)", "CAIQUE SOUSA (RM 563621)"):
        paragrafo(doc, nome, alinhamento=c, recuo=Cm(0))
    for _ in range(7):
        paragrafo(doc)
    pt = paragrafo(doc, "OBSERVABILIDADE DE UM ENDPOINT DE IA:", negrito=True, alinhamento=c, recuo=Cm(0))
    pt.add_run(" Sensor Monitoring API do Forzy Digital Twin")
    for _ in range(3):
        paragrafo(doc)
    natureza = ("Checkpoint apresentado à disciplina de Governança em IA do curso Tecnólogo em Inteligência "
                "Artificial da FIAP, integrado à disciplina de Front-end, como requisito parcial de avaliação.")
    for texto in (natureza, "", "Professor(a): [NOME DO PROFESSOR]"):
        q = paragrafo(doc, texto, recuo=Cm(0))
        q.paragraph_format.left_indent = Cm(8)
        q.paragraph_format.line_spacing = 1.0
    for _ in range(9):
        paragrafo(doc)
    paragrafo(doc, "SÃO PAULO", alinhamento=c, recuo=Cm(0))
    paragrafo(doc, "2026", alinhamento=c, recuo=Cm(0))


def resumo(doc):
    paragrafo(doc, "RESUMO", "Titulo sem numero")
    s = contagem_status()
    criticos = ", ".join(c["indicador"].lower() for c in s["critico"]) or "nenhum"
    texto = (
        "Este trabalho define e valida um contrato mínimo de observabilidade para o endpoint de sensores do "
        "Forzy Digital Twin. O grupo expôs o provider de Sensores como uma API FastAPI com rotas de leitura atual, "
        "histórico e observabilidade, e implementou um middleware que grava em SQLite, a cada chamada, os headers "
        "de contexto X-Session-Id e X-Feature, o instante em UTC, a latência, o código de status, a idade do dado "
        "e a completude do payload. A partir desses campos mapeamos "
        f"{len(CONTRATO['indicadores'])} indicadores, entre eles latência p95, disponibilidade, freshness, taxa de "
        "completude de freshness, tempo de atualização e cobertura de headers. Cada indicador recebeu definição, "
        "fórmula, baseline, limiar de alerta, limiar crítico, visualização recomendada e ação de resposta, "
        "reunidos num arquivo YAML versionado junto com o código. A baseline foi medida sobre "
        f"{br(DET['chamadas_baseline'], 0)} chamadas de operação normal, sem problemas de cliente, e a conformidade foi avaliada "
        f"sobre {br(DET['chamadas_avaliacao'], 0)} chamadas de um cenário misto, que inclui um cliente legado sem "
        "headers, consultas a tags inexistentes e maior concorrência. Na avaliação, "
        f"{len(s['dentro'])} indicadores ficaram dentro dos limiares, {len(s['alerta'])} em alerta e "
        f"{len(s['critico'])} em nível crítico ({criticos}). A interface em Streamlit consome os três endpoints "
        "com a biblioteca requests e mostra os indicadores com os mesmos gráficos propostos neste documento. "
        "Os registros permitiram identificar o cliente que chamava sem contexto pelo user agent, separar erros "
        "de cliente de falhas da fonte de dados e medir atrasos do coletor que a interface sozinha não "
        "mostraria."
    )
    paragrafo(doc, texto, recuo=Cm(0))
    n = len(texto.split())
    assert 150 <= n <= 500, f"resumo com {n} palavras"
    paragrafo(doc)
    q = paragrafo(doc, "Palavras-chave:", negrito=True, recuo=Cm(0))
    q.add_run(" Observabilidade. Governança de IA. Qualidade de dados. FastAPI. Metric contract.")
    return n


SIGLAS = [
    ("ABNT", "Associação Brasileira de Normas Técnicas"),
    ("API", "Application Programming Interface"),
    ("CLP", "Controlador Lógico Programável"),
    ("HTTP", "Hypertext Transfer Protocol"),
    ("IA", "Inteligência Artificial"),
    ("IEC", "International Electrotechnical Commission"),
    ("ISO", "International Organization for Standardization"),
    ("JSON", "JavaScript Object Notation"),
    ("KPI", "Key Performance Indicator"),
    ("MES", "Manufacturing Execution System"),
    ("NBR", "Norma Brasileira"),
    ("NIST", "National Institute of Standards and Technology"),
    ("RM", "Registro de Matrícula"),
    ("RMF", "Risk Management Framework"),
    ("SLI", "Service Level Indicator"),
    ("SLO", "Service Level Objective"),
    ("SQL", "Structured Query Language"),
    ("SRE", "Site Reliability Engineering"),
    ("UTC", "Tempo Universal Coordenado"),
    ("UUID", "Universally Unique Identifier"),
    ("YAML", "YAML Ain't Markup Language"),
]


def lista_siglas(doc):
    paragrafo(doc, "LISTA DE ABREVIATURAS E SIGLAS", "Titulo sem numero")
    for sigla, significado in SIGLAS:
        q = paragrafo(doc, recuo=Cm(0))
        q.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        q.paragraph_format.tab_stops.add_tab_stop(Cm(2.5))
        q.add_run(f"{sigla}\t{significado}")


# ---------------------------------------------------------------- textuais

def introducao(doc):
    titulo(doc, "1 INTRODUÇÃO")
    p(doc, "O Forzy Digital Twin é a solução que o grupo vem desenvolvendo no Challenge da Forzy para acompanhar "
           "equipamentos industriais a partir de leituras de sensores. Uma das partes da solução é o provider de "
           "Sensores, que devolve a leitura mais recente de uma tag e o histórico de leituras num intervalo. Essas "
           "leituras alimentam a classificação de severidade mostrada ao operador e, mais adiante, os modelos de IA "
           "do gêmeo digital.")
    p(doc, "Até este checkpoint o provider não deixava rastro de uso. Não era possível responder quem consultou "
           "uma tag, a partir de qual tela, quanto tempo a resposta levou ou se o dado entregue já estava velho. "
           "Sem esse registro não há como auditar o comportamento do serviço nem perceber que um coletor parou "
           "antes que alguém tome decisão com base numa leitura antiga.")
    p(doc, "O objetivo do trabalho é definir um contrato mínimo de observabilidade para o endpoint de sensores e "
           "verificar, com os registros efetivamente coletados pelo back-end, se esse contrato está sendo cumprido. "
           "Para isso o grupo construiu a API em FastAPI, um middleware de registro, uma interface em Streamlit, um "
           "gerador de tráfego e um script de análise que compara os números medidos com os limiares definidos.")
    p(doc, "O escopo segue o enunciado do checkpoint e fica menor que o da Sprint 4. Só o provider de Sensores "
           "(leitura atual e histórico) foi exposto, sem autenticação e sem migrar os providers de Equipamentos e "
           "Plantas. O provider usado aqui é simulado, com falhas de coleta reproduzidas de propósito, como explica "
           "a seção 3.4. O tema também deve entrar no próximo entregável do Challenge da Forzy, como recomenda o "
           "enunciado.")
    p(doc, "O documento está organizado assim: a seção 2 traz os conceitos usados; a seção 3 descreve a "
           "arquitetura e o que é registrado; as seções 4 a 7 apresentam o metric contract, as baselines e "
           "limiares, a camada de visualização e o plano de resposta; a seção 8 mostra os resultados medidos; a "
           "seção 9 relata o uso de IA no trabalho e a seção 10 traz a conclusão do grupo.")


def fundamentacao(doc):
    titulo(doc, "2 FUNDAMENTAÇÃO TEÓRICA")
    titulo(doc, "2.1 Observabilidade", 2)
    p(doc, "A documentação do OpenTelemetry define observabilidade como a capacidade de entender um sistema "
           "pelo lado de fora, fazendo perguntas sobre ele sem conhecer seu funcionamento interno, e coloca os "
           "sinais emitidos pela aplicação (traces, métricas e logs) como matéria-prima dessas perguntas "
           "(OPENTELEMETRY, 2026). O registro por chamada deste trabalho é um log estruturado: cada linha tem "
           "campos fixos que podem ser filtrados e agregados depois.")
    p(doc, "No capítulo sobre monitoramento de sistemas distribuídos, Beyer et al. (2016) propõem quatro sinais "
           "para começar a monitorar qualquer serviço voltado ao usuário: latência, tráfego, erros e saturação. Os "
           "três primeiros aparecem diretamente no contrato (latência em percentis, volume por minuto e taxas de "
           "erro). Saturação ficou de fora porque a API roda num único processo local e não há recurso "
           "compartilhado relevante para medir neste escopo.")
    titulo(doc, "2.2 Indicadores e objetivos de nível de serviço", 2)
    p(doc, "Beyer et al. (2016) distinguem o indicador de nível de serviço (SLI), que é uma medida quantitativa de "
           "algum aspecto do serviço, do objetivo de nível de serviço (SLO), que é o valor ou faixa desejada para "
           "esse indicador. Os autores recomendam trabalhar com percentis em vez de média para latência, porque a "
           "média esconde a cauda lenta que o usuário de fato sente, e sugerem tratar a diferença entre 100% e a "
           "meta como uma margem de erro (error budget) que pode ser gasta. O contrato usa essa linguagem: cada "
           "indicador é um SLI, os limiares de alerta e crítico funcionam como dois níveis de SLO, e a meta de "
           "disponibilidade foi escolhida pensando na margem mensal que ela deixa.")
    titulo(doc, "2.3 Qualidade de dados: freshness e completude", 2)
    p(doc, "A ISO/IEC 25012 descreve um modelo de qualidade de dados com quinze características. Duas delas "
           "guiam os indicadores de dado deste trabalho. Completude é o grau em que os dados têm valores para todos "
           "os atributos esperados num contexto de uso. Atualidade (currentness) é o grau em que os dados têm a "
           "idade certa para aquele contexto (INTERNATIONAL ORGANIZATION FOR STANDARDIZATION, 2008). No "
           "vocabulário de engenharia de dados a atualidade costuma ser chamada de freshness, termo usado no "
           "restante do texto.")
    p(doc, "Para um gêmeo digital, uma leitura com dez minutos de atraso pode ter valor normal e esconder um "
           "equipamento já em falha. Por isso o contrato mede a idade de cada leitura entregue e não só se a API "
           "respondeu.")
    titulo(doc, "2.4 Governança de IA e rastreabilidade", 2)
    p(doc, "O NIST AI RMF 1.0 organiza a gestão de riscos de IA em quatro funções (Govern, Map, Measure e Manage) e "
           "lista características de sistemas confiáveis, entre elas ser responsabilizável e transparente "
           "(accountable and transparent). A função Measure trata de acompanhar o sistema com métricas definidas e "
           "documentadas, e a Manage trata da resposta quando um risco se concretiza (NATIONAL INSTITUTE OF "
           "STANDARDS AND TECHNOLOGY, 2023). O metric contract cobre as duas: define o que medir e diz o que "
           "fazer quando o limiar estoura.")
    p(doc, "A ISO/IEC 42001 especifica requisitos para um sistema de gestão de IA dentro da organização, com "
           "políticas, objetivos e processos para desenvolver ou usar sistemas de IA de forma responsável "
           "(INTERNATIONAL ORGANIZATION FOR STANDARDIZATION, 2023). Este checkpoint não pretende atender a norma, "
           "mas os registros de uso e o plano de resposta são o tipo de evidência que um processo desses pede.")
    p(doc, "Sculley et al. (2015) mostram que, em sistemas de aprendizado de máquina reais, o código do modelo é "
           "uma parte pequena do total e boa parte da dívida técnica está nas dependências de dados e nos "
           "consumidores não declarados de um serviço. O header X-Feature ataca exatamente esse segundo ponto: "
           "toda funcionalidade que consome a API passa a se identificar, e um consumidor sem identificação "
           "aparece no relatório como ausente.")


def arquitetura(doc, cont):
    titulo(doc, "3 ARQUITETURA E COLETA")
    titulo(doc, "3.1 Desenho da API", 2)
    p(doc, "A API foi escrita em FastAPI e tem duas famílias de rotas. As de sensores são GET /v1/sensores (lista "
           "de tags), GET /v1/sensores/{tag}/leitura-atual e GET /v1/sensores/{tag}/historico, que aceita os "
           "parâmetros inicio, fim e limite. As de observabilidade são GET /v1/observabilidade, com filtros por "
           "feature, session_id, desde e limite, e GET /v1/observabilidade/resumo, que devolve os indicadores já "
           "calculados e o status de cada um frente ao contrato. Os parâmetros são validados com Pydantic. Tag "
           "inexistente devolve 404 com mensagem indicando a rota que lista as tags válidas, e intervalo inválido "
           "devolve 422.")
    p(doc, "A leitura atual devolve valor, unidade, timestamp da leitura, severidade (normal, alerta, critico ou "
           "indeterminada, quando o valor veio nulo), os limiares do sensor, a idade do dado em segundos e um campo "
           "desatualizado, verdadeiro quando a idade passa de 300 s. Esse campo é a implementação na própria API "
           "de uma das ações do plano de resposta (seção 7). A Figura 1 resume o fluxo.")
    figura(doc, cont, FIG / "fig01_arquitetura.png", "Arquitetura da solução e fluxo do registro de observabilidade",
           15)
    p(doc, "O middleware, registrado com o decorador de middleware HTTP do FastAPI, envolve só as rotas que "
           "começam com /v1/sensores. Ele mede a latência com time.perf_counter, como sugere a própria "
           "documentação do framework (FASTAPI, 2026), e grava uma linha na tabela chamadas do SQLite depois que a "
           "resposta fica pronta. As rotas de observabilidade não são registradas para que a consulta aos "
           "registros não altere os indicadores do endpoint observado. Se a gravação falhar, o erro vai para o log "
           "e a requisição segue, porque a observabilidade não pode derrubar o serviço que observa.")
    titulo(doc, "3.2 Headers de contexto e chamadas sem header", 2)
    p(doc, "Todo cliente da API deve enviar dois headers. X-Session-Id identifica a sessão: a interface Streamlit "
           "gera um UUID por sessão do navegador e guarda no session_state (STREAMLIT, 2026), e o script de consumo "
           "gera um por execução. X-Feature identifica a funcionalidade de origem, com valores como "
           "tela-leitura-atual, tela-historico, tela-observabilidade e script-historico.")
    p(doc, "O grupo decidiu não rejeitar chamadas sem esses headers. A chamada é atendida e o campo que faltou é "
           "gravado como ausente, com headers_completos igual a falso. Se a API respondesse 400, o cliente "
           "problemático deixaria de aparecer nos registros e a cobertura de headers ficaria artificialmente em "
           "100%, justamente o indicador que precisa revelar o problema. Atendendo e registrando, dá para medir a "
           "cobertura e achar o cliente pelo user agent. O contrato prevê endurecer a regra (passar a recusar) se "
           "a cobertura ficar abaixo do limiar crítico por mais de uma sprint.")
    titulo(doc, "3.3 Campos registrados", 2)
    p(doc, "O Quadro 1 lista os campos gravados em cada chamada. Os campos de domínio (idade do dado, completude, "
           "intervalos) são calculados pela rota e passados ao middleware pelo request.state, então o middleware "
           "não precisa ler o corpo da resposta.")
    campos = [
        ("id", "Sequencial do registro"),
        ("timestamp_utc", "Instante da resposta, ISO 8601 em UTC"),
        ("session_id", "Valor de X-Session-Id ou ausente"),
        ("feature", "Valor de X-Feature ou ausente"),
        ("headers_completos", "Verdadeiro se os dois headers vieram"),
        ("metodo, rota, tag", "Método HTTP, template da rota e tag consultada"),
        ("status_code", "Código HTTP devolvido"),
        ("latencia_ms", "Tempo dentro da API, medido com time.perf_counter"),
        ("idade_dado_s", "Leitura atual: segundos entre a leitura do sensor e a resposta"),
        ("completude", "Proporção de campos não nulos no payload, de 0 a 1"),
        ("qtd_registros", "Histórico: quantidade de leituras devolvidas"),
        ("intervalo_medio_s, intervalo_max_s", "Histórico: intervalo médio e maior intervalo entre leituras"),
        ("severidade", "Leitura atual: severidade devolvida"),
        ("tamanho_resposta_bytes", "Tamanho do corpo da resposta"),
        ("erro", "Mensagem de erro quando o status é 4xx ou 5xx"),
        ("user_agent", "Header User-Agent do cliente"),
    ]
    grade(doc, cont, "Quadro", "Campos do registro de observabilidade", ["Campo", "Conteúdo"],
          [list(c) for c in campos], [5.5, 10])
    titulo(doc, "3.4 Provider simulado", 2)
    p(doc, "O provider de Sensores construído em aula não foi copiado para este repositório. Para que o "
           "checkpoint rode em qualquer máquina sem depender de outra fonte de dados, o grupo escreveu um provider "
           "simulado com a mesma interface (leitura atual e histórico por tag) e quatro tags: TT-101 "
           "(temperatura do mancal do motor M-01, em °C), PT-201 (pressão de descarga da bomba B-02, em bar), "
           "VT-301 (vibração do redutor R-03, em mm/s) e CT-501 (corrente do motor M-05, em A). A amostragem "
           "nominal é de 30 s e cada amostra leva de 3 a 20 s para ser publicada.")
    p(doc, "As leituras são determinísticas: a mesma tag no mesmo instante sempre gera o mesmo valor, o que deixa "
           "o histórico estável entre consultas. O simulador reproduz de propósito problemas comuns de coleta. Em "
           "2% dos instantes a amostra se perde. Em cada janela de 4 minutos há 10% de chance de o coletor parar "
           "por 1 a 7 minutos. Valor nulo aparece em 1% das amostras e qualidade nula em 3%. A consulta tem "
           "latência variável, com 2% de consultas lentas (250 a 600 ms a mais), e a fonte falha com 0,4% de "
           "probabilidade, o que gera 503. Sem essas falhas todos os indicadores de dado ficariam em 100% e o "
           "contrato não teria o que verificar.")


def metric_contract(doc, cont):
    titulo(doc, "4 METRIC CONTRACT")
    p(doc, "O metric contract fica no arquivo governanca/metric_contract.yaml, versionado junto com o código. "
           "Para cada indicador ele traz nome, definição, fórmula, campo de origem no registro, janela de medição, "
           "unidade, direção (se valor maior ou menor é pior), baseline, limiar de alerta, limiar crítico, "
           "justificativa, visualização recomendada, ação em cada nível e responsável. O mesmo arquivo é lido pela "
           "rota de resumo da API, pela interface e pelo script de análise, então mudar um limiar no YAML muda o "
           "status em todos os lugares.")
    com_limiar = sum(i.get('limiar_alerta') is not None for i in CONTRATO['indicadores'])
    p(doc, f"Foram mapeados {len(CONTRATO['indicadores'])} indicadores. Desses, {com_limiar} têm limiares; uso por "
           "funcionalidade e sessões únicas são indicadores de contexto, sem limiar, que ajudam a explicar "
           "variações nos outros. O Quadro 2 mostra a definição e a fórmula de cada um.")
    linhas = [[i["nome"], i["definicao"], i["formula"], i["fonte"].replace("chamadas.", ""), i["janela"]]
              for i in CONTRATO["indicadores"]]
    grade(doc, cont, "Quadro", "Indicadores do metric contract",
          ["Indicador", "Definição", "Fórmula", "Campo", "Janela"], linhas, [2.8, 4.2, 4.2, 2.4, 2.4])
    p(doc, "Alguns indicadores do enunciado precisaram de interpretação. Tempo de atualização foi entendido como "
           "o intervalo entre leituras consecutivas que o histórico devolve, e por isso só existe nas chamadas de "
           "histórico. Taxa de completude de freshness foi entendida como a fração de leituras atuais entregues "
           "dentro do prazo de 90 s, que complementa o p95 da idade: o p95 mostra o tamanho do atraso na cauda e a "
           "taxa mostra com que frequência o prazo é quebrado.")


def baselines(doc, cont):
    titulo(doc, "5 BASELINES E LIMIARES")
    titulo(doc, "5.1 Obtenção da baseline", 2)
    p(doc, "A baseline foi calculada sobre registros reais gravados pela API, gerados pelo script "
           "scripts/gerar_trafego.py no cenário baseline. Esse cenário simula a operação normal: seis sessões da "
           "interface, todas com os dois headers, só tags válidas e uma chamada por vez. A execução ocorreu em "
           f"{data_br(EXEC_B['inicio'])}, das {hora(EXEC_B['inicio'])} às {hora(EXEC_B['fim'])} (UTC), e produziu "
           f"{br(DET['chamadas_baseline'], 0)} registros. As falhas do provider simulado (perda de amostra, parada "
           "do coletor, campo nulo, 503 ocasional) continuaram ativas, porque fazem parte da operação normal de um "
           "coletor industrial. O que o cenário baseline não tem são os problemas de cliente.")
    p(doc, "Em seguida rodamos o cenário avaliacao, das "
           f"{hora(EXEC_A['inicio'])} às {hora(EXEC_A['fim'])}, com {br(DET['chamadas_avaliacao'], 0)} chamadas e "
           f"concorrência {EXEC_A['concorrencia']}. Nele entram, além das telas, uma integração com o MES que faz "
           "polling da leitura atual, um cliente legado sem headers, chamadas com só um header, consultas a tags "
           "inexistentes e parâmetros fora da faixa. A conformidade da seção 8 é medida sobre esse segundo "
           "período. O script governanca/analise.py separa as duas janelas pelo arquivo data/execucoes.json e, com "
           "a opção --gravar-baseline, escreve os valores medidos no próprio contrato.")
    p(doc, "Há uma limitação: são poucos minutos de tráfego sintético num computador pessoal. A "
           "baseline serve para mostrar o método e calibrar a ordem de grandeza dos limiares; em produção ela "
           "precisaria ser recalculada sobre semanas de uso real, separando turnos.")
    titulo(doc, "5.2 Limiares e justificativas", 2)
    p(doc, "Os limiares foram definidos antes de olhar os resultados da avaliação, a partir de três referências: "
           "a experiência do operador na interface (tempo de resposta percebido), a característica do sensor "
           "(amostragem de 30 s e atraso de publicação de até 20 s) e a prática de SLO descrita por Beyer et al. "
           "(2016). A Tabela 1 mostra a baseline medida ao lado dos dois níveis de limiar.")

    def lim(i, chave):
        valor = i.get(chave)
        if valor is None:
            return "-"
        if i.get("limiar_relativo_baseline"):
            return f"{br(valor * 100, 0)}% da baseline"
        return f"{'>' if i['direcao'] == 'maior_pior' else '<'} {br(valor, 1 if valor % 1 else 0)}"

    linhas = [[i["nome"], i["unidade"], br(i["baseline"], 2) if i["baseline"] is not None else "-",
               lim(i, "limiar_alerta"), lim(i, "limiar_critico")]
              for i in CONTRATO["indicadores"] if i.get("limiar_alerta") is not None]
    grade(doc, cont, "Tabela", "Baseline medida e limiares por indicador",
          ["Indicador", "Unidade", "Baseline", "Alerta", "Crítico"], linhas, [5.4, 2.4, 2.4, 3.0, 3.0])
    p(doc, "Latência. Na interface cada interação dispara até três chamadas. Com p95 de 250 ms por chamada a soma "
           "fica abaixo de 1 s, faixa em que a resposta ainda parece imediata; acima de 1 s por chamada a tela "
           f"trava de forma visível. A baseline de p95 ficou em {br(BASE['latencia_p95_ms'])} ms, bem abaixo do "
           "alerta, o que é esperado num ambiente local. O p99 tem janela de 15 minutos porque, com poucas chamadas, "
           "o p99 de 5 minutos oscila demais.")
    p(doc, "Erros e disponibilidade. A meta de 99,5% deixa cerca de 3,6 horas de margem por mês, aceitável para um "
           "painel de apoio à manutenção que não comanda equipamento. Abaixo de 99% o problema deixa de ser "
           "pontual. O 4xx foi separado do 5xx porque a causa e o responsável mudam: 4xx quase sempre é cliente "
           "montando a URL errada, e a interface só oferece tags válidas, então 3% já é anormal.")
    p(doc, "Freshness e tempo de atualização. Uma leitura saudável tem até cerca de 50 s de idade (30 s de "
           "amostragem mais 20 s de publicação). Passar de 90 s quer dizer que pelo menos duas amostras seguidas "
           "não chegaram, e acima de 5 minutos o dado já não serve para decidir nada sobre o equipamento. Para o "
           "intervalo entre leituras, a média 20% acima do nominal (36 s) indica perda frequente de amostras; com "
           "45 s, uma em cada três amostras se perdeu.")
    p(doc, "Completude e cobertura. A completude tolera 2% de campos faltando antes do alerta porque um campo nulo "
           "isolado, como a qualidade, não impede a leitura. A cobertura de headers tem meta de 95% e não de 100% "
           "para aceitar chamadas manuais de teste pelo /docs. Volume não tem valor certo, depende do turno, então "
           "o limiar é relativo à baseline: o que preocupa é a queda brusca, sinal de cliente parado. A proporção "
           "de leituras críticas é um indicador do equipamento e não da API; 5% e 10% são pontos de partida que a "
           "engenharia de manutenção deveria revisar.")


VISUAL = [
    ("latencia_p95", "Linha no tempo de p50, p95 e p99, com os limiares tracejados (Figura 2), e histograma "
                     "(Figura 3)", "A linha mostra quando a degradação começou; o histograma mostra se a cauda é "
                     "feita de poucos casos extremos ou de um deslocamento geral."),
    ("erro_4xx", "Barras horizontais empilhadas por rota e código de status (Figura 4)",
     "Empilhar deixa ver a proporção de cada código dentro da rota e separa 404 de 422 e de 503."),
    ("disponibilidade", "Card de KPI com a meta na interface e linha por janela de 1 minuto (Figura 5)",
     "O card responde se a meta está sendo cumprida; a linha mostra se as falhas se concentram num momento."),
    ("freshness_p95", "Pontos de cada leitura no tempo, com mediana e faixas de alerta e crítico pintadas "
                      "(Figura 6)", "Cada ponto é uma resposta real; as faixas deixam claro em que momento e "
                      "por quanto tempo o dado ficou velho."),
    ("freshness_no_prazo", "Linha da evolução da taxa por janela de 2 minutos (Figura 7)",
     "É a forma sugerida no enunciado para acompanhar a evolução da taxa de completude de freshness."),
    ("completude_payload", "Linha da média por janela (Figura 8) e gauge no resumo",
     "A completude muda devagar; a linha mostra tendência e a queda fica visível contra o limiar."),
    ("intervalo_atualizacao", "Histograma dos intervalos entre leituras, em escala logarítmica (Figura 9)",
     "A maior parte dos intervalos é de 30 s; a escala log deixa ver as lacunas raras de vários minutos."),
    ("cobertura_headers", "KPI com meta e barras de cobertura por feature (Figura 10)",
     "As barras apontam direto qual funcionalidade ou cliente chama sem contexto."),
    ("throughput", "Linha de chamadas por minuto (Figura 11)",
     "Volume é uma série temporal; o interesse está em quedas e picos."),
    ("uso_feature", "Barras horizontais ordenadas (Figura 12)",
     "Comparação de magnitude entre categorias com nomes longos fica mais legível na horizontal."),
    ("sessoes_unicas", "Card de KPI", "É um número único de contexto; um gráfico não acrescentaria nada."),
    ("proporcao_critica", "Linha da proporção por janela de 2 minutos (Figura 13)",
     "Mostra se as leituras críticas são pontuais ou se formam uma sequência, o que muda a ação."),
]


def visualizacao(doc, cont):
    titulo(doc, "6 CAMADA DE VISUALIZAÇÃO")
    p(doc, "A escolha do gráfico partiu da pergunta que cada indicador responde. Indicadores que mudam no tempo "
           "viraram linhas, distribuições viraram histogramas, comparações entre categorias viraram barras e "
           "números únicos viraram cards. Os limiares aparecem sempre como linhas tracejadas em amarelo (alerta) e "
           "vermelho (crítico), cores reservadas para isso e que não são usadas em séries. O Quadro 3 resume a "
           "escolha, e as figuras a seguir foram geradas pelo script de análise com os dados coletados. Nas "
           "séries temporais a linha pontilhada vertical marca o início do cenário de avaliação; o que vem antes "
           "é a baseline.")
    linhas = [[IND[i]["nome"], vis, porque] for i, vis, porque in VISUAL]
    grade(doc, cont, "Quadro", "Visualização escolhida por indicador", ["Indicador", "Visualização", "Motivo"],
          linhas, [3.4, 6.0, 6.1])
    p(doc, "Na interface Streamlit, a aba Observabilidade mostra seis cards (chamadas, latência p95, "
           "disponibilidade, cobertura de headers, freshness no prazo e sessões únicas), a tabela de conformidade "
           "devolvida pela API e os gráficos de latência, volume, status, cobertura, freshness e uso por feature, "
           "com opção de atualizar a cada 5 segundos. As figuras deste documento seguem o mesmo desenho.")
    figs = [
        ("fig02_latencia_percentis.png", "Latência p50, p95 e p99 por janela de 1 minuto"),
        ("fig03_histograma_latencia.png", "Distribuição da latência na janela de avaliação"),
        ("fig04_status_por_rota.png", "Chamadas por rota e código de status"),
        ("fig05_disponibilidade.png", "Disponibilidade por janela de 1 minuto"),
        ("fig06_freshness.png", "Idade da leitura atual no momento da resposta"),
        ("fig07_freshness_no_prazo.png", "Taxa de completude de freshness por janela de 2 minutos"),
        ("fig08_completude.png", "Completude do payload por janela de 1 minuto"),
        ("fig09_intervalo_atualizacao.png", "Distribuição dos intervalos entre leituras consecutivas"),
        ("fig10_cobertura_headers.png", "Cobertura de headers por funcionalidade"),
        ("fig11_throughput.png", "Volume de chamadas por minuto"),
        ("fig12_uso_por_feature.png", "Uso por funcionalidade"),
        ("fig13_proporcao_critica.png", "Proporção de leituras críticas por janela de 2 minutos"),
    ]
    for arquivo, legenda in figs:
        figura(doc, cont, FIG / arquivo, legenda)
    p(doc, "A Figura 9 é a única que não sai direto da tabela de registros. O registro guarda só o intervalo "
           "médio e o máximo de cada chamada de histórico; para desenhar a distribuição completa, o script "
           "consulta o provider na mesma janela que o histórico devolveu. Como o provider é determinístico, os "
           "intervalos reconstruídos são os mesmos que a API entregou.")


def plano_resposta(doc, cont):
    titulo(doc, "7 PLANO DE RESPOSTA A VIOLAÇÕES")
    p(doc, "Cada indicador com limiar tem uma ação para o nível de alerta e outra para o crítico, além de um "
           "responsável. A lógica geral é que o alerta pede investigação e o crítico pede uma medida que proteja "
           "quem usa o dado, mesmo antes da causa ser encontrada. O Quadro 4 traz o plano completo.")
    linhas = [[i["nome"], " ".join(i["acao_alerta"].split()), " ".join(i["acao_critico"].split()),
               i["responsavel"]] for i in CONTRATO["indicadores"] if i.get("limiar_alerta") is not None]
    grade(doc, cont, "Quadro", "Ações por indicador e nível de limiar",
          ["Indicador", "Alerta", "Crítico", "Responsável"], linhas, [3.0, 5.2, 5.2, 2.4])
    p(doc, "Duas ações já estão implementadas no código. A leitura atual traz o campo desatualizado quando a idade "
           "passa de 300 s, e a interface mostra o aviso de dado desatualizado e diz que a severidade não deve ser "
           "usada para decisão. A interface também avisa quando o campo de qualidade vem vazio. As demais ações "
           "dependem de processo (chamado, plantão, contato com o dono do cliente) e ficam como proposta para a "
           "Sprint 4, quando houver alertas automáticos.")
    p(doc, "No caso da completude, a ação crítica de bloquear a inferência do modelo com payload incompleto é a "
           "ligação mais direta com IA. Um modelo que recebe valor nulo ou leitura velha devolve uma previsão com "
           "aparência de confiável, e o registro de observabilidade é o que permite barrar essa entrada antes.")


def resultados(doc, cont):
    titulo(doc, "8 RESULTADOS")
    s = contagem_status()
    p(doc, f"A Tabela 2 compara os indicadores medidos na janela de avaliação ({br(DET['chamadas_avaliacao'], 0)} "
           "chamadas) com os limiares do contrato. Os valores foram calculados pelo script governanca/analise.py "
           "sobre a tabela chamadas e coincidem com os devolvidos pela rota /v1/observabilidade/resumo para a "
           "mesma janela.")

    def lim(c, chave):
        v = c[chave]
        return "-" if v is None else br(v, 1)

    linhas = []
    for c in R["conformidade"]:
        if c["status"] == "informativo":
            continue
        unidade = c["unidade"] if c["unidade"] == "%" else f" {c['unidade']}"
        linhas.append([c["indicador"], f"{br(c['valor'], 2)}{unidade}",
                       br(c["baseline"], 2) if c["baseline"] is not None else "-",
                       lim(c, "limiar_alerta"), lim(c, "limiar_critico"), STATUS_PT[c["status"]]])
    grade(doc, cont, "Tabela", "Conformidade dos indicadores na janela de avaliação",
          ["Indicador", "Medido", "Baseline", "Alerta", "Crítico", "Status"], linhas, [4.4, 2.8, 2.0, 1.8, 1.8, 2.2])
    p(doc, f"Dos {sum(len(v) for v in s.values())} indicadores com limiar, {len(s['dentro'])} ficaram dentro, "
           f"{len(s['alerta'])} em alerta e {len(s['critico'])} em nível crítico. "
           f"Também foram registradas {AVAL['sessoes_unicas']} sessões únicas.")
    for texto in analise_resultados():
        p(doc, texto)


def analise_resultados() -> list[str]:
    """Parágrafos da análise. Escritos depois de ver os números; os valores vêm do JSON."""
    atrasadas = DET["atrasadas_90s_por_tag"]
    ct = atrasadas.get("CT-501", {"leituras": 0, "idade_max_s": 0, "primeira": EXEC_A["inicio"]})
    outras = {t: v for t, v in atrasadas.items() if t != "CT-501"}
    outras_txt = "; ".join(f"a {t} teve mais {br(v['leituras'], 0)}, com no máximo {br(v['idade_max_s'], 0)} s"
                           for t, v in outras.items())
    sem_header = DET["sem_header_por_feature_e_user_agent"]
    legado = sem_header.get("ausente | python-requests/legado", 0)
    parcial = sem_header.get("tela-leitura-atual | forzy-streamlit/1.0", 0)
    e404 = DET["erros_404_por_tag"]
    lacuna_b = DET["maior_lacuna_por_tag_baseline"]
    tags_lacuna = [t for t, v in lacuna_b.items() if v > IND["maior_lacuna"]["limiar_critico"]]
    return [
        "O problema mais sério apareceu nos indicadores de dado. A partir das "
        f"{hora(ct['primeira'])} a tag CT-501 passou a responder com leituras cada vez mais velhas, até "
        f"{br(ct['idade_max_s'], 0)} s, sinal de que o coletor dessa tag parou (Figura 6). Foram "
        f"{br(ct['leituras'], 0)} leituras acima de 90 s só dessa tag"
        + (f"; {outras_txt}" if outras_txt else "") + ". Com isso a taxa de completude de freshness caiu para "
        f"{br(AVAL['taxa_freshness_no_prazo_pct'])}%, abaixo do limiar crítico de 90%, e a Figura 7 mostra a queda "
        f"janela a janela. O p95 da idade ficou em {br(AVAL['freshness_p95_s'])} s, em alerta e perto do crítico. "
        f"Ao todo, {br(DET['leituras_desatualizadas_300s'], 0)} respostas passaram de 300 s e saíram com o campo "
        "desatualizado marcado, que é a ação crítica do contrato funcionando na prática.",

        "A mesma parada não apareceu no indicador de maior lacuna do histórico. A lacuna só pode ser medida quando "
        "a leitura seguinte chega, e o coletor da CT-501 ainda estava parado no fim da avaliação, então o "
        "histórico simplesmente terminava mais cedo. Isso mostra que os dois indicadores se completam: freshness "
        "pega a parada em curso e a lacuna registra a parada depois que ela acaba. O valor de "
        f"{br(AVAL['intervalo_atualizacao_max_s'], 0)} s que deixou a maior lacuna em nível crítico veio de paradas "
        f"anteriores das tags {' e '.join(tags_lacuna)}, que já estavam na última hora de histórico durante a "
        "baseline. O tempo médio de atualização ficou em "
        f"{br(AVAL['intervalo_atualizacao_medio_s'])} s, dentro do limiar, porque poucas lacunas longas pesam pouco "
        "na média (Figura 9).",

        f"A taxa de erro 4xx chegou a {br(AVAL['taxa_erro_4xx_pct'])}%, nível crítico. Foram "
        f"{br(DET['erros_4xx_por_status'].get('404', 0), 0)} respostas 404 e "
        f"{br(DET['erros_4xx_por_status'].get('422', 0), 0)} respostas 422. Os 404 vieram das tags "
        + ", ".join(f"{t} ({n})" for t, n in e404.items())
        + ". A PT-2O1 tem a letra O no lugar do zero, erro típico de tag digitada à mão. Os 422 foram pedidos de "
        "histórico com limite fora da faixa de 1 a 5000. Como essas chamadas traziam o header de feature das "
        "telas, o campo feature sozinho não basta para achar a origem; seria preciso cruzar com session_id e "
        "user_agent, que é o que a ação de alerta do contrato pede.",

        f"A cobertura de headers ficou em {br(AVAL['cobertura_headers_pct'], 2)}%, em alerta e a poucos décimos do "
        f"crítico. A Figura 10 aponta a origem: {br(legado, 0)} chamadas do cliente com user agent "
        f"python-requests/legado não mandaram nenhum header, e {br(parcial, 0)} chamadas da própria interface "
        "mandaram só o X-Feature. Esse resultado sustenta a decisão de não recusar chamadas sem header: se a API "
        "tivesse respondido 400, essas chamadas não estariam no banco e não haveria como saber qual cliente "
        "corrigir.",

        f"A latência ficou dentro dos limiares. O p95 foi de {br(AVAL['latencia_p95_ms'])} ms contra "
        f"{br(BASE['latencia_p95_ms'])} ms na baseline. O p99, porém, subiu de {br(BASE['latencia_p99_ms'])} ms "
        f"para {br(AVAL['latencia_p99_ms'])} ms com a concorrência maior e as consultas lentas do historiador "
        f"({br(DET['chamadas_lentas_acima_250ms'], 0)} chamadas acima de 250 ms). Na Figura 2 o p99 passa do "
        "valor de alerta do p95 em alguns minutos enquanto o p95 quase não se move, o que justifica acompanhar os "
        "dois. Por rota, o p95 do histórico foi de "
        f"{br(DET['latencia_p95_por_rota'].get('/v1/sensores/{tag}/historico'))} ms e o da leitura atual de "
        f"{br(DET['latencia_p95_por_rota'].get('/v1/sensores/{tag}/leitura-atual'))} ms.",

        f"A disponibilidade na avaliação foi de {br(AVAL['disponibilidade_pct'], 2)}%, com "
        f"{br(DET['erros_5xx'], 0)} resposta 503 no período. Na baseline, com {br(DET['erros_5xx_baseline'], 0)} falhas em "
        f"{br(DET['chamadas_baseline'], 0)} chamadas, ela ficou em {br(BASE['disponibilidade_pct'], 2)}%, abaixo "
        "da própria meta. Com amostras pequenas cada falha pesa muito (uma falha em 300 chamadas tira 0,33 ponto "
        "percentual), e por isso o contrato mede disponibilidade em 30 dias para o SLO e só usa a janela curta "
        "para acompanhamento. A completude do payload ficou em "
        f"{br(AVAL['completude_media_pct'])}%, o volume em {br(AVAL['throughput_por_min'])} chamadas por minuto e "
        f"não houve leitura crítica no período ({br(AVAL['proporcao_critica_pct'])}%).",

        violacoes_baseline(),
    ]


def violacoes_baseline() -> str:
    """Indicadores que já estouravam o limiar na própria baseline."""
    nomes = []
    for c in R["conformidade"]:
        if c["status"] == "informativo" or c["baseline"] is None:
            continue
        status = classificar(c["baseline"], c["limiar_alerta"], c["limiar_critico"], c["direcao"])
        if status in ("alerta", "critico"):
            nomes.append(f"{c['indicador'].lower()} ({br(c['baseline'], 2)}, nível {STATUS_PT[status].lower()})")
    if not nomes:
        return "Nenhum indicador estava fora dos limiares na baseline."
    lista = ", ".join(nomes[:-1]) + (" e " if len(nomes) > 1 else "") + nomes[-1]
    return (f"A própria baseline já estava fora do limiar em {len(nomes)} indicadores: {lista}. Os limiares foram "
            "mantidos como estavam, porque ajustá-los para caber na baseline esconderia justamente o que eles "
            "devem mostrar. Fica como achado para a revisão do contrato: ou o coletor e a fonte precisam melhorar, "
            "ou a meta precisa ser rediscutida com quem usa o dado.")


def uso_ia(doc):
    titulo(doc, "9 USO DE INTELIGÊNCIA ARTIFICIAL")
    p(doc, "O grupo usou o Claude Code, assistente de programação da Anthropic, ao longo do trabalho. Ele ajudou "
           "na implementação da API FastAPI e do middleware de observabilidade, do provider simulado, da interface "
           "Streamlit, dos scripts de consumo, de geração de tráfego e de análise, e na estruturação deste "
           "documento, incluindo o script que gera o arquivo no formato ABNT e o rascunho das seções de "
           "desenvolvimento.")
    p(doc, "O grupo revisou o código, executou os testes automatizados e a análise, conferiu cada referência "
           "bibliográfica na fonte original e escreveu a conclusão sem uso de IA, como pede o critério de "
           "avaliação. As escolhas de escopo, os limiares e a interpretação dos resultados foram discutidas e "
           "validadas pelo grupo.")
    destaque_amarelo(doc, [
        "[COMPLETAR PELO GRUPO]",
        "Descrever com mais detalhe o que cada integrante fez, quais trechos gerados foram ajustados "
        "manualmente, o que foi descartado e como as referências foram conferidas.",
    ])


def conclusao(doc):
    titulo(doc, "10 CONCLUSÃO")
    destaque_amarelo(doc, [
        "[ESCREVER PELO GRUPO]",
        "Perguntas-guia (apagar este bloco depois de escrever):",
        "O que os números medidos mostraram que vocês não esperavam?",
        "Qual indicador vocês acham mais útil para a Forzy e por quê?",
        "A decisão de não recusar chamadas sem header se mostrou acertada? Mudariam algo?",
        "Algum limiar pareceu mal calibrado quando vocês viram os dados?",
        "O que foi difícil na implementação?",
        "O que faltou para este contrato funcionar em produção?",
        "O que fariam diferente na Sprint 4?",
    ])


REFERENCIAS = [
    "BEYER, Betsy; JONES, Chris; PETOFF, Jennifer; MURPHY, Niall Richard (ed.). Site reliability engineering: how "
    "Google runs production systems. Sebastopol: O'Reilly Media, 2016. Disponível em: "
    "https://sre.google/sre-book/table-of-contents/. Acesso em: 4 out. 2026.",
    "FASTAPI. Middleware. [S. l.]: FastAPI, 2026. Disponível em: https://fastapi.tiangolo.com/tutorial/middleware/. "
    "Acesso em: 4 out. 2026.",
    "INTERNATIONAL ORGANIZATION FOR STANDARDIZATION. ISO/IEC 25012: software engineering: software product quality "
    "requirements and evaluation (SQuaRE): data quality model. Geneva: ISO, 2008.",
    "INTERNATIONAL ORGANIZATION FOR STANDARDIZATION. ISO/IEC 42001: information technology: artificial "
    "intelligence: management system. Geneva: ISO, 2023.",
    "NATIONAL INSTITUTE OF STANDARDS AND TECHNOLOGY. Artificial intelligence risk management framework (AI RMF "
    "1.0). Gaithersburg: NIST, 2023. (NIST AI 100-1). DOI: https://doi.org/10.6028/NIST.AI.100-1.",
    "OPENTELEMETRY. Observability primer. [S. l.]: OpenTelemetry, 2026. Disponível em: "
    "https://opentelemetry.io/docs/concepts/observability-primer/. Acesso em: 4 out. 2026.",
    "SCULLEY, D. et al. Hidden technical debt in machine learning systems. In: ADVANCES IN NEURAL INFORMATION "
    "PROCESSING SYSTEMS 28 (NIPS 2015), 2015, Montreal. Proceedings [...]. [S. l.: s. n.], 2015. p. 2503-2511. "
    "Disponível em: https://papers.nips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html. "
    "Acesso em: 4 out. 2026.",
    "STREAMLIT. Add statefulness to apps. [S. l.]: Snowflake, 2026. Disponível em: "
    "https://docs.streamlit.io/develop/concepts/architecture/session-state. Acesso em: 4 out. 2026.",
]

# Trechos em negrito em cada referência (título da obra, conforme NBR 6023).
DESTAQUE_REF = [
    "Site reliability engineering", "Middleware", "ISO/IEC 25012", "ISO/IEC 42001",
    "Artificial intelligence risk management framework (AI RMF 1.0)", "Observability primer",
    "Proceedings", "Add statefulness to apps",
]


def referencias(doc):
    doc.add_heading("REFERÊNCIAS", level=1).paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    H.append((1, "REFERÊNCIAS"))
    for texto, destaque in sorted(zip(REFERENCIAS, DESTAQUE_REF)):
        q = doc.add_paragraph(style="Referencia")
        antes, _, depois = texto.partition(destaque)
        q.add_run(antes)
        q.add_run(destaque).bold = True
        q.add_run(depois)


# ---------------------------------------------------------------- montagem

def montar() -> dict:
    doc = novo_documento()
    cont = Contador()

    capa(doc)
    nova_secao(doc, inicio_numeracao=1)
    folha_rosto(doc)
    quebra_pagina(doc)
    palavras = resumo(doc)

    # As listas e o sumário dependem do conteúdo, então o corpo é montado num documento
    # auxiliar primeiro só para coletar títulos e legendas.
    aux, aux_cont = novo_documento(), Contador()
    H.clear()
    corpo(aux, aux_cont)
    titulos = list(H)

    for nome, tipo in (("LISTA DE ILUSTRAÇÕES", "Figura"), ("LISTA DE QUADROS", "Quadro"),
                       ("LISTA DE TABELAS", "Tabela")):
        quebra_pagina(doc)
        paragrafo(doc, nome, "Titulo sem numero")
        campo_indice(doc, f'TOC \\h \\z \\c "{tipo}"', aux_cont.entradas[tipo])
    quebra_pagina(doc)
    lista_siglas(doc)
    quebra_pagina(doc)
    paragrafo(doc, "SUMÁRIO", "Titulo sem numero")
    campo_indice(doc, 'TOC \\o "1-3" \\h \\z \\u', titulos)

    nova_secao(doc, mostrar_numero=True)
    H.clear()
    corpo(doc, cont, primeira_sem_quebra=True)
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    doc.save(SAIDA)
    return {"palavras_resumo": palavras, "figuras": cont.n["Figura"], "quadros": cont.n["Quadro"],
            "tabelas": cont.n["Tabela"]}


def corpo(doc, cont, primeira_sem_quebra=False):
    introducao(doc)
    if primeira_sem_quebra:
        # A seção nova já começa em página nova; evita página em branco antes da Introdução.
        primeiro = next(par for par in doc.paragraphs if par.style.name == "Heading 1"
                        and par.text.startswith("1 INTRODUÇÃO"))
        primeiro.paragraph_format.page_break_before = False
    fundamentacao(doc)
    arquitetura(doc, cont)
    metric_contract(doc, cont)
    baselines(doc, cont)
    visualizacao(doc, cont)
    plano_resposta(doc, cont)
    resultados(doc, cont)
    uso_ia(doc)
    conclusao(doc)
    referencias(doc)


if __name__ == "__main__":
    info = montar()
    print(f"Documento gerado em {SAIDA.relative_to(RAIZ)}")
    print(info)
