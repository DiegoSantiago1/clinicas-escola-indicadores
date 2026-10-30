"""A padronização encontra exatamente o que foi plantado e devolve a verdade da simulação."""

import json
from pathlib import Path

import pandas as pd
import pytest

from clinicas.config import PASTA_FONTES
from clinicas.fontes import sha256


@pytest.mark.parametrize(("plantado", "regras", "fator"), [
    ("P01_linhas_repetidas_entre_meses", ["R01"], 1),
    ("P02_arquivos_com_coluna_CANAL", ["R02"], 1),
    ("P03_situacao_escrita_diferente", ["R03"], 1),
    ("P04_data_como_texto", ["R04"], 1),
    ("P05_horario_como_texto", ["R05"], 1),
    ("P06_nome_paciente_variante", ["R06"], 1),
    ("P07_prontuario_vazio", ["R07", "R07x"], 1),
    ("P08_linhas_duplicadas", ["R08"], 1),
    ("P09_linhas_de_total", ["R09"], 1),
    ("P10_linhas_em_branco", ["R10"], 1),
    ("P11_nome_aluno_variante", ["R11"], 1),
    ("P12_ano_digitado_errado", ["R12"], 1),
    ("P13_conflito_horario_aluno", ["R13"], 2),  # cada conflito envolve duas linhas
    ("P13b_tipo_em_branco", ["R13b"], 1),
    ("P14_unidade_ou_servico_escrito_diferente", ["R14"], 1),
    ("P15_primeira_consulta_antes_da_inscricao", ["R15"], 1),
    ("P16_motivo_escrito_livre", ["R16"], 1),
    ("P17_chamada_em_branco", ["R17"], 1),
    ("P18_chegada_registrada_duas_vezes", ["R18"], 1),
])
def test_cada_problema_plantado_e_encontrado(manifesto, resumo, plantado, regras, fator):
    esperado = manifesto["problemas_plantados"][plantado] * fator
    assert esperado > 0, "o gerador deixou de plantar o problema"
    assert sum(resumo[r] for r in regras) == esperado


def test_mesmo_numero_de_agendamentos_da_verdade(tratado, verdade, manifesto):
    assert len(tratado) == len(verdade) == manifesto["agendamentos_reais"]


def test_situacao_por_clinica_igual_a_verdade(tratado, verdade):
    chave = ["unidade", "servico", "situacao"]
    assert tratado.groupby(chave).size().equals(verdade.groupby(chave).size())


def test_linha_a_linha_igual_a_verdade(tratado, verdade):
    """Fora as linhas com horário alterado de propósito (R13), cada agendamento bate com a verdade."""
    chave = ["unidade", "servico", "data", "matricula_aluno", "hora"]
    sem_conflito = tratado[tratado["conflito_horario"] == "Não"]
    m = sem_conflito.merge(verdade, on=chave, suffixes=("", "_v"), validate="one_to_one")
    assert len(m) == len(sem_conflito)
    for coluna in ("situacao", "supervisor"):
        assert (m[coluna] == m[f"{coluna}_v"]).all(), coluna
    # O tipo só pode divergir onde não há prontuário (não dá para consultar a fila).
    divergentes = m[m["tipo"] != m["tipo_v"]]
    assert divergentes["prontuario"].isna().all()


def test_prontuario_recuperado_e_sempre_o_certo(tratado, verdade):
    chave = ["unidade", "servico", "data", "matricula_aluno", "hora"]
    rec = tratado[(tratado["prontuario_recuperado"] == "Sim") & (tratado["conflito_horario"] == "Não")]
    m = rec.merge(verdade, on=chave, suffixes=("", "_v"))
    assert len(m) == len(rec) > 1000
    assert (m["prontuario"] == m["prontuario_v"]).all()


def test_sem_prontuario_so_quando_ha_homonimo_ou_nome_desconhecido(tratado, resumo):
    assert tratado["prontuario"].isna().sum() == resumo["R07x"]
    assert resumo["R07x"] < 0.1 * (resumo["R07"] + resumo["R07x"])


def test_base_tratada_nao_leva_dado_pessoal_do_paciente(pastas):
    """Minimização (LGPD): nome e data de nascimento ficam só nas fontes."""
    atend = pd.read_csv(pastas["tratado"] / "atendimentos.csv", nrows=5)
    pac = pd.read_csv(pastas["tratado"] / "pacientes.csv", nrows=5)
    assert not {"paciente", "nome", "paciente_digitado"} & set(atend.columns)
    assert not {"nome", "data_nascimento"} & set(pac.columns)


