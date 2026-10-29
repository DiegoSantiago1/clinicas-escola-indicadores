// Clínicas-escola em dados: lê dados/painel.json (gerado pelo Python) e monta a página.
"use strict";

const PCT = (v, casas = 1) => (v * 100).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }) + "%";
const NUM = (v, casas = 0) => Number(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
const dias = (n) => `${NUM(n)} ${Number(n) === 1 ? "dia" : "dias"}`;
const NOMES = { ODO: "Odontologia", FIS: "Fisioterapia", PSI: "Psicologia", NUT: "Nutrição" };
const cor = (nome) => getComputedStyle(document.documentElement).getPropertyValue(nome).trim();

// ------------------------------------------------------------- a padronização ao vivo
// As mesmas regras do Python (src/clinicas/padronizar.py): norm, SITUACAO, ler_data, ler_hora.
const SITUACAO = {
  "atendido": "Realizado", "compareceu": "Realizado", "ok": "Realizado", "r": "Realizado",
  "faltou": "Falta", "falta": "Falta", "f": "Falta", "nao compareceu": "Falta",
  "desmarcou": "Cancelado pelo paciente", "paciente desmarcou": "Cancelado pelo paciente",
  "desmarcado": "Cancelado pelo paciente", "cp": "Cancelado pelo paciente",
  "cancelado (supervisor ausente)": "Cancelado pela clínica", "clinica cancelou": "Cancelado pela clínica",
  "cc": "Cancelado pela clínica",
};
// Quantas vezes cada forma apareceu nas cinco planilhas.
const VEZES = {
  "ok": 5757, "ATENDIDO": 5734, "atendido": 5687, "Atendido": 5624, "Compareceu": 5620, "falta": 1670,
  "faltou ": 1602, "F": 1593, "Faltou": 1577, "Não compareceu": 1568, "Desmarcou": 515, "desmarcado": 510,
  "Paciente desmarcou": 493, "Clínica cancelou": 167, "Cancelado (supervisor ausente)": 160,
};
const norm = (t) => t.normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/º/g, "o").replace(/ª/g, "a")
  .replace(/\s+/g, " ").trim().toLowerCase();

