"""O painel animado: cada número fecha com a base tratada e a rede é a soma das unidades."""

import pandas as pd
import pytest

from clinicas import dashboard


@pytest.fixture(scope="module")
def dados(pastas):
    return dashboard.montar(pastas["tratado"])


def test_rede_e_a_soma_das_unidades(dados):
    rede = dados["blocos"]["*"]["kpis"]
    unidades = [dados["blocos"][u]["kpis"] for u in ("REC", "OLI", "JAB")]
    for chave in ("agendamentos", "realizados", "faltas", "cancelados_paciente", "cancelados_clinica",
                  "aguardando"):
        assert rede[chave] == sum(u[chave] for u in unidades), chave
    assert rede["faturamento"] == pytest.approx(sum(u["faturamento"] for u in unidades))


def test_faturamento_fecha_com_a_base(dados, pastas):
    a = pd.read_csv(pastas["tratado"] / "atendimentos.csv")
    b = dados["blocos"]["*"]
    assert b["faturamento"]["total"] == pytest.approx(a["valor_cobrado"].sum())
    assert sum(s["valor"] for s in b["faturamento"]["por_servico"]) == pytest.approx(b["faturamento"]["total"])
    assert sum(m["faturamento"] for m in b["serie"]) == pytest.approx(b["faturamento"]["total"])
    assert (a.loc[a["situacao"] != "Realizado", "valor_cobrado"].fillna(0) == 0).all()


def test_motivos_somam_as_faltas_e_desmarcacoes(dados):
    b = dados["blocos"]["*"]
    assert sum(m["qtd"] for m in b["motivos"]["faltas"]) == b["kpis"]["faltas"]
    assert sum(m["qtd"] for m in b["motivos"]["desmarcacoes"]) == b["kpis"]["cancelados_paciente"]


def test_espera_cresce_ao_longo_do_turno_em_cada_servico(dados):
    for s in dados["blocos"]["*"]["espera"]["por_posicao"]:
        assert s["valores"] == sorted(s["valores"]), s["servico"]


def test_faixas_de_espera_cobrem_todos_os_medidos(dados):
    e = dados["blocos"]["*"]["espera"]
    assert sum(f["qtd"] for f in e["faixas"]) == e["medidos"]


def test_uma_resposta_para_cada_pergunta(dados):
    for u, b in dados["blocos"].items():
        esperado = 10 if u == "*" else 9
        assert len(b["perguntas"]) == esperado
        assert all(q["resposta"] and "nan" not in q["resposta"] for q in b["perguntas"])


def test_arredondamento_igual_ao_da_pagina():
    """A página usa Math.round (0,5 para cima); as respostas escritas em Python têm de bater com ela."""
    assert dashboard.inteiro(30.5) == 31
    assert dashboard.inteiro(28.5) == 29
    assert dashboard.inteiro(26.4) == 26
