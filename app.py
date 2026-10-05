from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
import sqlite3, secrets, random, csv, io, math

app = FastAPI(
    title="DATA CRISIS 2026 — Operação Sinal Fraco",
    version="1.0.0",
    description="Hackathon simples e progressivo de Data Science em Nova Aurora."
)

DB = "equipes.db"

# ============================================================
# BANCO DE EQUIPES
# ============================================================
def db():
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS equipes(
            token TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            integrantes TEXT DEFAULT '',
            etapa INTEGER NOT NULL DEFAULT 1,
            resposta_d1 TEXT DEFAULT '',
            resposta_d2 TEXT DEFAULT '',
            resposta_d3 TEXT DEFAULT ''
        )
    """)
    con.commit()
    return con

def get_team(token):
    if not token:
        raise HTTPException(401, "Token da equipe não informado.")
    con = db()
    row = con.execute(
        "SELECT token,nome,integrantes,etapa,resposta_d1,resposta_d2,resposta_d3 FROM equipes WHERE token=?",
        (token,)
    ).fetchone()
    con.close()
    if not row:
        raise HTTPException(401, "Token da equipe inválido.")
    return {
        "token": row[0],
        "nome": row[1],
        "integrantes": row[2],
        "etapa": row[3],
        "respostas": {1: row[4], 2: row[5], 3: row[6]},
    }

def set_stage(token, etapa, resposta_coluna, resposta):
    con = db()
    con.execute(
        f"UPDATE equipes SET etapa=?, {resposta_coluna}=? WHERE token=?",
        (etapa, resposta, token)
    )
    con.commit()
    con.close()

# ============================================================
# DADOS SINTÉTICOS DA CIDADE
# ============================================================
SETORES = ["SAUDE", "ENERGIA", "AGUA", "TRANSITO", "TELECOM"]

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def gerar_registro(rng, i, prefixo, novo=False, operacao=False):
    setor = rng.choices(
        SETORES,
        weights=[18, 18, 14, 28, 22] if novo else [24, 25, 17, 19, 15],
        k=1
    )[0]

    idade = rng.randint(2, 144)
    carga = clamp(rng.gauss(68 if novo else 62, 15), 8, 100)
    base_temp = {"SAUDE": 36, "ENERGIA": 43, "AGUA": 34, "TRANSITO": 39, "TELECOM": 42}[setor]
    temperatura = rng.gauss(base_temp + 0.08*carga, 4.4)
    vibracao = max(0.0, rng.gauss(1.15 + 0.017*carga + (0.35 if setor=="ENERGIA" else 0), 0.43))
    consumo = max(5, 25 + 1.42*carga + 0.18*idade + rng.gauss(0, 13))
    latencia = max(2, rng.gammavariate(2.0, 24) + (18 if setor=="TELECOM" else 0))
    erros = max(0, int(rng.gauss(1.2 + carga/32, 1.5)))
    manut = max(0, int(rng.gauss(0.6, 0.8)))
    umidade = clamp(rng.gauss(62, 15), 15, 100)

    z = (
        -4.0
        + 0.024*(temperatura-38)
        + 0.38*(vibracao-1.8)
        + 0.022*(carga-60)
        + 0.14*erros
        + 0.004*(latencia-45)
        + 0.004*(idade-55)
        + (0.22 if setor=="ENERGIA" else 0)
        + (0.17 if setor=="TELECOM" else 0)
        - 0.12*manut
    )
    p = 1/(1+math.exp(-z))
    falha = 1 if rng.random() < p else 0

    row = {
        "unidade_id": f"{prefixo}{i:05d}",
        "setor": setor,
        "temperatura": round(temperatura, 2),
        "vibracao": round(vibracao, 3),
        "consumo_energia": round(consumo, 2),
        "latencia_rede": round(latencia, 2),
        "carga_sistema": round(carga, 2),
        "erros_24h": erros,
        "manutencoes_30d": manut,
        "idade_equipamento_meses": idade,
        "umidade": round(umidade, 2),
    }

    if not operacao:
        row["falha"] = falha
    return row

def gerar_dados():
    rng = random.Random(20261005)

    historico = [gerar_registro(rng, i, "H", novo=False) for i in range(1, 3001)]

    # valores ausentes
    for row in rng.sample(historico, 95):
        row["vibracao"] = ""
    for row in rng.sample(historico, 60):
        row["latencia_rede"] = ""
    for row in rng.sample(historico, 45):
        row["umidade"] = ""

    # duplicatas exatas
    historico.extend([dict(x) for x in rng.sample(historico, 55)])

    novos = [gerar_registro(rng, i, "N", novo=True) for i in range(1, 701)]

    # DESAFIO 3: parte dos controladores envia carga_sistema em 0–1
    afetados = rng.sample(range(len(novos)), int(len(novos)*0.18))
    for idx in afetados:
        novos[idx]["carga_sistema"] = round(float(novos[idx]["carga_sistema"]) / 100.0, 4)

    operacao = [gerar_registro(rng, i, "OP", novo=True, operacao=True) for i in range(1, 401)]

    return historico, novos, operacao

HISTORICO, NOVOS, OPERACAO = gerar_dados()

COLUNAS_HIST = [
    "unidade_id","setor","temperatura","vibracao","consumo_energia",
    "latencia_rede","carga_sistema","erros_24h","manutencoes_30d",
    "idade_equipamento_meses","umidade","falha"
]
COLUNAS_OPER = [c for c in COLUNAS_HIST if c != "falha"]

def csv_response(rows, cols, filename):
    s = io.StringIO()
    w = csv.DictWriter(s, fieldnames=cols)
    w.writeheader()
    for row in rows:
        w.writerow({c: row.get(c, "") for c in cols})
    return Response(
        s.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

# ============================================================
# MODELOS DA API
# ============================================================
class EquipeIn(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    integrantes: str = Field(default="", max_length=300)

class ConfirmacaoIn(BaseModel):
    concluido: bool

# ============================================================
# VISUAL
# ============================================================
CSS = r"""
:root{
  --bg:#07111d;--panel:#101d2b;--panel2:#14263a;--line:#2a4159;
  --txt:#f4f7fb;--muted:#a9bac9;--blue:#67baff;--green:#68dfad;
  --amber:#ffc86a;--red:#ff7e88;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--txt);font-family:Inter,Arial,sans-serif;line-height:1.55}
.wrap{width:min(1080px,92%);margin:auto}
.hero{padding:62px 0 44px;background:radial-gradient(circle at 70% 20%,#174365 0,transparent 35%),linear-gradient(135deg,#0b1c30,#07111d);border-bottom:1px solid var(--line)}
.kicker{font-size:.76rem;letter-spacing:.17em;text-transform:uppercase;color:#9bd4ff;font-weight:800}
h1{font-size:clamp(2.8rem,7vw,5.6rem);line-height:.95;margin:.18em 0}
h2{font-size:1.7rem;margin-bottom:.3rem}
p{color:#d6e1eb}
.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}
.card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:20px}
.section{padding:34px 0}
.pillrow{display:flex;flex-wrap:wrap;gap:8px}.pill{padding:7px 10px;border:1px solid #35526d;background:#10243a;border-radius:999px;font-size:.82rem}
.problem{font-size:1.35rem;font-weight:800;padding:22px;border-left:4px solid var(--blue);background:#0b1927;border-radius:0 14px 14px 0}
.data-table{display:grid;gap:8px}.data-line{display:flex;justify-content:space-between;gap:12px;padding:12px 14px;background:#091725;border:1px solid #20394f;border-radius:10px}
.button{border:0;border-radius:10px;padding:12px 16px;font-weight:800;background:var(--blue);color:#06101b;cursor:pointer;text-decoration:none;display:inline-block}
.button.secondary{background:transparent;border:1px solid #3a5975;color:#e7f4ff}
input,textarea{width:100%;padding:12px;border-radius:9px;border:1px solid #38536c;background:#071420;color:#fff;margin:5px 0 12px}
textarea{min-height:92px;resize:vertical}
label{font-size:.86rem;color:#bfd0de;font-weight:700}
.team-box{background:#0b1928;border:1px solid #2a4660;border-radius:16px;padding:22px}
.progress{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:18px 0}
.step{padding:14px;border-radius:12px;border:1px solid #2a4056;background:#0b1723;color:#6f8294}
.step.done{border-color:#2e6a51;background:#10251e;color:#c6f6dc}.step.current{border-color:#67baff;background:#102840;color:#e5f5ff}
.challenge{margin-top:22px;border:1px solid #31526f;background:linear-gradient(180deg,#122a42,#0d1c2a);border-radius:18px;overflow:hidden;animation:show .45s ease}
.challenge-head{padding:20px 22px;border-bottom:1px solid #2a4359}.challenge-body{padding:22px}
.alert{display:inline-block;padding:6px 9px;border-radius:999px;background:#372a14;border:1px solid #70562b;color:#ffdc91;font-size:.78rem;font-weight:800}
.feedback{display:none;margin-top:12px;padding:12px;border-radius:10px}.feedback.show{display:block}.feedback.ok{background:#10281e;border:1px solid #2d694a;color:#c7f4d7}.feedback.bad{background:#2b171b;border:1px solid #6b3741;color:#ffd0d6}
.final{border:1px solid #2c6a4e;background:#0e251c}
@keyframes show{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
footer{border-top:1px solid var(--line);padding:28px 0;margin-top:40px;color:#879bad;font-size:.85rem}
@media(max-width:650px){.progress{grid-template-columns:1fr}}
"""

PAGE = r"""
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DATA CRISIS 2026 — Operação Sinal Fraco</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<header class="hero">
  <div class="wrap">
    <div class="kicker">Hackathon de Data Science</div>
    <h1>DATA CRISIS 2026</h1>
    <h2 style="margin-top:0;color:#8fceff">Operação Sinal Fraco</h2>
    <p style="max-width:780px">
      Sua equipe foi chamada para atuar como consultoria de dados da cidade de Nova Aurora.
      Vocês receberão dados operacionais e novos comunicados ao longo do processo.
    </p>
  </div>
</header>

<main class="wrap">

  <section class="section">
    <div class="kicker">01 • O CLIENTE</div>
    <h2>Prefeitura de Nova Aurora</h2>

    <div class="card" style="padding:26px">
      <p style="font-size:1.1rem;margin-top:0">
        Nova Aurora é uma cidade fictícia do estado do Rio de Janeiro, com aproximadamente 318 mil habitantes.
        A cidade utiliza uma rede de sensores para acompanhar serviços de saúde, energia, abastecimento de água,
        trânsito e telecomunicações.
      </p>

      <p style="font-size:1.1rem">
        Nas últimas semanas, equipamentos de diferentes setores começaram a apresentar falhas inesperadas.
        Em alguns casos, os sensores mostraram alterações antes da falha. Em outros, valores aparentemente
        anormais foram registrados sem que qualquer problema real acontecesse.
      </p>

      <p style="font-size:1.1rem;margin-bottom:0">
        A administração municipal possui registros históricos dessas unidades, mas ainda não sabe até que ponto
        esses dados permitem antecipar uma falha nem quais informações são realmente confiáveis.
      </p>
    </div>
  </section>

  <section class="section">
    <div class="kicker">02 • O PEDIDO</div>
    <h2>O que a cidade quer de vocês</h2>

    <div class="problem" style="font-size:1.5rem">
      Identifiquem quais unidades apresentam maior risco de falha crítica nas próximas horas
      e indiquem as 20 unidades que devem receber intervenção prioritária.
    </div>

    <div class="card" style="margin-top:16px">
      <h3 style="margin-top:0">A cidade espera receber</h3>
      <p>
        Uma solução baseada nos dados disponíveis, acompanhada de uma justificativa clara para as decisões tomadas.
        A equipe deve ser capaz de explicar por que confia no resultado apresentado e por que essas unidades foram priorizadas.
      </p>

    </div>
  </section>

  <section class="section">
    <div class="kicker">03 • DADOS INICIAIS</div>
    <h2>Material entregue pela cidade</h2>
    <div class="data-table">
      <div class="data-line">
        <div><strong>dados_historicos.csv</strong><br><span class="muted">Registros históricos das unidades monitoradas.</span></div>
      </div>
      <div class="data-line">
        <div><strong>operacao_real.csv</strong><br><span class="muted">Unidades que deverão ser avaliadas ao final. A variável de falha não está disponível.</span></div>
      </div>
    </div>
    <p class="muted">Durante o hackathon, a Central poderá enviar novas informações que alterem o cenário.</p>
  </section>

  <section class="section" id="cadastro">
    <div class="kicker">04 • EQUIPE</div>
    <h2>Cadastre sua equipe</h2>
    <div class="team-box" id="register-box">
      <label>Nome da equipe</label>
      <input id="team-name" placeholder="Ex.: Equipe Ada">
      <label>Integrantes</label>
      <input id="team-members" placeholder="Nomes dos integrantes">
      <button class="button" onclick="registerTeam()">Cadastrar e iniciar</button>
      <div class="feedback" id="register-feedback"></div>
    </div>
    <div id="team-info" style="display:none"></div>
  </section>

  <section class="section" id="operation" style="display:none">
    <div class="kicker">05 • OPERAÇÃO EM ANDAMENTO</div>
    <h2 id="team-title">Equipe</h2>

    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px">
      <button class="button secondary" onclick="downloadData('/dados/historicos.csv')">Baixar dados históricos</button>
      <button class="button secondary" onclick="downloadData('/dados/operacao-real.csv')">Baixar operação real</button>
    </div>

    <div class="progress">
      <div class="step" id="step1"><strong>Desafio 1</strong><br>Nova remessa</div>
      <div class="step" id="step2"><strong>Desafio 2</strong><br>Dado comprometido</div>
      <div class="step" id="step3"><strong>Desafio 3</strong><br>Controladores substituídos</div>
    </div>

    <div id="challenge-area"></div>
  </section>
</main>

<footer><div class="wrap">Nova Aurora é uma cidade fictícia criada para fins educacionais.</div></footer>

<script>
const token=()=>localStorage.getItem('dc_token');

function feedback(id, ok, text){
  const el=document.getElementById(id);
  el.className='feedback show '+(ok?'ok':'bad');
  el.textContent=text;
}

async function registerTeam(){
  const nome=document.getElementById('team-name').value.trim();
  const integrantes=document.getElementById('team-members').value.trim();
  if(nome.length<2){feedback('register-feedback',false,'Informe o nome da equipe.');return}

  const r=await fetch('/api/equipes',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({nome,integrantes})
  });

  const d=await r.json();
  if(!r.ok){feedback('register-feedback',false,d.detail||'Não foi possível cadastrar.');return}

  localStorage.setItem('dc_token',d.token);
  await load();
}

async function load(){
  if(!token()) return;

  const r=await fetch('/api/status',{headers:{'X-Team-Token':token()}});
  if(!r.ok){localStorage.removeItem('dc_token');return}
  const d=await r.json();

  document.getElementById('register-box').style.display='none';
  document.getElementById('team-info').style.display='block';
  document.getElementById('team-info').innerHTML=
    '<div class="team-box"><strong>Equipe:</strong> '+d.nome+
    '<br><span class="muted">'+(d.integrantes||'')+'</span></div>';

  document.getElementById('operation').style.display='block';
  document.getElementById('team-title').textContent='Equipe '+d.nome;

  for(let i=1;i<=3;i++){
    const e=document.getElementById('step'+i);
    e.className='step';
    if(i<d.etapa) e.classList.add('done');
    else if(i===d.etapa && d.etapa<=3) e.classList.add('current');
  }

  renderChallenge(d.etapa);
}

function confirmationBox(n){
  return `
    <div style="margin-top:24px;padding:16px;border:1px solid #35516a;border-radius:12px;background:#091725">
      <label style="display:flex;align-items:center;gap:10px;font-size:1rem">
        <input type="checkbox" id="done${n}" style="width:auto;margin:0">
        <span>Concluído</span>
      </label>
      <button class="button" style="margin-top:14px" onclick="finish(${n})">Confirmar conclusão</button>
      <div class="feedback" id="fb${n}"></div>
    </div>`;
}

function renderChallenge(stage){
  const area=document.getElementById('challenge-area');

  if(stage===1){
    area.innerHTML=`
      <section class="challenge">
        <div class="challenge-head">
          <span class="alert">COMUNICADO 01</span>
          <h2>Desafio 1 — Nova remessa de dados</h2>
        </div>
        <div class="challenge-body">
          <p>
            A Central informa que uma nova remessa de dados operacionais foi recebida.
            Os novos registros deverão ser analisados e considerados na continuidade da investigação e da modelagem.
          </p>
          <button class="button secondary" onclick="downloadData('/dados/novos.csv')">Baixar novos_dados.csv</button>
          ${confirmationBox(1)}
        </div>
      </section>`;
  }
  else if(stage===2){
    area.innerHTML=`
      <section class="challenge">
        <div class="challenge-head">
          <span class="alert">COMUNICADO 02</span>
          <h2>Desafio 2 — Informação de coleta</h2>
        </div>
        <div class="challenge-body">
          <p>
            Após verificação técnica, foi confirmado um problema no processo de coleta da variável
            <strong>temperatura</strong>. Os valores registrados nessa coluna não podem mais ser considerados confiáveis.
            A partir deste comunicado, a variável temperatura deverá ser desconsiderada nas análises e nos modelos.
          </p>
          ${confirmationBox(2)}
        </div>
      </section>`;
  }
  else if(stage===3){
    area.innerHTML=`
      <section class="challenge">
        <div class="challenge-head">
          <span class="alert">COMUNICADO 03</span>
          <h2>Desafio 3 — Controladores substituídos</h2>
        </div>
        <div class="challenge-body">
          <p>
            A equipe de campo confirmou que uma parte dos controladores das unidades presentes na nova remessa
            foi substituída recentemente.
          </p>
          <p>
            Há indícios de que pelo menos uma grandeza numérica passou a ser transmitida em uma escala diferente
            do padrão histórico. Não existe uma lista confiável das unidades afetadas, e a Central ainda não
            identificou qual campo sofreu a alteração.
          </p>
          ${confirmationBox(3)}
        </div>
      </section>`;
  }
  else{
    document.getElementById('step1').classList.add('done');
    document.getElementById('step2').classList.add('done');
    document.getElementById('step3').classList.add('done');

    area.innerHTML=`
      <section class="challenge final">
        <div class="challenge-head">
          <span class="alert" style="background:#123727;border-color:#2d6a4a;color:#bff3d3">COMUNICADOS ENCERRADOS</span>
          <h2>Etapa final da operação</h2>
        </div>
        <div class="challenge-body">
          <p>
            Os três comunicados foram recebidos e incorporados pela equipe.
            A Prefeitura de Nova Aurora aguarda agora a solução final.
          </p>
          <div class="problem">
            Quais são as 20 unidades que devem receber intervenção primeiro — e por quê?
          </div>
        </div>
      </section>`;
  }

  area.scrollIntoView({behavior:'smooth',block:'start'});
}

async function finish(n){
  const check=document.getElementById('done'+n);
  if(!check.checked){
    feedback('fb'+n,false,'Marque a caixa “Concluído” para continuar.');
    return;
  }

  const r=await fetch('/api/desafio/'+n,{
    method:'POST',
    headers:{'Content-Type':'application/json','X-Team-Token':token()},
    body:JSON.stringify({concluido:true})
  });

  const d=await r.json();

  if(!r.ok){
    feedback('fb'+n,false,d.detail||'Não foi possível concluir o desafio.');
    return;
  }

  feedback('fb'+n,true,'Concluído. Novo comunicado liberado.');
  setTimeout(load,700);
}

async function downloadData(url){
  const r=await fetch(url,{headers:{'X-Team-Token':token()}});
  if(!r.ok){alert('Cadastre uma equipe antes de baixar os dados.');return}

  const b=await r.blob();
  const a=document.createElement('a');
  a.href=URL.createObjectURL(b);
  a.download=url.split('/').pop();
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(()=>URL.revokeObjectURL(a.href),500);
}

load();
</script>
</body>
</html>
"""

# ============================================================
# ROTAS
# ============================================================
@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(PAGE)

@app.get("/style.css")
def style():
    return Response(CSS, media_type="text/css")

@app.post("/api/equipes")
def criar_equipe(payload: EquipeIn):
    token = secrets.token_hex(8)
    con = db()
    con.execute(
        "INSERT INTO equipes(token,nome,integrantes,etapa) VALUES(?,?,?,1)",
        (token, payload.nome, payload.integrantes)
    )
    con.commit()
    con.close()
    return {"token": token, "nome": payload.nome, "etapa": 1}

@app.get("/api/status")
def status(x_team_token: str | None = Header(default=None)):
    t = get_team(x_team_token)
    return {
        "nome": t["nome"],
        "integrantes": t["integrantes"],
        "etapa": t["etapa"]
    }

@app.get("/dados/historicos.csv")
def dados_historicos(x_team_token: str | None = Header(default=None)):
    get_team(x_team_token)
    return csv_response(HISTORICO, COLUNAS_HIST, "dados_historicos.csv")

@app.get("/dados/novos.csv")
def dados_novos(x_team_token: str | None = Header(default=None)):
    t = get_team(x_team_token)
    if t["etapa"] < 1:
        raise HTTPException(403, "Arquivo ainda não liberado.")
    return csv_response(NOVOS, COLUNAS_HIST, "novos_dados.csv")

@app.get("/dados/operacao-real.csv")
def operacao_real(x_team_token: str | None = Header(default=None)):
    get_team(x_team_token)
    return csv_response(OPERACAO, COLUNAS_OPER, "operacao_real.csv")

@app.post("/api/desafio/1")
def desafio1(payload: ConfirmacaoIn, x_team_token: str | None = Header(default=None)):
    t = get_team(x_team_token)
    if t["etapa"] != 1:
        raise HTTPException(409, "Este desafio não está disponível.")
    if not payload.concluido:
        raise HTTPException(400, "Confirme a conclusão do desafio.")
    set_stage(t["token"], 2, "resposta_d1", "Concluído")
    return {"ok": True, "proxima_etapa": 2}

@app.post("/api/desafio/2")
def desafio2(payload: ConfirmacaoIn, x_team_token: str | None = Header(default=None)):
    t = get_team(x_team_token)
    if t["etapa"] != 2:
        raise HTTPException(409, "Este desafio não está disponível.")
    if not payload.concluido:
        raise HTTPException(400, "Confirme a conclusão do desafio.")
    set_stage(t["token"], 3, "resposta_d2", "Concluído")
    return {"ok": True, "proxima_etapa": 3}

@app.post("/api/desafio/3")
def desafio3(payload: ConfirmacaoIn, x_team_token: str | None = Header(default=None)):
    t = get_team(x_team_token)
    if t["etapa"] != 3:
        raise HTTPException(409, "Este desafio não está disponível.")
    if not payload.concluido:
        raise HTTPException(400, "Confirme a conclusão do desafio.")
    set_stage(t["token"], 4, "resposta_d3", "Concluído")
    return {"ok": True, "proxima_etapa": 4}
