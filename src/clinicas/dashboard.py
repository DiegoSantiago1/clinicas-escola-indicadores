"""Números do painel animado (site/dashboard): faturamento, presença, profissionais, fila,
horários, motivos, espera na recepção, unidades e áreas.

Tudo sai da base tratada (data/tratado), com as mesmas definições de docs/INDICADORES.md.
Cada bloco é calculado para "*" (rede toda) e para cada unidade: a página só troca de bloco
quando o filtro muda, sem fazer conta no navegador (mediana não se soma).

Uso: python -m clinicas.dashboard
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from clinicas.config import INICIO, PASTA_TRATADO, RAIZ, SERVICOS, UNIDADES
from clinicas.indicadores import FIM_DADOS, _json, contagens, ler, taxa_faltas

PASTA_DASHBOARD = RAIZ / "site" / "dashboard" / "dados"
NOMES_MES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"]
ORDEM_SERVICOS = ["ODO", "FIS", "PSI", "NUT"]
FAIXAS_ESPERA = [(0, 10, "até 10 min"), (10, 20, "10 a 20"), (20, 30, "20 a 30"), (30, 45, "30 a 45"),
                 (45, 10_000, "45 ou mais")]


def meses_do_periodo() -> list[str]:
    return [str(p) for p in pd.period_range(INICIO, FIM_DADOS, freq="M")]


def rotulo_mes(m: str) -> str:
    return f"{NOMES_MES[int(m[5:7]) - 1]}/{m[2:4]}"


def nome_clinica(u: str, s: str) -> str:
    return f"{SERVICOS[s].nome} · {UNIDADES[u].split()[0]}"


def arred(x: float, casas: int = 1) -> float:
    return round(float(x), casas)


def bloco(a: pd.DataFrame, f: pd.DataFrame, sup: pd.DataFrame) -> dict:
    """Todos os números de um filtro (a rede ou uma unidade)."""
    meses = meses_do_periodo()
    a = a.assign(mes=a["data"].dt.strftime("%Y-%m"))
    c = contagens(a)
    realizado = a["situacao"] == "Realizado"
    falta = a["situacao"] == "Falta"

    # Série mensal (sparklines e o gráfico de presença).
    serie = []
    for m in meses:
        g = a[a["mes"] == m]
        serie.append({"mes": rotulo_mes(m), **contagens(g), "faturamento": float(g["valor_cobrado"].sum()),
                      "taxa_faltas": arred(taxa_faltas(g), 4),
                      "espera_min": arred(g["espera_recepcao_min"].mean()) if g["espera_recepcao_min"].notna().any()
                      else None})

    # Faturamento: o que entrou e o que deixou de entrar com as faltas de quem pagaria.
    pagantes_falta = a[falta & a["isento"].eq("Não")]
    faturamento = {
        "total": float(a["valor_cobrado"].sum()),
        "ticket_medio": arred(a.loc[a["valor_cobrado"] > 0, "valor_cobrado"].mean(), 2),
        "perdido_faltas": float(pagantes_falta["valor_tabela"].sum()),
        "sem_prontuario": int((realizado & a["valor_cobrado"].isna()).sum()),
        "por_servico": [{"servico": SERVICOS[s].nome, "valor": float(a.loc[a["servico"] == s, "valor_cobrado"].sum())}
                        for s in ORDEM_SERVICOS if (a["servico"] == s).any()],
        "por_procedimento": (a[realizado].groupby("procedimento")["valor_cobrado"].sum().sort_values(ascending=False)
                             .head(6).round(0).reset_index().rename(columns={"valor_cobrado": "valor"})
                             .to_dict("records")),
    }

    # Profissionais: o supervisor (professor) responsável por cada atendimento.
    nomes_sup = dict(zip(sup["codigo"], sup["nome"], strict=True))
    prof = []
    for codigo, g in a.groupby("supervisor"):
        base = g[g["situacao"].isin(["Realizado", "Falta"])]
        dia_turno = (base["data"].dt.day_of_week.map(lambda d: DIAS[d]) + " de " + base["turno"].str.lower()).mode()
        prof.append({"codigo": codigo, "nome": nomes_sup[codigo], "clinica": g["clinica"].iloc[0],
                     "atendimentos": int((g["situacao"] == "Realizado").sum()), "agendamentos": len(g),
                     "taxa_faltas": arred(taxa_faltas(g), 4), "turno_principal": dia_turno.iloc[0]})
    prof.sort(key=lambda p: (-p["atendimentos"], p["codigo"]))

    # Fila de espera por clínica: mediana de dias até a 1ª consulta (chamados no período)
    # e quantos ainda aguardam no último dia dos dados.
    fila = []
    for (u, s), g in f.groupby(["unidade", "servico"]):
        chamados = g[g["data_primeira"] >= pd.Timestamp(INICIO)]
        aguardando = g[g["situacao"] == "Aguardando"]
        fila.append({"clinica": nome_clinica(u, s), "espera_mediana_dias": float(chamados["dias_espera"].median()),
                     "aguardando": len(aguardando),
                     "entradas": int((g["data_inscricao"] >= pd.Timestamp(INICIO)).sum())})
    fila.sort(key=lambda x: -x["espera_mediana_dias"])

    # Horários: quantos agendamentos e quantas faltas em cada horário de início.
    horarios = []
    for h, g in a.groupby("hora"):
        horarios.append({"hora": h, "agendamentos": len(g), "realizados": int((g["situacao"] == "Realizado").sum()),
                         "faltas": int((g["situacao"] == "Falta").sum()), "taxa_faltas": arred(taxa_faltas(g), 4)})
    dia_turno = []
    for d in range(5):
        for turno in ("Manhã", "Tarde"):
            g = a[(a["data"].dt.day_of_week == d) & (a["turno"] == turno)]
            dia_turno.append({"dia": DIAS[d], "turno": turno, "taxa_faltas": arred(taxa_faltas(g), 4),
                              "agendamentos": len(g)})

    # Motivos de falta e de desmarcação (o que a recepção registrou).
    def contar_motivos(sel: pd.Series) -> list[dict]:
        cont = a.loc[sel, "motivo"].value_counts()
        total = int(cont.sum())
        return [{"motivo": k, "qtd": int(v), "pct": arred(v / total, 4)} for k, v in cont.items()]

    justificadas = falta & ~a["motivo"].isin(["Sem justificativa", "Não identificado"])
    temporada = a["data"].dt.month.between(4, 7)  # inverno chuvoso de Pernambuco
    chuva_mes = []
    for m in meses:
        g = a[(a["mes"] == m) & justificadas]
        chuva_mes.append({"mes": rotulo_mes(m), "pct_chuva": arred((g["motivo"] == "Chuva").mean(), 4)
                          if len(g) else None})
    motivos = {
        "faltas": contar_motivos(falta),
        "desmarcacoes": contar_motivos(a["situacao"] == "Cancelado pelo paciente"),
        "justificadas_pct": arred(justificadas.sum() / falta.sum(), 4) if falta.any() else 0.0,
        "chuva_temporada": arred((a.loc[justificadas & temporada, "motivo"] == "Chuva").mean(), 4),
        "chuva_resto": arred((a.loc[justificadas & ~temporada, "motivo"] == "Chuva").mean(), 4),
        "chuva_por_mes": chuva_mes,
        "transporte_por_unidade": [
            {"unidade": UNIDADES[u].split()[0],
             "pct": arred((a.loc[justificadas & (a["unidade"] == u), "motivo"] == "Transporte").mean(), 4)}
            for u in UNIDADES if (justificadas & (a["unidade"] == u)).any()],
    }

    # Espera na recepção: da chegada até o aluno chamar (só atendimentos com os dois horários).
    e = a[a["espera_recepcao_min"].notna()].copy()
    e["posicao"] = e.groupby(["unidade", "servico", "turno"])["hora"].rank(method="dense").astype(int)
    segunda_manha = (e["data"].dt.day_of_week == 0) & (e["turno"] == "Manhã")
    espera = {
        "media_min": arred(e["espera_recepcao_min"].mean()),
        "mediana_min": arred(e["espera_recepcao_min"].median()),
        "medidos": len(e),
        "sem_chamada": int((realizado & a["hora_chegada"].notna() & a["hora_chamada"].isna()).sum()),
        "por_clinica": sorted([{"clinica": k, "media_min": arred(v)} for k, v in
                               e.groupby("clinica")["espera_recepcao_min"].mean().items()],
                              key=lambda x: -x["media_min"]),
        "por_hora": [{"hora": k, "media_min": arred(v)} for k, v in e.groupby("hora")["espera_recepcao_min"].mean()
                     .items()],
        # Por serviço: a Odontologia tem 2 horários por turno e os outros serviços 4; juntos, a média
        # do 3º e do 4º horário não teria Odontologia e pareceria menor (mistura, não efeito).
        "por_posicao": [{"servico": SERVICOS[s].nome,
                         "valores": [arred(v) for v in e[e["servico"] == s].groupby("posicao")
                                     ["espera_recepcao_min"].mean()]}
                        for s in ORDEM_SERVICOS if (e["servico"] == s).any()],
        "faixas": [{"faixa": rot, "qtd": int(e["espera_recepcao_min"].between(lo, hi, inclusive="left").sum())}
                   for lo, hi, rot in FAIXAS_ESPERA],
        "segunda_manha_min": arred(e.loc[segunda_manha, "espera_recepcao_min"].mean()),
        "demais_min": arred(e.loc[~segunda_manha, "espera_recepcao_min"].mean()),
    }

    unidades = [{"unidade": UNIDADES[u].split()[0], **contagens(a[a["unidade"] == u]),
                 "faturamento": float(a.loc[a["unidade"] == u, "valor_cobrado"].sum()),
                 "taxa_faltas": arred(taxa_faltas(a[a["unidade"] == u]), 4)}
                for u in UNIDADES if (a["unidade"] == u).any()]
    entradas = f[f["data_inscricao"] >= pd.Timestamp(INICIO)]
    areas = [{"servico": SERVICOS[s].nome, "procura": int((entradas["servico"] == s).sum()),
              "agendamentos": int((a["servico"] == s).sum()),
              "realizados": int((realizado & (a["servico"] == s)).sum())}
             for s in ORDEM_SERVICOS if (a["servico"] == s).any()]
    areas.sort(key=lambda x: -x["procura"])

    return {
        "kpis": {**c, "taxa_faltas": arred(taxa_faltas(a), 4), "faturamento": faturamento["total"],
                 "espera_recepcao_min": espera["media_min"],
                 "aguardando": int((f["situacao"] == "Aguardando").sum()),
                 "espera_fila_mediana_dias": float(f.loc[f["data_primeira"] >= pd.Timestamp(INICIO),
                                                         "dias_espera"].median())},
        "serie": serie, "faturamento": faturamento, "profissionais": prof, "fila": fila,
        "horarios": horarios, "dia_turno": dia_turno, "motivos": motivos, "espera": espera,
        "unidades": unidades, "areas": areas,
    }


def moeda(v: float) -> str:
    inteiro = f"{v:,.0f}".replace(",", ".")
    return f"R$ {inteiro}"


def pct(v: float) -> str:
    return f"{v * 100:.1f}%".replace(".", ",")


def num(v: int) -> str:
    return f"{v:,}".replace(",", ".")


def inteiro(v: float) -> int:
    """Arredonda 0,5 para cima, como o Math.round da página (o round do Python arredonda para o par)."""
    return math.floor(v + 0.5)


def dias(v: float) -> str:
    return "1 dia" if inteiro(v) == 1 else f"{inteiro(v)} dias"


def hora(h: str) -> str:
    return h.replace(":00", "h").replace(":", "h")


def perguntas(b: dict, onde: str) -> list[dict]:
    """As perguntas do Diego, com a resposta escrita a partir dos números (nenhuma IA envolvida)."""
    k, fat, fila, hor = b["kpis"], b["faturamento"], b["fila"], b["horarios"]
    mais_hora = max(hor, key=lambda h: h["agendamentos"])
    pior = max(hor, key=lambda h: h["taxa_faltas"])
    melhor = min(hor, key=lambda h: h["taxa_faltas"])
    prof = b["profissionais"]
    mot = b["motivos"]
    falta_motivo = [m for m in mot["faltas"] if m["motivo"] not in ("Sem justificativa", "Não identificado")]
    desm = mot["desmarcacoes"]
    esp = b["espera"]
    odo = next(p["valores"] for p in esp["por_posicao"] if p["servico"] == "Odontologia")
    areas = b["areas"]
    rede = onde == "na rede"
    saida = [
        ("faturamento", "Quanto as clínicas faturaram?",
         f"{moeda(fat['total'])} em taxa social {onde}, de nov/25 a out/26. As faltas de quem pagaria "
         f"deixaram de trazer mais {moeda(fat['perdido_faltas'])}."),
        ("presenca", "Quantos foram e quantos cancelaram?",
         f"{num(k['realizados'])} consultas realizadas e {num(k['faltas'])} faltas ({pct(k['taxa_faltas'])}). "
         f"Outras {num(k['cancelados_paciente'])} foram desmarcadas pelo paciente e "
         f"{num(k['cancelados_clinica'])} canceladas pela clínica."),
        ("profissionais", "Qual professor atende mais e qual atende menos?",
         f"{prof[0]['nome']} ({prof[0]['clinica']}) supervisionou {num(prof[0]['atendimentos'])} atendimentos; "
         f"{prof[-1]['nome']} ({prof[-1]['clinica']}), {num(prof[-1]['atendimentos'])}. A diferença vem do "
         "tamanho da clínica, da duração da sessão e dos turnos de cada professor: o paciente escolhe o "
         "horário, não o professor."),
        ("fila", "Qual fila é a mais longa e qual é a mais curta?",
         f"Todas as filas {onde} andam no mesmo ritmo: mediana de {dias(fila[0]['espera_mediana_dias'])} até a "
         "1ª consulta." if fila[0]["espera_mediana_dias"] == fila[-1]["espera_mediana_dias"] else
         f"Mais longa: {fila[0]['clinica']}, mediana de {dias(fila[0]['espera_mediana_dias'])} até a 1ª "
         f"consulta. Mais curta: {fila[-1]['clinica']}, {dias(fila[-1]['espera_mediana_dias'])}."
         + ("" if fila[-2]["espera_mediana_dias"] != fila[-1]["espera_mediana_dias"] else
            " Outras filas empatam com ela.")),
        ("horarios", "Em qual horário as pessoas mais marcam?",
         f"{hora(mais_hora['hora'])}, com {num(mais_hora['agendamentos'])} agendamentos. É o primeiro horário "
         "de todas as clínicas, e a Odontologia (sessões de 2 horas) só atende às 8h, 10h, 13h30 e 15h30."),
        ("horarios", "Qual horário tem mais faltas e qual tem menos?",
         f"Mais faltas: {hora(pior['hora'])} ({pct(pior['taxa_faltas'])}). Menos: {hora(melhor['hora'])} "
         f"({pct(melhor['taxa_faltas'])})."
         + (" Às 9h e às 11h a Odontologia, que falta menos, não atende, e a Psicologia, que falta mais, "
            "pesa mais na conta." if rede else "")),
        ("motivos", "Por que os pacientes faltam ou desmarcam?",
         f"Entre as faltas justificadas, o motivo mais comum é “{falta_motivo[0]['motivo']}”; "
         f"{pct(1 - mot['justificadas_pct'])} das faltas nunca foram justificadas. Quem desmarca cita mais "
         f"“{desm[0]['motivo']}”. De abril a julho a chuva passa de {pct(mot['chuva_resto'])} para "
         f"{pct(mot['chuva_temporada'])} das faltas justificadas."),
        ("espera", "Quanto tempo o paciente espera na recepção?",
         f"{inteiro(esp['media_min'])} minutos em média, da chegada até ser chamado. A maior espera é em "
         f"{esp['por_clinica'][0]['clinica']} ({inteiro(esp['por_clinica'][0]['media_min'])} min). Na Odontologia, "
         f"quem tem o 2º horário do turno espera {inteiro(odo[1] - odo[0])} min a mais que quem tem o 1º: o atraso "
         f"de uma sessão passa para a seguinte. Segunda de manhã: {inteiro(esp['segunda_manha_min'])} min."),
        ("areas", "Qual área é a mais procurada?",
         f"{areas[0]['servico']}: {num(areas[0]['procura'])} pessoas entraram na fila no período. A menos "
         f"procurada é {areas[-1]['servico']}, com {num(areas[-1]['procura'])}."),
    ]
    if len(b["unidades"]) > 1:
        u = sorted(b["unidades"], key=lambda x: -x["realizados"])
        saida.insert(8, ("unidades", "Qual unidade atende mais e qual atende menos?",
                         f"{u[0]['unidade']} atende mais: {num(u[0]['realizados'])} consultas. {u[-1]['unidade']} "
                         f"atende menos: {num(u[-1]['realizados'])}. Recife tem quatro clínicas; Olinda e "
                         "Jaboatão, três cada."))
    return [{"alvo": a, "pergunta": p, "resposta": r} for a, p, r in saida]


def montar(pasta: Path = PASTA_TRATADO) -> dict:
    t = ler(pasta)
    a = t["atendimentos"]
    pac = pd.read_csv(pasta / "pacientes.csv", dtype=str)
    a["isento"] = a["prontuario"].map(dict(zip(pac["prontuario"], pac["isento_taxa"], strict=True)))
    sup = pd.read_csv(pasta / "supervisores.csv", dtype=str)
    f = t["fila"]
    filtros = {"*": "na rede"} | {u: f"em {UNIDADES[u].split()[0]}" for u in UNIDADES}
    blocos = {}
    for u, onde in filtros.items():
        au = a if u == "*" else a[a["unidade"] == u]
        fu = f if u == "*" else f[f["unidade"] == u]
        b = bloco(au, fu, sup)
        b["perguntas"] = perguntas(b, onde)
        blocos[u] = b
    return {
        "rede": "Rede Acolher de Clínicas-Escola",
        "aviso": "Dados 100% fictícios, gerados por simulação.",
        "periodo": [INICIO.isoformat(), FIM_DADOS.isoformat()],
        "unidades": {"*": "Todas"} | {u: UNIDADES[u].split()[0] for u in UNIDADES},
        "blocos": blocos,
    }


def salvar(dados: dict, destino: Path = PASTA_DASHBOARD) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / "dashboard.json"
    caminho.write_text(json.dumps(dados, ensure_ascii=False, default=_json, allow_nan=False), encoding="utf-8",
                       newline="\n")
    return caminho


if __name__ == "__main__":
    d = montar()
    caminho = salvar(d)
    print(f"{caminho} ({caminho.stat().st_size / 1024:.0f} KB)")
    for q in d["blocos"]["*"]["perguntas"]:
        print(f"- {q['pergunta']}\n  {q['resposta']}")
