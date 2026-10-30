// Clínicas-escola em dados: lê dados/painel.json (gerado pelo Python) e faz a página funcionar.
"use strict";

const NUM = (v, casas = 0) => Number(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
const PCT = (v, casas = 1) => NUM(v * 100, casas) + "%";
const DIAS = (n) => (n == null ? "sem fila" : `${NUM(n)} ${Number(n) === 1 ? "dia" : "dias"}`);
const cor = (nome) => getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const SERVICOS = { ODO: "Odontologia", FIS: "Fisioterapia", PSI: "Psicologia", NUT: "Nutrição" };
const UNIDADES = { REC: "Recife", OLI: "Olinda", JAB: "Jaboatão" };
let painel = null;
const graficos = {};

// ------------------------------------------------------------------ o painel com filtros
// As somas vêm da tabela mensal (somar e só depois dividir: a taxa fica certa com qualquer filtro).
// A espera é mediana e vem pronta do Python para cada combinação de filtro.
function filtrar(u, s) {
  const linhas = painel.filtros.mensal.filter((r) => (u === "*" || r.unidade === u) && (s === "*" || r.servico === s));
  const soma = (c) => linhas.reduce((t, r) => t + r[c], 0);
  const meses = {};
  for (const r of linhas) {
    const m = (meses[r.mes] ??= { realizados: 0, faltas: 0 });
    m.realizados += r.realizados;
    m.faltas += r.faltas;
  }
  return {
    linhas,
    realizados: soma("realizados"),
    faltas: soma("faltas"),
    agendamentos: soma("agendamentos"),
    ofertados: soma("horarios_ofertados"),
    perdidas: soma("horas_perdidas"),
    fila: painel.filtros.fila[`${u}|${s}`],
    meses: Object.entries(meses).sort(([a], [b]) => a.localeCompare(b)),
  };
}

function eixos(extra = {}) {
  const texto = cor("--muted"), grade = cor("--linha");
  const fonte = { family: "General Sans", size: 13 };
  return {
    x: { grid: { display: false }, ticks: { color: texto, font: fonte }, border: { display: false }, ...extra.x },
    y: { grid: { color: grade }, ticks: { color: texto, font: fonte }, border: { display: false }, ...extra.y },
  };
}
const opcoesBase = (extra = {}) => ({
  responsive: true, maintainAspectRatio: false, animation: { duration: 600 },
  plugins: { legend: { display: false } }, ...extra,
});

function desenharPainel() {
  const u = document.getElementById("f-unidade").value;
  const s = document.getElementById("f-servico").value;
  const d = filtrar(u, s);
  if (!d.linhas.length) {
    // Ex.: Olinda não tem Nutrição. Volta o serviço para "Todos" e avisa.
    document.getElementById("f-servico").value = "*";
    desenharPainel();
    document.getElementById("painel-nota").textContent = `${UNIDADES[u]} não tem ${SERVICOS[s]}: mostrando todos os serviços da unidade.`;
    return;
  }
  const taxa = d.faltas / (d.realizados + d.faltas);
  const valores = {
    "k-realizados": NUM(d.realizados),
    "k-faltas": PCT(taxa),
    "k-ocupacao": PCT(d.agendamentos / d.ofertados),
    "k-espera": DIAS(d.fila?.espera_mediana_dias),
    "k-perdidas": `${NUM(d.perdidas)} h`,
  };
  for (const [id, v] of Object.entries(valores)) {
    const el = document.getElementById(id);
    if (el.textContent !== v) {
      el.textContent = v;
      el.parentElement.classList.add("pisca");
      setTimeout(() => el.parentElement.classList.remove("pisca"), 350);
    }
  }
  const nome = [u === "*" ? null : UNIDADES[u], s === "*" ? null : SERVICOS[s]].filter(Boolean).join(" · ");
  document.getElementById("painel-nota").textContent = nome
    ? `Filtrado: ${nome}. ${NUM(d.agendamentos)} agendamentos, ${NUM(d.fila?.aguardando ?? 0)} pessoas na fila em 31/10.`
    : "Dados fictícios, gerados por simulação. Os mesmos números do relatório no Power BI.";

  const azul = cor("--d-azul"), coral = cor("--d-barra-falta");
  const rotulos = d.meses.map(([m]) => `${MESES[Number(m.slice(5, 7)) - 1]}/${m.slice(2, 4)}`);
  const dadosMes = {
    labels: rotulos,
    datasets: [
      { label: "Realizados", data: d.meses.map(([, v]) => v.realizados), backgroundColor: azul, borderRadius: 3 },
      { label: "Faltas", data: d.meses.map(([, v]) => v.faltas), backgroundColor: coral, borderRadius: 3 },
    ],
  };
  if (graficos.mes) { graficos.mes.data = dadosMes; graficos.mes.update(); }
  else if (window.Chart) {
    graficos.mes = new Chart(document.getElementById("g-mes"), {
      type: "bar", data: dadosMes,
      options: opcoesBase({
        plugins: { legend: { display: true, position: "top", align: "start", labels: { color: cor("--muted"), boxWidth: 10, font: { family: "General Sans", size: 13 } } },
          tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${NUM(c.raw)}` } } },
        scales: eixos({ y: { ticks: { color: cor("--muted"), callback: (v) => NUM(v) } } }),
      }),
    });
  }

  // Taxa de faltas por clínica, respeitando o filtro de unidade e de serviço.
  const clinicas = painel.por_clinica.filter((c) => (u === "*" || c.unidade === u) && (s === "*" || c.servico === s))
    .sort((a, b) => b.taxa_faltas - a.taxa_faltas);
  const dadosCli = {
    labels: clinicas.map((c) => c.clinica),
    datasets: [{ data: clinicas.map((c) => c.taxa_faltas), backgroundColor: clinicas.map((c) => (c.taxa_faltas >= 0.22 ? coral : azul)), borderRadius: 3 }],
  };
  if (graficos.cli) { graficos.cli.data = dadosCli; graficos.cli.update(); }
  else if (window.Chart) {
    graficos.cli = new Chart(document.getElementById("g-clinicas"), {
      type: "bar", data: dadosCli,
      options: opcoesBase({
        indexAxis: "y",
        onClick: (_e, itens) => {
          if (!itens.length) return;
          const c = graficos.cli.__clinicas[itens[0].index];
          document.getElementById("f-unidade").value = c.unidade;
          document.getElementById("f-servico").value = c.servico;
          desenharPainel();
        },
        onHover: (e, itens) => { e.native.target.style.cursor = itens.length ? "pointer" : "default"; },
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => ` ${PCT(c.raw)} de faltas` } } },
        scales: eixos({ x: { grid: { color: cor("--linha") }, ticks: { color: cor("--muted"), callback: (v) => PCT(v, 0) }, beginAtZero: true } }),
      }),
    });
  }
  if (graficos.cli) graficos.cli.__clinicas = clinicas;
}

// ------------------------------------------------------------------ o controle deslizante
function faixaEspera(dias) {
  const f = painel.espera_x_falta;
  if (dias <= 7) return f[0];
  if (dias <= 30) return f[1];
  if (dias <= 60) return f[2];
  return f[3];
}
function atualizarEspera() {
  const dias = Number(document.getElementById("dias").value);
  document.getElementById("dias-valor").textContent = DIAS(dias);
  const f = faixaEspera(dias);
  document.getElementById("chance").textContent = PCT(f.taxa_faltas, 0);
  const total = painel.espera_x_falta.reduce((t, x) => t + x.consultas, 0);
  document.getElementById("espera-conta").textContent =
    `Faixa “${f.faixa}”: ${PCT(f.taxa_faltas)} de faltas em ${NUM(f.consultas)} primeiras consultas. ` +
    `Medido nas ${NUM(total)} primeiras consultas do período; quem esperou até 7 dias falta ${PCT(painel.espera_x_falta[0].taxa_faltas, 0)} das vezes.`;
}

// ------------------------------------------------------------------ o editor (as mesmas regras do Python)
const SITUACAO = {
  "atendido": "Realizado", "compareceu": "Realizado", "ok": "Realizado", "r": "Realizado",
  "faltou": "Falta", "falta": "Falta", "f": "Falta", "nao compareceu": "Falta",
  "desmarcou": "Cancelado pelo paciente", "paciente desmarcou": "Cancelado pelo paciente",
  "desmarcado": "Cancelado pelo paciente", "cp": "Cancelado pelo paciente",
  "cancelado (supervisor ausente)": "Cancelado pela clínica", "clinica cancelou": "Cancelado pela clínica", "cc": "Cancelado pela clínica",
};
const norm = (t) => t.normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim().toLowerCase();
function lerData(t) {
  const m = t.trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{2}|\d{4})$/);
  if (!m) return null;
  const ano = m[3].length === 2 ? 2000 + Number(m[3]) : Number(m[3]);
  const d = new Date(ano, Number(m[2]) - 1, Number(m[1]));
  if (d.getMonth() !== Number(m[2]) - 1) return null;
  return { valor: `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${ano}`, texto: m[3].length === 2 || m[1].length === 1 };
}
function lerHora(t) {
  const m = t.trim().match(/^(\d{1,2})\s*[h:]\s*(\d{2})?$/);
  if (!m || Number(m[1]) > 23 || Number(m[2] || 0) > 59) return null;
  return { valor: `${m[1].padStart(2, "0")}:${m[2] || "00"}`, texto: /h/.test(t) };
}
function padronizarTexto() {
  const corpo = document.getElementById("limpo");
  corpo.innerHTML = "";
  let desconhecidas = 0;
  for (const linha of document.getElementById("bruto").value.split("\n")) {
    if (!linha.trim()) continue;
    const partes = linha.split(/[·;|]/).map((p) => p.trim());
    let data = null, hora = null, situacao = null, original = "";
    const regras = new Set();
    for (const p of partes) {
      const d = lerData(p), h = lerHora(p), s = SITUACAO[norm(p)];
      if (d && !data) { data = d.valor; if (d.texto) regras.add("R04"); }
      else if (h && !hora) { hora = h.valor; if (h.texto) regras.add("R05"); }
      else if (s && !situacao) { situacao = s; original = p; if (!["Atendido", "Faltou", "Desmarcou"].includes(p)) regras.add("R03"); }
      else if (p) { original = p; }
    }
    const tr = document.createElement("tr");
    const celulas = [data ?? "?", hora ?? "?", situacao ?? `“${original || linha.trim()}”`, situacao ? [...regras].join(" ") || "já no padrão" : "conferir na origem"];
    celulas.forEach((v, i) => {
      const td = document.createElement("td");
      td.textContent = v;
      if (i === 3) td.className = "regra";
      if ((i === 2 && !situacao) || v === "?") td.classList.add("erro");
      tr.appendChild(td);
    });
    if (!situacao) desconhecidas++;
    corpo.appendChild(tr);
  }
  document.getElementById("limpo-nota").textContent = desconhecidas
    ? `${desconhecidas} linha(s) com forma desconhecida: não é adivinhada, vai para a lista de conferência com arquivo, aba e linha.`
    : "Tudo reconhecido. Forma desconhecida não seria adivinhada: iria para a lista de conferência.";
}

// ------------------------------------------------------------------ achados: o palco fixo
function montarCalor() {
  const el = document.getElementById("calor");
  const dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"];
  const calor = painel.calor_faltas;
  const max = Math.max(...calor.map((c) => c.taxa_faltas)), min = Math.min(...calor.map((c) => c.taxa_faltas));
  let html = '<span class="cab"></span><span class="cab">Manhã</span><span class="cab">Tarde</span>';
  for (const d of dias) {
    html += `<span class="cab">${d}</span>`;
    for (const t of ["Manhã", "Tarde"]) {
      const c = calor.find((x) => x.dia === d && x.turno === t);
      const forca = Math.round(12 + 88 * (c.taxa_faltas - min) / (max - min));
      const texto = forca > 55 ? "#170b05" : "var(--ink)";
      html += `<span class="cel" style="background: color-mix(in srgb, var(--d-barra-falta) ${forca}%, var(--surface)); color: ${texto}">${PCT(c.taxa_faltas)}</span>`;
    }
  }
  el.innerHTML = html;
  const seg = calor.find((x) => x.dia === "Segunda" && x.turno === "Manhã");
  document.getElementById("seg-manha").textContent = PCT(seg.taxa_faltas);
}
function montarGraficosAchados() {
  if (!window.Chart) return;
  for (const k of ["olinda", "alunos"]) if (graficos[k]) graficos[k].destroy();
  const ordem = [...painel.por_clinica].sort((a, b) => a.ocupacao - b.ocupacao);
  graficos.olinda = new Chart(document.getElementById("g-olinda"), {
    type: "bar",
    data: { labels: ordem.map((c) => c.clinica), datasets: [{ data: ordem.map((c) => c.ocupacao), borderRadius: 3,
      backgroundColor: ordem.map((c) => (c.ocupacao < 0.6 ? cor("--d-barra-falta") : cor("--d-azul"))) }] },
    options: opcoesBase({ indexAxis: "y",
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => ` ${PCT(c.raw)} da agenda · espera ${DIAS(ordem[c.dataIndex].espera_mediana_dias)}` } } },
      scales: eixos({ x: { max: 1, grid: { color: cor("--linha") }, ticks: { color: cor("--muted"), callback: (v) => PCT(v, 0) } } }) }),
  });
  const al = ["ODO", "FIS", "PSI", "NUT"].map((s) => painel.alunos_2026_1.find((x) => x.servico === s));
  graficos.alunos = new Chart(document.getElementById("g-alunos"), {
    type: "bar",
    data: { labels: al.map((x) => SERVICOS[x.servico]), datasets: [
      { label: "Bateram a meta", data: al.map((x) => x.bateram_meta / x.alunos), backgroundColor: cor("--d-verde") },
      { label: "Bateriam sem as faltas", data: al.map((x) => x.bateriam_sem_faltas / x.alunos), backgroundColor: cor("--d-mostarda") },
      { label: "Abaixo da meta", data: al.map((x) => (x.alunos - x.bateram_meta - x.bateriam_sem_faltas) / x.alunos), backgroundColor: cor("--d-barra-falta") }] },
    options: opcoesBase({ indexAxis: "y",
      plugins: { legend: { display: true, position: "top", align: "start", labels: { color: cor("--muted"), boxWidth: 10, font: { family: "General Sans", size: 13 } } },
        tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${Math.round(c.raw * al[c.dataIndex].alunos)} alunos` } } },
      scales: eixos({ x: { stacked: true, max: 1, grid: { color: cor("--linha") }, ticks: { color: cor("--muted"), callback: (v) => PCT(v, 0) } }, y: { stacked: true } }) }),
  });
  const bateram = al.reduce((t, x) => t + x.bateram_meta, 0), total = al.reduce((t, x) => t + x.alunos, 0);
  document.getElementById("alunos-meta").textContent = `${bateram} de ${total}`;
  document.getElementById("alunos-sem").textContent = al.reduce((t, x) => t + x.bateriam_sem_faltas, 0);
}
function cenaAtiva(n) {
  document.querySelectorAll(".palco-cena").forEach((c) => c.classList.toggle("ativa", c.dataset.cena === n));
  document.querySelectorAll(".passo").forEach((p) => p.classList.toggle("ativo", p.dataset.cena === n));
}

