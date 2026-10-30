// Rede Acolher: o painel de trabalho. Lê dados/jornada.json (a jornada de cada paciente, calculada
// em Python) e ../dados/painel.json (as clínicas e a qualidade). Telas por hash: #/jornada,
// #/paciente/<prontuário>, #/clinicas, #/qualidade.
"use strict";

const NUM = (v, c = 0) => Number(v).toLocaleString("pt-BR", { minimumFractionDigits: c, maximumFractionDigits: c });
const PCT = (v, c = 1) => `${NUM(v * 100, c)}%`;
const DATA = (iso) => (iso ? new Date(`${iso}T12:00:00`).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" }).replace(".", "") : "—");
const CURTA = (iso) => (iso ? new Date(`${iso}T12:00:00`).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" }).replace(".", "").replace(" de ", " ") : "—");
const DIAS = (n) => (n == null ? "—" : `${NUM(n)} ${n === 1 ? "dia" : "dias"}`);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const tela = document.getElementById("tela");
let J = null, P = null;
const estado = { servico: "*", busca: "", soFaltas: false, etapaCelular: "sem_retorno" };

// Cor pálida e estável por aluno (identidade, não dado): 6 tons a 60 graus.
const TONS = ["#9fd8d2", "#b9c8f5", "#f3c4a8", "#d6c3f0", "#c9e3a5", "#f2b9cf"];
function tom(texto) { let h = 0; for (const c of texto) h = (h * 31 + c.charCodeAt(0)) >>> 0; return TONS[h % TONS.length]; }
const iniciais = (nome) => nome.split(" ").filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();

// O que cada etapa mostra no cartão.
const VALOR = {
  fila: (d) => [DIAS(d.dias_na_fila), "na fila"],
  chamado: (d) => [d.faltas ? `${d.faltas} ${d.faltas === 1 ? "falta" : "faltas"}` : "1ª consulta", d.faltas ? "sem vir ainda" : `marcada p/ ${CURTA(d.ultimo)}`],
  tratamento: (d) => [`${d.realizados} ${d.realizados === 1 ? "sessão" : "sessões"}`, `de ${d.agendamentos}`],
  sem_retorno: (d) => [DIAS(d.dias_sem_vir), "sem vir"],
  encerrado: (d) => [`${d.realizados} ${d.realizados === 1 ? "sessão" : "sessões"}`, `até ${CURTA(d.ultimo)}`],
  desistiu: (d) => [DIAS(d.dias_na_fila), "da inscrição"],
};
const MEDIANA = {
  fila: (m) => `mediana ${DIAS(m)}`,
  chamado: (m) => `mediana ${DIAS(m)}`,
  tratamento: (m) => `mediana ${NUM(m)} sessões`,
  sem_retorno: (m) => `mediana ${DIAS(m)}`,
  encerrado: (m) => `mediana ${NUM(m)} sessões`,
  desistiu: () => "sem data de saída",
};

// ------------------------------------------------------------------ tela: jornada
function telaJornada() {
  const t = J.totais;
  const sem = t.sem_retorno;
  tela.innerHTML = `
    <div class="titulo">
      <div>
        <h1>Jornada do paciente</h1>
        <p class="titulo-sub">${NUM(J.pacientes)} pacientes da fila à última consulta. <strong>${NUM(sem)} estão sem retorno há 31 a 90 dias</strong>: a recepção liga para eles primeiro.</p>
      </div>
      <button class="botao-primario" type="button" id="copiar-sem">
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>
        Copiar lista de ligação
      </button>
    </div>
    <div class="filtros">
      <label class="busca"><span class="sr" style="position:absolute;width:1px;height:1px;overflow:hidden">Buscar prontuário</span>
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="11" cy="11" r="6" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="m20 20-4.2-4.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
        <input id="busca" type="search" placeholder="Buscar prontuário nos cartões, ex.: REC005" value="${esc(estado.busca)}" autocomplete="off">
      </label>
      <button class="chip" type="button" data-servico="*" aria-pressed="${estado.servico === "*"}">Todos</button>
      ${Object.entries(J.servicos).map(([k, n]) => `<button class="chip" type="button" data-servico="${k}" aria-pressed="${estado.servico === k}"><span class="ponto-servico s-${k}"></span>${n}</button>`).join("")}
      <label class="alternar"><input type="checkbox" id="so-faltas" ${estado.soFaltas ? "checked" : ""}><span class="trilho" aria-hidden="true"></span>Só com faltas</label>
    </div>
    <div class="abas-etapa" id="abas-etapa" role="group" aria-label="Etapa mostrada no celular"></div>
    <div class="funil" id="funil"></div>`;
  desenharFunil();
  document.getElementById("busca").addEventListener("input", (e) => { estado.busca = e.target.value.trim().toUpperCase(); desenharFunil(); });
  document.querySelectorAll("[data-servico]").forEach((b) => b.addEventListener("click", () => {
    estado.servico = b.dataset.servico;
    document.querySelectorAll("[data-servico]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    desenharFunil();
  }));
  document.getElementById("so-faltas").addEventListener("change", (e) => { estado.soFaltas = e.target.checked; desenharFunil(); });
  document.getElementById("copiar-sem").addEventListener("click", (e) => copiarColuna("sem_retorno", e.currentTarget));
}

function desenharFunil() {
  const funil = document.getElementById("funil");
  const abas = document.getElementById("abas-etapa");
  abas.innerHTML = J.etapas.map((et) => `<button type="button" data-etapa="${et.chave}" aria-pressed="${estado.etapaCelular === et.chave}">${esc(et.nome)} ${NUM(J.colunas[`${estado.servico}|${et.chave}`].total)}</button>`).join("");
  abas.querySelectorAll("[data-etapa]").forEach((b) => b.addEventListener("click", () => { estado.etapaCelular = b.dataset.etapa; desenharFunil(); }));
  const marcada = abas.querySelector('[aria-pressed="true"]');
  if (marcada) abas.scrollLeft = marcada.offsetLeft - 16;
  funil.innerHTML = J.etapas.map((et, i) => {
    const col = J.colunas[`${estado.servico}|${et.chave}`];
    let cartoes = col.cartoes.map((p) => J.detalhes[p]);
    if (estado.busca) cartoes = cartoes.filter((d) => d.prontuario.includes(estado.busca));
    if (estado.soFaltas) cartoes = cartoes.filter((d) => d.faltas > 0);
    const resto = col.total - col.cartoes.length;
    const copiavel = col.todos.length > 0;
    return `<section class="coluna${estado.etapaCelular === et.chave ? " no-celular" : ""}" aria-label="${esc(et.nome)}">
      <div class="coluna-topo">
        <span class="etapa-n">${i + 1}</span>
        <div><p class="coluna-nome">${esc(et.nome)}</p><p class="coluna-meta">${NUM(col.total)} · ${col.mediana == null ? MEDIANA[et.chave]() : MEDIANA[et.chave](col.mediana)}</p></div>
        ${copiavel ? `<button class="copiar" type="button" data-copiar="${et.chave}" title="Copiar os ${NUM(col.total)} prontuários">Copiar</button>` : ""}
      </div>
      ${cartoes.length ? cartoes.map((d) => cartao(d, et.chave)).join("") : `<p class="vazio">${col.total ? "Nenhum dos cartões mais urgentes com esse filtro." : "Nenhum paciente nesta etapa."}</p>`}
      ${resto > 0 ? `<p class="coluna-pe">+ ${NUM(resto)} pacientes, em ordem de urgência</p>` : ""}
    </section>`;
  }).join("");
  funil.querySelectorAll("[data-copiar]").forEach((b) => b.addEventListener("click", () => copiarColuna(b.dataset.copiar, b)));
}

function cartao(d, etapa) {
  const [valor, sub] = VALOR[etapa](d);
  const aluno = d.aluno ? `<span class="avatar" style="background:${tom(d.aluno.nome)}" title="${esc(d.aluno.nome)}">${iniciais(d.aluno.nome)}</span><span>${d.ultimo ? `último ${CURTA(d.ultimo)}` : "sem agendamento"}</span>`
    : `<span>entrou ${CURTA(d.inscricao)}</span>`;
  return `<a class="cartao" href="#/paciente/${d.prontuario}">
    <p class="cartao-topo"><span class="ponto-servico s-${d.servico}"></span>${esc(J.servicos[d.servico])}<span class="unidade">${esc(d.unidade)}</span></p>
    <p class="cartao-titulo">${d.prontuario}</p>
    <p class="cartao-valor"><strong>${valor}</strong><span>${sub}</span></p>
    <p class="cartao-pe">${aluno}${d.faltas ? `<span class="selo selo-falta">${d.faltas} ${d.faltas === 1 ? "falta" : "faltas"}</span>` : ""}</p>
  </a>`;
}

async function copiarColuna(etapa, botao) {
  const col = J.colunas[`${estado.servico}|${etapa}`];
  const texto = col.todos.join("\n");
  const original = botao.innerHTML;
  try {
    await navigator.clipboard.writeText(texto);
    botao.textContent = `${NUM(col.todos.length)} copiados`;
  } catch (e) {
    botao.textContent = "Não foi possível copiar";
  }
  setTimeout(() => { botao.innerHTML = original; }, 1800);
}

// ------------------------------------------------------------------ tela: paciente
function telaPaciente(p) {
  const d = J.detalhes[p];
  if (!d) {
    tela.innerHTML = `<div class="detalhe-titulo"><a class="voltar" href="#/jornada" aria-label="Voltar">‹</a><h1>${esc(p)}</h1></div>
      <div class="painel"><p class="vazio">Este prontuário não está entre os cartões carregados. O painel traz os 12 mais urgentes de cada etapa; a base completa está em data/tratado.</p></div>`;
    return;
  }
  const etapaNome = J.etapas.find((e) => e.chave === d.etapa).nome;
  const taxa = d.realizados + d.faltas ? d.faltas / (d.realizados + d.faltas) : null;
  const passos = [
    { nome: "Inscrição na fila", data: DATA(d.inscricao), feito: true },
    { nome: "1ª consulta", data: d.primeira ? DATA(d.primeira) : "ainda não", feito: !!d.primeira },
    { nome: "Em tratamento", data: d.realizados ? `${d.realizados} ${d.realizados === 1 ? "sessão" : "sessões"}` : "nenhuma sessão", feito: d.realizados > 0 },
    { nome: "Último agendamento", data: d.ultimo ? DATA(d.ultimo) : "—", feito: !!d.ultimo },
    { nome: etapaNome, data: `em ${DATA(J.referencia)}`, atual: true },
  ];
  const nota = {
    fila: `Esperando há <strong>${DIAS(d.dias_na_fila)}</strong> desde a inscrição.`,
    chamado: `Chamado, ainda sem atendimento realizado · <strong>${d.faltas}</strong> ${d.faltas === 1 ? "falta" : "faltas"}.`,
    tratamento: `Em tratamento · <strong>${d.faltas}</strong> ${d.faltas === 1 ? "falta" : "faltas"} em ${d.agendamentos} agendamentos.`,
    sem_retorno: `Sem vir há <strong>${DIAS(d.dias_sem_vir)}</strong> · ligar antes que vire abandono.`,
    encerrado: `Último agendamento há <strong>${DIAS(d.dias_sem_vir)}</strong> · alta ou abandono (a base não diz qual).`,
    desistiu: `Desistiu da fila · inscrito há <strong>${DIAS(d.dias_na_fila)}</strong>.`,
  }[d.etapa];
  const alerta = ["sem_retorno", "chamado"].includes(d.etapa);
  const pillEtapa = alerta ? "p-alerta" : d.etapa === "tratamento" ? "p-pos" : "p-neutra";
  tela.innerHTML = `
    <div class="detalhe-titulo">
      <a class="voltar" href="#/jornada" aria-label="Voltar para a jornada">‹</a>
      <div>
        <h1>${d.prontuario}</h1>
        <p class="detalhe-linha"><span class="servico-rotulo"><span class="ponto-servico s-${d.servico}"></span>${esc(J.servicos[d.servico])} · ${esc(J.unidades[d.unidade])}</span>
          <span class="pilula ${pillEtapa}">${esc(etapaNome)}</span>
          ${d.recuperado ? '<span class="pilula p-acento">Prontuário recuperado pelo nome</span>' : ""}</p>
      </div>
    </div>
    <section class="painel">
      <div class="linha-tempo">${passos.map((s) => `
        <div class="passo-tempo ${s.atual ? "atual" + (alerta ? " alerta" : "") : s.feito ? "" : "futuro"}">
          <span class="marco" aria-hidden="true">${s.feito && !s.atual ? '<svg viewBox="0 0 24 24" width="14" height="14"><path d="m5 12 5 5 9-10" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>' : ""}</span>
          <p class="passo-nome">${esc(s.nome)}</p><p class="passo-data">${esc(s.data)}</p>
        </div>`).join("")}</div>
      <p class="tempo-nota"><span class="ponto" aria-hidden="true" style="background:${alerta ? "var(--pill-warn-ink)" : "var(--positive)"}"></span>${nota}</p>
    </section>
    <div class="detalhe-grade">
      <section class="painel">
        <h2>Ficha</h2>
        <p class="painel-sub">Só o que a base tratada guarda: sem nome nem data de nascimento (LGPD).</p>
        <dl class="ficha">
          <div><dt>Prontuário</dt><dd class="num">${d.prontuario}</dd></div>
          <div><dt>Clínica</dt><dd>${esc(J.servicos[d.servico])}</dd></div>
          <div><dt>Unidade</dt><dd>${esc(J.unidades[d.unidade])}</dd></div>
          <div><dt>Faixa etária</dt><dd>${esc(d.faixa_etaria ?? "—")}</dd></div>
          <div><dt>Sexo</dt><dd>${d.sexo === "F" ? "Feminino" : d.sexo === "M" ? "Masculino" : "—"}</dd></div>
          <div><dt>De onde vem o registro</dt><dd>${d.origem ? (d.origem === "Planilha" ? "Planilha da clínica" : "Sistema") : "—"}</dd></div>
          <div><dt>Aluno responsável</dt><dd>${d.aluno ? esc(d.aluno.nome) : "—"}</dd></div>
          <div><dt>Supervisor</dt><dd>${esc(d.supervisor ?? "—")}</dd></div>
          <div><dt>Esperou até a 1ª consulta</dt><dd>${DIAS(d.dias_espera)}</dd></div>
        </dl>
      </section>
      <aside class="painel">
        <h2>Faltas deste paciente</h2>
        <p class="painel-sub">Faltas / (realizados + faltas), como no painel da rede</p>
        <p class="lateral-valor">${taxa == null ? "—" : PCT(taxa, 0)}</p>
        <dl class="lista-chave">
          <div><dt>Agendamentos</dt><dd>${NUM(d.agendamentos)}</dd></div>
          <div><dt>Realizados</dt><dd>${NUM(d.realizados)}</dd></div>
          <div><dt>Faltas</dt><dd>${NUM(d.faltas)}</dd></div>
          <div><dt>Cancelados</dt><dd>${NUM(d.cancelados)}</dd></div>
          <div><dt>Horas de prática geradas</dt><dd>${NUM(d.horas, 1)} h</dd></div>
        </dl>
      </aside>
    </div>
    <section class="painel" style="margin-top:var(--gap)">
      <h2>Agendamentos</h2>
      <p class="painel-sub">${d.agenda.length ? `${d.agenda.length} no período, do mais antigo ao mais recente` : "Nenhum agendamento no período"}</p>
      ${d.agenda.length ? `<div class="tabela-rolagem"><table>
        <thead><tr><th>Data</th><th>Hora</th><th>Tipo</th><th>Situação</th></tr></thead>
        <tbody>${d.agenda.map((a) => `<tr><td class="num">${DATA(a.data)}</td><td class="num">${a.hora}</td><td>${esc(a.tipo)}</td><td>${pilulaSituacao(a.situacao)}</td></tr>`).join("")}</tbody>
      </table></div>` : ""}
    </section>`;
}
function pilulaSituacao(s) {
  const c = s === "Realizado" ? "p-pos" : s === "Falta" ? "p-neg" : "p-neutra";
  return `<span class="pilula ${c}">${esc(s)}</span>`;
}

// ------------------------------------------------------------------ tela: clínicas
function telaClinicas() {
  const lista = [...P.por_clinica].sort((a, b) => b.taxa_faltas - a.taxa_faltas);
  const situacao = (c) => c.ocupacao < 0.6 && c.fila_aguardando_fim > 100 ? ["Agenda ociosa", "p-neg"]
    : c.fila_aguardando_fim >= 10 ? ["Fila acumulando", "p-alerta"] : c.taxa_faltas >= 0.22 ? ["Faltas altas", "p-alerta"] : ["Em dia", "p-pos"];
  tela.innerHTML = `
    <div class="titulo"><div><h1>Clínicas</h1>
      <p class="titulo-sub">As 10 clínicas de nov/2025 a out/2026. <strong>Fisioterapia · Olinda</strong> tem a agenda mais vazia e a fila mais longa.</p></div></div>
    <section class="painel"><div class="tabela-rolagem"><table>
      <thead><tr><th>Clínica</th><th class="num">Agendamentos</th><th class="num">Taxa de faltas</th><th class="num">Agenda ocupada</th><th class="num">Espera mediana</th><th class="num">Na fila em 31/10</th><th>Situação</th></tr></thead>
      <tbody>${lista.map((c) => { const [s, k] = situacao(c); return `<tr>
        <td><span class="servico-rotulo"><span class="ponto-servico s-${c.servico}"></span>${esc(c.clinica)}</span></td>
        <td class="num">${NUM(c.agendamentos)}</td><td class="num">${PCT(c.taxa_faltas)}</td><td class="num">${PCT(c.ocupacao)}</td>
        <td class="num">${DIAS(c.espera_mediana_dias)}</td><td class="num">${NUM(c.fila_aguardando_fim)}</td><td><span class="pilula ${k}">${s}</span></td></tr>`; }).join("")}</tbody>
    </table></div></section>`;
}

// ------------------------------------------------------------------ tela: qualidade
function telaQualidade() {
  const regras = P.qualidade.regras;
  tela.innerHTML = `
    <div class="titulo"><div><h1>Qualidade dos dados</h1>
      <p class="titulo-sub">O que a padronização encontrou nas planilhas, no sistema e na fila. <strong>${NUM(P.qualidade.linhas_para_conferir)} linhas</strong> vão para conferência com arquivo, aba e linha.</p></div>
      <a class="botao" href="https://github.com/DiegoSantiago1/clinicas-escola-indicadores/blob/main/data/tratado/inconsistencias.csv">Ver as linhas para conferir</a></div>
    <section class="painel"><div class="tabela-rolagem"><table>
      <thead><tr><th>Regra</th><th>O que foi encontrado</th><th>O que foi feito</th><th class="num">Vezes</th></tr></thead>
      <tbody>${regras.map((r) => `<tr><td class="num">${esc(r.regra)}</td><td>${esc(r.descricao)}</td><td>${esc(r.acao)}</td><td class="num">${NUM(r.ocorrencias)}</td></tr>`).join("")}</tbody>
    </table></div></section>`;
}

// ------------------------------------------------------------------ rotas
function rota() {
  if (!J || !P) return;
  const [, nome, arg] = (location.hash || "#/jornada").split("/");
  const telaAtiva = nome === "paciente" ? "jornada" : (nome || "jornada");
  document.querySelectorAll(".nav a[data-tela]").forEach((a) => a.classList.toggle("ativo", a.dataset.tela === telaAtiva));
  const nomes = { jornada: "Jornada", clinicas: "Clínicas", qualidade: "Qualidade" };
  document.getElementById("trilha-atual").textContent = nome === "paciente" ? `Jornada › ${decodeURIComponent(arg || "")}` : nomes[telaAtiva] ?? "Jornada";
  if (nome === "paciente") telaPaciente(decodeURIComponent(arg || ""));
  else if (nome === "clinicas") telaClinicas();
  else if (nome === "qualidade") telaQualidade();
  else telaJornada();
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", rota);

document.getElementById("tema").addEventListener("click", () => {
  const r = document.documentElement;
  r.dataset.theme = r.dataset.theme === "light" ? "dark" : "light";
  try { localStorage.setItem("tema-painel", r.dataset.theme); } catch (e) { /* navegação privada */ }
});

tela.innerHTML = '<p class="vazio" style="margin-top:32px">Carregando a jornada dos pacientes…</p>';
Promise.all([fetch("dados/jornada.json").then((r) => r.json()), fetch("../dados/painel.json").then((r) => r.json())])
  .then(([j, p]) => {
    J = j; P = p;
    console.assert(Object.values(j.totais).reduce((a, b) => a + b, 0) === j.pacientes, "as etapas somam os pacientes");
    document.getElementById("nav-sem-retorno").textContent = NUM(j.totais.sem_retorno);
    document.getElementById("nav-conferir").textContent = NUM(p.qualidade.linhas_para_conferir);
    document.getElementById("estado").textContent = `Base de ${DATA(j.referencia)} · ${NUM(j.pacientes)} pacientes`;
    rota();
  })
  .catch(() => { tela.innerHTML = '<p class="vazio" style="margin-top:32px">Não foi possível carregar os dados. Tente recarregar a página.</p>'; });
