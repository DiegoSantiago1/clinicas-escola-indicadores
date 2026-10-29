"""Calcula os indicadores a partir da base tratada.

Serve a três coisas:
1. os números de referência para conferir o Power BI (cada medida DAX tem de bater com estes);
2. a tabela mensal e a planilha que o Looker Studio lê;
3. o arquivo painel.json que a página de resultados mostra.

As definições estão em docs/INDICADORES.md (o dicionário de indicadores).

Uso: python -m clinicas.indicadores
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from clinicas.config import PASTA_TRATADO, RAIZ, SERVICOS, UNIDADES

PASTA_SITE = RAIZ / "site" / "dados"
ORDEM_SERVICOS = ["ODO", "FIS", "PSI", "NUT"]
DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"]
FIM_DADOS = date(2026, 10, 31)


def ler(pasta: Path = PASTA_TRATADO) -> dict[str, pd.DataFrame]:
    def csv(nome: str, **kw) -> pd.DataFrame:
        return pd.read_csv(pasta / f"{nome}.csv", **kw)

    atend = csv("atendimentos", dtype={"prontuario": str, "matricula_aluno": str})
    atend["data"] = pd.to_datetime(atend["data"])
    oferta = csv("oferta")
    oferta["data"] = pd.to_datetime(oferta["data"])
    fila = csv("fila", dtype={"prontuario": str})
    for c in ("data_inscricao", "data_primeira"):
        fila[c] = pd.to_datetime(fila[c])
    return {
        "atendimentos": atend,
        "oferta": oferta,
        "fila": fila,
        "alunos": csv("alunos", dtype={"matricula": str, "semestre": str}),
        "semestres": csv("semestres", dtype={"semestre": str}),
        "clinicas": csv("clinicas"),
        "resumo_qualidade": csv("resumo_qualidade"),
        "inconsistencias": csv("inconsistencias"),
    }


def contagens(a: pd.DataFrame) -> dict[str, int]:
    s = a["situacao"]
    return {
        "agendamentos": len(a),
        "realizados": int((s == "Realizado").sum()),
        "faltas": int((s == "Falta").sum()),
        "cancelados_paciente": int((s == "Cancelado pelo paciente").sum()),
        "cancelados_clinica": int((s == "Cancelado pela clínica").sum()),
    }


def taxa_faltas(a: pd.DataFrame) -> float:
    """Faltas / (realizados + faltas). Cancelamento avisado não entra: o horário pôde ser remarcado."""
    s = a["situacao"]
    base = ((s == "Realizado") | (s == "Falta")).sum()
    return float((s == "Falta").sum() / base) if base else 0.0


def mensal(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    a = t["atendimentos"].copy()
    a["mes"] = a["data"].dt.to_period("M").dt.start_time
    o = t["oferta"].copy()
    o["mes"] = o["data"].dt.to_period("M").dt.start_time
    chave = ["mes", "unidade", "servico"]
    g = a.groupby(chave)
    base = pd.DataFrame({
        "agendamentos": g.size(),
        "realizados": g["situacao"].apply(lambda s: (s == "Realizado").sum()),
        "faltas": g["situacao"].apply(lambda s: (s == "Falta").sum()),
        "cancelados_paciente": g["situacao"].apply(lambda s: (s == "Cancelado pelo paciente").sum()),
        "cancelados_clinica": g["situacao"].apply(lambda s: (s == "Cancelado pela clínica").sum()),
        "primeiras_consultas": g["tipo"].apply(lambda s: (s == "Primeira consulta").sum()),
        "horas_pratica": g["horas_pratica"].sum(),
        "pacientes_atendidos": a[a["situacao"] == "Realizado"].groupby(chave)["prontuario"].nunique(),
    }).fillna(0)
    base = base.join(o.groupby(chave)["horarios_ofertados"].sum(), how="outer").fillna(0).reset_index()
    f = t["fila"].copy()
    f["mes"] = f["data_inscricao"].dt.to_period("M").dt.start_time
    entradas = f.groupby(chave).size().rename("entradas_fila")
    base = base.merge(entradas, on=chave, how="left").fillna({"entradas_fila": 0})
    base = base[base["mes"] >= pd.Timestamp("2025-11-01")]
    base = base.merge(t["clinicas"][["unidade", "servico", "unidade_nome", "servico_nome", "clinica"]],
                      on=["unidade", "servico"])
    inteiros = [c for c in base.columns if c not in ("mes", "unidade", "servico", "unidade_nome", "servico_nome",
                                                     "clinica", "horas_pratica")]
    base[inteiros] = base[inteiros].astype(int)
    base["mes"] = base["mes"].dt.strftime("%Y-%m-%d")
    return base.sort_values(["mes", "unidade", "servico"]).reset_index(drop=True)


def horas_alunos(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Horas de prática por aluno x meta proporcional aos dias letivos já decorridos.

    2025.2 fica de fora: os dados começam em novembro, no meio do semestre, e as horas de
    agosto a outubro não estão na base (comparar com a meta seria injusto com o aluno).
    """
    a = t["atendimentos"]
    al = t["alunos"][t["alunos"]["semestre"].isin(["2026.1", "2026.2"])].copy()
    sem = t["semestres"].set_index("semestre")
    horas = a.groupby("matricula_aluno")["horas_pratica"].sum()
    perdidas = a[a["situacao"] == "Falta"].groupby("matricula_aluno")["duracao_min"].sum() / 60
    al["horas"] = al["matricula"].map(horas).fillna(0)
    al["horas_perdidas_faltas"] = al["matricula"].map(perdidas).fillna(0)
    proporcao = {}
    for s in ("2026.1", "2026.2"):
        inicio, fim = pd.Timestamp(sem.at[s, "inicio"]), pd.Timestamp(sem.at[s, "fim"])
        uteis = pd.bdate_range(inicio, fim)
        proporcao[s] = len(uteis[uteis <= pd.Timestamp(FIM_DADOS)]) / len(uteis)
    al["proporcao_semestre"] = al["semestre"].map(proporcao)
    al["meta_ate_agora"] = al["meta_horas_semestre"] * al["proporcao_semestre"]
    al["atingimento"] = al["horas"] / al["meta_ate_agora"]
    al["sem_faltas_bateria"] = (al["horas"] + al["horas_perdidas_faltas"]) >= al["meta_ate_agora"]
    return al


