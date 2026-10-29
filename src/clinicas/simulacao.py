"""Simula um ano de atendimentos da rede fictícia: a "verdade" antes de virar planilha.

A simulação anda dia a dia por clínica:
1. pacientes entram na fila de espera nos dias úteis (inclusive no recesso: a procura não para);
2. nos dias de atendimento, as sessões já marcadas acontecem (ou o paciente falta, desmarca,
   ou a clínica cancela porque o supervisor não veio);
3. a recepção chama a fila para os horários de primeira consulta que sobraram;
4. cada sessão realizada (ou com falta) marca a próxima, até o fim do tratamento ou o abandono.

As faltas não são sorteadas com uma taxa fixa: dependem do serviço, do dia da semana, do mês,
de quanto tempo o paciente esperou na fila e do histórico dele. É isso que dá ao painel padrões
para descobrir (registrados no manifesto, para conferir depois que o painel os encontra).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

from clinicas.config import (
    CLINICAS,
    FERIADOS,
    FIM,
    INICIO,
    PLANTAO_FERIAS,
    SEMESTRES,
    SERVICOS,
    TURNOS,
    Clinica,
)
from clinicas.nomes import gerar_nome, gerar_nomes_unicos

# A simulação começa no início do semestre 2025.2 para a rede já estar "cheia" em novembro
# (sem isso, novembro sairia vazio, um artefato de partida). Só o período INICIO..FIM é exportado.
AQUECIMENTO = date(2025, 8, 4)
# Ocupação que a procura tenta atingir numa clínica que funciona bem.
OCUPACAO_ALVO = 0.74
# Agendamentos que cada paciente gera em média (sessões + faltas + remarcações), medidos numa
# primeira rodada da simulação. Servem só para calibrar quantos pacientes novos chegam por dia.
AGENDAMENTOS_POR_PACIENTE = {"ODO": 4.2, "FIS": 7.0, "PSI": 6.3, "NUT": 2.7}
# Fração dos pacientes com propensão alta a faltar (padrão plantado I5).
FRACAO_FALTOSOS = 0.12
# Probabilidade, por turno, de o supervisor faltar e a clínica cancelar o turno inteiro.
P_SUPERVISOR_AUSENTE = 0.008
# Olinda/Fisioterapia só marca primeira consulta às segundas (padrão plantado I2).
DIAS_PRIMEIRA = {("OLI", "FIS"): {0, 2}}
# Aumento da chance de abandono depois de uma falta, por serviço.
ABANDONO_APOS_FALTA = {"ODO": 0.25, "FIS": 0.30, "PSI": 0.42, "NUT": 0.35}

PROCEDIMENTOS = {
    "ODO": ("Avaliação odontológica", ["Profilaxia", "Restauração", "Raspagem", "Endodontia", "Exodontia"]),
    "FIS": ("Avaliação fisioterapêutica", ["Sessão de fisioterapia"]),
    "PSI": ("Triagem psicológica", ["Sessão de psicoterapia"]),
    "NUT": ("Avaliação nutricional", ["Retorno nutricional"]),
}


def semestre_de(dia: date) -> str | None:
    for rotulo, inicio, fim in SEMESTRES:
        if inicio <= dia <= fim:
            return rotulo
    if PLANTAO_FERIAS[0] <= dia <= PLANTAO_FERIAS[1]:
        return "2026.1"  # o plantão de julho conta para o semestre que acabou de terminar
    return None


def fator_salas(dia: date) -> float:
    """1 em dia normal, 0,5 no plantão de férias, 0 com a clínica fechada."""
    if dia.weekday() >= 5 or dia in FERIADOS:
        return 0.0
    if PLANTAO_FERIAS[0] <= dia <= PLANTAO_FERIAS[1]:
        return 0.5
    if any(inicio <= dia <= fim for _, inicio, fim in SEMESTRES):
        return 1.0
    return 0.0


def dias_periodo() -> list[date]:
    return [INICIO + timedelta(days=i) for i in range((FIM - INICIO).days + 1)]


def horarios(servico: str) -> list[tuple[str, time]]:
    """Horários de início de sessão em cada turno, conforme a duração do serviço."""
    duracao = SERVICOS[servico].duracao_min
    saida = []
    for nome, inicio, fim in TURNOS:
        atual = datetime.combine(INICIO, inicio)
        limite = datetime.combine(INICIO, fim)
        while atual + timedelta(minutes=duracao) <= limite:
            saida.append((nome, atual.time()))
            atual += timedelta(minutes=duracao)
    return saida


@dataclass
class Paciente:
    prontuario: str
    nome: str
    sexo: str
    unidade: str
    servico: str
    data_inscricao: date
    faltoso: bool
    sessoes_previstas: int
    data_primeira: date | None = None
    data_saida_fila: date | None = None
    situacao_fila: str = "Aguardando"
    sessoes_feitas: int = 0
    faltas_seguidas: int = 0
    aluno: str | None = None
    desfecho: str | None = None
    agendadas: int = 0


@dataclass
class Agenda:
    """Horários ocupados por dia e horário, para não marcar duas sessões na mesma sala."""

    salas: int
    ocupados: dict[tuple[date, time], int] = field(default_factory=lambda: defaultdict(int))

    def livres(self, dia: date, hora: time) -> int:
        return math.floor(self.salas * fator_salas(dia)) - self.ocupados[(dia, hora)]

    def reservar(self, dia: date, hora: time) -> None:
        self.ocupados[(dia, hora)] += 1


def simular_clinica(clinica: Clinica, rng: np.random.Generator, alunos: pd.DataFrame,
                    contador: list[int]) -> tuple[list[dict], list[Paciente]]:
    serv = SERVICOS[clinica.servico]
    grade = horarios(clinica.servico)
    agenda = Agenda(clinica.salas)
    # Procura calibrada: horários ofertados no ano x ocupação-alvo / agendamentos por paciente,
    # espalhada pelos dias úteis (a procura continua no recesso, quando a clínica está fechada).
    ofertados = sum(math.floor(clinica.salas * fator_salas(d)) for d in dias_periodo()) * len(grade)
    dias_uteis = sum(1 for d in dias_periodo() if d.weekday() < 5 and d not in FERIADOS)
    chegadas_dia = (OCUPACAO_ALVO * ofertados / AGENDAMENTOS_POR_PACIENTE[clinica.servico] / dias_uteis
                    * clinica.demanda)
    dias_primeira = DIAS_PRIMEIRA.get((clinica.unidade, clinica.servico), {0, 1, 2, 3, 4})

    fila: list[Paciente] = []
    pacientes: list[Paciente] = []
    marcadas: dict[date, list[tuple[time, Paciente, str]]] = defaultdict(list)
    registros: list[dict] = []
    carga_aluno: dict[str, int] = defaultdict(int)

    alunos_clinica = alunos[(alunos["unidade"] == clinica.unidade) & (alunos["servico"] == clinica.servico)]
    alunos_por_semestre = {s: list(g["matricula"]) for s, g in alunos_clinica.groupby("semestre")}

    ocupado: set[tuple[str, date, time]] = set()

    def escolher_aluno(pac: Paciente, dia: date, hora: time) -> str:
        """O mesmo aluno acompanha o paciente; se ele já atende outro paciente nesse horário,
        um colega da turma cobre a sessão. Um aluno nunca tem dois pacientes ao mesmo tempo."""
        turma = alunos_por_semestre[semestre_de(dia)]
        if pac.aluno not in turma:
            pac.aluno = min(turma, key=lambda m: (carga_aluno[m], m))
            carga_aluno[pac.aluno] += 1
        escolhido = pac.aluno
        if (escolhido, dia, hora) in ocupado:
            livres = [m for m in turma if (m, dia, hora) not in ocupado]
            escolhido = min(livres, key=lambda m: (carga_aluno[m], m))
        ocupado.add((escolhido, dia, hora))
        return escolhido

    def marcar(pac: Paciente, desde: date, hora_pref: time, tipo: str) -> None:
        dia = desde
        while dia <= FIM:
            if agenda.livres(dia, hora_pref) > 0:
                agenda.reservar(dia, hora_pref)
                marcadas[dia].append((hora_pref, pac, tipo))
                pac.agendadas += 1
                return
            for _, hora in grade:
                if agenda.livres(dia, hora) > 0:
                    agenda.reservar(dia, hora)
                    marcadas[dia].append((hora, pac, tipo))
                    pac.agendadas += 1
                    return
            dia += timedelta(days=1)

    def atender(dia: date, hora: time, pac: Paciente, tipo: str, ausentes: set[str],
                supervisores: list[str]) -> None:
        turno = "Manhã" if hora < time(12, 0) else "Tarde"
        aluno = escolher_aluno(pac, dia, hora)
        indice_sup = (dia.weekday() * 2 + (turno == "Tarde")) % len(supervisores)
        if turno in ausentes:
            situacao = "Cancelado pela clínica"
        else:
            situacao = sortear_situacao(rng, pac, dia, hora, tipo, clinica.servico)
        if tipo == "Primeira consulta":
            procedimento = PROCEDIMENTOS[clinica.servico][0]
        else:
            opcoes = PROCEDIMENTOS[clinica.servico][1]
            procedimento = opcoes[int(rng.integers(len(opcoes)))]
        contador[1] += 1
        registros.append({
            "id_agendamento": contador[1],
            "data": dia,
            "hora": hora,
            "turno": turno,
            "unidade": clinica.unidade,
            "servico": clinica.servico,
            "prontuario": pac.prontuario,
            "paciente": pac.nome,
            "aluno": aluno,
            "supervisor": supervisores[indice_sup],
            "tipo": tipo,
            "procedimento": procedimento,
            "situacao": situacao,
            "duracao_min": serv.duracao_min,
            "semestre": semestre_de(dia),
        })
        proximo = atualizar_paciente(rng, pac, situacao, tipo, clinica.servico)
        if proximo is not None:
            marcar(pac, dia + timedelta(days=proximo), hora, "Retorno")

    dia = AQUECIMENTO
    while dia <= FIM:
        util = dia.weekday() < 5 and dia not in FERIADOS
        # 1. Chegadas na fila (mais procura em março e agosto, começo de semestre).
        if util:
            sazonal = 1.15 if dia.month in (3, 8) else 1.0
            for _ in range(rng.poisson(chegadas_dia * sazonal)):
                contador[0] += 1
                sexo = "F" if rng.random() < 0.62 else "M"
                pac = Paciente(
                    prontuario=f"{clinica.unidade}{contador[0]:06d}",
                    nome=gerar_nome(rng, sexo),
                    sexo=sexo,
                    unidade=clinica.unidade,
                    servico=clinica.servico,
                    data_inscricao=dia,
                    faltoso=bool(rng.random() < FRACAO_FALTOSOS),
                    sessoes_previstas=int(rng.integers(serv.sessoes[0], serv.sessoes[1] + 1)),
                )
                fila.append(pac)
                pacientes.append(pac)
            # Desistência de quem espera há mais de 30 dias (cerca de 2% por semana).
            for pac in list(fila):
                if (dia - pac.data_inscricao).days > 30 and rng.random() < 0.004:
                    pac.situacao_fila = "Desistiu"
                    pac.data_saida_fila = dia
                    fila.remove(pac)

        if fator_salas(dia) > 0:
            ausentes = {nome for nome, _, _ in TURNOS if rng.random() < P_SUPERVISOR_AUSENTE}
            supervisores = [f"{clinica.unidade}-{clinica.servico}-S{i + 1}" for i in range(clinica.supervisores)]

            # 2. A recepção chama a fila para os horários que ainda estão livres hoje.
            if dia.weekday() in dias_primeira:
                for _, hora in grade:
                    while agenda.livres(dia, hora) > 0 and fila:
                        if rng.random() > clinica.chamada_fila:
                            break  # não conseguiu contato; o horário fica vago
                        pac = fila.pop(0)
                        pac.data_primeira = dia
                        pac.data_saida_fila = dia
                        pac.situacao_fila = "Chamado"
                        agenda.reservar(dia, hora)
                        marcadas[dia].append((hora, pac, "Primeira consulta"))

            # 3. Todas as sessões de hoje, em ordem de horário.
            for hora, pac, tipo in sorted(marcadas.pop(dia, []), key=lambda x: (x[0], x[1].prontuario)):
                atender(dia, hora, pac, tipo, ausentes, supervisores)
        dia += timedelta(days=1)

    return registros, pacientes


def sortear_situacao(rng: np.random.Generator, pac: Paciente, dia: date, hora: time, tipo: str,
                     servico: str) -> str:
    p = SERVICOS[servico].falta_base
    if dia.weekday() == 0 and hora < time(12, 0):
        p += 0.07  # segunda de manhã (padrão I1)
    elif dia.weekday() == 4 and hora >= time(13, 0):
        p += 0.04  # sexta à tarde
    if dia.month == 12:
        p += 0.05  # fim de ano
    if tipo == "Primeira consulta" and pac.data_primeira is not None:
        espera = (pac.data_primeira - pac.data_inscricao).days
        p += min(0.20, 0.003 * espera)  # quanto mais esperou, mais falta (padrão I6)
    if pac.faltas_seguidas > 0:
        p += 0.10
    if pac.faltoso:
        p = min(0.85, p * 3.2)
    sorteio = rng.random()
    if sorteio < p:
        return "Falta"
    if sorteio < p + 0.04:
        return "Cancelado pelo paciente"
    return "Realizado"


def atualizar_paciente(rng: np.random.Generator, pac: Paciente, situacao: str, tipo: str,
                       servico: str) -> int | None:
    """Atualiza o tratamento e devolve em quantos dias marcar a próxima sessão (ou None)."""
    serv = SERVICOS[servico]
    if situacao == "Realizado":
        pac.sessoes_feitas += 1
        pac.faltas_seguidas = 0
        if pac.sessoes_feitas >= pac.sessoes_previstas:
            pac.desfecho = "Alta"
            return None
        return serv.intervalo_dias
    if situacao == "Falta":
        pac.faltas_seguidas += 1
        chance = ABANDONO_APOS_FALTA[servico] * (2.2 if pac.faltas_seguidas >= 2 else 1.0)
        if tipo == "Primeira consulta":
            chance += 0.15
        if rng.random() < min(0.9, chance):
            pac.desfecho = "Abandono"
            return None
        return serv.intervalo_dias
    # Cancelado: remarca em poucos dias, sem contar como falta.
    return 2 if serv.intervalo_dias <= 3 else serv.intervalo_dias // 2


def relevante(p: Paciente, com_sessao: set[str]) -> bool:
    """Paciente aparece nos dados se teve sessão no período ou estava na fila em algum momento dele."""
    if p.prontuario in com_sessao:
        return True
    return p.data_saida_fila is None or p.data_saida_fila >= INICIO


def gerar_alunos(rng: np.random.Generator) -> pd.DataFrame:
    linhas = []
    total = sum(c.alunos_por_semestre for c in CLINICAS) * len(SEMESTRES)
    nomes = gerar_nomes_unicos(rng, total)
    i = 0
    for rotulo, _, _ in SEMESTRES:
        for clinica in CLINICAS:
            for _ in range(clinica.alunos_por_semestre):
                linhas.append({
                    "matricula": f"{2020 + int(rotulo[:4]) - 2020}{rotulo[-1]}{10000 + i:05d}",
                    "nome": nomes[i],
                    "curso": SERVICOS[clinica.servico].nome,
                    "semestre": rotulo,
                    "unidade": clinica.unidade,
                    "servico": clinica.servico,
                    "meta_horas_semestre": SERVICOS[clinica.servico].meta_horas_semestre,
                })
                i += 1
    return pd.DataFrame(linhas)


def simular(semente: int) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(semente)
    alunos = gerar_alunos(rng)
    contador = [0, 0]
    todos_registros: list[dict] = []
    todos_pacientes: list[Paciente] = []
    for clinica in CLINICAS:
        registros, pacientes = simular_clinica(clinica, rng, alunos, contador)
        todos_registros.extend(registros)
        todos_pacientes.extend(pacientes)

    atend = pd.DataFrame(todos_registros)
    atend = atend[atend["data"] >= INICIO].sort_values(["data", "hora", "unidade", "servico", "id_agendamento"])
    atend = atend.reset_index(drop=True)
    prontuarios_no_periodo = set(atend["prontuario"])
    pacientes = pd.DataFrame([{
        "prontuario": p.prontuario,
        "nome": p.nome,
        "unidade": p.unidade,
        "servico": p.servico,
        "data_inscricao": p.data_inscricao,
        "data_primeira": p.data_primeira,
        "situacao_fila": p.situacao_fila if p.data_primeira is None else "Chamado",
        "data_saida_fila": p.data_saida_fila,
        "sexo": p.sexo,
        "faltoso": p.faltoso,
        "desfecho": p.desfecho or ("Em tratamento" if p.data_primeira else None),
    } for p in todos_pacientes if relevante(p, prontuarios_no_periodo)])
    nascimento_dias = rng.integers(18 * 365, 80 * 365, len(pacientes))
    pacientes["data_nascimento"] = [FIM - timedelta(days=int(d)) for d in nascimento_dias]
    return {"atendimentos": atend, "pacientes": pacientes, "alunos": alunos}
