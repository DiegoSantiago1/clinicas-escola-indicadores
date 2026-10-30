"""Gera o relatório Power BI em formato de projeto (PBIP): modelo em TMDL e páginas em PBIR.

Uso:
    python powerbi/gerar_pbip.py

O relatório lê os CSVs de data/tratado. O caminho da pasta é um parâmetro do Power Query
(PastaDados): quem clonar o repositório troca em "Transformar dados > Editar parâmetros".

O que fica no Power Query (e não no Python), de propósito:
- os tipos de cada coluna, lidos com a cultura en-US (o CSV usa ponto decimal e data ISO;
  com pt-BR, "1.5" viraria 15);
- a chave id_clinica ("REC-ODO"), que liga as três tabelas de fatos à dimensão de clínicas;
- a mesclagem da fila com os atendimentos, que leva o tempo de espera até a 1ª consulta e
  permite medir a falta por faixa de espera;
- a faixa de espera da fila.

Os identificadores (lineageTag, logicalId) são UUIDs determinísticos: gerar de novo não
muda nada que não tenha mudado aqui.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PASTA = Path(__file__).resolve().parent
NOME = "clinicas_escola"
PASTA_DADOS = str((PASTA.parent / "data" / "tratado").resolve()) + "\\"
_ESPACO = uuid.UUID("3c9a1f52-7d0e-4b8a-a1c4-5e2f9b7d6c10")

SCHEMA_VISUAL = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
    "visualContainer/2.4.0/schema.json"
)
SCHEMA_PAGINA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
    "page/2.0.0/schema.json"
)

# Identidade própria do projeto (a mesma da página de resultados).
AZUL, CORAL, VERDE, MOSTARDA = "#1F4E79", "#E85A5A", "#2E8B6E", "#C9A227"
TEXTO, TEXTO_2, FUNDO = "#14213D", "#4A5568", "#F4F5F6"

TEMA: dict[str, Any] = {
    "name": "Clínicas-Escola",
    "dataColors": [AZUL, CORAL, VERDE, MOSTARDA, "#7A5C99", "#5DA9C9", "#9C6644", "#8D99AE"],
    "background": "#FFFFFF",
    "foreground": TEXTO,
    "tableAccent": AZUL,
    "good": VERDE,
    "neutral": MOSTARDA,
    "bad": CORAL,
    "maximum": CORAL,
    "center": "#F4B8B8",
    "minimum": "#FCEDED",
    "null": "#E5E7EB",
    "textClasses": {
        "title": {"fontFace": "Segoe UI Semibold", "color": TEXTO, "fontSize": 12},
        "label": {"fontFace": "Segoe UI", "color": TEXTO_2},
        "callout": {"fontFace": "Segoe UI Semibold", "color": TEXTO, "fontSize": 26},
    },
    "visualStyles": {
        "*": {
            "*": {
                "title": [{"fontColor": {"solid": {"color": TEXTO}}, "bold": True, "fontSize": 12}],
                "categoryAxis": [{"labelColor": {"solid": {"color": TEXTO_2}}}],
                "valueAxis": [{"labelColor": {"solid": {"color": TEXTO_2}}}],
                "legend": [{"labelColor": {"solid": {"color": TEXTO_2}}}],
                "background": [{"show": True, "color": {"solid": {"color": "#FFFFFF"}}}],
                "border": [{"show": True, "color": {"solid": {"color": "#E5E1D8"}}, "radius": 10}],
                "dropShadow": [{"show": False}],
            }
        },
        "page": {"*": {"background": [{"color": {"solid": {"color": FUNDO}}, "transparency": 0}]}},
        "card": {
            "*": {
                "labels": [{"color": {"solid": {"color": TEXTO}}}],
                "categoryLabels": [{"color": {"solid": {"color": TEXTO_2}}}],
            }
        },
        "textbox": {"*": {"background": [{"show": False}], "border": [{"show": False}]}},
        "slicer": {"*": {"background": [{"show": True, "color": {"solid": {"color": "#FFFFFF"}}}]}},
    },
}


def tag(*partes: str) -> str:
    """UUID determinístico: o mesmo objeto recebe sempre o mesmo identificador."""
    return str(uuid.uuid5(_ESPACO, "/".join(partes)))


# ============================================================== modelo (TMDL)


@dataclass(frozen=True)
class Coluna:
    nome: str
    tipo: str  # int64, double, string, boolean, dateTime
    formato: str | None = None
    resumo: str = "none"
    oculta: bool = False
    ordenar_por: str | None = None
    descricao: str | None = None
    chave: bool = False
    calculada_m: bool = False  # criada no Power Query (não vem do CSV)


@dataclass(frozen=True)
class Tabela:
    nome: str
    arquivo: str
    colunas: list[Coluna]
    descricao: str
    passos_m: list[tuple[str, str]] = field(default_factory=list)  # (nome do passo, expressão M)
    data: bool = False  # tabela de datas (marcada como tal no modelo)


@dataclass(frozen=True)
class Medida:
    nome: str
    dax: str
    formato: str
    descricao: str
    pasta: str


@dataclass(frozen=True)
class Relacao:
    de: str  # tabela.coluna (lado muitos)
    para: str  # tabela.coluna (lado um)


PCT = "0.0%"
INT = "#,0"
DEC1 = "#,0.0"
DATA = "dd/mm/yyyy"

TIPO_M = {"int64": "Int64.Type", "double": "type number", "string": "type text", "boolean": "type logical",
          "dateTime": "type date"}

ID_CLINICA = ("ComClinica", 'Table.AddColumn({ant}, "id_clinica", each [unidade] & "-" & [servico], type text)')

TABELAS = [
    Tabela(
        "atendimentos", "atendimentos.csv",
        [
            Coluna("id_atendimento", "string"),
            Coluna("data", "dateTime", DATA),
            Coluna("hora", "string"),
            Coluna("turno", "string"),
            Coluna("unidade", "string", oculta=True),
            Coluna("servico", "string", oculta=True),
            Coluna("clinica", "string", oculta=True),
            Coluna("prontuario", "string"),
            Coluna("matricula_aluno", "string"),
            Coluna("supervisor", "string"),
            Coluna("tipo", "string"),
            Coluna("procedimento", "string"),
            Coluna("situacao", "string"),
            Coluna("duracao_min", "int64", INT),
            Coluna("horas_pratica", "double", DEC1, "sum"),
            Coluna("origem", "string"),
            Coluna("arquivo", "string"),
            Coluna("conflito_horario", "string"),
            Coluna("prontuario_recuperado", "string"),
            Coluna("id_clinica", "string", oculta=True, calculada_m=True),
            Coluna("faixa_espera_1a_consulta", "string", ordenar_por="faixa_espera_ordem", calculada_m=True,
                   descricao="Só nas primeiras consultas: quanto o paciente esperou na fila (veio da mesclagem)."),
            Coluna("faixa_espera_ordem", "int64", "0", oculta=True, calculada_m=True),
        ],
        "Um agendamento por linha, das duas origens (sistema e planilhas), já padronizado em Python.",
        passos_m=[
            ID_CLINICA,
            # Mesclagem com a fila: traz quantos dias o paciente esperou até a 1ª consulta.
            ("MescladoComFila", 'Table.NestedJoin({ant}, {{"prontuario"}}, Fila, {{"prontuario"}}, "fila", JoinKind.LeftOuter)'),
            ("ComDiasEspera", 'Table.ExpandTableColumn({ant}, "fila", {{"dias_espera"}}, {{"dias_espera_fila"}})'),
            ("ComOrdemFaixa", 'Table.AddColumn({ant}, "faixa_espera_ordem", each if [tipo] <> "Primeira consulta" or '
            '[dias_espera_fila] = null then null else if [dias_espera_fila] <= 7 then 1 else if '
            '[dias_espera_fila] <= 30 then 2 else if [dias_espera_fila] <= 60 then 3 else 4, Int64.Type)'),
            ("ComFaixaEspera", 'Table.AddColumn({ant}, "faixa_espera_1a_consulta", each {{null, "Até 7 dias", "8 a 30 dias", '
            '"31 a 60 dias", "Mais de 60 dias"}}{{if [faixa_espera_ordem] = null then 0 else '
            '[faixa_espera_ordem]}}, type text)'),
            ("SemColunaAuxiliar", 'Table.RemoveColumns({ant}, {{"dias_espera_fila"}})'),
        ],
    ),
    Tabela(
        "oferta", "oferta.csv",
        [
            Coluna("data", "dateTime", DATA),
            Coluna("unidade", "string", oculta=True),
            Coluna("servico", "string", oculta=True),
            Coluna("turno", "string"),
            Coluna("horarios_ofertados", "int64", INT, "sum"),
            Coluna("id_clinica", "string", oculta=True, calculada_m=True),
        ],
        "Horários de atendimento ofertados por dia, clínica e turno (salas x horários; metade no plantão).",
        passos_m=[ID_CLINICA],
    ),
    Tabela(
        "fila", "fila.csv",
        [
            Coluna("prontuario", "string"),
            Coluna("unidade", "string", oculta=True),
            Coluna("servico", "string", oculta=True),
            Coluna("data_inscricao", "dateTime", DATA),
            Coluna("data_primeira", "dateTime", DATA),
            Coluna("situacao", "string"),
            Coluna("dias_espera", "int64", INT, "none"),
            Coluna("id_clinica", "string", oculta=True, calculada_m=True),
        ],
        "Fila de espera da recepção: inscrição, 1ª consulta e situação de cada paciente.",
        passos_m=[ID_CLINICA],
    ),
    Tabela(
        "clinicas", "clinicas.csv",
        [
            Coluna("unidade", "string", oculta=True),
            Coluna("servico", "string", oculta=True),
            Coluna("salas", "int64", INT),
            Coluna("duracao_min", "int64", INT),
            Coluna("unidade_nome", "string"),
            Coluna("servico_nome", "string"),
            Coluna("clinica", "string"),
            Coluna("origem_dados", "string"),
            Coluna("id_clinica", "string", oculta=True, chave=True, calculada_m=True),
        ],
        "As 10 clínicas: unidade, serviço, salas e de onde vêm os dados (sistema ou planilha).",
        passos_m=[ID_CLINICA],
    ),
    Tabela(
        "calendario", "calendario.csv",
        [
            Coluna("data", "dateTime", DATA, chave=True),
            Coluna("situacao", "string"),
            Coluna("fator_salas", "double", "0.0"),
            Coluna("ano", "int64", "0"),
            Coluna("mes_numero", "int64", "0", oculta=True),
            Coluna("mes", "dateTime", "mmm/yyyy"),
            Coluna("mes_nome", "string", ordenar_por="mes"),
            Coluna("dia_semana", "string", ordenar_por="dia_semana_numero"),
            Coluna("dia_semana_numero", "int64", "0", oculta=True),
            Coluna("semestre", "string"),
            Coluna("aberto", "boolean"),
        ],
        "Uma linha por dia do período, com recesso, feriados e plantão de férias.",
        data=True,
    ),
    Tabela(
        "alunos", "alunos.csv",
        [
            Coluna("matricula", "string", chave=True),
            Coluna("nome", "string"),
            Coluna("curso", "string"),
            Coluna("semestre", "string"),
            Coluna("unidade", "string"),
            Coluna("servico", "string", oculta=True),
            Coluna("meta_horas_semestre", "int64", INT),
            Coluna("proporcao_semestre", "double", PCT),
            Coluna("meta_ate_fim_dados", "double", DEC1, descricao="Meta proporcional aos dias letivos já "
                   "decorridos até 31/10/2026 (vazia em 2025.2, que começou antes dos dados)."),
        ],
        "Alunos de cada semestre, com a meta de horas de prática.",
    ),
    Tabela(
        "supervisores", "supervisores.csv",
        [
            Coluna("codigo", "string", chave=True),
            Coluna("nome", "string"),
            Coluna("unidade", "string", oculta=True),
            Coluna("servico", "string", oculta=True),
        ],
        "Professores supervisores de cada clínica.",
    ),
    Tabela(
        "resumo_qualidade", "resumo_qualidade.csv",
        [
            Coluna("regra", "string"),
            Coluna("descricao", "string"),
            Coluna("acao", "string"),
            Coluna("ocorrencias", "int64", INT, "sum"),
        ],
        "Quantas vezes cada regra de padronização foi aplicada.",
    ),
    Tabela(
        "inconsistencias", "inconsistencias.csv",
        [
            Coluna("regra", "string"),
            Coluna("descricao", "string"),
            Coluna("acao", "string"),
            Coluna("arquivo", "string"),
            Coluna("aba", "string"),
            Coluna("linha", "int64", "0"),
            Coluna("valor_original", "string"),
            Coluna("valor_final", "string"),
        ],
        "Linhas que precisam de conferência na origem: arquivo, aba e linha.",
    ),
]

RELACOES = [
    Relacao("atendimentos.data", "calendario.data"),
    Relacao("oferta.data", "calendario.data"),
    Relacao("fila.data_inscricao", "calendario.data"),
    Relacao("atendimentos.id_clinica", "clinicas.id_clinica"),
    Relacao("oferta.id_clinica", "clinicas.id_clinica"),
    Relacao("fila.id_clinica", "clinicas.id_clinica"),
    Relacao("atendimentos.matricula_aluno", "alunos.matricula"),
    Relacao("atendimentos.supervisor", "supervisores.codigo"),
]


def _situacao(valor: str) -> str:
    return f'CALCULATE ( [Agendamentos], atendimentos[situacao] = "{valor}" )'


MEDIDAS = [
    Medida("Agendamentos", "COUNTROWS ( atendimentos )", INT, "Todos os agendamentos, de qualquer situação.",
           "Atendimento"),
    Medida("Realizados", _situacao("Realizado"), INT, "Atendimentos em que o paciente veio.", "Atendimento"),
    Medida("Faltas", _situacao("Falta"), INT, "Paciente não veio e não avisou.", "Atendimento"),
    Medida("Cancelados pelo paciente", _situacao("Cancelado pelo paciente"), INT,
           "Paciente avisou com antecedência.", "Atendimento"),
    Medida("Cancelados pela clínica", _situacao("Cancelado pela clínica"), INT,
           "A clínica cancelou (supervisor ausente).", "Atendimento"),
    Medida("Taxa de faltas", "DIVIDE ( [Faltas], [Realizados] + [Faltas] )", PCT,
           "Faltas / (realizados + faltas). Cancelamento avisado fica de fora: o horário pôde ser remarcado.",
           "Atendimento"),
    Medida("Taxa de faltas (mês anterior)",
           "CALCULATE ( [Taxa de faltas], DATEADD ( calendario[data], -1, MONTH ) )", PCT,
           "A mesma taxa, no mês anterior (inteligência de tempo sobre a tabela de datas).", "Atendimento"),
    Medida("Variação das faltas (p.p.)",
           "VAR atual = [Taxa de faltas] VAR anterior = [Taxa de faltas (mês anterior)] "
           "RETURN IF ( NOT ISBLANK ( anterior ), ( atual - anterior ) * 100 )", "+0.0;-0.0;0.0",
           "Diferença em pontos percentuais contra o mês anterior.", "Atendimento"),
    Medida("Pacientes atendidos",
           'CALCULATE ( DISTINCTCOUNT ( atendimentos[prontuario] ), atendimentos[situacao] = "Realizado" )', INT,
           "Pacientes diferentes com ao menos um atendimento realizado.", "Atendimento"),
    Medida("Horários ofertados", "SUM ( oferta[horarios_ofertados] )", INT,
           "Capacidade: salas x horários de cada turno nos dias abertos.", "Agenda"),
    Medida("Ocupação da agenda", "DIVIDE ( [Agendamentos], [Horários ofertados] )", PCT,
           "Quanto da agenda foi preenchido com agendamentos.", "Agenda"),
    Medida("Aproveitamento", "DIVIDE ( [Realizados], [Horários ofertados] )", PCT,
           "Quanto da capacidade virou atendimento de fato (agenda cheia não é atendimento).", "Agenda"),
    Medida("Entradas na fila", "COUNTROWS ( fila )", INT, "Pacientes que entraram na fila (pela data de inscrição).",
           "Fila"),
    Medida("Espera mediana (dias)",
           "CALCULATE ( MEDIAN ( fila[dias_espera] ), fila[data_primeira] >= DATE ( 2025, 11, 1 ) )", "0",
           "Mediana de dias entre a inscrição e a 1ª consulta, para quem foi chamado no período.", "Fila"),
    Medida("Aguardando", 'CALCULATE ( COUNTROWS ( fila ), fila[situacao] = "Aguardando" )', INT,
           "Pacientes ainda na fila em 31/10/2026.", "Fila"),
    Medida("Horas de prática", "SUM ( atendimentos[horas_pratica] )", INT,
           "Horas de atendimento realizado: é a prática do aluno.", "Alunos"),
    Medida("Horas perdidas por faltas",
           'DIVIDE ( CALCULATE ( SUM ( atendimentos[duracao_min] ), atendimentos[situacao] = "Falta" ), 60 )', INT,
           "Horas de prática que o aluno deixou de fazer porque o paciente faltou.", "Alunos"),
    Medida("Alunos com meta",
           "COUNTROWS ( FILTER ( alunos, NOT ISBLANK ( alunos[meta_ate_fim_dados] ) ) )", INT,
           "Alunos de 2026.1 e 2026.2 (2025.2 começou antes dos dados).", "Alunos"),
    Medida("Alunos na meta",
           "COUNTROWS ( FILTER ( alunos, NOT ISBLANK ( alunos[meta_ate_fim_dados] ) && "
           "CALCULATE ( SUM ( atendimentos[horas_pratica] ) ) >= alunos[meta_ate_fim_dados] ) )", INT,
           "Alunos cujas horas já alcançaram a meta proporcional. O CALCULATE dentro do FILTER faz a transição "
           "de contexto: soma as horas de cada aluno da linha.", "Alunos"),
    Medida("% alunos na meta", "DIVIDE ( [Alunos na meta], [Alunos com meta] )", PCT,
           "Parte dos alunos que já alcançou a meta proporcional.", "Alunos"),
    Medida("Horas por aluno", "DIVIDE ( [Horas de prática], DISTINCTCOUNT ( atendimentos[matricula_aluno] ) )",
           DEC1, "Média de horas de prática por aluno que atendeu.", "Alunos"),
    Medida("Regras aplicadas", "SUM ( resumo_qualidade[ocorrencias] )", INT,
           "Total de correções e sinalizações feitas pela padronização.", "Qualidade"),
    Medida("Linhas para conferir", "COUNTROWS ( inconsistencias )", INT,
           "Linhas que a equipe deve conferir na origem (arquivo, aba e linha).", "Qualidade"),
    Medida("Prontuários recuperados",
           'CALCULATE ( [Agendamentos], atendimentos[prontuario_recuperado] = "Sim" )', INT,
           "Prontuário em branco na planilha, recuperado pelo nome (só quando o nome é único).", "Qualidade"),
]


def _nome_tmdl(nome: str) -> str:
    """Nomes com espaço, acento ou símbolo vão entre aspas simples no TMDL."""
    return nome if nome.replace("_", "").isalnum() and nome.isascii() else f"'{nome}'"


def m_fonte(t: Tabela) -> tuple[list[str], str]:
    """Consulta M da tabela: lê o CSV, promove o cabeçalho, aplica os tipos (en-US) e os passos extras."""
    lidas = [c for c in t.colunas if not c.calculada_m]
    tipos = ", ".join(f'{{"{c.nome}", {TIPO_M[c.tipo]}}}' for c in lidas)
    passos = [
        f'Fonte = Csv.Document(File.Contents(PastaDados & "{t.arquivo}"), '
        "[Delimiter = \",\", Encoding = 65001, QuoteStyle = QuoteStyle.Csv])",
        "Cabecalho = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true])",
        # Só as colunas que o modelo declara: uma coluna nova no CSV não quebra a atualização.
        "Colunas = Table.SelectColumns(Cabecalho, {" + ", ".join(f'"{c.nome}"' for c in lidas) + "})",
        f'Tipos = Table.TransformColumnTypes(Colunas, {{{tipos}}}, "en-US")',
    ]
    if t.nome == "atendimentos":
        passos += [
            'FilaFonte = Csv.Document(File.Contents(PastaDados & "fila.csv"), '
            "[Delimiter = \",\", Encoding = 65001, QuoteStyle = QuoteStyle.Csv])",
            'Fila = Table.TransformColumnTypes(Table.SelectColumns(Table.PromoteHeaders(FilaFonte), '
            '{"prontuario", "dias_espera"}), {{"dias_espera", Int64.Type}}, "en-US")',
        ]
    anterior = "Tipos"
    for nome, modelo in t.passos_m:
        passos.append(f"{nome} = " + modelo.format(ant=anterior))
        anterior = nome
    return passos, anterior


def tmdl_tabela(t: Tabela) -> str:
    linhas = [f"/// {t.descricao}", f"table {t.nome}", f"\tlineageTag: {tag('tabela', t.nome)}"]
    if t.data:
        linhas.append("\tdataCategory: Time")
    linhas.append("")
    for c in t.colunas:
        if c.descricao:
            linhas.append(f"\t/// {c.descricao}")
        linhas.append(f"\tcolumn {_nome_tmdl(c.nome)}")
        linhas.append(f"\t\tdataType: {c.tipo}")
        if c.chave:
            linhas.append("\t\tisKey")
        if c.oculta:
            linhas.append("\t\tisHidden")
        if c.formato:
            linhas.append(f"\t\tformatString: {c.formato}")
        linhas.append(f"\t\tlineageTag: {tag('coluna', t.nome, c.nome)}")
        linhas.append(f"\t\tsummarizeBy: {c.resumo}")
        linhas.append(f"\t\tsourceColumn: {c.nome}")
        if c.ordenar_por:
            linhas.append(f"\t\tsortByColumn: {c.ordenar_por}")
        if c.tipo == "dateTime":
            linhas += ["", "\t\tannotation UnderlyingDateTimeDataType = Date"]
        linhas.append("")
    passos, ultimo = m_fonte(t)
    linhas += [f"\tpartition {t.nome} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet"]
    for i, passo in enumerate(passos):
        virgula = "," if i < len(passos) - 1 else ""
        linhas.append(f"\t\t\t\t    {passo}{virgula}")
    linhas += ["\t\t\t\tin", f"\t\t\t\t    {ultimo}", ""]
    return "\n".join(linhas)


def tmdl_medidas() -> str:
    linhas = ["table Medidas", f"\tlineageTag: {tag('tabela', 'Medidas')}", ""]
    for m in MEDIDAS:
        linhas.append(f"\t/// {m.descricao}")
        linhas.append(f"\tmeasure {_nome_tmdl(m.nome)} = {m.dax}")
        if m.formato:
            linhas.append(f"\t\tformatString: {m.formato}")
        linhas.append(f"\t\tdisplayFolder: {m.pasta}")
        linhas.append(f"\t\tlineageTag: {tag('medida', m.nome)}")
        linhas.append("")
    linhas += [
        "\tcolumn Coluna",
        "\t\tdataType: string",
        "\t\tisHidden",
        f"\t\tlineageTag: {tag('coluna', 'Medidas', 'Coluna')}",
        "\t\tsummarizeBy: none",
        "\t\tsourceColumn: Coluna",
        "",
        "\tpartition Medidas = m",
        "\t\tmode: import",
        "\t\tsource = #table(type table [Coluna = text], {})",
        "",
    ]
    return "\n".join(linhas)


def tmdl_expressoes() -> str:
    caminho = PASTA_DADOS.replace('"', '""')
    return (
        "/// Pasta com os CSVs de data/tratado (termina com barra).\n"
        f'expression PastaDados = "{caminho}" meta [IsParameterQuery = true, Type = "Text", '
        "IsParameterQueryRequired = true]\n"
        f"\tlineageTag: {tag('expressao', 'PastaDados')}\n\n"
        "\tannotation PBI_ResultType = Text\n\n"
    )


def tmdl_modelo() -> str:
    nomes = [t.nome for t in TABELAS] + ["Medidas"]
    linhas = [
        "model Model",
        "\tculture: pt-BR",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: pt-BR",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        f"annotation PBI_QueryOrder = {json.dumps(['PastaDados', *nomes], ensure_ascii=False)}",
        "",
        'annotation PBI_ProTooling = ["DevMode"]',
        "",
        *[f"ref table {n}" for n in nomes],
        "",
        "ref cultureInfo pt-BR",
        "",
    ]
    return "\n".join(linhas)


def tmdl_relacoes() -> str:
    linhas = []
    for r in RELACOES:
        linhas += [f"relationship {tag('relacao', r.de, r.para)}", f"\tfromColumn: {r.de}",
                   f"\ttoColumn: {r.para}", ""]
    return "\n".join(linhas)


# ============================================================== relatório (PBIR)


def _ref(entidade: str, propriedade: str, medida: bool) -> dict[str, Any]:
    tipo = "Measure" if medida else "Column"
    return {tipo: {"Expression": {"SourceRef": {"Entity": entidade}}, "Property": propriedade}}


def campo(texto: str, rotulo: str | None = None) -> dict[str, Any]:
    """'Medidas.Faltas' (medida) ou 'clinicas.clinica' (coluna) -> projeção do PBIR."""
    entidade, propriedade = texto.split(".", 1)
    projecao: dict[str, Any] = {
        "field": _ref(entidade, propriedade, entidade == "Medidas"),
        "queryRef": texto,
        "nativeQueryRef": propriedade,
    }
    if rotulo:
        projecao["displayName"] = rotulo
    return projecao


def _literal(valor: str) -> dict[str, Any]:
    return {"expr": {"Literal": {"Value": valor}}}


def titulo(texto: str) -> dict[str, Any]:
    return {"title": [{"properties": {"show": _literal("true"), "text": _literal(f"'{texto}'")}}]}


@dataclass
class Visual:
    nome: str
    tipo: str
    x: int
    y: int
    largura: int
    altura: int
    papeis: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    titulo: str | None = None
    objetos: dict[str, Any] | None = None
    filtros: list[dict[str, Any]] | None = None
    ordenar: dict[str, Any] | None = None


GRAFICOS = {"columnChart", "clusteredBarChart", "lineChart", "clusteredColumnChart", "barChart"}
SEM_TITULO_EIXOS = {
    "valueAxis": [{"properties": {"showAxisTitle": _literal("false")}}],
    "categoryAxis": [{"properties": {"showAxisTitle": _literal("false")}}],
    "labels": [{"properties": {"show": _literal("true")}}],
}


def _json_visual(v: Visual, z: int) -> dict[str, Any]:
    corpo: dict[str, Any] = {"visualType": v.tipo}
    if v.objetos is None and v.tipo in GRAFICOS:
        v.objetos = SEM_TITULO_EIXOS
    if v.papeis:
        corpo["query"] = {"queryState": {papel: {"projections": proj} for papel, proj in v.papeis.items()}}
        if v.ordenar:
            corpo["query"]["sortDefinition"] = v.ordenar
    if v.objetos:
        corpo["objects"] = v.objetos
    if v.titulo:
        corpo["visualContainerObjects"] = titulo(v.titulo)
    resultado: dict[str, Any] = {
        "$schema": SCHEMA_VISUAL,
        "name": v.nome,
        "position": {"x": v.x, "y": v.y, "z": z, "width": v.largura, "height": v.altura, "tabOrder": z},
        "visual": corpo,
    }
    if v.filtros:
        resultado["filterConfig"] = {"filters": v.filtros}
    return resultado


def cabecalho(texto: str, subtitulo: str) -> Visual:
    paragrafos = [
        {"textRuns": [{"value": texto, "textStyle": {"fontWeight": "bold", "fontSize": "20pt", "color": TEXTO}}]},
        {"textRuns": [{"value": subtitulo, "textStyle": {"fontSize": "11pt", "color": TEXTO_2}}]},
    ]
    return Visual("cabecalho", "textbox", 16, 8, 1248, 64,
                  objetos={"general": [{"properties": {"paragraphs": paragrafos}}]})


def nota(nome: str, x: int, y: int, largura: int, altura: int, texto: str) -> Visual:
    paragrafos = [{"textRuns": [{"value": texto, "textStyle": {"fontSize": "10pt", "color": TEXTO_2}}]}]
    return Visual(nome, "textbox", x, y, largura, altura,
                  objetos={"general": [{"properties": {"paragraphs": paragrafos}}]})


def cartao(nome: str, x: int, medida: str, rotulo: str, y: int = 80, largura: int = 240) -> Visual:
    rotulos = {"labels": [{"properties": {"labelDisplayUnits": _literal("1D")}}]}
    return Visual(nome, "card", x, y, largura, 100, {"Values": [campo(medida, rotulo)]}, objetos=rotulos)


def segmentador(nome: str, x: int, y: int, largura: int, coluna: str, rotulo: str) -> Visual:
    objetos = {"data": [{"properties": {"mode": _literal("'Dropdown'")}}]}
    return Visual(nome, "slicer", x, y, largura, 64, {"Values": [campo(coluna, rotulo)]}, objetos=objetos)


def filtro_valores(nome: str, coluna: str, literais: list[str]) -> dict[str, Any]:
    entidade, propriedade = coluna.split(".", 1)
    return {
        "name": nome,
        "field": _ref(entidade, propriedade, False),
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": "t", "Entity": entidade, "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": propriedade}}],
                "Values": [[{"Literal": {"Value": v}}] for v in literais],
            }}}],
        },
    }


def ordenar_por(coluna: str, direcao: str = "Ascending") -> dict[str, Any]:
    entidade, propriedade = coluna.split(".", 1)
    return {"sort": [{"field": _ref(entidade, propriedade, entidade == "Medidas"), "direction": direcao}]}


def filtros_padrao() -> list[Visual]:
    return [
        segmentador("seg_unidade", 912, 8, 172, "clinicas.unidade_nome", "Unidade"),
        segmentador("seg_servico", 1092, 8, 172, "clinicas.servico_nome", "Serviço"),
    ]


SO_PRIMEIRA = filtro_valores("so_faixas", "atendimentos.faixa_espera_1a_consulta",
                             ["'Até 7 dias'", "'8 a 30 dias'", "'31 a 60 dias'", "'Mais de 60 dias'"])
SEMESTRE_2026_1 = filtro_valores("so_2026_1", "alunos.semestre", ["'2026.1'"])

PAGINAS: list[tuple[str, str, list[Visual]]] = [
    (
        "visao_geral", "Visão geral",
        [
            cabecalho("Clínicas-escola: visão geral",
                      "Rede fictícia, 10 clínicas em 3 unidades, nov/2025 a out/2026. Dados simulados."),
            *filtros_padrao(),
            cartao("c_realizados", 16, "Medidas.Realizados", "Atendimentos realizados"),
            cartao("c_faltas", 268, "Medidas.Taxa de faltas", "Taxa de faltas"),
            cartao("c_ocupacao", 520, "Medidas.Ocupação da agenda", "Ocupação da agenda"),
            cartao("c_espera", 772, "Medidas.Espera mediana (dias)", "Espera mediana na fila (dias)"),
            cartao("c_horas", 1024, "Medidas.Horas de prática", "Horas de prática dos alunos"),
            Visual("colunas_mes", "clusteredColumnChart", 16, 192, 760, 516,
                   {"Category": [campo("calendario.mes_nome", "Mês")],
                    "Y": [campo("Medidas.Realizados", "Realizados"), campo("Medidas.Faltas", "Faltas")]},
                   titulo="Atendimentos e faltas por mês (dez-jan: recesso; jul: plantão de férias)",
                   ordenar=ordenar_por("calendario.mes_nome")),
            Visual("barras_clinica", "clusteredBarChart", 792, 192, 472, 516,
                   {"Category": [campo("clinicas.clinica", "Clínica")],
                    "Y": [campo("Medidas.Taxa de faltas", "Taxa de faltas")]},
                   titulo="Taxa de faltas por clínica",
                   ordenar=ordenar_por("Medidas.Taxa de faltas", "Descending")),
        ],
    ),
    (
        "faltas", "Faltas",
        [
            cabecalho("Faltas", "Quando e quem falta? Faltas / (realizados + faltas): cancelamento avisado não conta."),
            *filtros_padrao(),
            cartao("c_faltas", 16, "Medidas.Faltas", "Faltas no período"),
            cartao("c_taxa", 268, "Medidas.Taxa de faltas", "Taxa de faltas"),
            cartao("c_variacao", 520, "Medidas.Variação das faltas (p.p.)", "Variação vs. mês anterior (p.p.)"),
            cartao("c_perdidas", 772, "Medidas.Horas perdidas por faltas", "Horas de prática perdidas"),
            cartao("c_cancel", 1024, "Medidas.Cancelados pela clínica", "Cancelados pela clínica"),
            Visual("matriz_dia_turno", "pivotTable", 16, 192, 520, 250,
                   {"Rows": [campo("calendario.dia_semana", "Dia")],
                    "Columns": [campo("atendimentos.turno", "Turno")],
                    "Values": [campo("Medidas.Taxa de faltas", "Taxa de faltas")]},
                   titulo="Taxa de faltas por dia e turno",
                   ordenar=ordenar_por("calendario.dia_semana")),
            Visual("colunas_espera", "clusteredColumnChart", 552, 192, 712, 250,
                   {"Category": [campo("atendimentos.faixa_espera_1a_consulta", "Espera na fila")],
                    "Y": [campo("Medidas.Taxa de faltas", "Taxa de faltas na 1ª consulta")]},
                   titulo="Falta na 1ª consulta por tempo de espera na fila",
                   filtros=[SO_PRIMEIRA], ordenar=ordenar_por("atendimentos.faixa_espera_1a_consulta")),
            Visual("linha_mes", "lineChart", 16, 458, 760, 250,
                   {"Category": [campo("calendario.mes_nome", "Mês")],
                    "Y": [campo("Medidas.Taxa de faltas", "Taxa de faltas")]},
                   titulo="Taxa de faltas por mês", ordenar=ordenar_por("calendario.mes_nome")),
            nota("nota_faltas", 792, 458, 472, 250,
                 "Como ler: a segunda de manhã concentra as faltas, e quem esperou mais de 60 dias na fila "
                 "falta duas vezes mais na 1ª consulta do que quem esperou até 7 dias. Ação sugerida: "
                 "confirmação na véspera (WhatsApp) para as primeiras consultas e para a segunda de manhã, "
                 "e lista de espera para preencher o horário de quem desmarca."),
        ],
    ),
    (
        "agenda_fila", "Agenda e fila",
        [
            cabecalho("Agenda e fila de espera",
                      "A agenda está cheia? Quem está esperando? Ocupação = agendamentos / horários ofertados."),
            *filtros_padrao(),
            cartao("c_ofertados", 16, "Medidas.Horários ofertados", "Horários ofertados"),
            cartao("c_ocupacao", 268, "Medidas.Ocupação da agenda", "Ocupação da agenda"),
            cartao("c_aproveitamento", 520, "Medidas.Aproveitamento", "Aproveitamento (realizados)"),
            cartao("c_entradas", 772, "Medidas.Entradas na fila", "Entradas na fila"),
            cartao("c_aguardando", 1024, "Medidas.Aguardando", "Aguardando em 31/10"),
            Visual("barras_ocupacao", "clusteredBarChart", 16, 192, 620, 516,
                   {"Category": [campo("clinicas.clinica", "Clínica")],
                    "Y": [campo("Medidas.Ocupação da agenda", "Ocupação"),
                          campo("Medidas.Aproveitamento", "Aproveitamento")]},
                   titulo="Ocupação e aproveitamento por clínica",
                   ordenar=ordenar_por("Medidas.Ocupação da agenda")),
            Visual("tabela_fila", "tableEx", 652, 192, 612, 300,
                   {"Values": [campo("clinicas.clinica", "Clínica"),
                               campo("Medidas.Ocupação da agenda", "Ocupação"),
                               campo("Medidas.Espera mediana (dias)", "Espera mediana (dias)"),
                               campo("Medidas.Aguardando", "Aguardando")]},
                   titulo="Fila por clínica", ordenar=ordenar_por("Medidas.Espera mediana (dias)", "Descending")),
            nota("nota_fila", 652, 508, 612, 200,
                 "Como ler: Fisioterapia de Olinda tem a agenda mais vazia e a fila mais longa ao mesmo tempo. "
                 "Não falta sala: a primeira consulta só é marcada às segundas e quartas, e a recepção não "
                 "consegue contato com parte da fila. Ação sugerida: abrir primeira consulta todos os dias e "
                 "atualizar os telefones da fila."),
        ],
    ),
    (
        "alunos", "Alunos e estágio",
        [
            cabecalho("Alunos e horas de prática",
                      "A clínica-escola existe para formar: cada falta é uma hora de prática a menos (2026.1)."),
            cartao("c_meta", 16, "Medidas.% alunos na meta", "Alunos que bateram a meta"),
            cartao("c_horas_aluno", 268, "Medidas.Horas por aluno", "Horas por aluno"),
            cartao("c_perdidas", 520, "Medidas.Horas perdidas por faltas", "Horas perdidas por faltas"),
            cartao("c_alunos", 772, "Medidas.Alunos com meta", "Alunos no semestre"),
            Visual("colunas_servico", "clusteredColumnChart", 16, 192, 620, 516,
                   {"Category": [campo("alunos.curso", "Curso")],
                    "Y": [campo("Medidas.% alunos na meta", "% na meta")]},
                   titulo="Alunos que bateram a meta, por curso", filtros=[SEMESTRE_2026_1]),
            Visual("tabela_alunos", "tableEx", 652, 192, 612, 516,
                   {"Values": [campo("alunos.matricula", "Matrícula"), campo("alunos.nome", "Aluno"),
                               campo("alunos.curso", "Curso"), campo("alunos.unidade", "Unidade"),
                               campo("Medidas.Horas de prática", "Horas"),
                               campo("alunos.meta_ate_fim_dados", "Meta"),
                               campo("Medidas.Horas perdidas por faltas", "Perdidas")]},
                   titulo="Horas de cada aluno (2026.1)", filtros=[SEMESTRE_2026_1],
                   ordenar=ordenar_por("Medidas.Horas de prática")),
        ],
    ),
    (
        "qualidade", "Qualidade dos dados",
        [
            cabecalho("Qualidade dos dados",
                      "O que a padronização encontrou nas planilhas, no sistema e na fila, e o que fez com cada caso."),
            cartao("c_regras", 16, "Medidas.Regras aplicadas", "Correções e sinalizações"),
            cartao("c_conferir", 268, "Medidas.Linhas para conferir", "Linhas para conferir na origem"),
            cartao("c_recuperados", 520, "Medidas.Prontuários recuperados", "Prontuários recuperados"),
            Visual("tabela_regras", "tableEx", 16, 192, 620, 516,
                   {"Values": [campo("resumo_qualidade.regra", "Regra"),
                               campo("resumo_qualidade.descricao", "O que foi encontrado"),
                               campo("resumo_qualidade.acao", "O que foi feito"),
                               campo("resumo_qualidade.ocorrencias", "Ocorrências")]},
                   titulo="Regras de padronização", ordenar=ordenar_por("resumo_qualidade.regra")),
            Visual("tabela_inconsistencias", "tableEx", 652, 192, 612, 516,
                   {"Values": [campo("inconsistencias.regra", "Regra"),
                               campo("inconsistencias.arquivo", "Arquivo"),
                               campo("inconsistencias.aba", "Aba"),
                               campo("inconsistencias.linha", "Linha"),
                               campo("inconsistencias.valor_original", "Valor original"),
                               campo("inconsistencias.valor_final", "Valor final")]},
                   titulo="Linhas para conferir na origem"),
        ],
    ),
]


# ============================================================== escrita


def _texto(conteudo: str | dict[str, Any]) -> str:
    if isinstance(conteudo, str):
        return conteudo
    return json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n"


def plataforma(tipo: str) -> dict[str, Any]:
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/"
        "platformProperties/2.0.0/schema.json",
        "metadata": {"type": tipo, "displayName": NOME},
        "config": {"version": "2.0", "logicalId": tag("item", tipo)},
    }


def gerar(destino: Path = PASTA) -> list[Path]:
    """Escreve o projeto; não apaga pastas inteiras (o OneDrive trava pasta recém-apagada)."""
    relatorio = destino / f"{NOME}.Report"
    modelo = destino / f"{NOME}.SemanticModel"
    arquivos: dict[Path, str] = {}

    def _gravar(caminho: Path, conteudo: str | dict[str, Any]) -> None:
        arquivos[caminho] = _texto(conteudo)

    _gravar(destino / f"{NOME}.pbip", {"version": "1.0", "artifacts": [{"report": {"path": f"{NOME}.Report"}}],
                                      "settings": {"enableAutoRecovery": True}})
    _gravar(destino / ".gitignore", "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")
    _gravar(modelo / ".platform", plataforma("SemanticModel"))
    _gravar(modelo / "definition.pbism", {"version": "4.2", "settings": {}})
    d = modelo / "definition"
    _gravar(d / "database.tmdl", "database\n\tcompatibilityLevel: 1606\n\n")
    _gravar(d / "model.tmdl", tmdl_modelo())
    _gravar(d / "expressions.tmdl", tmdl_expressoes())
    _gravar(d / "relationships.tmdl", tmdl_relacoes())
    _gravar(d / "cultures" / "pt-BR.tmdl", "cultureInfo pt-BR\n\n")
    for t in TABELAS:
        _gravar(d / "tables" / f"{t.nome}.tmdl", tmdl_tabela(t))
    _gravar(d / "tables" / "Medidas.tmdl", tmdl_medidas())

    _gravar(relatorio / ".platform", plataforma("Report"))
    _gravar(relatorio / "definition.pbir",
            {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NOME}.SemanticModel"}}})
    r = relatorio / "definition"
    _gravar(r / "version.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/"
        "definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    })
    _gravar(relatorio / "StaticResources" / "RegisteredResources" / "tema-clinicas.json", TEMA)
    _gravar(r / "report.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/"
        "definition/report/3.3.0/schema.json",
        "themeCollection": {"customTheme": {
            "name": "tema-clinicas.json",
            "reportVersionAtImport": {"visual": "2.13.0", "report": "3.4.0", "page": "2.3.1"},
            "type": "RegisteredResources",
        }},
        "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                              "items": [{"name": "tema-clinicas.json", "path": "tema-clinicas.json",
                                         "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True,
                     "useEnhancedTooltips": False},
    })
    _gravar(r / "pages" / "pages.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/"
        "definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [nome for nome, _, _ in PAGINAS],
        "activePageName": PAGINAS[0][0],
    })
    for nome, exibicao, visuais in PAGINAS:
        _gravar(r / "pages" / nome / "page.json", {"$schema": SCHEMA_PAGINA, "name": nome, "displayName": exibicao,
                                                  "displayOption": "FitToPage", "height": 720, "width": 1280})
        for z, v in enumerate(visuais):
            _gravar(r / "pages" / nome / "visuals" / v.nome / "visual.json", _json_visual(v, z * 1000))

    for caminho, texto in arquivos.items():
        caminho.parent.mkdir(parents=True, exist_ok=True)
        if not caminho.exists() or caminho.read_text(encoding="utf-8") != texto:
            caminho.write_text(texto, encoding="utf-8", newline="\n")
    for pasta in (relatorio / "definition", modelo / "definition", relatorio / "StaticResources"):
        for antigo in pasta.rglob("*"):
            if antigo.is_file() and antigo not in arquivos:
                antigo.unlink()
    return sorted(arquivos)


if __name__ == "__main__":
    print(f"{len(gerar())} arquivos gerados em {PASTA}")
