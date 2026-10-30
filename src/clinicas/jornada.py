"""A jornada de cada paciente em 31/10/2026, para o painel em funil (site/painel).

Etapas, definidas só com a base tratada (o simulador sabe mais, mas o painel não pode usar a verdade):

- Na fila: a fila da recepção diz "Aguardando".
- Desistiu da fila: a fila diz "Desistiu".
- Chamado: foi chamado, ainda não teve nenhum atendimento realizado e o último agendamento foi há
  30 dias ou menos (marcou e ainda não veio).
- Em tratamento: tem atendimento realizado e o último agendamento foi há 30 dias ou menos.
- Sem retorno: o último agendamento foi há 31 a 90 dias (risco de abandono: a recepção deve ligar).
- Encerrado: nada há mais de 90 dias, ou chamado antes do período sem agendamento nele (alta ou
  abandono: a base não diz qual, então a etapa não finge saber).

Uso: python -m clinicas.jornada
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from clinicas.config import PASTA_TRATADO, RAIZ, SERVICOS, UNIDADES

REFERENCIA = pd.Timestamp(date(2026, 10, 31))
DESTINO = RAIZ / "site" / "painel" / "dados" / "jornada.json"
ETAPAS = [
    ("fila", "Na fila"),
    ("chamado", "Chamado"),
    ("tratamento", "Em tratamento"),
    ("sem_retorno", "Sem retorno"),
    ("encerrado", "Encerrado"),
    ("desistiu", "Desistiu da fila"),
]
CARTOES_POR_COLUNA = 12


def etapa_de(situacao_fila: str, realizados: int, ultimo: pd.Timestamp | None) -> str:
    if situacao_fila == "Desistiu":
        return "desistiu"
    if situacao_fila == "Aguardando":
        return "fila"
    if ultimo is None:
        return "encerrado"
    dias = (REFERENCIA - ultimo).days
    if dias <= 30:
        return "tratamento" if realizados > 0 else "chamado"
    if dias <= 90:
        return "sem_retorno"
    return "encerrado"


def montar() -> dict:
    t = PASTA_TRATADO
    atend = pd.read_csv(t / "atendimentos.csv", dtype={"prontuario": str, "matricula_aluno": str})
    atend["data"] = pd.to_datetime(atend["data"])
    fila = pd.read_csv(t / "fila.csv", dtype={"prontuario": str})
    for c in ("data_inscricao", "data_primeira"):
        fila[c] = pd.to_datetime(fila[c])
    pacientes = pd.read_csv(t / "pacientes.csv", dtype={"prontuario": str}).set_index("prontuario")
    alunos = pd.read_csv(t / "alunos.csv", dtype={"matricula": str}).set_index("matricula")
    sup = pd.read_csv(t / "supervisores.csv").set_index("codigo")

    a = atend.dropna(subset=["prontuario"])
    por = a.groupby("prontuario")
    resumo = pd.DataFrame({
        "agendamentos": por.size(),
        "realizados": por["situacao"].apply(lambda s: int((s == "Realizado").sum())),
        "faltas": por["situacao"].apply(lambda s: int((s == "Falta").sum())),
        "cancelados": por["situacao"].apply(lambda s: int(s.str.startswith("Cancelado").sum())),
        "ultimo": por["data"].max(),
        "primeiro": por["data"].min(),
        "horas": por["horas_pratica"].sum(),
    })
    f = fila.set_index("prontuario").join(resumo, how="left")
    f[["agendamentos", "realizados", "faltas", "cancelados"]] = f[
        ["agendamentos", "realizados", "faltas", "cancelados"]].fillna(0).astype(int)
    f["horas"] = f["horas"].fillna(0.0)
    f["etapa"] = [etapa_de(s, r, None if pd.isna(u) else u)
                  for s, r, u in zip(f["situacao"], f["realizados"], f["ultimo"], strict=True)]
    f["dias_na_fila"] = (REFERENCIA - f["data_inscricao"]).dt.days
    f["dias_sem_vir"] = (REFERENCIA - f["ultimo"]).dt.days

    # Ordem de cada coluna: quem precisa de atenção primeiro.
    ordem = {
        "fila": (["dias_na_fila"], [False]),
        "chamado": (["faltas", "dias_sem_vir"], [False, True]),
        "tratamento": (["faltas", "realizados"], [False, False]),
        "sem_retorno": (["dias_sem_vir", "faltas"], [True, False]),
        "encerrado": (["ultimo"], [False]),
        "desistiu": (["dias_espera_desist"], [False]),
    }
    f["dias_espera_desist"] = 0
    # A data da desistência não está na base: conta-se a espera até o fim do período como teto.
    desist = f["etapa"] == "desistiu"
    f.loc[desist, "dias_espera_desist"] = f.loc[desist, "dias_na_fila"]

    escolhidos: set[str] = set()
    colunas: dict[str, dict] = {}
    for filtro in ("*", *SERVICOS):
        sub = f if filtro == "*" else f[f["servico"] == filtro]
        for chave, _nome in ETAPAS:
            g = sub[sub["etapa"] == chave]
            campos, asc = ordem[chave]
            topo = g.sort_values(campos, ascending=asc).head(CARTOES_POR_COLUNA)
            escolhidos.update(topo.index)
            mediana = {
                "fila": g["dias_na_fila"].median(),
                "chamado": g["dias_sem_vir"].median(),
                "tratamento": g["realizados"].median(),
                "sem_retorno": g["dias_sem_vir"].median(),
                "encerrado": g["realizados"].median(),
                "desistiu": None,
            }[chave]
            colunas[f"{filtro}|{chave}"] = {
                "total": int(len(g)),
                "mediana": None if mediana is None or pd.isna(mediana) else float(mediana),
                "faltas": int(g["faltas"].sum()),
                "cartoes": list(topo.index),
                "todos": list(g.sort_values(campos, ascending=asc).index) if chave in (
                    "fila", "sem_retorno") else [],
            }

    def iso(v: object) -> str | None:
        return None if pd.isna(v) else pd.Timestamp(v).date().isoformat()

    detalhes = {}
    for p in sorted(escolhidos):
        r = f.loc[p]
        ag = a[a["prontuario"] == p].sort_values(["data", "hora"])
        ultimo_aluno = ag["matricula_aluno"].iloc[-1] if len(ag) else None
        ultimo_sup = ag["supervisor"].iloc[-1] if len(ag) else None
        pac = pacientes.loc[p] if p in pacientes.index else None
        detalhes[p] = {
            "prontuario": p,
            "unidade": r["unidade"], "servico": r["servico"], "etapa": r["etapa"],
            "situacao_fila": r["situacao"],
            "inscricao": iso(r["data_inscricao"]), "primeira": iso(r["data_primeira"]),
            "ultimo": iso(r["ultimo"]),
            "dias_na_fila": int(r["dias_na_fila"]),
            "dias_espera": None if pd.isna(r["dias_espera"]) else int(r["dias_espera"]),
            "dias_sem_vir": None if pd.isna(r["dias_sem_vir"]) else int(r["dias_sem_vir"]),
            "agendamentos": int(r["agendamentos"]), "realizados": int(r["realizados"]),
            "faltas": int(r["faltas"]), "cancelados": int(r["cancelados"]), "horas": round(float(r["horas"]), 1),
            "sexo": None if pac is None else pac["sexo"],
            "faixa_etaria": None if pac is None else pac["faixa_etaria"],
            "aluno": None if ultimo_aluno is None else {"matricula": ultimo_aluno,
                                                        "nome": alunos.at[ultimo_aluno, "nome"]},
            "supervisor": None if ultimo_sup is None else sup.at[ultimo_sup, "nome"],
            "origem": None if not len(ag) else ag["origem"].iloc[-1],
            "recuperado": bool((ag["prontuario_recuperado"] == "Sim").any()),
            # Motivo (falta ou desmarcação) e espera na recepção (quando veio), da exportação do tablet.
            "agenda": [{"data": d.date().isoformat(), "hora": h, "tipo": tp, "situacao": s,
                        "motivo": None if pd.isna(m) else m, "espera_min": None if pd.isna(e) else int(e)}
                       for d, h, tp, s, m, e in zip(ag["data"], ag["hora"], ag["tipo"], ag["situacao"], ag["motivo"],
                                                    ag["espera_recepcao_min"], strict=True)],
        }

    totais = {chave: int((f["etapa"] == chave).sum()) for chave, _ in ETAPAS}
    assert sum(totais.values()) == len(f), "as etapas têm de somar todos os pacientes da fila"
    return {
        "referencia": REFERENCIA.date().isoformat(),
        "pacientes": int(len(f)),
        "etapas": [{"chave": c, "nome": n} for c, n in ETAPAS],
        "servicos": {k: s.nome for k, s in SERVICOS.items()},
        "unidades": UNIDADES,
        "totais": totais,
        "colunas": colunas,
        "detalhes": detalhes,
    }


if __name__ == "__main__":
    dados = montar()
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8",
                       newline="\n")
    print(dados["pacientes"], dados["totais"], len(dados["detalhes"]), f"{DESTINO.stat().st_size / 1024:.0f} KB")
    for c in ("*|fila", "*|sem_retorno", "*|tratamento"):
        col = dados["colunas"][c]
        print(c, col["total"], col["mediana"], col["faltas"])
