// A página do projeto: o palco fixo da abertura, o cartão das quatro etapas e o índice do Power BI.
// (Os números, o painel, o editor e os achados ficam em app.js.)
"use strict";

(() => {
  const reduz = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const LEGENDAS = { 1: "O horário que ninguém usou", 2: "Odontologia", 3: "Psicologia", 4: "Fisioterapia" };

  // Palco da abertura: a foto troca quando o capítulo correspondente passa pelo meio da tela.
  function capitulo(n) {
    document.querySelectorAll(".palco-foto").forEach((f) => f.classList.toggle("ativa", f.dataset.capitulo === n));
    const legenda = document.getElementById("palco-legenda");
    if (legenda) legenda.textContent = LEGENDAS[n];
  }

  // Quatro etapas: o cartão fixo mostra o estado da frase que está no meio da tela.
  function etapa(n) {
    document.querySelectorAll(".etapa").forEach((e) => e.classList.toggle("ativa", e.dataset.etapa === n));
    document.querySelectorAll(".ficha-sis").forEach((f) => f.classList.toggle("ativa", f.dataset.etapa === n));
  }
  etapa("1");

  if ("IntersectionObserver" in window) {
    const meio = { rootMargin: "-45% 0px -45% 0px", threshold: 0 };
    const obsCap = new IntersectionObserver((itens) => {
      for (const it of itens) if (it.isIntersecting) capitulo(it.target.dataset.capitulo);
    }, meio);
    document.querySelectorAll(".capitulo").forEach((c) => obsCap.observe(c));
    const obsEtapa = new IntersectionObserver((itens) => {
      for (const it of itens) if (it.isIntersecting) etapa(it.target.dataset.etapa);
    }, meio);
    document.querySelectorAll(".etapa").forEach((e) => obsEtapa.observe(e));
  }

  // Índice do Power BI: clicar no nome troca a página no palco (setas também funcionam).
  const nomes = [...document.querySelectorAll(".vitrine-nomes button")];
  const img = document.getElementById("vitrine-img");
  function mostrar(botao, foco = false) {
    if (botao.getAttribute("aria-selected") === "true") return;
    nomes.forEach((b) => b.setAttribute("aria-selected", String(b === botao)));
    nomes.forEach((b) => (b.tabIndex = b === botao ? 0 : -1));
    if (foco) botao.focus();
    const trocar = () => {
      img.src = botao.dataset.img;
      img.alt = `Página ${botao.textContent} do relatório no Power BI`;
      img.classList.remove("trocando");
    };
    if (reduz) { trocar(); return; }
    img.classList.add("trocando");
    setTimeout(trocar, 200);
  }
  nomes.forEach((b, i) => {
    b.tabIndex = i === 0 ? 0 : -1;
    b.addEventListener("click", () => mostrar(b));
    b.addEventListener("keydown", (ev) => {
      const passo = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[ev.key];
      if (!passo) return;
      ev.preventDefault();
      mostrar(nomes[(i + passo + nomes.length) % nomes.length], true);
    });
  });
  // As imagens das outras páginas já vêm para o cache: a troca fica instantânea.
  const pre = () => nomes.slice(1).forEach((b) => { const i = new Image(); i.src = b.dataset.img; });
  if ("requestIdleCallback" in window) requestIdleCallback(pre); else setTimeout(pre, 1500);
})();
