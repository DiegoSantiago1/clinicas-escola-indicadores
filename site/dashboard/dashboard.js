/* Painel animado da Rede Acolher.
   Lê dados/dashboard.json (gerado por python -m clinicas.dashboard) e não faz conta nenhuma
   além de formatar: cada número vem pronto, por unidade. */
(() => {
  "use strict";

  const raiz = document.documentElement;
  const reduz = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  // ---------- formatos ----------
  const nInt = new Intl.NumberFormat("pt-BR");
  const nMoeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
  const nMoeda2 = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: 2 });
  const FMT = {
    int: (v) => nInt.format(Math.round(v)),
    moeda: (v) => nMoeda.format(Math.round(v)),
    moeda2: (v) => nMoeda2.format(v),
    pct: (v) => (v * 100).toFixed(1).replace(".", ",") + "%",
    pct0: (v) => Math.round(v * 100) + "%",
    min: (v) => Math.round(v) + " min",
    dias: (v) => (Math.round(v) === 1 ? "1 dia" : Math.round(v) + " dias"),
  };
  const hora = (h) => h.replace(":00", "h").replace(":", "h");

  // ---------- sons (Web Audio, sintetizados; nada toca antes do primeiro gesto) ----------
  const Som = (() => {
    let ctx = null;
    let gesto = false;
    let ligado = true;
    let ultimoTique = 0;
    try { ligado = localStorage.getItem("som-dashboard") !== "off"; } catch (e) { /* sem armazenamento */ }
    const marcarGesto = () => { gesto = true; };
    addEventListener("pointerdown", marcarGesto, { capture: true, once: true });
    addEventListener("keydown", marcarGesto, { capture: true, once: true });

    function contexto() {
      if (!gesto || !ligado) return null;
      if (!ctx) {
        const C = window.AudioContext || window.webkitAudioContext;
        if (!C) return null;
        ctx = new C();
      }
      if (ctx.state === "suspended") ctx.resume();
      return ctx;
    }
    function tom(freq, dur, { tipo = "sine", vol = 0.05, ate = null, atraso = 0 } = {}) {
      const c = contexto();
      if (!c) return;
      const t = c.currentTime + atraso;
      const o = c.createOscillator();
      const g = c.createGain();
      o.type = tipo;
      o.frequency.setValueAtTime(freq, t);
      if (ate) o.frequency.exponentialRampToValueAtTime(ate, t + dur);
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(vol, t + 0.012);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g).connect(c.destination);
      o.start(t);
      o.stop(t + dur + 0.03);
    }
    function sopro(dur, vol) {
      const c = contexto();
      if (!c) return;
      const t = c.currentTime;
      const buf = c.createBuffer(1, Math.ceil(c.sampleRate * dur), c.sampleRate);
      const d = buf.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
      const src = c.createBufferSource();
      src.buffer = buf;
      const f = c.createBiquadFilter();
      f.type = "bandpass";
      f.Q.value = 0.8;
      f.frequency.setValueAtTime(400, t);
      f.frequency.exponentialRampToValueAtTime(2400, t + dur);
      const g = c.createGain();
      g.gain.setValueAtTime(vol, t);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      src.connect(f).connect(g).connect(c.destination);
      src.start(t);
    }
    return {
      clique: () => tom(880, 0.06, { tipo: "triangle", vol: 0.045, ate: 620 }),
      aba: () => { sopro(0.22, 0.05); tom(520, 0.14, { vol: 0.025, ate: 780 }); },
      tique: () => {
        const agora = performance.now();
        if (agora - ultimoTique < 85) return;
        ultimoTique = agora;
        tom(1700, 0.02, { tipo: "square", vol: 0.006 });
      },
      pronto: () => { tom(660, 0.14, { vol: 0.035 }); tom(990, 0.24, { vol: 0.03, atraso: 0.09 }); },
      abre: () => { tom(523, 0.12, { vol: 0.04 }); tom(784, 0.2, { vol: 0.035, atraso: 0.08 }); },
      fecha: () => tom(700, 0.12, { vol: 0.03, ate: 420 }),
      pop: () => tom(420, 0.1, { vol: 0.05, ate: 900 }),
      tema: () => { sopro(0.4, 0.035); tom(320, 0.35, { vol: 0.03, ate: 140 }); },
      get ligado() { return ligado; },
      set ligado(v) {
        ligado = v;
        try { localStorage.setItem("som-dashboard", v ? "on" : "off"); } catch (e) { /* sem armazenamento */ }
      },
    };
  })();

  // ---------- contagem dos números ----------
  let tiqueNaContagem = false;
  function contar(el, para, fmt = "int", dur = 1150) {
    if (!el) return;
    const f = FMT[fmt];
    const de = Number(el.dataset.v || 0);
    el.dataset.v = para;
    if (reduz || de === para) { el.textContent = f(para); return; }
    const t0 = performance.now();
    const passo = (t) => {
      const p = Math.min(1, (t - t0) / dur);
      const e = p === 1 ? 1 : 1 - Math.pow(2, -10 * p);
      el.textContent = f(de + (para - de) * e);
      if (p < 1) {
        if (tiqueNaContagem) Som.tique();
        requestAnimationFrame(passo);
      }
    };
    requestAnimationFrame(passo);
  }
  const contarChave = (chave, valor) => {
    const el = $(`[data-contar="${chave}"]`);
    if (el) contar(el, valor, el.dataset.fmt || "int");
  };

  // ---------- cores (lidas do CSS, para o tema valer nos gráficos) ----------
  function cores() {
    const s = getComputedStyle(raiz);
    const v = (n) => s.getPropertyValue(n).trim();
    return { quente: v("--quente"), suave: v("--quente-suave"), neutro: v("--neutro"), claro: v("--neutro-claro"),
      tinta: v("--tinta"), tinta2: v("--tinta-2"), tinta3: v("--tinta-3"), cartao: v("--cartao"), c2: v("--cartao-2") };
  }
  function alfa(hex, a) {
    const n = parseInt(hex.replace("#", ""), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }
  function listras(cor) {
    const c = document.createElement("canvas");
    c.width = c.height = 8;
    const g = c.getContext("2d");
    g.strokeStyle = cor;
    g.lineWidth = 2;
    g.beginPath();
    g.moveTo(-2, 10); g.lineTo(10, -2); g.moveTo(6, 10); g.lineTo(10, 6); g.moveTo(-2, 2); g.lineTo(2, -2);
    g.stroke();
    return g.createPattern(c, "repeat");
  }

  // ---------- gráficos (Chart.js) ----------
  const graficos = {};
  let animarGraficos = true;
  function baseOpcoes(c, extra = {}) {
    return {
      responsive: true, maintainAspectRatio: false,
      animation: animarGraficos && !reduz ? { duration: 1100, easing: "easeOutQuart" } : false,
      plugins: { legend: { display: false }, tooltip: { backgroundColor: c.tinta, titleColor: c.cartao, bodyColor: c.cartao,
        padding: 10, cornerRadius: 10, displayColors: false } },
      scales: {
        x: { grid: { display: false }, border: { display: false }, ticks: { color: c.tinta2, font: { size: 12 } } },
        y: { grid: { color: c.c2 }, border: { display: false }, ticks: { color: c.tinta2, font: { size: 12 }, maxTicksLimit: 5 },
          beginAtZero: true },
      },
      ...extra,
    };
  }
  function grafico(id, montarConfig) {
    const canvas = document.getElementById(id);
    if (!canvas || typeof Chart === "undefined") return;
    const cfg = montarConfig(cores());
    const atual = graficos[id];
    if (atual) {
      atual.data.labels = cfg.data.labels;
      cfg.data.datasets.forEach((d, i) => {
        if (atual.data.datasets[i]) Object.assign(atual.data.datasets[i], d);
        else atual.data.datasets.push(d);
      });
      atual.data.datasets.length = cfg.data.datasets.length;
      atual.update();
      return;
    }
    graficos[id] = new Chart(canvas, cfg);
  }
  function destruirGraficos(tela) {
    $$("canvas", tela).forEach((cv) => {
      if (graficos[cv.id]) { graficos[cv.id].destroy(); delete graficos[cv.id]; }
    });
  }

  // ---------- sparklines (SVG que se desenha) ----------
  function spark(svg, valores) {
    if (!svg) return;
    const r = svg.getBoundingClientRect();
    const W = Math.max(40, Math.round(r.width)), H = Math.max(24, Math.round(r.height));
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const pontos = valores.map((v, i) => [i, v]).filter(([, v]) => v !== null && v !== undefined);
    const vals = pontos.map(([, v]) => v);
    const min = Math.min(...vals), max = Math.max(...vals);
    const x = (i) => 4 + (i / (valores.length - 1)) * (W - 8);
    const y = (v) => H - 5 - ((v - min) / (max - min || 1)) * (H - 12);
    const d = pontos.map(([i, v], k) => `${k ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const [ui, uv] = pontos[pontos.length - 1];
    svg.innerHTML = `<path class="area" d="${d} L${x(ui)},${H} L${x(pontos[0][0])},${H} Z"/>` +
      `<path class="linha" d="${d}"/><circle cx="${x(ui)}" cy="${y(uv)}" r="3.5"/>`;
    const linha = $(".linha", svg);
    const area = $(".area", svg);
    if (reduz) return;
    const L = linha.getTotalLength();
    linha.style.strokeDasharray = L;
    linha.style.strokeDashoffset = L;
    area.style.opacity = 0;
    linha.getBoundingClientRect();
    linha.style.transition = "stroke-dashoffset 1300ms cubic-bezier(.22,1,.36,1)";
    area.style.transition = "opacity 900ms ease 400ms";
    requestAnimationFrame(() => { linha.style.strokeDashoffset = 0; area.style.opacity = 1; });
  }

  // ---------- barras horizontais ----------
  function barras(cont, itens, fmt, grande = false) {
    if (!cont) return;
    const max = Math.max(...itens.map((i) => i.valor)) || 1;
    const chave = itens.map((i) => i.rotulo).join("|");
    if (cont.dataset.chave !== chave) {
      cont.dataset.chave = chave;
      cont.innerHTML = itens.map((it, k) => grande ? `
        <div class="barra grande ${it.classe || ""}" style="--d:${k * 80}ms">
          <span class="barra-rotulo">${it.rotulo}</span>
          <span class="barra-valor" data-v="0">–</span>
          <span class="barra-trilha"><span class="barra-cheia"></span></span>
          <small class="barra-sub">${it.sub || ""}</small>
        </div>` : `
        <div class="barra ${it.classe || ""}" style="--d:${k * 60}ms">
          <span class="barra-rotulo">${it.rotulo}${it.sub ? `<small>${it.sub}</small>` : ""}</span>
          <span class="barra-trilha"><span class="barra-cheia"></span></span>
          <span class="barra-valor" data-v="0">–</span>
        </div>`).join("");
    }
    const linhas = $$(".barra", cont);
    requestAnimationFrame(() => {
      itens.forEach((it, k) => {
        const l = linhas[k];
        l.className = `barra ${grande ? "grande " : ""}${it.classe || ""}`;
        const sub = $(".barra-rotulo small, .barra-sub", l);
        if (sub && it.sub) sub.textContent = it.sub;
        $(".barra-cheia", l).style.width = `${(it.valor / max) * 100}%`;
        contar($(".barra-valor", l), it.valor, it.fmt || fmt);
      });
    });
  }

  // ---------- medidor (meia-lua) ----------
  function medidor(cont, fracao, rotulo) {
    if (!cont) return;
    const L = Math.PI * 90;
    if (!$("svg", cont)) {
      const marcas = Array.from({ length: 11 }, (_, k) => {
        const a = Math.PI * (1 - k / 10);
        const x1 = 110 + Math.cos(a) * 66, y1 = 110 - Math.sin(a) * 66;
        const x2 = 110 + Math.cos(a) * 72, y2 = 110 - Math.sin(a) * 72;
        return `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}"/>`;
      }).join("");
      cont.innerHTML = `<svg viewBox="0 0 220 120" aria-hidden="true">
          <path class="fundo" d="M20 110 A90 90 0 0 1 200 110"/>
          <path class="cheio" d="M20 110 A90 90 0 0 1 200 110" style="stroke-dasharray:${L};stroke-dashoffset:${L}"/>
          <g class="marcas">${marcas}</g></svg>
        <p class="medidor-valor"><strong data-v="0">0%</strong><span>${rotulo}</span></p>`;
    }
    $(".medidor-valor span", cont).textContent = rotulo;
    const cheio = $(".cheio", cont);
    cheio.getBoundingClientRect();
    requestAnimationFrame(() => { cheio.style.strokeDashoffset = L * (1 - fracao); });
    contar($(".medidor-valor strong", cont), fracao, "pct0");
  }

  // ---------- estado ----------
  const estado = { dados: null, u: "*", aba: "geral" };
  const bloco = () => estado.dados.blocos[estado.u];
  const NOTA_FILTRO = { "*": "Rede toda: 10 clínicas em 3 cidades", REC: "Recife: Odontologia, Fisioterapia, Psicologia e Nutrição",
    OLI: "Olinda: Odontologia, Fisioterapia e Psicologia", JAB: "Jaboatão: Odontologia, Psicologia e Nutrição" };

  // ---------- telas ----------
  const telas = {
    geral() {
      const b = bloco(), k = b.kpis, f = b.faturamento, s = b.serie;
      contarChave("fat-total", f.total);
      contarChave("fat-perdido", f.perdido_faltas);
      contarChave("fat-ticket", f.ticket_medio);
      contarChave("k-realizados", k.realizados);
      contarChave("k-faltas", k.faltas);
      contarChave("k-taxa", k.taxa_faltas);
      contarChave("k-cancel", k.cancelados_paciente + k.cancelados_clinica);
      contarChave("k-espera", k.espera_recepcao_min);
      $("#n-realizadas").textContent = `de ${FMT.int(k.agendamentos)} consultas marcadas`;
      $("#n-cancel").textContent = `${FMT.int(k.cancelados_paciente)} pelo paciente · ${FMT.int(k.cancelados_clinica)} pela clínica`;
      spark($("#spark-fat"), s.map((m) => m.faturamento));
      spark($("#spark-real"), s.map((m) => m.realizados));
      spark($("#spark-faltas"), s.map((m) => m.faltas));
      spark($("#spark-cancel"), s.map((m) => m.cancelados_paciente + m.cancelados_clinica));
      spark($("#spark-espera"), s.map((m) => m.espera_min));

      grafico("g-presenca", (c) => ({
        type: "bar",
        data: { labels: s.map((m) => m.mes), datasets: [
          { label: "Realizadas", data: s.map((m) => m.realizados), backgroundColor: c.neutro, borderRadius: 6, stack: "a", maxBarThickness: 38 },
          { label: "Faltas", data: s.map((m) => m.faltas), backgroundColor: c.quente, borderRadius: 6, stack: "a", maxBarThickness: 38 },
          { label: "Desmarcadas", data: s.map((m) => m.cancelados_paciente + m.cancelados_clinica), backgroundColor: listras(c.tinta3),
            borderRadius: 6, stack: "a", maxBarThickness: 38 },
        ] },
        options: baseOpcoes(c, { interaction: { mode: "index", intersect: false },
          scales: { x: { stacked: true, grid: { display: false }, border: { display: false }, ticks: { color: c.tinta2 } },
            y: { stacked: true, grid: { color: c.c2 }, border: { display: false }, ticks: { color: c.tinta2, maxTicksLimit: 5 } } } }),
      }));

      const un = [...b.unidades].sort((x, y) => y.realizados - x.realizados);
      barras($("#b-unidades"), un.map((u, i) => ({ rotulo: u.unidade, valor: u.realizados, classe: i === 0 && un.length > 1 ? "quente" : "",
        sub: `consultas realizadas · ${FMT.moeda(u.faturamento)} faturados · ${FMT.pct(u.taxa_faltas)} de faltas` })), "int", true);
      $("#n-unidades").textContent = un.length > 1
        ? `${un[un.length - 1].unidade} atende menos: ${FMT.int(un[un.length - 1].realizados)} consultas realizadas.`
        : "Escolha “Todas” para comparar as três unidades.";

      const tons = [1, 0.7, 0.45, 0.25];
      const ar = b.areas;
      contarChave("areas-total", ar.reduce((t, a) => t + a.procura, 0));
      grafico("g-areas", (c) => ({
        type: "doughnut",
        data: { labels: ar.map((a) => a.servico), datasets: [{ data: ar.map((a) => a.procura),
          backgroundColor: ar.map((_, i) => alfa(c.quente, tons[i])), borderColor: c.cartao, borderWidth: 3, borderRadius: 6 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: "70%",
          animation: animarGraficos && !reduz ? { animateRotate: true, duration: 1200, easing: "easeOutQuart" } : false,
          plugins: { legend: { display: false }, tooltip: { backgroundColor: c.tinta, bodyColor: c.cartao, displayColors: false } } },
      }));
      const c0 = cores();
      const maxA = Math.max(...ar.map((a) => a.procura));
      $("#l-areas").innerHTML = ar.map((a, i) => `<li><i class="sw" style="background:${alfa(c0.quente, tons[i])}"></i>
        <span>${a.servico}</span><strong>${FMT.int(a.procura)}</strong>
        <span class="trilha-mini"><i style="background:${alfa(c0.quente, tons[i])}" data-w="${(a.procura / maxA) * 100}"></i></span></li>`).join("");
      requestAnimationFrame(() => $$("#l-areas .trilha-mini i").forEach((el) => { el.style.width = el.dataset.w + "%"; }));

      const pr = f.por_procedimento;
      barras($("#b-procedimentos"), pr.map((p, i) => ({ rotulo: p.procedimento, valor: p.valor, classe: i === 0 ? "quente" : "" })), "moeda");
      $("#n-procedimentos").textContent = `${FMT.int(f.sem_prontuario)} atendimentos sem prontuário ficaram de fora: não dá para saber se o paciente é isento.`;
    },

    agenda() {
      const b = bloco(), h = b.horarios;
      const maisMarcado = h.reduce((x, y) => (y.agendamentos > x.agendamentos ? y : x));
      const pior = h.reduce((x, y) => (y.taxa_faltas > x.taxa_faltas ? y : x));
      const melhor = h.reduce((x, y) => (y.taxa_faltas < x.taxa_faltas ? y : x));
      grafico("g-horarios", (c) => ({
        type: "bar",
        data: { labels: h.map((x) => hora(x.hora)), datasets: [{ data: h.map((x) => x.agendamentos), borderRadius: 8, maxBarThickness: 34,
          backgroundColor: h.map((x) => (x === maisMarcado ? c.quente : c.neutro)) }] },
        options: baseOpcoes(c),
      }));
      $("#n-horarios").textContent = `${hora(maisMarcado.hora)} lidera: é o primeiro horário de todas as clínicas. A Odontologia só atende às 8h, 10h, 13h30 e 15h30.`;
      grafico("g-horarios-faltas", (c) => ({
        type: "bar",
        data: { labels: h.map((x) => hora(x.hora)), datasets: [{ data: h.map((x) => x.taxa_faltas * 100), borderRadius: 8, maxBarThickness: 34,
          backgroundColor: h.map((x) => (x === pior ? c.quente : x === melhor ? c.claro : c.neutro)) }] },
        options: baseOpcoes(c, { plugins: { legend: { display: false }, tooltip: { backgroundColor: c.tinta, bodyColor: c.cartao, titleColor: c.cartao,
          displayColors: false, callbacks: { label: (ctx) => ctx.parsed.y.toFixed(1).replace(".", ",") + "% de faltas" } } } }),
      }));
      $("#n-horarios-faltas").textContent = `Mais faltas: ${hora(pior.hora)} (${FMT.pct(pior.taxa_faltas)}). Menos: ${hora(melhor.hora)} (${FMT.pct(melhor.taxa_faltas)}).`;

      const dt = b.dia_turno;
      const taxas = dt.map((x) => x.taxa_faltas);
      const mn = Math.min(...taxas), mx = Math.max(...taxas);
      const dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"];
      const calor = $("#calor");
      let html = `<span></span>${dias.map((d) => `<span class="cab">${d.slice(0, 3)}</span>`).join("")}`;
      ["Manhã", "Tarde"].forEach((t, ti) => {
        html += `<span class="rot">${t}</span>`;
        dias.forEach((d, di) => {
          const x = dt.find((y) => y.dia === d && y.turno === t);
          const forca = mx > mn ? (x.taxa_faltas - mn) / (mx - mn) : 0;
          html += `<span class="celula${forca > 0.6 ? " forte" : ""}" style="--d:${(ti * 5 + di) * 50}ms" data-o="${(0.12 + forca * 0.88).toFixed(2)}"
            title="${d} de ${t.toLowerCase()}: ${FMT.pct(x.taxa_faltas)} de faltas"><span>${FMT.pct0(x.taxa_faltas)}</span></span>`;
        });
      });
      calor.innerHTML = html;
      calor.getBoundingClientRect();
      requestAnimationFrame(() => $$(".celula", calor).forEach((el) => el.style.setProperty("--o", el.dataset.o)));
      const topo = dt.reduce((x, y) => (y.taxa_faltas > x.taxa_faltas ? y : x));
      $("#n-calor").textContent = `O turno com mais faltas é ${topo.dia.toLowerCase()} de ${topo.turno.toLowerCase()} (${FMT.pct(topo.taxa_faltas)}).`;

      const fila = b.fila;
      barras($("#b-fila"), fila.map((x, i) => ({ rotulo: x.clinica, valor: x.espera_mediana_dias, classe: i === 0 ? "quente" : "",
        sub: x.aguardando ? `${FMT.int(x.aguardando)} aguardando agora` : "ninguém aguardando agora", fmt: "dias" })), "dias");
      const ultima = fila[fila.length - 1];
      $("#n-fila").textContent = fila[0].espera_mediana_dias === ultima.espera_mediana_dias
        ? "Todas as filas desta unidade andam no mesmo ritmo."
        : `Mais longa: ${fila[0].clinica}. Mais curta: ${ultima.clinica} (${FMT.dias(ultima.espera_mediana_dias)}).`;

      const prof = b.profissionais;
      const linha = (p, i, topo1) => {
        const partes = p.nome.replace(/^Profa?\. /, "").split(" ");
        const ini = partes[0][0] + partes[partes.length - 1][0];
        return `<div class="prof${topo1 && i === 0 ? " topo1" : ""}"><span class="avatar">${ini}</span>
          <span class="prof-nome">${p.nome}<small>${p.clinica} · ${p.turno_principal.toLowerCase()}</small></span>
          <span class="prof-num"><span data-v="0" class="n-prof">0</span><small>${FMT.pct(p.taxa_faltas)} faltas</small></span></div>`;
      };
      const n = Math.min(7, Math.floor(prof.length / 2));
      const mais = prof.slice(0, n), menos = prof.slice(-n).reverse();
      $("#r-prof").innerHTML = `<div><h3>Mais atendimentos</h3>${mais.map((p, i) => linha(p, i, true)).join("")}</div>
        <div><h3>Menos atendimentos</h3>${menos.map((p, i) => linha(p, i, false)).join("")}</div>`;
      const nums = $$("#r-prof .n-prof");
      [...mais, ...menos].forEach((p, i) => contar(nums[i], p.atendimentos));
    },

    motivos() {
      const m = bloco().motivos;
      barras($("#b-motivos-falta"), m.faltas.map((x) => ({ rotulo: x.motivo, valor: x.qtd, sub: FMT.pct(x.pct) + " das faltas",
        classe: ["Sem justificativa", "Não identificado"].includes(x.motivo) ? "cinza" : (x === m.faltas.find((y) =>
          !["Sem justificativa", "Não identificado"].includes(y.motivo)) ? "quente" : "") })), "int");
      medidor($("#m-justificadas"), m.justificadas_pct, "das faltas tiveram motivo");
      barras($("#b-motivos-desm"), m.desmarcacoes.map((x, i) => ({ rotulo: x.motivo, valor: x.qtd, classe: i === 0 ? "quente" : "" })), "int");
      const ch = m.chuva_por_mes;
      grafico("g-chuva", (c) => ({
        type: "line",
        data: { labels: ch.map((x) => x.mes), datasets: [{ data: ch.map((x) => (x.pct_chuva === null ? null : x.pct_chuva * 100)),
          borderColor: c.quente, backgroundColor: alfa(c.quente, 0.14), fill: true, tension: 0.4, borderWidth: 2.5,
          pointRadius: ch.map((x) => (/^(Abr|Mai|Jun|Jul)/.test(x.mes) ? 4.5 : 2.5)), pointBackgroundColor: c.quente,
          pointBorderColor: c.cartao, pointBorderWidth: 2, spanGaps: false }] },
        options: baseOpcoes(c, { plugins: { legend: { display: false }, tooltip: { backgroundColor: c.tinta, bodyColor: c.cartao, titleColor: c.cartao,
          displayColors: false, callbacks: { label: (ctx) => ctx.parsed.y.toFixed(1).replace(".", ",") + "% por chuva" } } },
          scales: { x: { grid: { display: false }, border: { display: false }, ticks: { color: c.tinta2, maxRotation: 0, autoSkipPadding: 10 } },
            y: { grid: { color: c.c2 }, border: { display: false }, beginAtZero: true,
              ticks: { color: c.tinta2, maxTicksLimit: 4, callback: (v) => v + "%" } } } }),
      }));
      $("#n-chuva").textContent = `De abril a julho, ${FMT.pct(m.chuva_temporada)} das faltas justificadas foram por chuva; no resto do ano, ${FMT.pct(m.chuva_resto)}. Janeiro é recesso.`;
      const tr = [...m.transporte_por_unidade].sort((x, y) => y.pct - x.pct);
      barras($("#b-transporte"), tr.map((x, i) => ({ rotulo: x.unidade, valor: x.pct, classe: i === 0 && tr.length > 1 ? "quente" : "",
        sub: "das faltas justificadas" })), "pct", true);
    },

    espera() {
      const e = bloco().espera;
      contarChave("e-media", e.media_min);
      contarChave("e-segunda", e.segunda_manha_min);
      contarChave("e-demais", e.demais_min);
      $("#n-espera-medidos").textContent = `Medido em ${FMT.int(e.medidos)} atendimentos. ${FMT.int(e.sem_chamada)} ficaram de fora: o aluno chamou sem registrar no tablet.`;
      const ate30 = e.faixas.slice(0, 3).reduce((t, x) => t + x.qtd, 0) / e.medidos;
      medidor($("#m-ate30"), ate30, "dos pacientes atendidos");
      const longos = e.faixas[e.faixas.length - 1].qtd;
      $("#n-ate30").textContent = `${FMT.int(longos)} atendimentos (${FMT.pct(longos / e.medidos)}) esperaram 45 minutos ou mais.`;
      const fx = e.faixas;
      const maxF = fx.reduce((x, y) => (y.qtd > x.qtd ? y : x));
      grafico("g-faixas", (c) => ({
        type: "bar",
        data: { labels: fx.map((x) => x.faixa), datasets: [{ data: fx.map((x) => x.qtd), borderRadius: 8, maxBarThickness: 40,
          backgroundColor: fx.map((x) => (x === maxF ? c.quente : c.neutro)) }] },
        options: baseOpcoes(c),
      }));
      barras($("#b-espera-clinica"), e.por_clinica.map((x, i) => ({ rotulo: x.clinica, valor: x.media_min, classe: i === 0 ? "quente" : "" })), "min");
      const pos = e.por_posicao;
      const tonsLinha = (c) => [c.quente, c.neutro, c.tinta3, c.claro];
      const c1 = cores();
      $("#leg-cascata").innerHTML = pos.map((p, i) => `<li><i class="sw" style="background:${tonsLinha(c1)[i]}"></i>${p.servico}</li>`).join("");
      grafico("g-cascata", (c) => ({
        type: "line",
        data: { labels: ["1º horário", "2º horário", "3º horário", "4º horário"], datasets: pos.map((p, i) => ({
          label: p.servico, data: p.valores, borderColor: tonsLinha(c)[i], backgroundColor: tonsLinha(c)[i], borderWidth: i === 0 ? 3 : 2,
          tension: 0.35, pointRadius: 4, pointBorderColor: c.cartao, pointBorderWidth: 2 })) },
        options: baseOpcoes(c, { interaction: { mode: "index", intersect: false }, scales: {
          x: { grid: { display: false }, border: { display: false }, ticks: { color: c.tinta2 } },
          y: { grid: { color: c.c2 }, border: { display: false }, ticks: { color: c.tinta2, maxTicksLimit: 5, callback: (v) => v + " min" } } },
          plugins: { legend: { display: false }, tooltip: { backgroundColor: c.tinta, bodyColor: c.cartao, titleColor: c.cartao,
            callbacks: { label: (ctx) => `${ctx.dataset.label}: ${Math.round(ctx.parsed.y)} min` } } } }),
      }));
      const odo = pos.find((p) => p.servico === "Odontologia");
      $("#n-cascata").textContent = odo
        ? `Na Odontologia, o paciente do 2º horário espera ${Math.round(odo.valores[1] - odo.valores[0])} min a mais que o do 1º: montar e esterilizar o equipo atrasa a sessão seguinte.`
        : "Nas sessões de 1 hora, cada horário do turno herda um pouco do atraso do anterior.";
    },
  };

  // ---------- entrada em cascata ----------
  function entrar(tela) {
    $$(".cartao", tela).forEach((c, i) => {
      c.classList.remove("entra");
      c.style.setProperty("--i", i);
      void c.offsetWidth;
      c.classList.add("entra");
    });
  }
  function zerar(tela) {
    $$("[data-v]", tela).forEach((el) => { el.dataset.v = 0; });
    $$(".barras", tela).forEach((el) => { el.dataset.chave = ""; el.innerHTML = ""; });
    $$(".medidor", tela).forEach((el) => { el.innerHTML = ""; });
    $$("[data-contar]", tela).forEach((el) => { el.dataset.v = 0; });
  }
  function desenhar(aba, { comSom = false } = {}) {
    tiqueNaContagem = comSom;
    telas[aba]();
    if (comSom) setTimeout(() => { tiqueNaContagem = false; Som.pronto(); }, reduz ? 0 : 1150);
  }

  // ---------- navegação entre telas ----------
  function marcarAba(aba) {
    $$(".abas [role=tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.aba === aba)));
    $$(".trilho-item").forEach((b) => b.setAttribute("aria-current", String(b.dataset.aba === aba)));
  }
  function irPara(aba, { som = true } = {}) {
    if (aba === estado.aba || !telas[aba]) return Promise.resolve();
    if (som) Som.aba();
    marcarAba(aba);
    const velha = $(`.tela[data-tela="${estado.aba}"]`);
    const nova = $(`.tela[data-tela="${aba}"]`);
    try { history.replaceState(null, "", "#" + aba); } catch (e) { /* arquivo local */ }
    return new Promise((ok) => {
      velha.classList.add("sai");
      setTimeout(() => {
        destruirGraficos(velha);
        velha.hidden = true;
        velha.classList.remove("sai");
        estado.aba = aba;
        nova.hidden = false;
        zerar(nova);
        entrar(nova);
        animarGraficos = true;
        desenhar(aba, { comSom: som });
        scrollTo({ top: 0, behavior: reduz ? "auto" : "smooth" });
        ok();
      }, reduz ? 0 : 200);
    });
  }

  // ---------- filtro de unidade ----------
  function montarFiltro() {
    const seg = $("#unidades");
    seg.innerHTML = Object.entries(estado.dados.unidades).map(([u, nome]) =>
      `<button type="button" role="radio" data-u="${u}" aria-checked="${u === estado.u}">${nome}</button>`).join("");
    seg.addEventListener("click", (ev) => {
      const b = ev.target.closest("button");
      if (!b || b.dataset.u === estado.u) return;
      Som.clique();
      estado.u = b.dataset.u;
      $$("button", seg).forEach((x) => x.setAttribute("aria-checked", String(x === b)));
      $("#nota-filtro").textContent = NOTA_FILTRO[estado.u];
      animarGraficos = true;
      desenhar(estado.aba, { comSom: true });
      montarPerguntas();
    });
  }

  // ---------- tema (revelação circular) ----------
  function aplicarTema(novo) {
    raiz.dataset.theme = novo;
    try { localStorage.setItem("tema-dashboard", novo); } catch (e) { /* sem armazenamento */ }
    const tela = $(`.tela[data-tela="${estado.aba}"]`);
    destruirGraficos(tela);
    animarGraficos = false;
    telas[estado.aba]();
    animarGraficos = true;
  }
  $("#tema").addEventListener("click", (ev) => {
    const novo = raiz.dataset.theme === "dark" ? "light" : "dark";
    Som.tema();
    if (!document.startViewTransition || reduz) { aplicarTema(novo); return; }
    const r = ev.currentTarget.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    const raio = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
    const vt = document.startViewTransition(() => aplicarTema(novo));
    vt.ready.then(() => {
      raiz.animate({ clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${raio}px at ${x}px ${y}px)`] },
        { duration: 650, easing: "cubic-bezier(.22,1,.36,1)", pseudoElement: "::view-transition-new(root)" });
    });
  });

  // ---------- som ----------
  const botaoSom = $("#som");
  function marcarSom() {
    botaoSom.setAttribute("aria-pressed", String(Som.ligado));
    botaoSom.setAttribute("aria-label", Som.ligado ? "Som ligado" : "Som desligado");
  }
  botaoSom.addEventListener("click", () => { Som.ligado = !Som.ligado; marcarSom(); Som.clique(); });
  marcarSom();

  // ---------- perguntas ----------
  const ALVO = { faturamento: ["geral", "c-faturamento"], presenca: ["geral", "c-presenca"], unidades: ["geral", "c-unidades"],
    areas: ["geral", "c-areas"], horarios: ["agenda", "c-horarios-faltas"], fila: ["agenda", "c-fila"],
    profissionais: ["agenda", "c-profissionais"], motivos: ["motivos", "c-motivos"], espera: ["espera", "c-espera"] };
  const chat = $("#chat"), bolha = $("#bolha"), msgs = $("#chat-msgs");
  function abrirChat(abrir) {
    chat.hidden = !abrir;
    bolha.setAttribute("aria-expanded", String(abrir));
    $("#perguntar").setAttribute("aria-expanded", String(abrir));
    if (abrir) { Som.abre(); $("#chat-perguntas button")?.focus(); } else Som.fecha();
  }
  bolha.addEventListener("click", () => abrirChat(chat.hidden));
  $("#perguntar").addEventListener("click", () => abrirChat(chat.hidden));
  $("#fechar-chat").addEventListener("click", () => { abrirChat(false); bolha.focus(); });
  addEventListener("keydown", (ev) => { if (ev.key === "Escape" && !chat.hidden) { abrirChat(false); bolha.focus(); } });

  function montarPerguntas() {
    $("#chat-perguntas").innerHTML = bloco().perguntas.map((q, i) => `<button type="button" data-i="${i}">${q.pergunta}</button>`).join("");
  }
  $("#chat-perguntas").addEventListener("click", (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    const q = bloco().perguntas[Number(b.dataset.i)];
    Som.clique();
    const eu = document.createElement("p");
    eu.className = "msg msg-eu";
    eu.textContent = q.pergunta;
    msgs.append(eu);
    const resp = document.createElement("div");
    resp.className = "msg msg-painel";
    resp.innerHTML = '<span class="digitando" aria-label="Calculando"><i></i><i></i><i></i></span>';
    msgs.append(resp);
    msgs.scrollTop = msgs.scrollHeight;
    setTimeout(() => {
      Som.pop();
      resp.innerHTML = "";
      const texto = document.createElement("p");
      resp.append(texto);
      const fim = () => {
        const ir = document.createElement("button");
        ir.type = "button";
        ir.textContent = "Ver no painel";
        ir.addEventListener("click", () => mostrar(q.alvo));
        resp.append(ir);
        msgs.scrollTop = msgs.scrollHeight;
      };
      if (reduz) { texto.textContent = q.resposta; fim(); return; }
      let n = 0;
      const tic = setInterval(() => {
        n += 3;
        texto.textContent = q.resposta.slice(0, n);
        msgs.scrollTop = msgs.scrollHeight;
        if (n >= q.resposta.length) { clearInterval(tic); fim(); }
      }, 16);
    }, reduz ? 0 : 650);
  });
  async function mostrar(alvo) {
    const [aba, id] = ALVO[alvo];
    if (matchMedia("(max-width: 640px)").matches) abrirChat(false);
    await irPara(aba);
    const c = document.getElementById(id);
    setTimeout(() => {
      c.scrollIntoView({ behavior: reduz ? "auto" : "smooth", block: "center" });
      c.classList.remove("foco");
      void c.offsetWidth;
      c.classList.add("foco");
    }, reduz ? 0 : 450);
  }

  // ---------- início ----------
  $$("[data-aba]").forEach((b) => b.addEventListener("click", () => irPara(b.dataset.aba)));
  let temaSalvo = null;
  try { temaSalvo = localStorage.getItem("tema-dashboard"); } catch (e) { /* sem armazenamento */ }
  if (!temaSalvo && matchMedia("(prefers-color-scheme: dark)").matches) raiz.dataset.theme = "dark";
  if (typeof Chart !== "undefined") {
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.font.size = 12;
  }

  const inicio = performance.now();
  fetch("dados/dashboard.json")
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((dados) => {
      estado.dados = dados;
      const pedida = location.hash.replace("#", "");
      if (telas[pedida]) {
        $(`.tela[data-tela="geral"]`).hidden = true;
        $(`.tela[data-tela="${pedida}"]`).hidden = false;
        estado.aba = pedida;
      }
      marcarAba(estado.aba);
      montarFiltro();
      montarPerguntas();
      const espera = reduz ? 0 : Math.max(0, 700 - (performance.now() - inicio));
      setTimeout(() => {
        document.body.classList.remove("carregando");
        const tela = $(`.tela[data-tela="${estado.aba}"]`);
        entrar(tela);
        desenhar(estado.aba);
      }, espera);
    })
    .catch(() => {
      document.body.classList.remove("carregando");
      $("#conteudo").innerHTML = '<p class="cartao">Não foi possível carregar os dados do painel. Recarregue a página.</p>';
    });
})();
