# Roteiro do vídeo (3 a 5 minutos)

Tópicos para falar com as próprias palavras. Os tempos são aproximados.

Antes de gravar: apagar `data/observabilidade.db` se quiser começar do zero, deixar dois terminais abertos na raiz do projeto e o navegador fechado.

## 1. Abertura (20 s)

- Nomes e RM.
- Uma frase sobre o que é: provider de Sensores do Forzy exposto em FastAPI, com registro de observabilidade por chamada.

## 2. Subir a API (30 s)

- Terminal 1: `uvicorn app.main:app --app-dir backend --port 8000`.
- Abrir `http://127.0.0.1:8000/docs`.
- Mostrar as rotas de sensores e de observabilidade.
- Executar a leitura atual do S1 pelo próprio /docs (sem headers, de propósito).
- Executar com um sensor que não existe (S9) e mostrar o 404.

## 3. Script de consumo (30 s)

- Terminal 2: `python scripts/consumo_requests.py`.
- Apontar o session_id gerado, a latência de cada chamada e os registros da sessão no final.

## 4. Streamlit (1 min 30 s)

- `streamlit run frontend/app.py`.
- Barra lateral: session_id da sessão.
- Aba Leitura atual: trocar entre S1 e S2, mostrar vibração, aceleração e temperatura com a cor da severidade, a idade do dado e o aviso de motor desligado ou de sensor offline.
- Aba Histórico: trocar a grandeza, mostrar o gráfico com as linhas de limiar da Sprint 3 e a tabela.
- Comentar que os valores são o histórico real de 19/05 e que só a coleta é simulada.
- Aba Observabilidade: cards, tabela de conformidade, filtrar pelo session_id da barra lateral e mostrar que as chamadas que acabamos de fazer estão lá com `tela-leitura-atual` e `tela-historico`.

## 5. Gerador de tráfego com a aba atualizando (50 s)

- Ligar o "Atualizar a cada 5 s" na aba Observabilidade.
- Terminal 2: `python scripts/gerar_trafego.py --cenario avaliacao --chamadas 200 --duracao 90`.
- Mostrar o volume subindo, a cobertura de headers caindo por causa do cliente legado e os 404 aparecendo no gráfico de status.
- Se o motor entrar em operação no replay, mostrar a proporção de leituras críticas subindo (platô de 6,6 mm/s cai na zona D).
- Comentar por que chamada sem header não é recusada.

## 6. Registro no banco (30 s)

- Mostrar um registro cru: `python -c "import sqlite3; c=sqlite3.connect('data/observabilidade.db'); print(c.execute('select * from chamadas order by id desc limit 1').fetchone())"`.
- Ou abrir o banco no DB Browser for SQLite, se tiver instalado.
- Apontar os campos timestamp_utc, session_id, feature, latencia_ms e idade_dado_s.

## 7. Fechamento (20 s)

- Onde ficam o metric contract, a análise e o documento.
- Rodar `pytest` rapidamente, se der tempo.
