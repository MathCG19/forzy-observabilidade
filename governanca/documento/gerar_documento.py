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
SETTINGS_REPLAY = "variável FORZY_REPLAY_INICIO"

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
        "Forzy Digital Twin, que acompanha os sensores S1 e S2 de um motor WEG W22. O grupo expôs o provider de "
        "Sensores como uma API FastAPI com rotas de leitura atual, "
        "histórico e observabilidade, e implementou um middleware que grava em SQLite, a cada chamada, os headers "
        "de contexto X-Session-Id e X-Feature, o instante em UTC, a latência, o código de status, a idade do dado "
        "e a completude do payload. A partir desses campos mapeamos "
        f"{len(CONTRATO['indicadores'])} indicadores, entre eles latência p95, disponibilidade, freshness, taxa de "
        "completude de freshness, tempo de atualização e cobertura de headers. Cada indicador recebeu definição, "
        "fórmula, baseline, limiar de alerta, limiar crítico, visualização recomendada e ação de resposta, "
        "reunidos num arquivo YAML versionado junto com o código e alinhados ao Metric Contract da Sprint 3. As "
        "leituras servidas pela API vêm do histórico real dos dois sensores, repetido sobre o relógio atual, e só a "
        "coleta é simulada. A baseline foi medida sobre "
        f"{br(DET['chamadas_baseline'], 0)} chamadas de operação normal, sem problemas de cliente, e a conformidade foi avaliada "
        f"sobre {br(DET['chamadas_avaliacao'], 0)} chamadas de um cenário misto, que inclui um cliente legado sem "
        "headers, consultas a sensores inexistentes e maior concorrência. Na avaliação, "
        f"{len(s['dentro'])} indicadores ficaram dentro dos limiares, {len(s['alerta'])} em alerta e "
        f"{len(s['critico'])} em nível crítico ({criticos}). A interface em Streamlit consome os três endpoints "
        "com a biblioteca requests e mostra os indicadores com os mesmos gráficos propostos neste documento. "
        "Os registros permitiram identificar pelo user agent o cliente que chamava sem contexto, separar erros "
        "de cliente de falhas de coleta e mostrar que, com os limiares da Sprint 3, o motor em operação cai quase "
        "sempre na zona crítica de vibração, ponto que pede revisão do contrato."
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
    ("HTTP", "Hypertext Transfer Protocol"),
    ("IA", "Inteligência Artificial"),
    ("IEC", "International Electrotechnical Commission"),
    ("ISO", "International Organization for Standardization"),
    ("JSON", "JavaScript Object Notation"),
    ("KPI", "Key Performance Indicator"),
    ("MES", "Manufacturing Execution System"),
    ("NBR", "Norma Brasileira"),
    ("NIST", "National Institute of Standards and Technology"),
    ("RBAC", "Role-Based Access Control"),
    ("RM", "Registro de Matrícula"),
    ("RMS", "Root Mean Square"),
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
           "motores industriais a partir de leituras de sensores. O ativo de referência é um motor WEG W22 de 2,2 kW "
           "com dois sensores, S1 e S2, que medem velocidade de vibração, aceleração e temperatura. No forzy-api, um "
           "poller consulta os dois sensores a cada 10 s e grava as leituras no banco; o provider de Sensores devolve "
           "a leitura mais recente e o histórico de cada um. Essas leituras alimentam a classificação de severidade "
           "mostrada ao operador e os modelos de IA do gêmeo digital (Isolation Forest e LSTM Autoencoder).")
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
           "Plantas. Os valores servidos são o histórico real dos sensores e só a coleta é simulada, como explica "
           "a seção 3.4. Os limiares de condição do motor e as regras de qualidade de dado foram herdados do Metric "
           "Contract da Sprint 3 (GOMES et al., 2026), e este checkpoint acrescenta a camada que faltava: medir a "
           "própria API e o dado que ela entrega. O tema também deve entrar no próximo entregável do Challenge, "
           "como recomenda o enunciado. O código completo (back-end, front-end, scripts, análise e o gerador deste "
           "documento) está em https://github.com/MathCG19/forzy-observabilidade.")
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
    p(doc, "A severidade de cada leitura segue a ISO 10816-1, que divide a velocidade de vibração RMS em zonas de "
           "A a D conforme a classe da máquina (INTERNATIONAL ORGANIZATION FOR STANDARDIZATION, 1995). O motor de "
           "2,2 kW é Classe I, e o Metric Contract da Sprint 3 adotou 1,8 mm/s (início da zona C) como atenção e "
           "4,5 mm/s (zona D) como crítico, além de 70 °C e 90 °C para temperatura e 2 g e 4 g para aceleração "
           "(GOMES et al., 2026). Cabe uma ressalva: a ISO 10816-1 foi substituída pela ISO 20816-1 em 2016, e uma "
           "revisão futura do contrato deveria conferir os limiares na norma vigente.")
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
    p(doc, "A leitura atual devolve, para S1 ou S2, a velocidade de vibração (mm/s), a aceleração (g), a "
           "temperatura (°C), o timestamp da leitura, a severidade de cada grandeza e a geral (a pior das três), se "
           "o motor está ligado (vibração a partir de 0,3 mm/s), a idade do dado em segundos e um campo offline, "
           "verdadeiro quando a idade passa de 30 s. Esse campo implementa na API o circuit breaker da Sprint 3, que "
           "proíbe decidir pelo último valor quando o sensor está offline. A Figura 1 resume o fluxo.")
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
           "tela-leitura-atual, tela-historico, tela-observabilidade e script-historico. O forzy-api já gravava um "
           "session_id fixo (poller) na tabela de leituras brutas; aqui o identificador passa a vir de quem consulta.")
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
    titulo(doc, "3.4 Origem dos dados: histórico real e coleta simulada", 2)
    hr = DET["historico_real"]
    p(doc, "Os sensores da Forzy hoje devolvem dado zerado, defeito confirmado pelo fabricante, e nos dias em que "
           "funcionaram mandaram cerca de 10 minutos de dados no total (GOMES et al., 2026). Por isso o provider "
           "deste checkpoint usa o mesmo recurso do modo demonstração do forzy-api: o histórico real exportado do "
           f"mestre IO-Link em 19/05/2026, com {br(hr['linhas'], 0)} linhas e {br(hr['duracao_h'], 2)} horas de "
           "velocidade, aceleração e temperatura das portas 1 (S1) e 2 (S2). O arquivo foi copiado sem alteração "
           "para o repositório.")
    p(doc, "O registrador do IO-Link grava uma linha quando o valor muda, então com o motor parado aparecem "
           "intervalos de até 228 s sem linha, que não são falha de coleta. Para não confundir as duas coisas, o "
           "provider imita o pipeline real: a cada 10 s um poller lê o último valor de cada sensor, como faz o "
           "forzy_poller.py, e grava a leitura. O histórico é repetido em laço sobre o relógio atual, a partir de um "
           f"ponto configurável (padrão 13:38, ajustável pela {SETTINGS_REPLAY}), e valores fora da faixa física válida da "
           "Sprint 3 são anulados.")
    p(doc, "O que é simulado é a coleta e o custo da consulta. Em cada janela de 4 minutos há 10% de chance de o "
           "endpoint dos sensores ficar fora do ar por 1 a 7 minutos, derrubando S1 e S2 juntos, e 2% dos polls se "
           "perdem individualmente. A consulta ao banco tem latência variável, com 2% de consultas lentas (250 a "
           "600 ms a mais), e falha com 0,4% de probabilidade, o que gera 503. Com isso os indicadores de dado têm "
           "o que medir, e os valores do motor, que alimentam a severidade, continuam sendo os medidos de fato.")


