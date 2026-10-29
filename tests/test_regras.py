"""Regras pequenas, testadas com entradas hostis."""

from datetime import date, datetime, time

import pandas as pd
import pytest

from clinicas.indicadores import taxa_faltas
from clinicas.padronizar import SITUACAO, ler_data, ler_hora, norm


@pytest.mark.parametrize(("entrada", "esperado"), [
    ("  Ana   SOUZA ", "ana souza"),
    ("Jaboatão dos Guararapes", "jaboatao dos guararapes"),
    ("Nº prontuário", "no prontuario"),
    (None, ""),
    (123, "123"),
])
def test_norm(entrada, esperado):
    assert norm(entrada) == esperado


@pytest.mark.parametrize(("entrada", "esperado", "texto"), [
    (datetime(2026, 3, 5), date(2026, 3, 5), False),
    (date(2026, 3, 5), date(2026, 3, 5), False),
    ("05/03/2026", date(2026, 3, 5), True),
    ("5/3/26", date(2026, 3, 5), True),
    (" 05/03/2026 ", date(2026, 3, 5), True),
    ("2026-03-05", None, False),
    ("31/02/2026", None, False),
    ("", None, False),
    (None, None, False),
    (45000, None, False),
])
def test_ler_data(entrada, esperado, texto):
    assert ler_data(entrada) == (esperado, texto)


@pytest.mark.parametrize(("entrada", "esperado"), [
    (time(8, 0), time(8, 0)),
    (datetime(2026, 1, 1, 13, 30), time(13, 30)),
    ("8h", time(8, 0)),
    ("13h30", time(13, 30)),
    ("08:00", time(8, 0)),
    (" 8:00 ", time(8, 0)),
    ("oito", None),
    ("25h", None),
    ("8h75", None),
    (None, None),
])
def test_ler_hora(entrada, esperado):
    assert ler_hora(entrada)[0] == esperado


@pytest.mark.parametrize("escrita", ["Atendido", "atendido", "ATENDIDO", "Compareceu", "ok", " ok "])
def test_formas_de_atendido(escrita):
    assert SITUACAO[norm(escrita)] == "Realizado"


@pytest.mark.parametrize("escrita", ["Faltou", "falta", "F", "Não compareceu", "faltou "])
def test_formas_de_falta(escrita):
    assert SITUACAO[norm(escrita)] == "Falta"


def test_situacao_desconhecida_nao_e_adivinhada():
    assert norm("Remarcado") not in SITUACAO


def test_taxa_de_faltas_ignora_cancelamentos():
    a = pd.DataFrame({"situacao": ["Realizado"] * 3 + ["Falta"] + ["Cancelado pelo paciente"] * 6})
    assert taxa_faltas(a) == 0.25


def test_taxa_de_faltas_sem_base_e_zero():
    assert taxa_faltas(pd.DataFrame({"situacao": ["Cancelado pela clínica"]})) == 0.0