// ------------------------------------------------------------------ chaves, tema, entradas, hora
document.querySelectorAll(".chave").forEach((b) => {
  b.addEventListener("click", () => {
    const ligada = b.getAttribute("aria-checked") !== "true";
    b.setAttribute("aria-checked", String(ligada));
    b.closest(".faixa").classList.toggle("ligada", ligada);
  });
});

document.querySelector(".tema").addEventListener("click", () => {
  const raiz = document.documentElement;
  const escuroAgora = raiz.dataset.theme === "dark";
  raiz.dataset.theme = escuroAgora ? "light" : "dark";
  try { localStorage.setItem("tema", raiz.dataset.theme); } catch (e) { /* navegação privada */ }
  if (!painel) return;
  for (const k of Object.keys(graficos)) { graficos[k].destroy(); delete graficos[k]; }
  desenharPainel(); montarGraficosAchados(); montarCalor();
});

function relogio() {
  if (!document.getElementById("hora")) return;
  const agora = new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Recife", hour: "2-digit", minute: "2-digit" }).format(new Date());
  document.getElementById("hora").textContent = `${agora} em Recife`;
}
relogio(); setInterval(relogio, 30000);

const observador = "IntersectionObserver" in window ? new IntersectionObserver((itens) => {
  for (const it of itens) if (it.isIntersecting) { it.target.classList.add("visivel"); observador.unobserve(it.target); }
}, { rootMargin: "0px 0px -6% 0px", threshold: 0 }) : null;
document.querySelectorAll("section, footer").forEach((secao) => {
  secao.querySelectorAll(".revela").forEach((el, i) => {
    el.style.transitionDelay = `${Math.min(i, 5) * 75}ms`;
    if (observador) observador.observe(el); else el.classList.add("visivel");
  });
});
document.querySelectorAll(".hero .revela").forEach((el, i) => setTimeout(() => el.classList.add("visivel"), 120 + i * 110));