def test_inconsistencias_apontam_arquivo_e_linha(pastas):
    inc = pd.read_csv(pastas["tratado"] / "inconsistencias.csv")
    planilhas = inc[inc["arquivo"].str.endswith(".xlsx")]
    assert planilhas["linha"].notna().all()
    assert (planilhas["linha"] >= 2).all()


def test_oferta_so_em_dias_abertos(pastas):
    oferta = pd.read_csv(pastas["tratado"] / "oferta.csv")
    cal = pd.read_csv(pastas["tratado"] / "calendario.csv")
    fechados = set(cal.loc[~cal["aberto"], "data"])
    assert not set(oferta["data"]) & fechados


def test_fontes_sao_reprodutiveis(manifesto):
    """Mesma semente, mesmos arquivos: os dados versionados em data/fontes batem com o gerador."""
    versionado = json.loads((PASTA_FONTES / "manifesto.json").read_text(encoding="utf-8"))
    assert manifesto["arquivos"] == versionado["arquivos"]


def test_hash_de_planilha_ignora_data_de_gravacao(tmp_path: Path):
    from openpyxl import Workbook

    caminhos = []
    for i in range(2):
        wb = Workbook()
        wb.active.append(["a", 1])
        wb.properties.modified = pd.Timestamp(f"2026-01-0{i + 1}").to_pydatetime()
        caminho = tmp_path / f"p{i}.xlsx"
        wb.save(caminho)
        caminhos.append(caminho)
    assert sha256(caminhos[0]) == sha256(caminhos[1])


@pytest.fixture(scope="session")
def com_verdade(tratado, verdade) -> pd.DataFrame:
    chave = ["unidade", "servico", "data", "matricula_aluno", "hora"]
    sem_conflito = tratado[tratado["conflito_horario"] == "Não"]
    return sem_conflito.merge(verdade, on=chave, suffixes=("", "_v"), validate="one_to_one")


def test_motivo_igual_a_verdade(com_verdade):
    """Com prontuário, o motivo da base tratada é o que a recepção ouviu do paciente."""
    m = com_verdade[com_verdade["prontuario"].notna() & com_verdade["motivo_v"].notna()]
    assert len(m) > 10_000
    assert (m["motivo"] == m["motivo_v"]).all()
    sem = com_verdade[com_verdade["prontuario"].isna() & com_verdade["situacao"].isin(
        ["Falta", "Cancelado pelo paciente"])]
    assert (sem["motivo"] == "Não identificado").all()
    assert com_verdade.loc[com_verdade["situacao"] == "Realizado", "motivo"].isna().all()


def test_espera_na_recepcao_igual_a_verdade(com_verdade):
    m = com_verdade[com_verdade["espera_recepcao_min"].notna()].copy()
    assert len(m) > 40_000
    minutos = pd.to_datetime(m["chamada"], format="%H:%M") - pd.to_datetime(m["chegada"], format="%H:%M")
    assert (m["espera_recepcao_min"].astype(float) == minutos.dt.total_seconds() / 60).all()
    assert (m["espera_recepcao_min"].astype(float) > 0).all()


def test_faturamento_igual_a_verdade(com_verdade, tratado, verdade):
    """Linha a linha igual; no total, a diferença é só o que ficou sem prontuário (sem saber se é isento)."""
    m = com_verdade[com_verdade["valor_cobrado"].notna()]
    assert (m["valor_cobrado"].astype(float) == m["valor_cobrado_v"].astype(float)).all()
    total_tratado = tratado["valor_cobrado"].astype(float).sum()
    total_verdade = verdade["valor_cobrado"].astype(float).sum()
    sem_valor = com_verdade[com_verdade["valor_cobrado"].isna()]
    assert set(sem_valor["prontuario"].isna()) == {True}
    assert 0 < total_verdade - total_tratado < 0.01 * total_verdade


def test_registro_da_recepcao_sem_agendamento_e_so_de_quem_ficou_sem_prontuario(com_verdade, resumo):
    """R19: o tablet sabe o prontuário, mas o agendamento dele perdeu o número na planilha (R07x)."""
    sem = com_verdade[com_verdade["prontuario"].isna()]
    com_registro = sem["chegada"].notna() | (sem["justificou"] == "True")
    assert resumo["R19"] <= resumo["R07x"]
    assert abs(resumo["R19"] - com_registro.sum()) <= resumo["R13"]  # linhas em conflito ficam fora do merge
