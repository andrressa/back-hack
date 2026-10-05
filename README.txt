DATA CRISIS 2026 — BACKEND COM CONTROLE DA PROFESSORA

ARQUIVOS:
- app.py
- requirements.txt
- render.yaml

RENDER
Build Command:
pip install -r requirements.txt

Start Command:
uvicorn app:app --host 0.0.0.0 --port $PORT

ENVIRONMENT VARIABLE RECOMENDADA:
ADMIN_KEY = escolha-uma-senha

Se ADMIN_KEY não for definida, a chave padrão será:
professora2026

ROTAS:
/
Portal dos alunos

/professora
Painel da professora

FUNCIONAMENTO:
- Equipes se cadastram.
- Dados históricos e operação real ficam disponíveis desde o início.
- Nenhum desafio aparece inicialmente.
- Professora entra em /professora.
- Libera Desafio 1, depois 2, depois 3.
- Portais dos alunos verificam automaticamente a cada 8 segundos.
- Cada equipe pode marcar cada desafio como concluído.
- O painel da professora mostra quantas equipes concluíram cada um.

SOLUÇÃO PEDIDA AO ALUNO:
- comparar pelo menos 3 métodos supervisionados;
- escolher e justificar o modelo final;
- classificar/estimar risco das unidades da operação;
- indicar as 20 unidades prioritárias.

DESAFIOS:
1. Nova remessa de dados.
2. Sensores de temperatura identificados como funcionando de forma incorreta.
3. Dados de latencia_rede medidos incorretamente, com erro sistemático aproximado de 20%.

Os comunicados aparecem apenas quando a professora libera 1, 2 e 3 no painel /professora.
Nenhum comunicado diz aos alunos qual procedimento, método ou correção aplicar.