def metric_contract(doc, cont):
    titulo(doc, "4 METRIC CONTRACT")
    p(doc, "O Metric Contract da Sprint 3 normatizou a interpretação dos sensores: limiares de vibração, "
           "temperatura e aceleração, faixas físicas válidas e o circuit breaker para dado offline ou lacuna. O "
           "contrato deste checkpoint parte dele e cobre o que ficou de fora: o comportamento da API e a qualidade "
           "do dado no momento em que é entregue a quem consulta. "
           "Ele fica no arquivo governanca/metric_contract.yaml, versionado junto com o código. "
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
           "dentro do prazo de 30 s, o critério de sensor online da Sprint 3, que complementa o p95 da idade: o p95 "
           "mostra o tamanho do atraso na cauda e a taxa mostra com que frequência o sensor estava offline. A "
           "cobertura mínima de cinco leituras válidas em 5 minutos, também da Sprint 3, aparece aqui pelo tempo de "
           "atualização e pela maior lacuna, e a faixa física válida aparece pela completude.")


def baselines(doc, cont):
    titulo(doc, "5 BASELINES E LIMIARES")
    titulo(doc, "5.1 Obtenção da baseline", 2)
    p(doc, "A baseline foi calculada sobre registros reais gravados pela API, gerados pelo script "
           "scripts/gerar_trafego.py no cenário baseline. Esse cenário simula o uso normal: seis sessões da "
           "interface, todas com os dois headers, só os sensores S1 e S2 e uma chamada por vez. A API foi iniciada "
           "logo antes, com o replay no trecho das 13:38 do histórico, então a baseline coincidiu com o motor parado "
           "e a avaliação pegou a partida das 13:44 e a operação plena que vem depois. A execução ocorreu em "
           f"{data_br(EXEC_B['inicio'])}, das {hora(EXEC_B['inicio'])} às {hora(EXEC_B['fim'])} (UTC), e produziu "
           f"{br(DET['chamadas_baseline'], 0)} registros. As falhas do provider simulado (perda de amostra, parada "
           "do endpoint, 503 ocasional) continuaram ativas, porque fazem parte da operação normal da coleta. O que o "
           "cenário baseline não tem são os problemas de cliente.")
    p(doc, "Em seguida rodamos o cenário avaliacao, das "
           f"{hora(EXEC_A['inicio'])} às {hora(EXEC_A['fim'])}, com {br(DET['chamadas_avaliacao'], 0)} chamadas e "
           f"concorrência {EXEC_A['concorrencia']}. Nele entram, além das telas, uma integração com o MES que faz "
           "polling da leitura atual, um cliente legado sem headers, chamadas com só um header, consultas a sensores "
           "inexistentes e parâmetros fora da faixa. A conformidade da seção 8 é medida sobre esse segundo "
           "período. O script governanca/analise.py separa as duas janelas pelo arquivo data/execucoes.json e, com "
           "a opção --gravar-baseline, escreve os valores medidos no próprio contrato.")
    p(doc, "Há uma limitação: são poucos minutos de tráfego sintético num computador pessoal. A "
           "baseline serve para mostrar o método e calibrar a ordem de grandeza dos limiares; em produção ela "
           "precisaria ser recalculada sobre semanas de uso real, separando turnos.")
    titulo(doc, "5.2 Limiares e justificativas", 2)
    p(doc, "Os limiares foram definidos antes de olhar os resultados da avaliação, a partir de três referências: "
           "a experiência do operador na interface (tempo de resposta percebido), as regras de qualidade de dado "
           "do Metric Contract da Sprint 3 (poll de 10 s, offline acima de 30 s, janela de diagnóstico de 5 minutos) "
           "e a prática de SLO descrita por Beyer et al. (2016). A Tabela 1 mostra a baseline medida ao lado dos dois níveis de limiar.")

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
    p(doc, "Freshness e tempo de atualização. Com poll a cada 10 s, uma leitura saudável tem até cerca de 11 s "
           "de idade. O alerta em 30 s é o critério de sensor offline da Sprint 3, e o crítico em 300 s corresponde "
           "a uma janela de diagnóstico de 5 minutos inteira sem dado novo. Para o intervalo entre leituras, a média "
           "20% acima do nominal (12 s) indica perda frequente de polls; com 15 s, uma em cada três leituras se "
           "perdeu. A maior lacuna usa os mesmos 30 s e 300 s.")
    p(doc, "Completude e cobertura. A completude tolera 2% de campos faltando antes do alerta porque um campo nulo "
           "isolado, como a qualidade, não impede a leitura. A cobertura de headers tem meta de 95% e não de 100% "
           "para aceitar chamadas manuais de teste pelo /docs. Volume não tem valor certo, depende do turno, então "
           "o limiar é relativo à baseline: o que preocupa é a queda brusca, sinal de cliente parado. A proporção "
           "de leituras críticas é um indicador do equipamento e não da API. Ela usa a severidade calculada com os "
           "limiares da Sprint 3, e 5% e 10% são pontos de partida que o Técnico N2 e o Gestor N3 deveriam revisar.")


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
    p(doc, "Três ações já estão implementadas no código. A leitura atual traz o campo offline quando a idade "
           "passa de 30 s, e a interface avisa que, pelo circuit breaker, a severidade não deve ser usada para "
           "decisão. Com o motor abaixo de 0,3 mm/s a interface informa que o diagnóstico não se aplica, como manda "
           "a Sprint 3. Valores fora da faixa física válida são anulados antes de chegar ao cliente. As demais ações "
           "dependem de processo (chamado, plantão, contato com o dono do cliente) e ficam como proposta para a "
           "Sprint 4, quando houver alertas automáticos. Os papéis Técnico N2 e Gestor N3 são os do RBAC definido "
           "na Sprint 1.")
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
    sev_b = DET["severidade_leitura_atual_baseline"]
    sev_a = DET["severidade_leitura_atual_avaliacao"]
    hr = DET["historico_real"]
    sem_header = DET["sem_header_por_feature_e_user_agent"]
    legado = sem_header.get("ausente | python-requests/legado", 0)
    parcial = sem_header.get("tela-leitura-atual | forzy-streamlit/1.0", 0)
    e404 = DET["erros_404_por_tag"]
    lacunas = DET["maior_lacuna_por_tag_avaliacao"]
    return [
        "O resultado mais importante não veio da API, e sim do motor. Na baseline, com o motor parado, as "
        f"{br(sum(sev_b.values()), 0)} leituras atuais saíram todas normais. Na avaliação o replay chegou à partida "
        f"das 13:44 e à operação plena, e {br(sev_a.get('critico', 0), 0)} das {br(sum(sev_a.values()), 0)} "
        f"leituras saíram críticas, uma proporção de {br(AVAL['proporcao_critica_pct'])}%, muito acima do limiar "
        "de 10% (Figura 13). A causa é só a vibração: no histórico inteiro a temperatura não passou de "
        f"{br(max(hr['S1']['temperatura_max_c'], hr['S2']['temperatura_max_c']), 0)} °C e a aceleração não passou "
        f"de {br(max(hr['S1']['aceleracao_max_g'], hr['S2']['aceleracao_max_g']), 2)} g, longe dos limiares, enquanto "
        f"o platô de operação fica em {br(hr['S1']['mediana_plato_mm_s'], 2)} mm/s no S1 e "
        f"{br(hr['S2']['mediana_plato_mm_s'], 2)} mm/s no S2, dentro da zona D da Classe I (acima de 4,5 mm/s).",

        "Contando as linhas do histórico de 19/05 com o motor ligado, "
        f"{br(hr['S1']['zona_d_entre_ligado_pct'])}% (S1) e {br(hr['S2']['zona_d_entre_ligado_pct'])}% (S2) estão "
        "na zona D. Esses percentuais são por linha do registrador, que grava mais linhas com o motor em "
        "movimento, então servem como ordem de grandeza e não como tempo exato. O documento da Sprint 3 cita "
        "cerca de 0,57 mm/s como leitura em operação normal, valor bem abaixo do platô e que, nesse histórico, "
        "só aparece fora dele. Ou o motor está de fato numa condição de vibração inaceitável, ou os "
        "limiares da Classe I não se aplicam a esta montagem (motor em bancada, posição do sensor), ou o valor "
        "de referência da Sprint 3 veio de outro período. O contrato não decide isso sozinho; é exatamente o "
        "cenário de assinatura conhecida do ativo que a Sprint 3 deixou para decisão humana, e a alteração de "
        "limiar exige o Gestor N3.",

        "Nos indicadores de dado, a avaliação não pegou nenhuma queda do endpoint: o p95 da idade ficou em "
        f"{br(AVAL['freshness_p95_s'])} s, todas as leituras chegaram dentro dos 30 s e o tempo médio de "
        f"atualização foi de {br(AVAL['intervalo_atualizacao_medio_s'])} s, perto dos 10 s nominais. Mesmo assim a "
        f"maior lacuna ficou em {br(AVAL['intervalo_atualizacao_max_s'], 0)} s, em alerta, nos dois sensores ao "
        f"mesmo tempo ({', '.join(f'{t}: {br(v, 0)} s' for t, v in lacunas.items())}). Foi uma queda do endpoint "
        "anterior ao teste, que ainda estava na última hora devolvida pelo histórico; como derrubou S1 e S2 "
        "juntos, aponta para a conectividade e não para um sensor. Freshness mede só o agora, e a lacuna é o "
        "indicador que guarda a memória da última hora, então os dois se completam (Figuras 6 e 9).",

        f"A taxa de erro 4xx chegou a {br(AVAL['taxa_erro_4xx_pct'])}%, nível crítico. Foram "
        f"{br(DET['erros_4xx_por_status'].get('404', 0), 0)} respostas 404 e "
        f"{br(DET['erros_4xx_por_status'].get('422', 0), 0)} respostas 422. Os 404 vieram dos identificadores "
        + ", ".join(f"{t} ({n})" for t, n in e404.items())
        + ". O SI tem a letra I no lugar do número 1, erro típico de identificador digitado à mão, e o MOTOR-2 "
        "mistura o nome do componente com a tag do sensor. Os 422 foram pedidos de histórico com limite fora da "
        "faixa de 1 a 5000. Como essas chamadas traziam o header de feature das telas, o campo feature sozinho "
        "não basta para achar a origem; é preciso cruzar com session_id e user_agent, que é o que a ação de "
        "alerta do contrato pede.",

        f"A cobertura de headers ficou em {br(AVAL['cobertura_headers_pct'], 2)}%, em alerta e a poucos décimos do "
        f"crítico. A Figura 10 aponta a origem: {br(legado, 0)} chamadas do cliente com user agent "
        f"python-requests/legado não mandaram nenhum header, e {br(parcial, 0)} chamadas da própria interface "
        "mandaram só o X-Feature. Esse resultado sustenta a decisão de não recusar chamadas sem header: se a API "
        "tivesse respondido 400, essas chamadas não estariam no banco e não haveria como saber qual cliente "
        "corrigir.",

        f"A latência ficou dentro dos limiares. O p95 foi de {br(AVAL['latencia_p95_ms'])} ms contra "
        f"{br(BASE['latencia_p95_ms'])} ms na baseline. O p99, porém, subiu de {br(BASE['latencia_p99_ms'])} ms "
        f"para {br(AVAL['latencia_p99_ms'])} ms com a concorrência maior e as consultas lentas "
        f"({br(DET['chamadas_lentas_acima_250ms'], 0)} chamadas acima de 250 ms). Na Figura 2 o p99 passa do "
        "valor de alerta do p95 em alguns minutos enquanto o p95 quase não se move, o que justifica acompanhar os "
        "dois. Por rota, o p95 do histórico foi de "
        f"{br(DET['latencia_p95_por_rota'].get('/v1/sensores/{tag}/historico'))} ms e o da leitura atual de "
        f"{br(DET['latencia_p95_por_rota'].get('/v1/sensores/{tag}/leitura-atual'))} ms.",

        f"A disponibilidade foi de {br(AVAL['disponibilidade_pct'], 2)}% nas duas janelas, sem nenhuma resposta "
        "5xx, e a completude do payload ficou em "
        f"{br(AVAL['completude_media_pct'])}%. Este último número merece cuidado: o histórico real não tem nenhum "
        "valor fora da faixa física válida, então a completude não teve como cair aqui. Ela passa a ser útil "
        "quando o hardware voltar a mandar dado ao vivo, e o defeito de dado zerado já relatado pela Forzy é o "
        "tipo de falha que esse indicador, combinado com a faixa válida, deveria pegar. O volume ficou em "
        f"{br(AVAL['throughput_por_min'])} chamadas por minuto, acima da baseline, porque o cenário de avaliação "
        "tem mais clientes.",

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
    qtd = "1 indicador" if len(nomes) == 1 else f"{len(nomes)} indicadores"
    return (f"A própria baseline já estava fora do limiar em {qtd}: {lista}. Os limiares foram "
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
    "GOMES, Matheus Cardoso et al. Forzy: gêmeo digital com IA: governança em IA e business analytics: Challenge "
    "Sprint 3. São Paulo: FIAP, 2026. Documento interno do grupo.",
    "INTERNATIONAL ORGANIZATION FOR STANDARDIZATION. ISO 10816-1: mechanical vibration: evaluation of machine "
    "vibration by measurements on non-rotating parts: part 1: general guidelines. Geneva: ISO, 1995.",
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
    "Site reliability engineering", "Middleware", "Forzy", "ISO 10816-1", "ISO/IEC 25012", "ISO/IEC 42001",
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
