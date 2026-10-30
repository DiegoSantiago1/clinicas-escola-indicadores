"""Cadastro fixo da rede fictícia: unidades, serviços, salas, calendário e metas.

Tudo aqui é inventado. Os números foram escolhidos para parecer com uma clínica-escola
de verdade (turnos de manhã e de tarde, recesso entre semestres, alunos com meta de horas),
não para reproduzir nenhuma instituição real.
"""

from dataclasses import dataclass
from datetime import date, time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PASTA_FONTES = RAIZ / "data" / "fontes"
PASTA_TRATADO = RAIZ / "data" / "tratado"

REDE = "Rede Acolher de Clínicas-Escola"
SEMENTE = 20261103

INICIO = date(2025, 11, 1)
FIM = date(2026, 10, 31)

UNIDADES = {
    "REC": "Recife",
    "OLI": "Olinda",
    "JAB": "Jaboatão dos Guararapes",
}


@dataclass(frozen=True)
class Servico:
    codigo: str
    nome: str
    duracao_min: int
    # Intervalo entre sessões do mesmo tratamento, em dias.
    intervalo_dias: int
    # Faixa de sessões previstas por tratamento (mínimo, máximo).
    sessoes: tuple[int, int]
    # Probabilidade base de o paciente faltar.
    falta_base: float
    # Meta de horas de prática por aluno em um semestre completo.
    meta_horas_semestre: int
    # Onde o registro nasce: "sistema" (exportação CSV) ou "planilha" (Excel preenchido à mão).
    origem: str


SERVICOS = {
    "ODO": Servico("ODO", "Odontologia", 120, 7, (3, 6), 0.10, 210, "sistema"),
    "FIS": Servico("FIS", "Fisioterapia", 60, 3, (8, 12), 0.12, 165, "sistema"),
    "PSI": Servico("PSI", "Psicologia", 60, 7, (8, 16), 0.17, 200, "planilha"),
    "NUT": Servico("NUT", "Nutrição", 60, 21, (2, 4), 0.11, 200, "planilha"),
}


@dataclass(frozen=True)
class Clinica:
    unidade: str
    servico: str
    salas: int
    alunos_por_semestre: int
    supervisores: int
    # Procura relativa: 1,0 = pacientes novos suficientes para ocupar ~84% da agenda.
    demanda: float
    # Fração dos horários livres de primeira consulta que a recepção oferece à fila.
    # Abaixo de 1 = a fila não é chamada para todos os horários vagos.
    chamada_fila: float = 0.97


CLINICAS = [
    Clinica("REC", "ODO", 10, 30, 4, 1.2),
    Clinica("REC", "FIS", 8, 24, 3, 1.05),
    Clinica("REC", "PSI", 8, 24, 3, 1.24),
    Clinica("REC", "NUT", 4, 12, 2, 1.0),
    Clinica("OLI", "ODO", 6, 18, 3, 1.08),
    # Olinda/Fisioterapia: a fila cresce com a agenda sobrando (padrão plantado I2).
    Clinica("OLI", "FIS", 6, 18, 2, 0.95, chamada_fila=0.6),
    Clinica("OLI", "PSI", 5, 15, 2, 1.1),
    Clinica("JAB", "ODO", 6, 18, 3, 1.04),
    Clinica("JAB", "PSI", 5, 15, 2, 1.08),
    Clinica("JAB", "NUT", 3, 9, 1, 0.95),
]

# Taxa social por procedimento realizado, em reais (valores inventados; falta e desmarcação não pagam).
TAXA_SOCIAL = {
    "Avaliação odontológica": 20.0, "Profilaxia": 30.0, "Restauração": 45.0, "Raspagem": 40.0,
    "Endodontia": 90.0, "Exodontia": 50.0,
    "Avaliação fisioterapêutica": 25.0, "Sessão de fisioterapia": 20.0,
    "Triagem psicológica": 15.0, "Sessão de psicoterapia": 20.0,
    "Avaliação nutricional": 20.0, "Retorno nutricional": 15.0,
}
# Pacientes isentos da taxa pelo cadastro socioeconômico.
FRACAO_ISENTOS = 0.28

# Turnos de atendimento: (nome, início, fim).
TURNOS = [("Manhã", time(8, 0), time(12, 0)), ("Tarde", time(13, 30), time(17, 30))]

# Semestres letivos: (rótulo, início, fim). As clínicas fecham fora deles,
# exceto em julho, quando funcionam com metade das salas (plantão de férias).
SEMESTRES = [
    ("2025.2", date(2025, 8, 4), date(2025, 12, 19)),
    ("2026.1", date(2026, 2, 2), date(2026, 7, 3)),
    ("2026.2", date(2026, 8, 3), date(2026, 12, 18)),
]
PLANTAO_FERIAS = (date(2026, 7, 6), date(2026, 7, 31))

# Dias em que a rede fecha: feriados nacionais, Carnaval, Sexta-feira Santa,
# Corpus Christi e São João (calendário único da rede fictícia, igual nas três unidades).
FERIADOS = {
    date(2025, 11, 15): "Proclamação da República",
    date(2025, 11, 20): "Dia da Consciência Negra",
    date(2025, 12, 25): "Natal",
    date(2026, 1, 1): "Confraternização Universal",
    date(2026, 2, 16): "Carnaval",
    date(2026, 2, 17): "Carnaval",
    date(2026, 4, 3): "Sexta-feira Santa",
    date(2026, 4, 21): "Tiradentes",
    date(2026, 5, 1): "Dia do Trabalho",
    date(2026, 6, 4): "Corpus Christi",
    date(2026, 6, 24): "São João",
    date(2026, 9, 7): "Independência",
    date(2026, 10, 12): "Nossa Senhora Aparecida",
}
