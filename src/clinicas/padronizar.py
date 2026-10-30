"""Padroniza as fontes e gera a base tratada que o Power BI e o Looker Studio leem.

Regras (cada uma registrada no resumo de qualidade; as que afetam uma linha específica também
vão para inconsistencias.csv, com arquivo, aba e linha para a pessoa conferir na origem):

R01 agendamento repetido entre exportações mensais do sistema ........ removido
R02 coluna nova no sistema (CANAL) ................................... ignorada
R03 situação escrita de outro jeito ("faltou", "F", "ok"...) ......... padronizada
R04 data digitada como texto ........................................ convertida
R05 horário digitado como texto ("8h") .............................. convertido
R06 nome do paciente diferente do cadastro .......................... cadastro prevalece
R07 prontuário em branco ............................................ recuperado pelo nome (ou sinalizado)
R08 linha copiada duas vezes ........................................ removida
R09 linha de total no fim da aba .................................... removida
R10 linha em branco ................................................. removida
R11 nome do aluno diferente do cadastro ............................. ligado à matrícula
R12 ano digitado errado (fora do mês da aba) ........................ corrigido pelo mês da aba
R13 aluno com dois pacientes no mesmo horário ....................... sinalizado (mantido)
R13b tipo de atendimento em branco .................................. deduzido pela fila de espera
R14 unidade/serviço escrito de outro jeito na fila ................... padronizado
R15 1ª consulta antes da inscrição na fila .......................... corrigida pelos atendimentos
R16 motivo digitado em texto livre no tablet da recepção ............. classificado
R17 chegada sem o horário em que o paciente foi chamado .............. fora da média de espera
R18 chegada registrada duas vezes (cartão passado de novo) ........... mantida a primeira
R19 registro da recepção sem agendamento correspondente .............. sinalizado

Faturamento: a taxa social da tabela vale só para atendimento realizado de paciente não isento.
Atendimento sem prontuário (R07x) fica sem valor: não dá para saber se o paciente é isento.

Uso: python -m clinicas.padronizar
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from clinicas.config import PASTA_FONTES, PASTA_TRATADO, SEMESTRES, SERVICOS, UNIDADES
from clinicas.simulacao import PROCEDIMENTOS

MESES = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10,
         "NOV": 11, "DEZ": 12}
NOMES_MES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

DESCRICAO_REGRA = {
    "R01": ("Agendamento repetido entre exportações mensais do sistema", "removido"),
    "R02": ("Coluna nova no sistema a partir de mai/2026 (CANAL)", "ignorada"),
    "R03": ("Situação escrita de outro jeito", "padronizada"),
    "R04": ("Data digitada como texto", "convertida"),
    "R05": ("Horário digitado como texto", "convertido"),
    "R06": ("Nome do paciente diferente do cadastro", "cadastro prevalece"),
    "R07": ("Prontuário em branco", "recuperado pelo nome"),
    "R07x": ("Prontuário em branco sem como recuperar", "sinalizado"),
    "R08": ("Linha copiada duas vezes", "removida"),
    "R09": ("Linha de total no fim da aba", "removida"),
    "R10": ("Linha em branco", "removida"),
    "R11": ("Nome do aluno diferente do cadastro", "ligado à matrícula"),
    "R12": ("Ano digitado errado (fora do mês da aba)", "corrigido pelo mês da aba"),
    "R13": ("Aluno com dois pacientes no mesmo horário", "sinalizado"),
    "R13b": ("Tipo de atendimento em branco", "deduzido pela fila"),
    "R14": ("Unidade ou serviço escrito de outro jeito na fila", "padronizado"),
    "R15": ("1ª consulta antes da inscrição na fila", "corrigida pelos atendimentos"),
    "R16": ("Motivo digitado em texto livre na recepção", "classificado"),
    "R17": ("Chegada sem o horário de chamada", "fora da média de espera"),
    "R18": ("Chegada registrada duas vezes", "mantida a primeira"),
    "R19": ("Registro da recepção sem agendamento correspondente", "sinalizado"),
}
# Regras que viram uma linha em inconsistencias.csv (as demais só são contadas).
REGRAS_POR_LINHA = {"R01", "R07", "R07x", "R08", "R09", "R10", "R12", "R13", "R15", "R17", "R18", "R19"}

SITUACAO = {
    "atendido": "Realizado", "compareceu": "Realizado", "ok": "Realizado", "r": "Realizado",
    "faltou": "Falta", "falta": "Falta", "f": "Falta", "nao compareceu": "Falta",
    "desmarcou": "Cancelado pelo paciente", "paciente desmarcou": "Cancelado pelo paciente",
    "desmarcado": "Cancelado pelo paciente", "cp": "Cancelado pelo paciente",
    "cancelado (supervisor ausente)": "Cancelado pela clínica", "clinica cancelou": "Cancelado pela clínica",
    "cc": "Cancelado pela clínica",
}
SITUACAO_CANONICA = {"Atendido", "Faltou", "Desmarcou", "Cancelado (supervisor ausente)"}
UNIDADE = {"recife": "REC", "rec": "REC", "clin recife": "REC", "olinda": "OLI", "clin olinda": "OLI",
           "jaboatao": "JAB", "jaboatao dos guararapes": "JAB", "clin jaboatao": "JAB"}
SERVICO = {"odontologia": "ODO", "odonto": "ODO", "fisioterapia": "FIS", "fisio": "FIS",
           "psicologia": "PSI", "psico": "PSI", "nutricao": "NUT"}
TIPO = {"1a consulta": "Primeira consulta", "1a vez": "Primeira consulta", "sim": "Primeira consulta",
        "retorno": "Retorno", "nao": "Retorno"}
# Motivos como a recepção digita (já normalizados por norm) e a categoria de cada um.
MOTIVO = {
    "esqueceu": "Esqueceu", "esqueceu da consulta": "Esqueceu", "paciente esqueceu": "Esqueceu",
    "nao lembrou": "Esqueceu",
    "trabalho": "Trabalho", "nao foi liberado do trabalho": "Trabalho", "horario de trabalho": "Trabalho",
    "transporte": "Transporte", "sem passagem": "Transporte", "onibus atrasou": "Transporte",
    "sem transporte": "Transporte",
    "doenca": "Doença", "estava doente": "Doença", "gripe": "Doença", "doente": "Doença",
    "chuva": "Chuva", "choveu muito": "Chuva", "rua alagada": "Chuva", "chuva forte": "Chuva",
    "familia": "Família", "problema familiar": "Família", "filho doente": "Família",
    "problema na familia": "Família",
    "compromisso pessoal": "Compromisso pessoal", "compromisso": "Compromisso pessoal",
    "outro compromisso": "Compromisso pessoal",
    "sentiu melhora": "Sentiu melhora", "melhorou": "Sentiu melhora", "disse que esta melhor": "Sentiu melhora",
}
MOTIVO_CANONICO = set(MOTIVO.values())
COLUNAS_PLANILHA = {
    "data": "data", "dt atendimento": "data",
    "horario": "hora", "hora": "hora",
    "paciente": "paciente", "nome do paciente": "paciente",
    "prontuario": "prontuario", "no prontuario": "prontuario",
    "estagiario(a)": "aluno", "aluno(a)": "aluno",
    "supervisor(a)": "supervisor", "professor(a)": "supervisor",
    "tipo": "tipo", "primeira vez?": "tipo",
    "situacao": "situacao", "status": "situacao",
    "observacao": "observacao",
}


def norm(texto: object) -> str:
    """Minúsculas, sem acento e sem espaços repetidos: a chave para comparar textos digitados à mão."""
    if texto is None:
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c)).replace("º", "o").replace("ª", "a")
    return re.sub(r"\s+", " ", s).strip().lower()


@dataclass
class Registro:
    """Junta as contagens de cada regra e as linhas que precisam ser conferidas na origem."""

    contagem: Counter = field(default_factory=Counter)
    linhas: list[dict] = field(default_factory=list)

    def anotar(self, regra: str, arquivo: str = "", aba: str = "", linha: int | None = None,
               valor_original: object = "", valor_final: object = "") -> None:
        self.contagem[regra] += 1
        if regra in REGRAS_POR_LINHA:
            descricao, acao = DESCRICAO_REGRA[regra]
            self.linhas.append({
                "regra": regra, "descricao": descricao, "acao": acao, "arquivo": arquivo, "aba": aba,
                "linha": linha, "valor_original": "" if valor_original is None else str(valor_original),
                "valor_final": "" if valor_final is None else str(valor_final),
            })


def ler_data(valor: object) -> tuple[date | None, bool]:
    """Devolve (data, veio_como_texto)."""
    if isinstance(valor, datetime):
        return valor.date(), False
    if isinstance(valor, date):
        return valor, False
    if isinstance(valor, str):
        for formato in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(valor.strip(), formato).date(), True
            except ValueError:
                pass
    return None, False


def ler_hora(valor: object) -> tuple[time | None, bool]:
    if isinstance(valor, time):
        return valor, False
    if isinstance(valor, datetime):
        return valor.time(), False
    if isinstance(valor, str):
        m = re.fullmatch(r"\s*(\d{1,2})\s*[h:]\s*(\d{2})?\s*", valor)
        if m:
            try:
                return time(int(m.group(1)), int(m.group(2) or 0)), True
            except ValueError:  # "25h", "8h75"
                return None, False
    return None, False


def procedimento_padrao() -> dict[str, str]:
    saida = {}
    for primeira, demais in PROCEDIMENTOS.values():
        for nome in [primeira, *demais]:
            saida[norm(nome)] = nome
    return saida


def ler_cadastros(fontes: Path) -> dict[str, pd.DataFrame]:
    cad = fontes / "cadastros"
    return {
        "pacientes": pd.read_csv(cad / "pacientes.csv", dtype=str),
        "alunos": pd.read_csv(cad / "alunos.csv", dtype={"matricula": str, "semestre": str}),
        "supervisores": pd.read_csv(cad / "supervisores.csv", dtype=str),
        "grade": pd.read_csv(cad / "grade_horarios.csv"),
        "calendario": pd.read_csv(cad / "calendario_rede.csv"),
        "taxa": pd.read_csv(cad / "tabela_taxa_social.csv"),
    }


def ler_sistema(fontes: Path, cad: dict[str, pd.DataFrame], reg: Registro) -> pd.DataFrame:
    partes = []
    for caminho in sorted((fontes / "sistema").glob("agendamentos_*.csv")):
        df = pd.read_csv(caminho, sep=";", encoding="cp1252", dtype=str)
        if "CANAL" in df.columns:
            reg.anotar("R02")
            df = df.drop(columns=["CANAL"])
        df["arquivo"] = caminho.name
        df["linha"] = range(2, len(df) + 2)
        partes.append(df)
    bruto = pd.concat(partes, ignore_index=True)

    repetidos = bruto.duplicated("COD_AGENDAMENTO", keep="first")
    for r in bruto[repetidos].itertuples():
        reg.anotar("R01", r.arquivo, "", r.linha, f"COD_AGENDAMENTO {r.COD_AGENDAMENTO}", "")
    bruto = bruto[~repetidos]

    sup = dict(zip(cad["supervisores"]["nome"], cad["supervisores"]["codigo"], strict=True))
    proc = procedimento_padrao()
    df = pd.DataFrame({
        "id_atendimento": "SIS-" + bruto["COD_AGENDAMENTO"],
        "data": pd.to_datetime(bruto["DT_AGENDA"], format="%d/%m/%Y").dt.date,
        "hora": pd.to_datetime(bruto["HR_AGENDA"], format="%H:%M").dt.time,
        "unidade": bruto["UNIDADE"].map(lambda v: UNIDADE[norm(v)]),
        "servico": bruto["ESPECIALIDADE"].map(lambda v: SERVICO[norm(v)]),
        "prontuario": bruto["NR_PRONTUARIO"],
        "matricula_aluno": bruto["MATRICULA"],
        "supervisor": bruto["NM_SUPERVISOR"].map(sup),
        "tipo": bruto["TP_ATENDIMENTO"].map(lambda v: TIPO[norm(v)]),
        "procedimento": bruto["DS_PROCEDIMENTO"].map(lambda v: proc[norm(v)]),
        "situacao": bruto["ST_AGENDA"].map(lambda v: SITUACAO[norm(v)]),
        "origem": "Sistema",
        "arquivo": bruto["arquivo"],
        "prontuario_recuperado": False,
    })
    if df.isna().any().any():
        raise ValueError(f"Valor desconhecido na exportação do sistema: {df.columns[df.isna().any()].tolist()}")
    return df


def aba_para_mes(titulo: str) -> tuple[int, int]:
    mes, ano = titulo.split()
    return int(ano), MESES[mes.upper()]


def ler_planilhas(fontes: Path, cad: dict[str, pd.DataFrame], reg: Registro) -> pd.DataFrame:
    alunos = cad["alunos"]
    aluno_por_nome = {(norm(r.nome), r.semestre): r.matricula for r in alunos.itertuples()}
    sup = {norm(n): c for n, c in zip(cad["supervisores"]["nome"], cad["supervisores"]["codigo"], strict=True)}
    pac = cad["pacientes"]
    nome_cadastro = dict(zip(pac["prontuario"], pac["nome"], strict=True))
    linhas_saida: list[dict] = []

    for caminho in sorted((fontes / "planilhas").glob("*.xlsx")):
        servico_nome, unidade_nome = caminho.stem.split(" - ")
        servico = SERVICO[norm(servico_nome)]
        unidade = UNIDADE[norm(unidade_nome)]
        wb = load_workbook(caminho, data_only=True, read_only=True)
        for ws in wb.worksheets:
            ano_aba, mes_aba = aba_para_mes(ws.title)
            linhas = ws.iter_rows(values_only=True)
            cabecalho = [COLUNAS_PLANILHA[norm(c)] for c in next(linhas)]
            vistas: set[tuple] = set()
            for numero, valores in enumerate(linhas, start=2):
                if all(v is None or str(v).strip() == "" for v in valores):
                    reg.anotar("R10", caminho.name, ws.title, numero)
                    continue
                if isinstance(valores[0], str) and norm(valores[0]).startswith("total"):
                    reg.anotar("R09", caminho.name, ws.title, numero, " | ".join(str(v) for v in valores if v))
                    continue
                if valores in vistas:
                    reg.anotar("R08", caminho.name, ws.title, numero, f"{valores[2]} {valores[0]}")
                    continue
                vistas.add(valores)
                v = dict(zip(cabecalho, valores, strict=False))

                dia, texto = ler_data(v["data"])
                if dia is None:
                    raise ValueError(f"{caminho.name} {ws.title} linha {numero}: data ilegível {v['data']!r}")
                if texto:
                    reg.anotar("R04")
                if (dia.year, dia.month) != (ano_aba, mes_aba):
                    if dia.month == mes_aba:
                        corrigida = dia.replace(year=ano_aba)
                        reg.anotar("R12", caminho.name, ws.title, numero, dia.isoformat(), corrigida.isoformat())
                        dia = corrigida
                    else:
                        raise ValueError(f"{caminho.name} {ws.title} linha {numero}: data {dia} fora da aba")
                hora, texto = ler_hora(v["hora"])
                if hora is None:
                    raise ValueError(f"{caminho.name} {ws.title} linha {numero}: horário ilegível {v['hora']!r}")
                if texto:
                    reg.anotar("R05")

                situacao_original = str(v["situacao"])
                situacao = SITUACAO.get(norm(situacao_original))
                if situacao is None:
                    raise ValueError(f"{caminho.name} {ws.title} linha {numero}: situação desconhecida "
                                     f"{situacao_original!r}. Acrescente a forma nova ao dicionário SITUACAO.")
                if situacao_original not in SITUACAO_CANONICA:
                    reg.anotar("R03")

                semestre = semestre_da_data(dia)
                matricula = aluno_por_nome.get((norm(v["aluno"]), semestre))
                if matricula is None:
                    raise ValueError(f"{caminho.name} {ws.title} linha {numero}: aluno {v['aluno']!r} não está "
                                     f"no cadastro do semestre {semestre}")
                if v["aluno"] != alunos.loc[alunos["matricula"] == matricula, "nome"].iloc[0]:
                    reg.anotar("R11")

                prontuario = str(v["prontuario"]).strip() if v["prontuario"] else None
                if prontuario and v["paciente"] != nome_cadastro.get(prontuario):
                    reg.anotar("R06")

                tipo = TIPO.get(norm(v["tipo"])) if v["tipo"] else None
                linhas_saida.append({
                    "id_atendimento": f"PLA-{servico}-{unidade}-{ano_aba}{mes_aba:02d}-{numero:04d}",
                    "data": dia,
                    "hora": hora,
                    "unidade": unidade,
                    "servico": servico,
                    "prontuario": prontuario,
                    "paciente_digitado": v["paciente"],
                    "matricula_aluno": matricula,
                    "supervisor": sup[norm(v["supervisor"])],
                    "tipo": tipo,
                    "procedimento": None,
                    "situacao": situacao,
                    "origem": "Planilha",
                    "arquivo": caminho.name,
                    "aba": ws.title,
                    "linha": numero,
                    "prontuario_recuperado": False,
                })
        wb.close()

    df = pd.DataFrame(linhas_saida)
    recuperar_prontuarios(df, pac, reg)
    return df


def recuperar_prontuarios(df: pd.DataFrame, pac: pd.DataFrame, reg: Registro) -> None:
    """R07: prontuário em branco é procurado pelo nome, na mesma unidade e serviço.

    Só recupera quando o nome é único no cadastro. Com homônimos, a linha fica sinalizada sem
    prontuário: na dúvida, é melhor um registro sem paciente do que um atendimento no paciente errado.
    """
    candidatos: dict[tuple, list[str]] = {}
    for r in pac.itertuples():
        candidatos.setdefault((norm(r.nome), r.unidade, r.servico), []).append(r.prontuario)
    for i in df.index[df["prontuario"].isna()]:
        chave = (norm(df.at[i, "paciente_digitado"]), df.at[i, "unidade"], df.at[i, "servico"])
        opcoes = candidatos.get(chave, [])
        if len(opcoes) == 1:
            df.at[i, "prontuario"] = opcoes[0]
            df.at[i, "prontuario_recuperado"] = True
            reg.anotar("R07", df.at[i, "arquivo"], df.at[i, "aba"], int(df.at[i, "linha"]),
                       df.at[i, "paciente_digitado"], opcoes[0])
        else:
            reg.anotar("R07x", df.at[i, "arquivo"], df.at[i, "aba"], int(df.at[i, "linha"]),
                       df.at[i, "paciente_digitado"], f"{len(opcoes)} candidatos")


def semestre_da_data(dia: date) -> str:
    for rotulo, inicio, fim in SEMESTRES:
        if inicio <= dia <= fim:
            return rotulo
    return "2026.1"  # plantão de julho conta para o semestre que terminou


def ler_fila(fontes: Path, reg: Registro) -> pd.DataFrame:
    wb = load_workbook(fontes / "Fila de espera - Recepção.xlsx", data_only=True, read_only=True)
    ws = wb["Fila"]
    linhas = ws.iter_rows(values_only=True)
    next(linhas)
    saida = []
    for numero, (unidade, servico, prontuario, _nome, inscricao, primeira, situacao) in enumerate(linhas, 2):
        if unidade not in ("Recife", "Olinda", "Jaboatão") or servico not in (
                "Odontologia", "Fisioterapia", "Psicologia", "Nutrição"):
            reg.anotar("R14")
        saida.append({
            "prontuario": str(prontuario),
            "unidade": UNIDADE[norm(unidade)],
            "servico": SERVICO[norm(servico)],
            "data_inscricao": inscricao.date(),
            "data_primeira": primeira.date() if primeira else None,
            "situacao": {"chamado": "Chamado", "atendido": "Chamado", "desistiu": "Desistiu",
                         "desistencia": "Desistiu", "aguardando": "Aguardando"}[norm(situacao)],
            "linha": numero,
        })
    wb.close()
    return pd.DataFrame(saida)


def ler_recepcao(fontes: Path, reg: Registro) -> pd.DataFrame:
    partes = []
    for caminho in sorted((fontes / "recepcao").glob("recepcao_*.csv")):
        df = pd.read_csv(caminho, encoding="utf-8-sig", dtype=str)
        df["arquivo"] = caminho.name
        df["linha"] = range(2, len(df) + 2)
        partes.append(df)
    rec = pd.concat(partes, ignore_index=True)
    rec["data"] = pd.to_datetime(rec["data"], format="%Y-%m-%d").dt.date
    rec["unidade"] = rec["unidade"].map(lambda v: UNIDADE[norm(v)])
    rec["servico"] = rec["servico"].map(lambda v: SERVICO[norm(v)])
    aviso = rec["registro"] == "AVISO"
    rec["motivo"] = None
    for i in rec.index[aviso]:
        texto = rec.at[i, "motivo_informado"]
        rec.at[i, "motivo"] = MOTIVO[norm(texto)]  # texto desconhecido: KeyError, não se adivinha
        if texto not in MOTIVO_CANONICO:
            reg.anotar("R16")
    return rec


def juntar_recepcao(atend: pd.DataFrame, rec: pd.DataFrame, reg: Registro) -> pd.DataFrame:
    """Liga cada registro do tablet ao agendamento do mesmo paciente no mesmo dia.

    Um paciente tem um só serviço e nunca duas sessões no mesmo dia, então (data, prontuário) basta.
    """
    chave = ["data", "prontuario"]
    chegadas = rec[rec["registro"] == "CHEGADA"]
    repetida = chegadas.duplicated(chave, keep="first")
    for r in chegadas[repetida].itertuples():
        reg.anotar("R18", r.arquivo, "", r.linha, f"{r.prontuario} {r.data} {r.chegada}", "removida")
    chegadas = chegadas[~repetida]
    for r in chegadas[chegadas["chamada"].isna()].itertuples():
        reg.anotar("R17", r.arquivo, "", r.linha, f"{r.prontuario} {r.data} chegada {r.chegada}", "sem espera")
    avisos = rec[rec["registro"] == "AVISO"]

    com_pront = atend.dropna(subset=["prontuario"])
    if com_pront.duplicated(chave).any():
        raise ValueError("Paciente com dois agendamentos no mesmo dia: (data, prontuário) deixou de ser chave")
    conhecidos = set(zip(com_pront["data"], com_pront["prontuario"], strict=True))
    for r in pd.concat([chegadas, avisos]).itertuples():
        if (r.data, r.prontuario) not in conhecidos:
            reg.anotar("R19", r.arquivo, "", r.linha, f"{r.registro} {r.prontuario} {r.data}", "")

    atend = atend.merge(chegadas[[*chave, "chegada", "chamada"]], on=chave, how="left", validate="many_to_one")
    atend = atend.merge(avisos[[*chave, "motivo"]], on=chave, how="left", validate="many_to_one")
    sem_pront = atend["prontuario"].isna()
    falta = atend["situacao"] == "Falta"
    atend.loc[falta & atend["motivo"].isna() & ~sem_pront, "motivo"] = "Sem justificativa"
    atend.loc[atend["situacao"] == "Cancelado pela clínica", "motivo"] = "Supervisor ausente"
    atend.loc[(falta | (atend["situacao"] == "Cancelado pelo paciente")) & sem_pront, "motivo"] = "Não identificado"

    def minutos(h: object) -> float:
        return float("nan") if not isinstance(h, str) else int(h[:2]) * 60 + int(h[3:5])

    atend["hora_chegada"] = atend["chegada"]
    atend["hora_chamada"] = atend["chamada"]
    atend["espera_recepcao_min"] = atend["chamada"].map(minutos) - atend["chegada"].map(minutos)
    return atend.drop(columns=["chegada", "chamada"])


def completar_tipo_e_fila(atend: pd.DataFrame, fila: pd.DataFrame, reg: Registro) -> None:
    """R15 e R13b: a fila e os atendimentos se corrigem um ao outro.

    Primeiro a fila é corrigida com os atendimentos que têm o tipo preenchido (R15); depois,
    com a fila já certa, deduz-se o tipo dos atendimentos em branco (R13b). A ordem importa:
    ao contrário, uma data errada da fila contaminaria a dedução.
    """
    # A 1ª consulta é o primeiro agendamento do paciente depois de entrar na fila. Se ele entrou na
    # fila antes do começo dos dados, a 1ª consulta pode ter sido antes também: aí não dá para saber.
    por_paciente = atend.dropna(subset=["prontuario"]).groupby("prontuario")["data"].apply(sorted)
    inicio_dados = atend["data"].min()
    for i in fila.index:
        prim, insc = fila.at[i, "data_primeira"], fila.at[i, "data_inscricao"]
        if prim is not None and prim < insc:
            datas = [d for d in por_paciente.get(fila.at[i, "prontuario"], []) if d >= insc]
            correta = datas[0] if datas and insc >= inicio_dados else None
            fila.at[i, "data_primeira"] = correta
            reg.anotar("R15", "Fila de espera - Recepção.xlsx", "Fila", int(fila.at[i, "linha"]),
                       prim.isoformat(), correta.isoformat() if correta else "sem atendimento")

    primeira_na_fila = dict(zip(fila["prontuario"], fila["data_primeira"], strict=True))
    for i in atend.index[atend["tipo"].isna()]:
        p = atend.at[i, "prontuario"]
        eh_primeira = p is not None and primeira_na_fila.get(p) == atend.at[i, "data"]
        atend.at[i, "tipo"] = "Primeira consulta" if eh_primeira else "Retorno"
        reg.anotar("R13b")


def marcar_conflitos(atend: pd.DataFrame, reg: Registro) -> None:
    chave = ["matricula_aluno", "data", "hora"]
    repetido = atend.duplicated(chave, keep=False) & (atend["origem"] == "Planilha")
    atend["conflito_horario"] = repetido
    for r in atend[repetido].sort_values(chave).itertuples():
        reg.anotar("R13", r.arquivo, r.aba, int(r.linha), f"aluno {r.matricula_aluno} {r.data} {r.hora}")


def montar_oferta(cad: dict[str, pd.DataFrame]) -> pd.DataFrame:
    cal = cad["calendario"]
    cal = cal[cal["fator_salas"] > 0]
    oferta = cal.merge(cad["grade"], how="cross")
    oferta["horarios_ofertados"] = (oferta["salas"] * oferta["fator_salas"]).astype(int) * oferta["horarios_por_sala"]
    return oferta[["data", "unidade", "servico", "turno", "horarios_ofertados"]].sort_values(
        ["data", "unidade", "servico", "turno"]).reset_index(drop=True)


def montar_calendario(cad: dict[str, pd.DataFrame]) -> pd.DataFrame:
    cal = cad["calendario"].copy()
    datas = pd.to_datetime(cal["data"])
    cal["ano"] = datas.dt.year
    cal["mes_numero"] = datas.dt.month
    cal["mes"] = datas.dt.to_period("M").dt.start_time.dt.strftime("%Y-%m-%d")
    cal["mes_nome"] = [f"{NOMES_MES[d.month - 1]}/{d.year % 100:02d}" for d in datas]
    cal["dia_semana"] = [DIAS_SEMANA[d.weekday()] for d in datas]
    cal["dia_semana_numero"] = datas.dt.day_of_week + 1
    cal["semestre"] = [semestre_da_data(d.date()) if f > 0 else "" for d, f in zip(datas, cal["fator_salas"],
                                                                                    strict=True)]
    cal["aberto"] = cal["fator_salas"] > 0
    return cal


def alunos_com_meta(alunos: pd.DataFrame, fim_dados: date) -> pd.DataFrame:
    """Meta de horas proporcional aos dias letivos já decorridos até o fim dos dados.

    2025.2 fica sem meta: os dados começam em novembro, no meio do semestre, e as horas de
    agosto a outubro não estão na base (comparar seria injusto com o aluno).
    """
    saida = alunos.copy()
    proporcao = {}
    for rotulo, inicio, fim in SEMESTRES:
        uteis = pd.bdate_range(inicio, fim)
        proporcao[rotulo] = round(len(uteis[uteis <= pd.Timestamp(fim_dados)]) / len(uteis), 4)
    proporcao["2025.2"] = None
    saida["proporcao_semestre"] = saida["semestre"].map(proporcao)
    saida["meta_ate_fim_dados"] = (saida["meta_horas_semestre"] * saida["proporcao_semestre"]).round(1)
    return saida


def padronizar(fontes: Path = PASTA_FONTES, destino: Path = PASTA_TRATADO) -> dict[str, pd.DataFrame]:
    reg = Registro()
    cad = ler_cadastros(fontes)
    sistema = ler_sistema(fontes, cad, reg)
    planilhas = ler_planilhas(fontes, cad, reg)
    atend = pd.concat([sistema, planilhas], ignore_index=True)
    fila = ler_fila(fontes, reg)
    completar_tipo_e_fila(atend, fila, reg)
    marcar_conflitos(atend, reg)
    atend = juntar_recepcao(atend, ler_recepcao(fontes, reg), reg)

    # Procedimento das planilhas: elas não têm a coluna; vale o padrão do serviço.
    sem_proc = atend["procedimento"].isna()
    atend.loc[sem_proc, "procedimento"] = [
        PROCEDIMENTOS[s][0] if t == "Primeira consulta" else PROCEDIMENTOS[s][1][0]
        for s, t in zip(atend.loc[sem_proc, "servico"], atend.loc[sem_proc, "tipo"], strict=True)]

    # Faturamento: taxa da tabela, só no realizado e só de quem não é isento.
    taxa = dict(zip(cad["taxa"]["procedimento"], cad["taxa"]["valor"], strict=True))
    isento = dict(zip(cad["pacientes"]["prontuario"], cad["pacientes"]["isento_taxa"], strict=True))
    atend["valor_tabela"] = atend["procedimento"].map(taxa)
    paga = atend["prontuario"].map(isento).map({"Não": 1.0, "Sim": 0.0})  # sem prontuário: em branco
    atend["valor_cobrado"] = atend["valor_tabela"] * paga * (atend["situacao"] == "Realizado")

    atend["duracao_min"] = atend["servico"].map(lambda s: SERVICOS[s].duracao_min)
    atend["horas_pratica"] = (atend["situacao"] == "Realizado") * atend["duracao_min"] / 60
    atend["turno"] = atend["hora"].map(lambda h: "Manhã" if h < time(12, 0) else "Tarde")
    atend["clinica"] = atend["servico"].map(lambda s: SERVICOS[s].nome) + " · " + atend["unidade"].map(
        lambda u: UNIDADES[u].split()[0])
    atend = atend.sort_values(["data", "hora", "unidade", "servico", "id_atendimento"]).reset_index(drop=True)
    atend["conflito_horario"] = atend["conflito_horario"].map({True: "Sim", False: "Não"})
    atend["prontuario_recuperado"] = atend["prontuario_recuperado"].map({True: "Sim", False: "Não"})
    atend["hora"] = atend["hora"].map(lambda h: h.strftime("%H:%M"))
    atend = atend[["id_atendimento", "data", "hora", "turno", "unidade", "servico", "clinica", "prontuario",
                   "matricula_aluno", "supervisor", "tipo", "procedimento", "situacao", "duracao_min",
                   "horas_pratica", "origem", "arquivo", "conflito_horario", "prontuario_recuperado",
                   "valor_tabela", "valor_cobrado", "motivo", "hora_chegada", "hora_chamada",
                   "espera_recepcao_min"]]

    fila["dias_espera"] = [(p - i).days if p is not None and p == p else None
                           for p, i in zip(fila["data_primeira"], fila["data_inscricao"], strict=True)]
    fila = fila.drop(columns=["linha"])

    pac = cad["pacientes"].copy()
    idade = (pd.Timestamp("2026-10-31") - pd.to_datetime(pac["data_nascimento"])).dt.days // 365
    pac["faixa_etaria"] = pd.cut(idade, [0, 29, 44, 59, 200], labels=["18-29", "30-44", "45-59", "60+"]).astype(str)
    # Minimização (LGPD): a base de análise não leva nome nem data de nascimento do paciente.
    pacientes = pac[["prontuario", "sexo", "faixa_etaria", "unidade", "servico", "isento_taxa"]]

    clinicas = (cad["grade"].groupby(["unidade", "servico"], as_index=False)
                .agg(salas=("salas", "first"), duracao_min=("duracao_min", "first")))
    clinicas["unidade_nome"] = clinicas["unidade"].map(UNIDADES)
    clinicas["servico_nome"] = clinicas["servico"].map(lambda s: SERVICOS[s].nome)
    clinicas["clinica"] = clinicas["servico_nome"] + " · " + clinicas["unidade_nome"].str.split().str[0]
    clinicas["origem_dados"] = clinicas["servico"].map(lambda s: SERVICOS[s].origem.capitalize())

    semestres = pd.DataFrame([{"semestre": s, "inicio": i.isoformat(), "fim": f.isoformat()}
                              for s, i, f in SEMESTRES])
    resumo = pd.DataFrame([{"regra": r, "descricao": DESCRICAO_REGRA[r][0], "acao": DESCRICAO_REGRA[r][1],
                            "ocorrencias": reg.contagem.get(r, 0)} for r in DESCRICAO_REGRA])
    tabelas = {
        "atendimentos": atend,
        "alunos": alunos_com_meta(cad["alunos"], atend["data"].max()),
        "oferta": montar_oferta(cad),
        "fila": fila,
        "pacientes": pacientes,
        "supervisores": cad["supervisores"],
        "clinicas": clinicas,
        "calendario": montar_calendario(cad),
        "semestres": semestres,
        "inconsistencias": pd.DataFrame(reg.linhas),
        "resumo_qualidade": resumo,
    }
    destino.mkdir(parents=True, exist_ok=True)
    for nome, tabela in tabelas.items():
        tabela.to_csv(destino / f"{nome}.csv", index=False, encoding="utf-8", lineterminator="\n")
    return tabelas


if __name__ == "__main__":
    t = padronizar()
    print(t["resumo_qualidade"].to_string(index=False))
    print(f"\n{len(t['atendimentos'])} atendimentos na base tratada")
