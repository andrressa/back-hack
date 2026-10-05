from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
import sqlite3, secrets, random, csv, io, math, os

app = FastAPI(
    title="DATA CRISIS 2026 — Operação Sinal Fraco",
    version="3.0.0",
    description="Hackathon de Data Science — Nova Aurora"
)

DB = "data_crisis.db"
ADMIN_KEY = os.getenv("ADMIN_KEY", "professora2026")

# ============================================================
# BANCO
# ============================================================
def db():
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS equipes(
            token TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            integrantes TEXT DEFAULT '',
            desafio1_concluido INTEGER NOT NULL DEFAULT 0,
            desafio2_concluido INTEGER NOT NULL DEFAULT 0,
            desafio3_concluido INTEGER NOT NULL DEFAULT 0
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS configuracao(
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    """)
    con.execute(
        "INSERT OR IGNORE INTO configuracao(chave,valor) VALUES('desafio_liberado','0')"
    )
    con.commit()
    return con

def get_config_int(chave, default=0):
    con = db()
    row = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    con.close()
    return int(row[0]) if row else default

def set_config(chave, valor):
    con = db()
    con.execute(
        "INSERT INTO configuracao(chave,valor) VALUES(?,?) "
        "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
        (chave, str(valor))
    )
    con.commit()
    con.close()

def get_team(token):
    if not token:
        raise HTTPException(401, "Token da equipe não informado.")
    con = db()
    row = con.execute("""
        SELECT token,nome,integrantes,
               desafio1_concluido,desafio2_concluido,desafio3_concluido
        FROM equipes WHERE token=?
    """, (token,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(401, "Token da equipe inválido.")
    return {
        "token": row[0],
        "nome": row[1],
        "integrantes": row[2],
        "concluidos": [bool(row[3]), bool(row[4]), bool(row[5])]
    }

def admin_ok(key):
    if key != ADMIN_KEY:
        raise HTTPException(401, "Chave da professora inválida.")

# ============================================================
# DADOS
# ============================================================
SETORES = ["SAUDE", "ENERGIA", "AGUA", "TRANSITO", "TELECOM"]

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def registro(rng, i, prefixo, novo=False, operacao=False):
    setor = rng.choices(
        SETORES,
        weights=[18,18,14,28,22] if novo else [24,25,17,19,15],
        k=1
    )[0]
    idade = rng.randint(2, 144)
    carga = clamp(rng.gauss(67 if novo else 62, 15), 8, 100)
    base_temp = {"SAUDE":36,"ENERGIA":43,"AGUA":34,"TRANSITO":39,"TELECOM":42}[setor]
    temperatura = rng.gauss(base_temp + 0.08*carga, 4.4)
    vibracao = max(0.0, rng.gauss(1.15 + 0.017*carga + (0.35 if setor=="ENERGIA" else 0), 0.43))
    consumo = max(5, 25 + 1.42*carga + 0.18*idade + rng.gauss(0,13))
    latencia_real = max(2, rng.gammavariate(2.0,24) + (18 if setor=="TELECOM" else 0))
    erros = max(0, int(rng.gauss(1.2 + carga/32, 1.5)))
    manut = max(0, int(rng.gauss(0.6,0.8)))
    umidade = clamp(rng.gauss(62,15),15,100)

    z = (
        -4.0
        + 0.024*(temperatura-38)
        + 0.38*(vibracao-1.8)
        + 0.022*(carga-60)
        + 0.14*erros
        + 0.004*(latencia_real-45)
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
        "temperatura": round(temperatura,2),
        "vibracao": round(vibracao,3),
        "consumo_energia": round(consumo,2),
        "latencia_rede": round(latencia_real,2),
        "carga_sistema": round(carga,2),
        "erros_24h": erros,
        "manutencoes_30d": manut,
        "idade_equipamento_meses": idade,
        "umidade": round(umidade,2),
    }
    if not operacao:
        row["falha"] = falha
    return row

def gerar_dados():
    rng = random.Random(20261005)

    hist = [registro(rng,i,"H",False,False) for i in range(1,3001)]
    # Imperfeições normais da base.
    for row in rng.sample(hist, 95):
        row["vibracao"] = ""
    for row in rng.sample(hist, 60):
        row["latencia_rede"] = ""
    for row in rng.sample(hist, 45):
        row["umidade"] = ""
    hist.extend([dict(x) for x in rng.sample(hist,55)])

    novos = [registro(rng,i,"N",True,False) for i in range(1,701)]

    # Desafio 2: parte dos sensores de temperatura funcionou incorretamente.
    # A anomalia existe nos dados, mas o portal não informa quais unidades.
    afetados_temp = rng.sample(range(len(novos)), int(len(novos)*0.22))
    for idx in afetados_temp:
        if novos[idx]["temperatura"] != "":
            novos[idx]["temperatura"] = round(float(novos[idx]["temperatura"]) + rng.choice([-1,1])*rng.uniform(9,18),2)

    # Desafio 3: latência recente contém erro sistemático aproximado de 20%.
    # O comunicado NÃO informa a direção do erro.
    for row in novos:
        if row["latencia_rede"] != "":
            row["latencia_rede"] = round(float(row["latencia_rede"]) * 1.20, 2)

    operacao = [registro(rng,i,"OP",True,True) for i in range(1,401)]
    return hist, novos, operacao

HISTORICO, NOVOS, OPERACAO = gerar_dados()

COL_HIST = [
    "unidade_id","setor","temperatura","vibracao","consumo_energia",
    "latencia_rede","carga_sistema","erros_24h","manutencoes_30d",
    "idade_equipamento_meses","umidade","falha"
]
COL_OPER = [c for c in COL_HIST if c != "falha"]

def csv_response(rows, cols, filename):
    s = io.StringIO()
    w = csv.DictWriter(s, fieldnames=cols)
    w.writeheader()
    for row in rows:
        w.writerow({c:row.get(c,"") for c in cols})
    return Response(
        s.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":f'attachment; filename="{filename}"'}
    )

# ============================================================
# MODELOS
# ============================================================
class EquipeIn(BaseModel):
    nome: str = Field(min_length=2,max_length=80)
    integrantes: str = Field(default="",max_length=300)

class ConclusaoIn(BaseModel):
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
.wrap{width:min(1100px,92%);margin:auto}
.hero{padding:62px 0 46px;background:radial-gradient(circle at 72% 16%,#174365 0,transparent 35%),linear-gradient(135deg,#0b1c30,#07111d);border-bottom:1px solid var(--line)}
.kicker{font-size:.76rem;letter-spacing:.17em;text-transform:uppercase;color:#9bd4ff;font-weight:800}
h1{font-size:clamp(2.8rem,7vw,5.4rem);line-height:.96;margin:.18em 0}
h2{font-size:1.75rem;margin-bottom:.35rem}
h3{margin-bottom:.35rem}
p{color:#d6e1eb}
.muted{color:var(--muted)}
.section{padding:34px 0}
.card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:22px}
.client-ask{font-size:1.35rem;font-weight:800;padding:24px;border-left:5px solid var(--blue);background:#0b1927;border-radius:0 14px 14px 0}
.deliverables{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-top:16px}
.deliverable{padding:16px;background:#0a1826;border:1px solid #264058;border-radius:12px}
.pillrow{display:flex;flex-wrap:wrap;gap:8px}.pill{padding:7px 10px;border:1px solid #35526d;background:#10243a;border-radius:999px;font-size:.82rem}
.data-table{display:grid;gap:8px}.data-line{padding:13px 15px;background:#091725;border:1px solid #20394f;border-radius:10px}
.button{border:0;border-radius:10px;padding:12px 16px;font-weight:800;background:var(--blue);color:#06101b;cursor:pointer;text-decoration:none;display:inline-block}
.button.secondary{background:transparent;border:1px solid #3a5975;color:#e7f4ff}
input{width:100%;padding:12px;border-radius:9px;border:1px solid #38536c;background:#071420;color:#fff;margin:5px 0 12px}
label{font-size:.86rem;color:#bfd0de;font-weight:700}
.team-box{background:#0b1928;border:1px solid #2a4660;border-radius:16px;padding:22px}
.progress{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:18px 0}
.step{padding:14px;border-radius:12px;border:1px solid #2a4056;background:#0b1723;color:#6f8294}
.step.done{border-color:#2e6a51;background:#10251e;color:#c6f6dc}.step.current{border-color:#67baff;background:#102840;color:#e5f5ff}.step.wait{opacity:.45}
.challenge{margin-top:22px;border:1px solid #31526f;background:linear-gradient(180deg,#122a42,#0d1c2a);border-radius:18px;overflow:hidden;animation:show .45s ease}
.challenge-head{padding:20px 22px;border-bottom:1px solid #2a4359}.challenge-body{padding:22px}
.alert{display:inline-block;padding:6px 9px;border-radius:999px;background:#372a14;border:1px solid #70562b;color:#ffdc91;font-size:.78rem;font-weight:800}
.waiting{padding:28px;border:1px dashed #35516c;border-radius:14px;text-align:center;background:#091522;color:#9fb2c3;margin-top:20px}
.feedback{display:none;margin-top:12px;padding:12px;border-radius:10px}.feedback.show{display:block}.feedback.ok{background:#10281e;border:1px solid #2d694a;color:#c7f4d7}.feedback.bad{background:#2b171b;border:1px solid #6b3741;color:#ffd0d6}
.admin-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.admin-card{padding:18px;border:1px solid #2f4961;background:#0b1927;border-radius:13px}
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
<title>DATA CRISIS 2026</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<header class="hero">
 <div class="wrap">
  <div class="kicker">Hackathon de Data Science</div>
  <h1>DATA CRISIS 2026</h1>
  <h2 style="margin-top:0;color:#8fceff">Operação Sinal Fraco</h2>
  <p style="max-width:790px">
   Sua equipe foi contratada pela Prefeitura de Nova Aurora para desenvolver uma solução de apoio à decisão
   capaz de identificar unidades com maior risco de falha crítica.
  </p>
 </div>
</header>

<main class="wrap">

<section class="section">
 <div class="kicker">01 • O CLIENTE</div>
 <h2>Prefeitura de Nova Aurora</h2>
 <div class="card">
  <p style="font-size:1.08rem;margin-top:0">
   Nova Aurora é uma cidade fictícia do estado do Rio de Janeiro, com aproximadamente 318 mil habitantes.
   Saúde, energia, abastecimento de água, trânsito e telecomunicações são acompanhados por uma rede de sensores.
  </p>
  <p style="font-size:1.08rem">
   Nas últimas semanas, diferentes unidades começaram a apresentar falhas inesperadas. Em alguns casos,
   alterações nos sensores ocorreram antes da falha. Em outros, comportamentos incomuns não resultaram em problema real.
  </p>
  <p style="font-size:1.08rem;margin-bottom:0">
   A Prefeitura possui dados históricos e quer transformar esses registros em uma ferramenta objetiva de priorização operacional.
  </p>
 </div>
</section>

<section class="section">
 <div class="kicker">02 • O PROBLEMA DO CLIENTE</div>
 <h2>A solução solicitada</h2>

 <div class="client-ask">
  Desenvolvam uma solução de Data Science que estime o risco de falha das unidades monitoradas
  e permita à Prefeitura decidir quais unidades devem receber atenção primeiro.
 </div>

 <div class="deliverables">
  <div class="deliverable"><strong>1. Comparação de modelos</strong><br><span class="muted">Avaliar pelo menos <b>3 métodos supervisionados</b>.</span></div>
  <div class="deliverable"><strong>2. Escolha da solução final</strong><br><span class="muted">Selecionar e justificar o modelo que será utilizado na operação.</span></div>
  <div class="deliverable"><strong>3. Classificação operacional</strong><br><span class="muted">Estimar risco/classe para as unidades do arquivo de operação.</span></div>
  <div class="deliverable"><strong>4. Prioridade de intervenção</strong><br><span class="muted">Indicar as <b>20 unidades prioritárias</b> e justificar a decisão.</span></div>
 </div>

 <div class="card" style="margin-top:14px">
  <strong>Pedido da Prefeitura:</strong>
  <p style="margin-bottom:0;font-size:1.08rem">
   “Não queremos apenas uma taxa de acerto. Queremos saber qual solução vocês recomendam,
   por que ela é adequada para este problema e quais 20 unidades devem receber intervenção primeiro.”
  </p>
 </div>
</section>

<section class="section">
 <div class="kicker">03 • DADOS INICIAIS</div>
 <h2>Material disponível</h2>
 <div class="data-table">
  <div class="data-line"><strong>dados_historicos.csv</strong><br><span class="muted">Histórico das unidades monitoradas, incluindo a ocorrência ou não de falha.</span></div>
  <div class="data-line"><strong>operacao_real.csv</strong><br><span class="muted">Unidades da operação atual. Não contém a variável resposta.</span></div>
 </div>
 <p class="muted">A Central poderá emitir novos comunicados durante o hackathon.</p>
</section>

<section class="section">
 <div class="kicker">04 • EQUIPE</div>
 <h2>Cadastro</h2>
 <div class="team-box" id="register-box">
  <label>Nome da equipe</label>
  <input id="team-name" placeholder="Ex.: Equipe Ada">
  <label>Integrantes</label>
  <input id="team-members" placeholder="Nomes dos integrantes">
  <button class="button" onclick="registerTeam()">Cadastrar equipe</button>
  <div class="feedback" id="register-feedback"></div>
 </div>
 <div id="team-info" style="display:none"></div>
</section>

<section class="section" id="operation" style="display:none">
 <div class="kicker">05 • ÁREA DA EQUIPE</div>
 <h2 id="team-title"></h2>

 <div style="display:flex;gap:10px;flex-wrap:wrap">
  <button class="button secondary" onclick="downloadData('/dados/historicos.csv')">Baixar dados históricos</button>
  <button class="button secondary" onclick="downloadData('/dados/operacao-real.csv')">Baixar operação real</button>
 </div>

 <div class="progress">
  <div class="step wait" id="step1"><strong>Desafio 1</strong><br>Comunicado da Central</div>
  <div class="step wait" id="step2"><strong>Desafio 2</strong><br>Comunicado da Central</div>
  <div class="step wait" id="step3"><strong>Desafio 3</strong><br>Comunicado da Central</div>
 </div>

 <div id="challenge-area"></div>
</section>
</main>

<footer><div class="wrap">Nova Aurora é uma cidade fictícia criada para fins educacionais.</div></footer>

<script>
const token=()=>localStorage.getItem('dc_token');
let lastReleased=-1;

function feedback(id,ok,text){
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
  '<div class="team-box"><strong>Equipe cadastrada:</strong> '+d.nome+
  '<br><span class="muted">'+(d.integrantes||'')+'</span></div>';
 document.getElementById('operation').style.display='block';
 document.getElementById('team-title').textContent='Equipe '+d.nome;

 for(let i=1;i<=3;i++){
  const e=document.getElementById('step'+i);
  e.className='step';
  if(d.concluidos[i-1]) e.classList.add('done');
  else if(i<=d.desafio_liberado) e.classList.add('current');
  else e.classList.add('wait');
 }

 renderChallenges(d);
 lastReleased=d.desafio_liberado;
}

function doneBox(n,checked){
 if(checked){
  return '<div class="feedback show ok">✓ Desafio marcado como concluído pela equipe.</div>';
 }
 return `
  <div style="margin-top:18px;padding:14px;border:1px solid #35516a;border-radius:11px;background:#091725">
   <label style="display:flex;align-items:center;gap:10px;font-size:1rem">
    <input type="checkbox" id="done${n}" style="width:auto;margin:0">
    <span>Concluído</span>
   </label>
   <button class="button" style="margin-top:12px" onclick="finish(${n})">Confirmar</button>
   <div class="feedback" id="fb${n}"></div>
  </div>`;
}

function challenge1(done){
 return `
 <section class="challenge">
  <div class="challenge-head"><span class="alert">SISTEMA • ATUALIZAÇÃO DE DADOS</span><h2>Desafio 1</h2></div>
  <div class="challenge-body">
   <p>A Central Integrada de Operações informa que uma nova remessa de dados operacionais acaba de ser recebida.</p>
   <p>Os registros correspondem a medições mais recentes das unidades monitoradas de Nova Aurora e passam a integrar o conjunto de informações disponível para a operação.</p>
   <p>O arquivo <strong>novos_dados.csv</strong> encontra-se disponível no sistema.</p>
   <button class="button secondary" onclick="downloadData('/dados/novos.csv')">Baixar novos_dados.csv</button>
   ${doneBox(1,done)}
  </div>
 </section>`;
}

function challenge2(done){
 return `
 <section class="challenge">
  <div class="challenge-head"><span class="alert">SISTEMA • ALERTA TÉCNICO</span><h2>Desafio 2</h2></div>
  <div class="challenge-body">
   <p>Durante uma inspeção realizada pela equipe de infraestrutura, foram identificadas falhas no funcionamento de parte dos sensores responsáveis pela medição de <strong>temperatura</strong>.</p>
   <p>Foi constatado que alguns desses sensores não estavam funcionando de forma correta durante o período em que os registros foram produzidos.</p>
   <p>Não há informação precisa sobre quando a irregularidade teve início nem sobre quais unidades foram afetadas.</p>
   ${doneBox(2,done)}
  </div>
 </section>`;
}

function challenge3(done){
 return `
 <section class="challenge">
  <div class="challenge-head"><span class="alert">SISTEMA • COMUNICADO TÉCNICO</span><h2>Desafio 3</h2></div>
  <div class="challenge-body">
   <p>Após uma verificação dos equipamentos de comunicação, a equipe de infraestrutura identificou que os dados de <strong>latencia_rede</strong> registrados recentemente foram medidos de forma incorreta.</p>
   <p>Os testes realizados em campo indicam que as medições apresentam um <strong>erro sistemático de aproximadamente 20%</strong> em relação aos valores reais.</p>
   <p>A origem da irregularidade ainda está sendo investigada. Não foram identificados problemas semelhantes nas demais medições, e a Central mantém o prazo previsto para conclusão da operação.</p>
   ${doneBox(3,done)}
  </div>
 </section>`;
}

function renderChallenges(d){
 const area=document.getElementById('challenge-area');

 if(d.desafio_liberado===0){
  area.innerHTML='<div class="waiting"><strong>Nenhum comunicado adicional foi emitido.</strong><br>A Central informará a equipe caso a situação operacional seja atualizada.</div>';
  return;
 }

 let html='';
 if(d.desafio_liberado>=1) html+=challenge1(d.concluidos[0]);
 if(d.desafio_liberado>=2) html+=challenge2(d.concluidos[1]);
 if(d.desafio_liberado>=3) html+=challenge3(d.concluidos[2]);

 if(d.concluidos.every(Boolean)){
  html+=`
   <section class="challenge" style="border-color:#2f6a4e">
    <div class="challenge-head"><span class="alert" style="background:#123727;border-color:#2d6a4a;color:#bff3d3">ETAPA FINAL</span><h2>Decisão operacional</h2></div>
    <div class="challenge-body">
     <div class="client-ask">Quais são as 20 unidades que devem receber intervenção primeiro — e por quê?</div>
    </div>
   </section>`;
 }

 area.innerHTML=html;
}

async function finish(n){
 const box=document.getElementById('done'+n);
 if(!box.checked){
  feedback('fb'+n,false,'Marque “Concluído” para confirmar.');
  return;
 }
 const r=await fetch('/api/desafio/'+n+'/concluir',{
  method:'POST',
  headers:{'Content-Type':'application/json','X-Team-Token':token()},
  body:JSON.stringify({concluido:true})
 });
 const d=await r.json();
 if(!r.ok){feedback('fb'+n,false,d.detail||'Não foi possível concluir.');return}
 await load();
}

async function downloadData(url){
 const r=await fetch(url,{headers:{'X-Team-Token':token()}});
 if(!r.ok){alert('Arquivo ainda não disponível.');return}
 const b=await r.blob();
 const a=document.createElement('a');
 a.href=URL.createObjectURL(b);
 a.download=url.split('/').pop();
 document.body.appendChild(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(a.href),500);
}

load();
setInterval(load,8000);
</script>
</body>
</html>
"""

ADMIN = r"""
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Painel da Professora</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<header class="hero" style="padding:45px 0 32px">
 <div class="wrap">
  <div class="kicker">DATA CRISIS 2026</div>
  <h1 style="font-size:3rem">Painel da Professora</h1>
  <p>Libere os comunicados no momento desejado durante a aula.</p>
 </div>
</header>

<main class="wrap">
<section class="section">
 <div class="card">
  <label>Chave da professora</label>
  <input id="key" type="password" placeholder="ADMIN_KEY">
  <button class="button secondary" onclick="refresh()">Atualizar painel</button>
  <div class="feedback" id="fb"></div>
 </div>
</section>

<section class="section">
 <div class="kicker">CONTROLE DOS DESAFIOS</div>
 <h2>Comunicados da Central</h2>
 <div class="admin-grid">
  <div class="admin-card">
   <h3>Desafio 1</h3>
   <p class="muted">Nova remessa de dados.</p>
   <button class="button" onclick="release(1)">Liberar Desafio 1</button>
  </div>
  <div class="admin-card">
   <h3>Desafio 2</h3>
   <p class="muted">Sensores de temperatura funcionando de forma incorreta.</p>
   <button class="button" onclick="release(2)">Liberar Desafio 2</button>
  </div>
  <div class="admin-card">
   <h3>Desafio 3</h3>
   <p class="muted">Medições de latencia_rede com erro sistemático aproximado de 20%.</p>
   <button class="button" onclick="release(3)">Liberar Desafio 3</button>
  </div>
  <div class="admin-card">
   <h3>Reiniciar comunicados</h3>
   <p class="muted">Oculta novamente todos os desafios.</p>
   <button class="button secondary" onclick="release(0)">Voltar para 0</button>
  </div>
 </div>
</section>

<section class="section">
 <div class="kicker">STATUS</div>
 <h2>Situação atual</h2>
 <div class="card" id="status">Informe a chave e clique em Atualizar painel.</div>
</section>
</main>

<script>
const key=()=>document.getElementById('key').value;

function feedback(ok,text){
 const el=document.getElementById('fb');
 el.className='feedback show '+(ok?'ok':'bad');
 el.textContent=text;
}

async function release(n){
 if(!key()){feedback(false,'Informe a chave da professora.');return}
 const r=await fetch('/api/professora/liberar/'+n,{
  method:'POST',
  headers:{'X-Admin-Key':key()}
 });
 const d=await r.json();
 if(!r.ok){feedback(false,d.detail||'Erro.');return}
 feedback(true,d.mensagem);
 refresh();
}

async function refresh(){
 if(!key()) return;
 const r=await fetch('/api/professora/status',{headers:{'X-Admin-Key':key()}});
 const d=await r.json();
 if(!r.ok){feedback(false,d.detail||'Erro.');return}
 document.getElementById('status').innerHTML=
  '<strong>Último desafio liberado:</strong> '+d.desafio_liberado+
  '<br><strong>Equipes cadastradas:</strong> '+d.equipes+
  '<br><strong>Concluíram D1:</strong> '+d.d1+
  '<br><strong>Concluíram D2:</strong> '+d.d2+
  '<br><strong>Concluíram D3:</strong> '+d.d3;
}
</script>
</body>
</html>
"""

# ============================================================
# ROTAS PÚBLICAS
# ============================================================
@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(PAGE)

@app.get("/professora", response_class=HTMLResponse)
def professora():
    return HTMLResponse(ADMIN)

@app.get("/style.css")
def style():
    return Response(CSS, media_type="text/css")

@app.post("/api/equipes")
def criar_equipe(payload: EquipeIn):
    token = secrets.token_hex(8)
    con = db()
    con.execute(
        "INSERT INTO equipes(token,nome,integrantes) VALUES(?,?,?)",
        (token,payload.nome,payload.integrantes)
    )
    con.commit()
    con.close()
    return {"token":token,"nome":payload.nome}

@app.get("/api/status")
def status(x_team_token: str | None = Header(default=None)):
    t = get_team(x_team_token)
    return {
        "nome": t["nome"],
        "integrantes": t["integrantes"],
        "concluidos": t["concluidos"],
        "desafio_liberado": get_config_int("desafio_liberado",0)
    }

@app.get("/dados/historicos.csv")
def dados_historicos(x_team_token: str | None = Header(default=None)):
    get_team(x_team_token)
    return csv_response(HISTORICO,COL_HIST,"dados_historicos.csv")

@app.get("/dados/operacao-real.csv")
def operacao_real(x_team_token: str | None = Header(default=None)):
    get_team(x_team_token)
    return csv_response(OPERACAO,COL_OPER,"operacao_real.csv")

@app.get("/dados/novos.csv")
def dados_novos(x_team_token: str | None = Header(default=None)):
    get_team(x_team_token)
    if get_config_int("desafio_liberado",0) < 1:
        raise HTTPException(403,"A nova remessa ainda não foi liberada.")
    return csv_response(NOVOS,COL_HIST,"novos_dados.csv")

@app.post("/api/desafio/{numero}/concluir")
def concluir_desafio(
    numero: int,
    payload: ConclusaoIn,
    x_team_token: str | None = Header(default=None)
):
    t = get_team(x_team_token)
    liberado = get_config_int("desafio_liberado",0)

    if numero not in [1,2,3]:
        raise HTTPException(404,"Desafio inexistente.")
    if numero > liberado:
        raise HTTPException(403,"Este desafio ainda não foi liberado.")
    if not payload.concluido:
        raise HTTPException(400,"Confirme a conclusão.")

    con = db()
    con.execute(
        f"UPDATE equipes SET desafio{numero}_concluido=1 WHERE token=?",
        (t["token"],)
    )
    con.commit()
    con.close()
    return {"ok":True,"desafio":numero}

# ============================================================
# ROTAS DA PROFESSORA
# ============================================================
@app.post("/api/professora/liberar/{numero}")
def liberar(numero: int, x_admin_key: str | None = Header(default=None)):
    admin_ok(x_admin_key)
    if numero not in [0,1,2,3]:
        raise HTTPException(400,"Use 0, 1, 2 ou 3.")

    atual = get_config_int("desafio_liberado",0)

    # Evita pular desafio sem querer.
    if numero > atual + 1:
        raise HTTPException(
            400,
            f"Libere os desafios em sequência. Atualmente está em {atual}."
        )

    set_config("desafio_liberado",numero)

    if numero == 0:
        msg = "Todos os comunicados foram ocultados."
    else:
        msg = f"Desafio {numero} liberado para todas as equipes."

    return {"ok":True,"desafio_liberado":numero,"mensagem":msg}

@app.get("/api/professora/status")
def status_professora(x_admin_key: str | None = Header(default=None)):
    admin_ok(x_admin_key)
    con = db()
    row = con.execute("""
        SELECT COUNT(*),
               COALESCE(SUM(desafio1_concluido),0),
               COALESCE(SUM(desafio2_concluido),0),
               COALESCE(SUM(desafio3_concluido),0)
        FROM equipes
    """).fetchone()
    con.close()

    return {
        "desafio_liberado": get_config_int("desafio_liberado",0),
        "equipes": row[0],
        "d1": row[1],
        "d2": row[2],
        "d3": row[3]
    }
