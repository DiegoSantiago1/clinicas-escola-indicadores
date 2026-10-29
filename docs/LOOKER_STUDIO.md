# Looker Studio: passo a passo (cerca de 1 hora)

O Looker Studio não pode ser criado por código: precisa da sua conta Google. A base já está pronta em `data/looker/base_looker_studio.xlsx`, com três abas:

| Aba | Linhas | Uma linha é |
|---|---|---|
| `indicadores_mensais` | 110 | um mês de uma clínica (agendamentos, realizados, faltas, horários ofertados, horas...) |
| `faltas_dia_turno` | 1.084 | um mês, uma clínica, um dia da semana e um turno (realizados e faltas) |
| `fila` | 15.153 | um paciente na fila (inscrição, 1ª consulta, situação, dias de espera) |

## 1. Subir a base (5 min)
1. drive.google.com → Novo → Upload de arquivo → `base_looker_studio.xlsx`.
2. Clique com o botão direito → Abrir com → Planilhas Google. Isso cria uma planilha Google com as três abas.

## 2. Conectar no Looker Studio (5 min)
1. lookerstudio.google.com → Criar → Relatório.
2. Adicionar dados → Planilhas Google → escolha a planilha → aba `indicadores_mensais` → marque "Usar a primeira linha como cabeçalho" → Adicionar.
3. Repita "Adicionar dados" para as abas `faltas_dia_turno` e `fila`.
4. Em Recurso → Gerenciar fontes de dados → `indicadores_mensais` → Editar: confira que `mes` está como **Data** e os números como **Número**.

## 3. Campos calculados (10 min)
Na fonte `indicadores_mensais`, Adicionar um campo:

| Nome | Fórmula |
|---|---|
| Taxa de faltas | `SUM(faltas) / (SUM(realizados) + SUM(faltas))` (tipo: Percentual) |
| Ocupação da agenda | `SUM(agendamentos) / SUM(horarios_ofertados)` (Percentual) |
| Aproveitamento | `SUM(realizados) / SUM(horarios_ofertados)` (Percentual) |

Na fonte `faltas_dia_turno`, a mesma Taxa de faltas. Na fonte `fila`, nada: use `dias_espera` com agregação **Mediana**.

**Por que a fórmula soma antes de dividir:** se a planilha tivesse a taxa de cada mês e o Looker fizesse a média das taxas, um mês pequeno pesaria igual a um mês grande. Somando faltas e realizados e dividindo depois, a taxa continua certa com qualquer filtro (é o mesmo motivo do DIVIDE sobre medidas no DAX).

## 4. Página (30 min)
1. **Cartões de visão geral** (fonte `indicadores_mensais`): `realizados` (Soma), Taxa de faltas, Ocupação da agenda, `horas_pratica` (Soma).
2. **Gráfico de colunas**: dimensão `mes`, métricas `realizados` e `faltas`.
3. **Barras**: dimensão `clinica`, métrica Taxa de faltas, ordenado decrescente.
4. **Tabela dinâmica** (fonte `faltas_dia_turno`): linha `dia_semana`, coluna `turno`, métrica Taxa de faltas, com mapa de calor (Estilo → Mapa de calor).
5. **Tabela** (fonte `fila`): dimensão `clinica`, métrica `dias_espera` com agregação Mediana, e Contagem de registros filtrada por `situacao = Aguardando`.
6. **Controles**: Inserir → Lista suspensa de `unidade_nome` e de `servico_nome`.

## 5. Conferir (5 min)
Sem filtro, os números têm de ser: **53.582** realizados, **20,3%** de faltas, **84,4%** de ocupação, Fisioterapia · Olinda com **41,5%** de ocupação. Se algum não bater, a agregação de algum campo está errada (por exemplo, Média em vez de Soma).

## 6. Compartilhar (5 min)
Compartilhar → Gerenciar acesso → "Qualquer pessoa com o link pode ver". Cole o link no README (seção "Acessar o projeto") e me mande para eu pôr na página.

## Power BI x Looker Studio (para a entrevista)
- O Power BI tem modelo de dados (relacionamentos, DAX, Power Query); o Looker Studio trabalha melhor com tabelas já agregadas e campos calculados simples.
- O Looker Studio é gratuito e se compartilha por link, como um documento Google; o Power BI precisa do Power BI Service (licença) para compartilhar.
- Por isso a base do Looker já vem agregada: a modelagem pesada fica no Python e no Power BI.