function lerData(t) {
  const m = t.trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{2}|\d{4})$/);
  if (!m) return null;
  const ano = m[3].length === 2 ? 2000 + Number(m[3]) : Number(m[3]);
  const d = new Date(ano, Number(m[2]) - 1, Number(m[1]));
  if (d.getMonth() !== Number(m[2]) - 1) return null;
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${ano}`;
}
function lerHora(t) {
  const m = t.trim().match(/^(\d{1,2})\s*[h:]\s*(\d{2})?$/);
  if (!m || Number(m[1]) > 23 || Number(m[2] || 0) > 59) return null;
  return `${m[1].padStart(2, "0")}:${m[2] || "00"}`;
}

function padronizar() {
  const valor = document.getElementById("entrada").value;
  const saida = document.getElementById("saida");
  const nota = document.getElementById("saida-nota");
  const caixa = saida.closest(".resposta");
  caixa.classList.remove("erro");
  if (!valor.trim()) { saida.textContent = "…"; nota.textContent = "Digite uma anotação."; return; }
  const situacao = SITUACAO[norm(valor)];
  if (situacao) {
    saida.textContent = situacao;
    const vezes = VEZES[valor];
    nota.textContent = (situacao === valor ? "Já está no padrão." : "Regra R03: situação escrita de outro jeito.") +
      (vezes ? ` Esta forma exata apareceu ${NUM(vezes)} vezes nas planilhas.` : "");
    return;
  }
  const data = lerData(valor);
  if (data) { saida.textContent = data; nota.textContent = "Regra R04: data digitada como texto, convertida para data."; return; }
  const hora = lerHora(valor);
  if (hora) { saida.textContent = hora; nota.textContent = "Regra R05: horário digitado como texto, convertido."; return; }
  caixa.classList.add("erro");
  saida.textContent = "Forma desconhecida";
  nota.textContent = "A padronização para com o arquivo, a aba e a linha, em vez de adivinhar. Alguém confere e a forma nova entra no dicionário.";
}

// ------------------------------------------------------------- o quadro das clínicas
function situacaoDa(c) {
  if (c.ocupacao < 0.6 && c.fila_aguardando_fim > 100) return ["Agenda ociosa", "s-ociosa"];
  if (c.fila_aguardando_fim >= 10) return ["Fila acumulando", "s-fila"];
  if (c.taxa_faltas >= 0.22) return ["Faltas altas", "s-faltas"];
  return ["Em dia", "s-dia"];
}
function detalheDa(c) {
  const base = `${PCT(c.taxa_faltas)} de faltas, ${PCT(c.ocupacao)} da agenda ocupada, espera mediana de ${dias(c.espera_mediana_dias)} e ${NUM(c.fila_aguardando_fim)} pessoas aguardando em 31/10.`;
  if (c.unidade === "OLI" && c.servico === "FIS")
    return base + " Não falta sala: a primeira consulta só é marcada às segundas e quartas, e a recepção não consegue contato com parte da fila.";
  if (c.unidade === "REC" && (c.servico === "ODO" || c.servico === "PSI"))
    return base + " A procura é maior que a capacidade: a agenda está quase cheia e a fila não zera.";
  if (c.taxa_faltas >= 0.22) return base + " A agenda está cheia, mas mais de um em cada cinco pacientes não aparece.";
  return base;
}
function montarQuadro(clinicas) {
  const ordem = { "s-ociosa": 0, "s-fila": 1, "s-faltas": 2, "s-dia": 3 };
  const lista = [...clinicas].sort((a, b) => ordem[situacaoDa(a)[1]] - ordem[situacaoDa(b)[1]] || b.taxa_faltas - a.taxa_faltas);
  const ol = document.getElementById("linhas");
  ol.innerHTML = "";
  lista.forEach((c, i) => {
    const [texto, classe] = situacaoDa(c);
    const li = document.createElement("li");
    li.className = "linha-clinica" + (i === 0 ? " aberta" : "");
    li.innerHTML = `<button type="button" aria-expanded="${i === 0}">
      <span class="nome"></span>
      <span class="col"><span class="rotulo">Faltas</span>${PCT(c.taxa_faltas)}</span>
      <span class="col"><span class="rotulo">Agenda</span>${PCT(c.ocupacao, 0)}</span>
      <span class="col"><span class="rotulo">Espera</span>${dias(c.espera_mediana_dias)}</span>
      <span class="situacao ${classe}">${texto}</span>
      <span class="detalhe"></span></button>`;
    li.querySelector(".nome").textContent = c.clinica;
    li.querySelector(".detalhe").textContent = detalheDa(c);
    li.querySelector("button").addEventListener("click", () => {
      ol.querySelectorAll(".linha-clinica").forEach((o) => { o.classList.remove("aberta"); o.querySelector("button").setAttribute("aria-expanded", "false"); });
      li.classList.add("aberta");
      li.querySelector("button").setAttribute("aria-expanded", "true");
    });
    ol.appendChild(li);
  });
}

// ------------------------------------------------------------- achados
function montarCalor(calor) {
  const el = document.getElementById("calor");
  const dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"];
  const max = Math.max(...calor.map((c) => c.taxa_faltas));
  const min = Math.min(...calor.map((c) => c.taxa_faltas));
  let html = '<span class="cab"></span><span class="cab">Manhã</span><span class="cab">Tarde</span>';
  for (const d of dias) {
    html += `<span class="cab">${d}</span>`;
    for (const t of ["Manhã", "Tarde"]) {
      const c = calor.find((x) => x.dia === d && x.turno === t);
      const forca = Math.round(18 + 82 * (c.taxa_faltas - min) / (max - min));
      const texto = forca > 60 ? "#14213d" : "var(--ink)";
      html += `<span class="cel" style="background: color-mix(in srgb, var(--coral) ${forca}%, var(--surface)); color: ${texto}">${PCT(c.taxa_faltas)}</span>`;
    }
  }
  el.innerHTML = html;
}

const graficos = [];
function eixos() {
  const grade = cor("--surface"), texto = cor("--muted");
  return {
    x: { grid: { display: false }, ticks: { color: texto, font: { family: "General Sans", size: 14 } }, border: { display: false } },
    y: { grid: { color: grade }, ticks: { color: texto, font: { family: "General Sans", size: 14 } }, border: { display: false } },
  };
}
function base(extra = {}) {
  return {
    responsive: true, maintainAspectRatio: false, animation: { duration: 900 }, layout: { padding: { left: 6 } },
    plugins: { legend: { labels: { color: cor("--ink"), font: { family: "General Sans", size: 14 }, boxWidth: 12 } },
      tooltip: { callbacks: {} } },
    ...extra,
  };
}
function montarGraficos(p) {
  graficos.splice(0).forEach((g) => g.destroy());
  if (!window.Chart) return;
  const coral = cor("--coral"), azul = cor("--azul"), verde = cor("--verde"), mostarda = cor("--mostarda");

  const esp = p.espera_x_falta;
  const e = eixos();
  graficos.push(new Chart(document.getElementById("g-espera"), {
    type: "bar",
    data: { labels: ["Até 7 dias", "8 a 30 dias", "31 a 60 dias", "Mais de 60 dias"],
      datasets: [{ label: "Falta na 1ª consulta", data: esp.map((x) => x.taxa_faltas), backgroundColor: [azul, azul, coral, coral], borderRadius: 0 }] },
    options: base({ plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => ` ${PCT(c.raw)} de ${NUM(esp[c.dataIndex].consultas)} consultas` } } },
      scales: { x: e.x, y: { ...e.y, ticks: { ...e.y.ticks, callback: (v) => PCT(v, 0) }, beginAtZero: true } } }),
  }));

  const nomesMes = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
  const rot = p.meses.map((m) => `${nomesMes[Number(m.mes.slice(5)) - 1]}/${m.mes.slice(2, 4)}`);
  graficos.push(new Chart(document.getElementById("g-meses"), {
    type: "bar",
    data: { labels: rot, datasets: [
      { label: "Realizados", data: p.meses.map((m) => m.realizados), backgroundColor: azul, borderRadius: 0 },
      { label: "Faltas", data: p.meses.map((m) => m.faltas), backgroundColor: coral, borderRadius: 0 }] },
    options: base({ scales: { x: e.x, y: { ...e.y, ticks: { ...e.y.ticks, callback: (v) => NUM(v) } } },
      plugins: { legend: { position: "top", align: "start", labels: { color: cor("--ink"), font: { family: "General Sans", size: 14 }, boxWidth: 12 } } } }),
  }));

  const al = p.alunos_2026_1;
  const ordem = ["ODO", "FIS", "PSI", "NUT"].map((s) => al.find((x) => x.servico === s));
  graficos.push(new Chart(document.getElementById("g-alunos"), {
    type: "bar",
    data: { labels: ordem.map((x) => NOMES[x.servico]), datasets: [
      { label: "Bateram a meta", data: ordem.map((x) => x.bateram_meta / x.alunos), backgroundColor: verde },
      { label: "Bateriam sem as faltas", data: ordem.map((x) => x.bateriam_sem_faltas / x.alunos), backgroundColor: mostarda },
      { label: "Abaixo da meta", data: ordem.map((x) => (x.alunos - x.bateram_meta - x.bateriam_sem_faltas) / x.alunos), backgroundColor: coral }] },
    options: base({ indexAxis: "y",
      plugins: { legend: { position: "top", align: "start", labels: { color: cor("--ink"), font: { family: "General Sans", size: 14 }, boxWidth: 12 } },
        tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${PCT(c.raw, 0)} (${Math.round(c.raw * ordem[c.dataIndex].alunos)} alunos)` } } },
      scales: { x: { ...e.x, stacked: true, max: 1, grid: { color: cor("--surface") }, ticks: { ...e.x.ticks, callback: (v) => PCT(v, 0) } }, y: { ...e.y, stacked: true, grid: { display: false } } } }),
  }));
}

