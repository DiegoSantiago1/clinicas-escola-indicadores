"""Gera as fontes e a base tratada uma vez por execução, numa pasta temporária.

Assim os testes não dependem dos arquivos versionados em data/ e não deixam resíduo.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from clinicas.fontes import gerar
from clinicas.padronizar import padronizar


@pytest.fixture(scope="session")
def pastas(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    raiz = tmp_path_factory.mktemp("clinicas")
    fontes = raiz / "fontes"
    gerar(destino=fontes)
    padronizar(fontes=fontes, destino=raiz / "tratado")
    return {"raiz": raiz, "fontes": fontes, "tratado": raiz / "tratado", "verdade": raiz / "verdade"}


@pytest.fixture(scope="session")
def manifesto(pastas: dict[str, Path]) -> dict:
    return json.loads((pastas["fontes"] / "manifesto.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def tratado(pastas: dict[str, Path]) -> pd.DataFrame:
    return pd.read_csv(pastas["tratado"] / "atendimentos.csv", dtype=str)


@pytest.fixture(scope="session")
def verdade(pastas: dict[str, Path]) -> pd.DataFrame:
    v = pd.read_csv(pastas["verdade"] / "atendimentos_verdade.csv", dtype=str)
    v["hora"] = v["hora"].str[:5]
    return v.rename(columns={"aluno": "matricula_aluno"})


@pytest.fixture(scope="session")
def resumo(pastas: dict[str, Path]) -> dict[str, int]:
    r = pd.read_csv(pastas["tratado"] / "resumo_qualidade.csv")
    return dict(zip(r["regra"], r["ocorrencias"], strict=True))
