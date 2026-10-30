"""A jornada do painel: cada paciente da fila cai em exatamente uma etapa."""

import pandas as pd
import pytest

from clinicas import jornada
from clinicas.jornada import REFERENCIA, etapa_de


@pytest.mark.parametrize(("situacao", "realizados", "dias_atras", "esperado"), [
    ("Aguardando", 0, None, "fila"),
    ("Desistiu", 0, None, "desistiu"),
    ("Chamado", 0, None, "encerrado"),       # chamado antes do período, nada nele
    ("Chamado", 0, 10, "chamado"),           # marcou e ainda não veio
    ("Chamado", 2, 30, "tratamento"),        # limite de 30 dias ainda é tratamento
    ("Chamado", 2, 31, "sem_retorno"),
    ("Chamado", 2, 90, "sem_retorno"),
    ("Chamado", 2, 91, "encerrado"),
])
def test_etapa_de(situacao, realizados, dias_atras, esperado):
    ultimo = None if dias_atras is None else REFERENCIA - pd.Timedelta(days=dias_atras)
    assert etapa_de(situacao, realizados, ultimo) == esperado


def test_etapas_somam_todos_os_pacientes(pastas, monkeypatch):
    monkeypatch.setattr(jornada, "PASTA_TRATADO", pastas["tratado"])
    dados = jornada.montar()
    assert sum(dados["totais"].values()) == dados["pacientes"]
    for chave, total in dados["totais"].items():
        col = dados["colunas"][f"*|{chave}"]
        assert col["total"] == total
        assert len(col["cartoes"]) == min(total, jornada.CARTOES_POR_COLUNA)
        assert all(dados["detalhes"][p]["etapa"] == chave for p in col["cartoes"])
    # Os quatro serviços somam o "todos" em cada etapa.
    for chave in dados["totais"]:
        por_servico = sum(dados["colunas"][f"{s}|{chave}"]["total"] for s in dados["servicos"])
        assert por_servico == dados["totais"][chave]


def test_detalhe_fecha_a_conta(pastas, monkeypatch):
    monkeypatch.setattr(jornada, "PASTA_TRATADO", pastas["tratado"])
    for d in jornada.montar()["detalhes"].values():
        assert d["agendamentos"] == len(d["agenda"])
        assert d["realizados"] + d["faltas"] + d["cancelados"] == d["agendamentos"]
