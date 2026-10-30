"""Confere as medidas DAX do Power BI contra os números calculados em Python.

Como funciona: com o relatório aberto no Power BI Desktop, o motor do modelo (Analysis
Services) roda numa porta local. Este script gera um PowerShell que se conecta a essa porta
pela biblioteca ADOMD que vem com o Power BI, atualiza os dados e executa consultas DAX.
O resultado é comparado com o painel.json (Python). Se algum número divergir, o script falha.

Uso (com o clinicas_escola.pbip aberto no Power BI Desktop):
    python scripts/conferir_powerbi.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "powerbi" / "conferencia_powerbi.json"
DLL = r"C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.AdomdClient.dll"

CONSULTAS = {
    "geral": """EVALUATE ROW(
        "agendamentos", [Agendamentos], "realizados", [Realizados], "faltas", [Faltas],
        "taxa_faltas", [Taxa de faltas], "ofertados", [Horários ofertados],
        "ocupacao", [Ocupação da agenda], "aproveitamento", [Aproveitamento],
        "horas_pratica", [Horas de prática], "horas_perdidas_faltas", [Horas perdidas por faltas],
        "espera_mediana_dias", [Espera mediana (dias)], "fila_aguardando_fim", [Aguardando],
        "linhas_para_conferir", [Linhas para conferir])""",
    "por_clinica": """EVALUATE SUMMARIZECOLUMNS(clinicas[clinica],
        "taxa_faltas", [Taxa de faltas], "ocupacao", [Ocupação da agenda],
        "espera_mediana_dias", [Espera mediana (dias)], "fila_aguardando_fim", [Aguardando])""",
    "calor": """EVALUATE SUMMARIZECOLUMNS(calendario[dia_semana], atendimentos[turno],
        "taxa_faltas", [Taxa de faltas])""",
    "espera": """EVALUATE SUMMARIZECOLUMNS(atendimentos[faixa_espera_1a_consulta],
        "taxa_faltas", [Taxa de faltas], "consultas", [Realizados] + [Faltas])""",
    "alunos": """EVALUATE CALCULATETABLE(SUMMARIZECOLUMNS(alunos[servico],
        "bateram_meta", [Alunos na meta], "alunos", [Alunos com meta]), alunos[semestre] = "2026.1")""",
    "variacao": """EVALUATE SUMMARIZECOLUMNS(calendario[mes], "taxa", [Taxa de faltas],
        "variacao_pp", [Variação das faltas (p.p.)])""",
    "novas": """EVALUATE ROW(
        "faturamento", [Faturamento], "perdido_faltas", [Deixou de entrar com faltas],
        "ticket_medio", [Ticket médio], "espera_media", [Espera na recepção (min)],
        "ate_30", [Chamados em até 30 min], "segunda_manha", [Espera segunda de manhã (min)],
        "justificadas", [% faltas justificadas], "chuva", [% faltas por chuva])""",
    "fat_unidade": """EVALUATE SUMMARIZECOLUMNS(clinicas[unidade_nome], "faturamento", [Faturamento])""",
    "motivos": """EVALUATE SUMMARIZECOLUMNS(atendimentos[motivo], "faltas", [Faltas],
        "desmarcacoes", [Cancelados pelo paciente])""",
}

POWERSHELL = r"""
$ErrorActionPreference = 'Stop'
Add-Type -Path '__DLL__'
$pasta = Join-Path $env:LOCALAPPDATA 'Microsoft\Power BI Desktop\AnalysisServicesWorkspaces'
$arquivo = Get-ChildItem $pasta -Recurse -Filter 'msmdsrv.port.txt' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$porta = [System.Text.Encoding]::Unicode.GetString([System.IO.File]::ReadAllBytes($arquivo.FullName)).Trim([char]0, ' ')
$con = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$porta")
$con.Open()
$cmd = $con.CreateCommand()
$cmd.CommandText = 'SELECT [CATALOG_NAME] FROM $SYSTEM.DBSCHEMA_CATALOGS'
$leitor = $cmd.ExecuteReader(); $leitor.Read() | Out-Null; $banco = $leitor.GetString(0); $leitor.Close()
$cmd.CommandText = '{"refresh": {"type": "full", "objects": [{"database": "' + $banco + '"}]}}'
$cmd.ExecuteNonQuery() | Out-Null
$resultado = @{}
foreach ($par in (Get-Content '__CONSULTAS__' -Raw -Encoding UTF8 | ConvertFrom-Json).PSObject.Properties) {
    $cmd.CommandText = $par.Value
    $leitor = $cmd.ExecuteReader()
    $linhas = @()
    while ($leitor.Read()) {
        $linha = [ordered]@{}
        for ($i = 0; $i -lt $leitor.FieldCount; $i++) {
            $nome = $leitor.GetName($i) -replace '^.*\[(.*)\]$', '$1'
            $linha[$nome] = if ($leitor.IsDBNull($i)) { $null } else { $leitor.GetValue($i) }
        }
        $linhas += [pscustomobject]$linha
    }
    $leitor.Close()
    $resultado[$par.Name] = $linhas
}
$con.Close()
$resultado | ConvertTo-Json -Depth 5 | Out-File '__SAIDA__' -Encoding utf8
"""


def rodar_powershell() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        consultas = Path(tmp) / "consultas.json"
        consultas.write_text(json.dumps(CONSULTAS, ensure_ascii=False), encoding="utf-8")
        saida = Path(tmp) / "saida.json"
        script = Path(tmp) / "conferir.ps1"
        texto = (POWERSHELL.replace("__DLL__", DLL).replace("__CONSULTAS__", str(consultas))
                 .replace("__SAIDA__", str(saida)))
        script.write_text(texto, encoding="utf-8-sig")  # PowerShell 5.1 precisa do BOM para acentos
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], check=True)
        return json.loads(saida.read_text(encoding="utf-8-sig"))


def perto(a: float | None, b: float | None, tolerancia: float = 1e-6) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tolerancia * max(1.0, abs(float(b)))


def comparar(pbi: dict, painel: dict) -> list[str]:
    erros: list[str] = []

    def confere(rotulo: str, valor_pbi: object, valor_py: object) -> None:
        ok = perto(valor_pbi, valor_py, 1e-4)
        print(f"  {'ok ' if ok else 'ERRO'} {rotulo:<52} Power BI={valor_pbi!s:<14} Python={valor_py}")
        if not ok:
            erros.append(rotulo)

    print("Geral")
    geral = pbi["geral"][0] if isinstance(pbi["geral"], list) else pbi["geral"]
    for chave, valor in geral.items():
        alvo = painel["qualidade"]["linhas_para_conferir"] if chave == "linhas_para_conferir" else \
            painel["geral"][chave]
        confere(chave, valor, alvo)

    print("Por clínica")
    py = {c["clinica"]: c for c in painel["por_clinica"]}
    for linha in pbi["por_clinica"]:
        c = py[linha["clinica"]]
        for chave in ("taxa_faltas", "ocupacao", "espera_mediana_dias", "fila_aguardando_fim"):
            confere(f"{linha['clinica']} · {chave}", linha[chave] or 0, c[chave])

    print("Faltas por dia e turno")
    py_calor = {(x["dia"], x["turno"]): x["taxa_faltas"] for x in painel["calor_faltas"]}
    for linha in pbi["calor"]:
        confere(f"{linha['dia_semana']} {linha['turno']}", linha["taxa_faltas"],
                py_calor[(linha["dia_semana"], linha["turno"])])

    print("Falta na 1ª consulta por espera")
    nomes = {"Até 7 dias": "até 7 dias", "8 a 30 dias": "8 a 30", "31 a 60 dias": "31 a 60",
             "Mais de 60 dias": "mais de 60"}
    py_espera = {x["faixa"]: x for x in painel["espera_x_falta"]}
    for linha in pbi["espera"]:
        if linha["faixa_espera_1a_consulta"]:
            x = py_espera[nomes[linha["faixa_espera_1a_consulta"]]]
            confere(f"{linha['faixa_espera_1a_consulta']} · taxa", linha["taxa_faltas"], x["taxa_faltas"])
            confere(f"{linha['faixa_espera_1a_consulta']} · consultas", linha["consultas"], x["consultas"])

    print("Alunos 2026.1 na meta")
    py_alunos = {x["servico"]: x for x in painel["alunos_2026_1"]}
    for linha in pbi["alunos"]:
        x = py_alunos[linha["servico"]]
        confere(f"{linha['servico']} · bateram a meta", linha["bateram_meta"], x["bateram_meta"])
        confere(f"{linha['servico']} · alunos", linha["alunos"], x["alunos"])

    # Medidas do faturamento, da recepção e dos motivos, contra o painel animado (dashboard.json).
    # Os valores do painel são arredondados (1 casa nos minutos, 2 nos reais, 4 nas frações).
    dash = json.loads((RAIZ / "site" / "dashboard" / "dados" / "dashboard.json").read_text(encoding="utf-8"))
    b = dash["blocos"]["*"]
    novas = pbi["novas"][0] if isinstance(pbi["novas"], list) else pbi["novas"]
    e = b["espera"]
    ate_30 = sum(f["qtd"] for f in e["faixas"][:3]) / e["medidos"]
    chuva = next(m["qtd"] for m in b["motivos"]["faltas"] if m["motivo"] == "Chuva")
    com_motivo = sum(m["qtd"] for m in b["motivos"]["faltas"] if m["motivo"] not in ("Sem justificativa",
                                                                                   "Não identificado"))

    def confere_aprox(rotulo: str, valor_pbi: float, valor_py: float, tolerancia: float) -> None:
        ok = valor_pbi is not None and abs(float(valor_pbi) - float(valor_py)) <= tolerancia
        print(f"  {'ok ' if ok else 'ERRO'} {rotulo:<52} Power BI={valor_pbi!s:<14} Python={valor_py}")
        if not ok:
            erros.append(rotulo)

    print("Faturamento, recepção e motivos")
    confere("faturamento", novas["faturamento"], b["faturamento"]["total"])
    confere("deixou de entrar com faltas", novas["perdido_faltas"], b["faturamento"]["perdido_faltas"])
    confere_aprox("ticket médio", novas["ticket_medio"], b["faturamento"]["ticket_medio"], 0.005)
    confere_aprox("espera na recepção (min)", novas["espera_media"], e["media_min"], 0.05)
    confere("chamados em até 30 min", novas["ate_30"], ate_30)
    confere_aprox("espera segunda de manhã (min)", novas["segunda_manha"], e["segunda_manha_min"], 0.05)
    confere_aprox("% faltas justificadas", novas["justificadas"], b["motivos"]["justificadas_pct"], 0.00005)
    confere("% faltas por chuva", novas["chuva"], chuva / com_motivo)
    py_un = {u["unidade"]: u["faturamento"] for u in b["unidades"]}
    for linha in pbi["fat_unidade"]:
        confere(f"faturamento · {linha['unidade_nome']}", linha["faturamento"],
                py_un[linha["unidade_nome"].split()[0]])
    py_f = {m["motivo"]: m["qtd"] for m in b["motivos"]["faltas"]}
    py_d = {m["motivo"]: m["qtd"] for m in b["motivos"]["desmarcacoes"]}
    for linha in pbi["motivos"]:
        if linha["motivo"]:
            confere(f"faltas · {linha['motivo']}", linha["faltas"] or 0, py_f.get(linha["motivo"], 0))
            confere(f"desmarcações · {linha['motivo']}", linha["desmarcacoes"] or 0, py_d.get(linha["motivo"], 0))
    return erros


if __name__ == "__main__":
    resultado = rodar_powershell()
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    painel = json.loads((RAIZ / "site" / "dados" / "painel.json").read_text(encoding="utf-8"))
    falhas = comparar(resultado, painel)
    print(f"\n{'Tudo confere.' if not falhas else f'{len(falhas)} divergências.'}")
    sys.exit(1 if falhas else 0)
