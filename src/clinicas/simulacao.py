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

A recepção (motivo de falta ou desmarcação, horário de chegada e de chamada) e a taxa social
usam um gerador aleatório próprio: acrescentá-las não muda nenhum sorteio da agenda, então
fila, faltas e atendimentos continuam idênticos aos da primeira versão.
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
    FRACAO_ISENTOS,
    INICIO,
    PLANTAO_FERIAS,
    SEMESTRES,
    SERVICOS,
    TAXA_SOCIAL,
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

# Motivos que a recepção registra (pesos base; sortear_motivo ajusta pelo contexto).
MOTIVOS_FALTA = {"Esqueceu": 0.26, "Trabalho": 0.20, "Transporte": 0.14, "Doença": 0.16, "Chuva": 0.06,
                 "Família": 0.10, "Compromisso pessoal": 0.08}
MOTIVOS_DESMARCACAO = {"Trabalho": 0.24, "Doença": 0.22, "Compromisso pessoal": 0.20, "Transporte": 0.08,
                       "Chuva": 0.05, "Família": 0.11, "Sentiu melhora": 0.10}
# Fração das faltas que o paciente justifica depois (o resto fica "Sem justificativa").
JUSTIFICA_FALTA = 0.62
# Atraso para chamar o paciente, em minutos: a recepção de Recife atende quatro clínicas;
# a Odontologia precisa montar e esterilizar o equipo antes de cada paciente.
ATRASO_RECEPCAO = {"REC": 9.0, "OLI": 4.0, "JAB": 5.0}
ATRASO_SERVICO = {"ODO": 6.0, "FIS": 2.0, "PSI": 0.0, "NUT": 1.0}
# Cada horário seguinte do turno herda o atraso do anterior (efeito cascata).
ATRASO_CASCATA = {"ODO": 7.0, "FIS": 2.0, "PSI": 1.5, "NUT": 2.0}

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
                    contador: list[int], rng_recepcao: np.random.Generator) -> tuple[list[dict], list[Paciente]]:
    serv = SERVICOS[clinica.servico]
    grade = horarios(clinica.servico)
    posicao_no_turno = {}
    for nome, _, _ in TURNOS:
        for k, hora_turno in enumerate(h for t, h in grade if t == nome):
            posicao_no_turno[hora_turno] = k
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
            "valor_tabela": TAXA_SOCIAL[procedimento],
            **recepcao(rng_recepcao, pac, dia, hora, tipo, situacao, clinica, posicao_no_turno[hora]),
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


def sortear_motivo(rng: np.random.Generator, pesos_base: dict[str, float], pac: Paciente, dia: date,
                   hora: time, tipo: str) -> str:
    """Motivo de falta ou desmarcação. Padrões plantados M1 a M4 (ver o manifesto)."""
    pesos = dict(pesos_base)
    manha = hora < time(12, 0)
    if 4 <= dia.month <= 7:
        pesos["Chuva"] *= 4.0 * (1.3 if manha else 1.0)  # M1: inverno chuvoso de Pernambuco
    if dia.weekday() == 0:
        pesos["Trabalho"] *= 1.8  # M2: segunda-feira
    if manha:
        pesos["Trabalho"] *= 1.3
    if pac.unidade == "JAB":
        pesos["Transporte"] *= 2.2  # M3: Jaboatão, pacientes vêm de mais longe
    if hora == time(8, 0):
        pesos["Transporte"] *= 1.6
    if "Esqueceu" in pesos:  # só falta: quem desmarca lembrou da consulta
        if pac.servico == "NUT":
            pesos["Esqueceu"] *= 1.8  # M4: retorno a cada 21 dias, o paciente esquece
        if tipo == "Primeira consulta" and pac.data_primeira and (pac.data_primeira - pac.data_inscricao).days > 45:
            pesos["Esqueceu"] *= 1.8  # M4: esperou tanto que já não contava com a vaga
    if "Sentiu melhora" in pesos:
        if tipo == "Primeira consulta":
            pesos["Sentiu melhora"] = 0.0
        elif pac.servico not in ("FIS", "PSI"):
            pesos["Sentiu melhora"] *= 0.3
    nomes = list(pesos)
    p = np.array([pesos[n] for n in nomes])
    return nomes[int(rng.choice(len(nomes), p=p / p.sum()))]


def recepcao(rng: np.random.Generator, pac: Paciente, dia: date, hora: time, tipo: str, situacao: str,
             clinica: Clinica, posicao: int) -> dict:
    """O que a recepção vê: motivo (falta ou desmarcação) e, se o paciente veio, chegada e chamada."""
    saida: dict = {"motivo": None, "justificou": False, "chegada": None, "chamada": None}
    if situacao == "Falta":
        motivo = sortear_motivo(rng, MOTIVOS_FALTA, pac, dia, hora, tipo)
        if rng.random() < JUSTIFICA_FALTA:
            saida.update(motivo=motivo, justificou=True)
        else:
            saida["motivo"] = "Sem justificativa"
    elif situacao == "Cancelado pelo paciente":
        saida.update(motivo=sortear_motivo(rng, MOTIVOS_DESMARCACAO, pac, dia, hora, tipo), justificou=True)
    elif situacao == "Cancelado pela clínica":
        saida["motivo"] = "Supervisor ausente"
    else:
        marcado = datetime.combine(dia, hora)
        if rng.random() < 0.12:
            chegada = marcado + timedelta(minutes=int(rng.integers(1, 16)))  # chegou atrasado
        else:
            chegada = marcado - timedelta(minutes=int(rng.integers(0, 26)))
        atraso = (ATRASO_RECEPCAO[clinica.unidade] + ATRASO_SERVICO[clinica.servico]
                  + ATRASO_CASCATA[clinica.servico] * posicao + rng.exponential(4.0))
        if dia.weekday() == 0 and hora < time(12, 0):
            atraso += 5.0  # segunda de manhã: fila no balcão
        chamada = max(chegada + timedelta(minutes=1), marcado + timedelta(minutes=round(atraso)))
        saida.update(chegada=chegada.strftime("%H:%M"), chamada=chamada.strftime("%H:%M"))
    return saida


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
    rng_recepcao = np.random.default_rng(semente + 7)
    alunos = gerar_alunos(rng)
    contador = [0, 0]
    todos_registros: list[dict] = []
    todos_pacientes: list[Paciente] = []
    for clinica in CLINICAS:
        registros, pacientes = simular_clinica(clinica, rng, alunos, contador, rng_recepcao)
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
    # Isenção da taxa social (cadastro socioeconômico): quem é isento não paga nada.
    pacientes["isento_taxa"] = rng_recepcao.random(len(pacientes)) < FRACAO_ISENTOS
    isento = dict(zip(pacientes["prontuario"], pacientes["isento_taxa"], strict=True))
    pago = (atend["situacao"] == "Realizado") & ~atend["prontuario"].map(isento).astype(bool)
    atend["valor_cobrado"] = atend["valor_tabela"].where(pago, 0)
    return {"atendimentos": atend, "pacientes": pacientes, "alunos": alunos}