function preencher(p) {
  const g = p.geral;
  document.querySelector('[data-valor="taxa_faltas"]').textContent = PCT(g.taxa_faltas);
  document.querySelector('[data-valor="horas_perdidas"]').textContent = `${NUM(g.horas_perdidas_faltas)} h`;
  const seg = p.calor_faltas.find((x) => x.dia === "Segunda" && x.turno === "Manhã");
  document.getElementById("seg-manha").textContent = PCT(seg.taxa_faltas);
  document.getElementById("espera-alta").textContent = PCT(p.espera_x_falta.at(-1).taxa_faltas, 0);
  document.getElementById("espera-baixa").textContent = PCT(p.espera_x_falta[0].taxa_faltas, 0);
  const al = p.alunos_2026_1;
  const bateram = al.reduce((s, x) => s + x.bateram_meta, 0), total = al.reduce((s, x) => s + x.alunos, 0);
  document.getElementById("alunos-meta").textContent = `${bateram} de ${total}`;
  document.getElementById("alunos-sem-faltas").textContent = al.reduce((s, x) => s + x.bateriam_sem_faltas, 0);

  const regra = (id) => p.qualidade.regras.find((r) => r.regra === id).ocorrencias;
  document.getElementById("removidas").textContent = `${NUM(regra("R01"))} + ${NUM(regra("R09"))} + ${NUM(regra("R10"))} removidas`;
  document.getElementById("recuperados").textContent = NUM(regra("R07"));
  document.getElementById("sinalizados").textContent = NUM(regra("R07x"));

  const tbody = document.querySelector("#tabela-regras tbody");
  tbody.innerHTML = "";
  for (const r of p.qualidade.regras) {
    const tr = document.createElement("tr");
    for (const [v, cls] of [[r.regra], [r.descricao], [r.acao], [NUM(r.ocorrencias), "num"]]) {
      const td = document.createElement("td");
      td.textContent = v;
      if (cls) td.className = cls;
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  montarQuadro(p.por_clinica);
  montarCalor(p.calor_faltas);
  montarGraficos(p);
}

// ------------------------------------------------------------- tema e entradas
let painel = null;
document.querySelector(".tema").addEventListener("click", () => {
  const raiz = document.documentElement;
  const escuroAgora = raiz.dataset.theme ? raiz.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  raiz.dataset.theme = escuroAgora ? "light" : "dark";
  try { localStorage.setItem("tema", raiz.dataset.theme); } catch (e) { /* navegação privada */ }
  if (painel) montarGraficos(painel);
});

document.getElementById("entrada").addEventListener("input", padronizar);
document.querySelectorAll("[data-ex]").forEach((b) => b.addEventListener("click", () => {
  const entrada = document.getElementById("entrada");
  entrada.value = b.dataset.ex;
  padronizar();
  entrada.focus();
}));

// Cada bloco é observado sozinho (limiar 0): uma seção mais alta que a tela nunca deixa conteúdo escondido.
const observador = "IntersectionObserver" in window ? new IntersectionObserver((itens) => {
  for (const it of itens) if (it.isIntersecting) { it.target.classList.add("visivel"); observador.unobserve(it.target); }
}, { rootMargin: "0px 0px -6% 0px", threshold: 0 }) : null;
document.querySelectorAll("section, .rodape").forEach((secao) => {
  secao.querySelectorAll(".revela").forEach((el, i) => {
    el.style.transitionDelay = `${Math.min(i, 5) * 75}ms`;
    if (observador) observador.observe(el); else el.classList.add("visivel");
  });
});
document.querySelectorAll(".abertura .revela").forEach((el, i) => setTimeout(() => el.classList.add("visivel"), 650 + i * 120));

fetch("dados/painel.json").then((r) => r.json()).then((p) => { painel = p; preencher(p); })
  .catch(() => { document.getElementById("linhas").textContent = "Não foi possível carregar os dados."; });
padronizar();