def gerar_painel(t: dict[str, pd.DataFrame]) -> dict:
    a, o, f = t["atendimentos"], t["oferta"], t["fila"]
    c = contagens(a)
    ofertados = int(o["horarios_ofertados"].sum())

    por_clinica = []
    for (u, s), g in a.groupby(["unidade", "servico"]):
        fc = f[(f["unidade"] == u) & (f["servico"] == s) & (f["data_primeira"] >= "2025-11-01")]
        ofer = int(o[(o["unidade"] == u) & (o["servico"] == s)]["horarios_ofertados"].sum())
        aguardando = f[(f["unidade"] == u) & (f["servico"] == s) & (f["situacao"] == "Aguardando")]
        por_clinica.append({
            "unidade": u, "servico": s, "clinica": g["clinica"].iloc[0],
            **contagens(g),
            "taxa_faltas": round(taxa_faltas(g), 4),
            "ocupacao": round(len(g) / ofer, 4),
            "aproveitamento": round((g["situacao"] == "Realizado").sum() / ofer, 4),
            "espera_mediana_dias": float(fc["dias_espera"].median()),
            "fila_aguardando_fim": len(aguardando),
            "espera_atual_mediana_dias": (
                float((pd.Timestamp(FIM_DADOS) - aguardando["data_inscricao"]).dt.days.median())
                if len(aguardando) else 0.0),
        })

    a2 = a.assign(mes=a["data"].dt.strftime("%Y-%m"))
    meses = []
    for m, g in a2.groupby("mes"):
        entradas = int((f["data_inscricao"].dt.strftime("%Y-%m") == m).sum())
        chamados = f[f["data_primeira"].dt.strftime("%Y-%m") == m]
        meses.append({"mes": m, **contagens(g), "taxa_faltas": round(taxa_faltas(g), 4),
                      "ofertados": int(o[o["data"].dt.strftime("%Y-%m") == m]["horarios_ofertados"].sum()),
                      "entradas_fila": entradas,
                      "espera_mediana_chamados": float(chamados["dias_espera"].median()) if len(chamados) else None})

    a2["dia"] = a2["data"].dt.day_of_week
    calor = []
    for (d, turno), g in a2[a2["dia"] < 5].groupby(["dia", "turno"]):
        calor.append({"dia": DIAS[d], "turno": turno, "taxa_faltas": round(taxa_faltas(g), 4),
                      "faltas": int((g["situacao"] == "Falta").sum())})

    # Concentração das faltas (I5): quantos pacientes respondem por metade das faltas.
    faltas_pac = a[a["situacao"] == "Falta"].groupby("prontuario").size().sort_values(ascending=False)
    pacientes_com_agenda = a["prontuario"].nunique()
    acumulado = faltas_pac.cumsum() / faltas_pac.sum()
    metade = int((acumulado < 0.5).sum() + 1)
    tres_mais = faltas_pac[faltas_pac >= 3]

    # Espera x falta na 1ª consulta (I6).
    prim = a[(a["tipo"] == "Primeira consulta") & a["situacao"].isin(["Realizado", "Falta"])]
    prim = prim.merge(f[["prontuario", "dias_espera"]], on="prontuario", how="inner")
    faixas = pd.cut(prim["dias_espera"], [-1, 7, 30, 60, 1000], labels=["até 7 dias", "8 a 30", "31 a 60",
                                                                         "mais de 60"])
    espera_falta = [{"faixa": str(k), "taxa_faltas": round(taxa_faltas(g), 4), "consultas": len(g)}
                    for k, g in prim.groupby(faixas, observed=True)]

    # Continuidade: entre quem fez a 1ª consulta até agosto, quantos voltaram para um retorno realizado.
    feitas = a[(a["tipo"] == "Primeira consulta") & (a["situacao"] == "Realizado") & (a["data"] <= "2026-08-31")]
    retornos = set(a[(a["tipo"] == "Retorno") & (a["situacao"] == "Realizado")]["prontuario"])
    continuidade = {s: round(float(g["prontuario"].isin(retornos).mean()), 4)
                    for s, g in feitas.groupby("servico")}

    al = horas_alunos(t)
    al1 = al[al["semestre"] == "2026.1"]
    alunos_servico = []
    for s, g in al1.groupby("servico"):
        alunos_servico.append({
            "servico": s, "alunos": len(g),
            "bateram_meta": int((g["atingimento"] >= 1).sum()),
            "horas_medias": round(float(g["horas"].mean()), 1),
            "meta": int(g["meta_horas_semestre"].iloc[0]),
            "horas_perdidas_medias": round(float(g["horas_perdidas_faltas"].mean()), 1),
            "bateriam_sem_faltas": int(((g["atingimento"] < 1) & g["sem_faltas_bateria"]).sum()),
        })
    horas_perdidas = float((a["situacao"] == "Falta").mul(a["duracao_min"]).sum() / 60)

    qual = t["resumo_qualidade"]
    painel = {
        "aviso": "Dados 100% fictícios, gerados por simulação para demonstrar o método.",
        "periodo": ["2025-11-01", FIM_DADOS.isoformat()],
        "geral": {
            **c, "taxa_faltas": round(taxa_faltas(a), 4), "ofertados": ofertados,
            "ocupacao": round(c["agendamentos"] / ofertados, 4),
            "aproveitamento": round(c["realizados"] / ofertados, 4),
            "horas_pratica": round(float(a["horas_pratica"].sum()), 1),
            "horas_perdidas_faltas": round(horas_perdidas, 1),
            "pacientes": int(pacientes_com_agenda),
            "fila_aguardando_fim": int((f["situacao"] == "Aguardando").sum()),
            "espera_mediana_dias": float(f[f["data_primeira"] >= "2025-11-01"]["dias_espera"].median()),
            "unidades": len(UNIDADES), "clinicas": len(por_clinica),
        },
        "por_clinica": por_clinica,
        "por_servico": [{"servico": s, "nome": SERVICOS[s].nome, **contagens(g),
                         "taxa_faltas": round(taxa_faltas(g), 4)}
                        for s in ORDEM_SERVICOS for g in [a[a["servico"] == s]]],
        "meses": meses,
        "calor_faltas": calor,
        "concentracao_faltas": {
            "pacientes_com_falta": int(len(faltas_pac)),
            "pacientes_com_agenda": int(pacientes_com_agenda),
            "pacientes_metade_das_faltas": metade,
            "pct_pacientes_metade_das_faltas": round(metade / pacientes_com_agenda, 4),
            "pacientes_3_ou_mais_faltas": int(len(tres_mais)),
            "faltas_desses": int(tres_mais.sum()),
            "pct_faltas_desses": round(float(tres_mais.sum() / faltas_pac.sum()), 4),
        },
        "espera_x_falta": espera_falta,
        "continuidade": continuidade,
        "alunos_2026_1": alunos_servico,
        "qualidade": {
            "regras": qual.to_dict(orient="records"),
            "linhas_para_conferir": int(len(t["inconsistencias"])),
        },
    }
    return painel