if ("IntersectionObserver" in window) {
  const passos = new IntersectionObserver((itens) => {
    for (const it of itens) if (it.isIntersecting) cenaAtiva(it.target.dataset.cena);
  }, { rootMargin: "-45% 0px -45% 0px", threshold: 0 });
  document.querySelectorAll(".passo").forEach((p) => passos.observe(p));
}
cenaAtiva("1");

document.getElementById("bruto").addEventListener("input", padronizarTexto);
padronizarTexto();

fetch("dados/painel.json").then((r) => r.json()).then((p) => {
  painel = p;
  desenharPainel();
  montarCalor();
  montarGraficosAchados();
  atualizarEspera();
  const c = p.cenario_segunda;
  document.getElementById("efeito-1").textContent =
    `Se a segunda de manhã caísse para a média dos outros turnos (${PCT(c.taxa_outros)}), seriam ${NUM(c.faltas_a_menos)} faltas a menos no ano.`;
  const r03 = p.qualidade.regras.find((r) => r.regra === "R03").ocorrencias;
  document.getElementById("efeito-5").textContent = `${NUM(r03)} situações escritas fora do padrão deixariam de existir.`;
  for (const id of ["f-unidade", "f-servico"]) document.getElementById(id).addEventListener("change", desenharPainel);
  document.getElementById("limpar").addEventListener("click", () => {
    document.getElementById("f-unidade").value = "*";
    document.getElementById("f-servico").value = "*";
    desenharPainel();
  });
  document.getElementById("dias").addEventListener("input", atualizarEspera);
}).catch(() => { document.getElementById("painel-nota").textContent = "Não foi possível carregar os dados."; });