def salvar(t: dict[str, pd.DataFrame], painel: dict, tratado: Path = PASTA_TRATADO, site: Path = PASTA_SITE) -> None:
    men = mensal(t)
    men.to_csv(tratado / "indicadores_mensais.csv", index=False, encoding="utf-8", lineterminator="\n")
    site.mkdir(parents=True, exist_ok=True)
    (site / "painel.json").write_text(json.dumps(painel, ensure_ascii=False, indent=1, default=_json),
                                      encoding="utf-8", newline="\n")


def _json(valor: object) -> object:
    if isinstance(valor, np.integer):
        return int(valor)
    if isinstance(valor, np.floating):
        return float(valor)
    raise TypeError(type(valor))


if __name__ == "__main__":
    tabelas = ler()
    p = gerar_painel(tabelas)
    salvar(tabelas, p)
    g = p["geral"]
    print(f"Agendamentos {g['agendamentos']:,} | realizados {g['realizados']:,} | faltas {g['taxa_faltas']:.1%} | "
          f"ocupação {g['ocupacao']:.1%} | aproveitamento {g['aproveitamento']:.1%}")
    print(f"Horas de prática {g['horas_pratica']:,.0f} | perdidas por faltas {g['horas_perdidas_faltas']:,.0f}")
    print(f"Espera mediana {g['espera_mediana_dias']} dias | aguardando no fim {g['fila_aguardando_fim']}")
    for c in p["por_clinica"]:
        print(f"  {c['clinica']:<26} faltas {c['taxa_faltas']:.1%} ocupação {c['ocupacao']:.1%} "
              f"espera {c['espera_mediana_dias']:>5} fila {c['fila_aguardando_fim']}")
    print("calor:", [(x["dia"][:3], x["turno"][:1], f"{x['taxa_faltas']:.1%}") for x in p["calor_faltas"]])
    print("concentração:", p["concentracao_faltas"])
    print("espera x falta:", p["espera_x_falta"])
    print("continuidade:", p["continuidade"])
    print("alunos 2026.1:", p["alunos_2026_1"])
