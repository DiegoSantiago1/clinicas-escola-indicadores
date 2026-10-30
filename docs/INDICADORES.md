# Dicionário de indicadores

Cada indicador tem nome, fórmula, fonte, frequência e para que serve. As fórmulas são as mesmas no Python (`src/clinicas/indicadores.py`), no DAX (`powerbi/gerar_pbip.py`) e nos campos calculados do Looker Studio (`docs/LOOKER_STUDIO.md`). O `scripts/conferir_powerbi.py` confere que o DAX e o Python dão o mesmo número.

| Indicador | Fórmula | Fonte | Frequência | Para que serve |
|---|---|---|---|---|
| Agendamentos | quantidade de linhas de `atendimentos` | sistema + planilhas | diária | volume de trabalho da recepção |
| Atendimentos realizados | agendamentos com situação "Realizado" | sistema + planilhas | diária | produção da clínica |
| **Taxa de faltas** | faltas / (realizados + faltas) | sistema + planilhas | semanal | o principal indicador da operação |
| Cancelados pelo paciente | situação "Cancelado pelo paciente" | sistema + planilhas | semanal | remarcação; não conta como falta |
| Cancelados pela clínica | situação "Cancelado pela clínica" | sistema + planilhas | semanal | turnos perdidos por ausência do supervisor |
| Horários ofertados | salas x horários do turno, nos dias abertos (metade no plantão de julho) | grade de horários + calendário | mensal | capacidade |
| **Ocupação da agenda** | agendamentos / horários ofertados | atendimentos + oferta | mensal | a agenda está cheia? |
| Aproveitamento | realizados / horários ofertados | atendimentos + oferta | mensal | quanto da capacidade virou atendimento |
| Entradas na fila | pacientes inscritos na fila (pela data de inscrição) | fila da recepção | mensal | procura |
| **Espera mediana** | mediana de dias entre inscrição e 1ª consulta, de quem foi chamado no período | fila da recepção | mensal | quanto o paciente espera |
| Aguardando | pacientes com situação "Aguardando" em 31/10/2026 | fila da recepção | semanal | tamanho da fila hoje |
| **Horas de prática** | soma da duração dos atendimentos realizados (60 min; Odontologia 120 min) | atendimentos | semanal | a prática do aluno, razão de existir da clínica-escola |
| Horas perdidas por faltas | soma da duração dos agendamentos com falta | atendimentos | semanal | o custo da falta para a formação |
| Alunos na meta | alunos com horas ≥ meta proporcional | atendimentos + alunos | semanal | quem está no ritmo do estágio |
| Linhas para conferir | linhas sinalizadas pela padronização | inconsistências | a cada carga | qualidade dos dados |
| **Faturamento** | soma da taxa social dos atendimentos realizados de pacientes não isentos | atendimentos + tabela da taxa + cadastro | mensal | receita da clínica |
| Deixou de entrar com faltas | soma da taxa dos agendamentos com falta de pacientes não isentos | atendimentos + tabela + cadastro | mensal | o custo da falta em dinheiro |
| Ticket médio | faturamento / atendimentos pagos | atendimentos | mensal | quanto paga quem paga |
| **Espera na recepção** | média de minutos entre a chegada e a chamada, nos atendimentos com os dois horários | tablet da recepção | semanal | tempo do paciente na sala de espera |
| Chamados em até 30 min | atendimentos com espera < 30 min / atendimentos com espera medida | tablet da recepção | semanal | meta de atendimento |
| Faltas justificadas | faltas com motivo informado / faltas | tablet da recepção | mensal | quanto a recepção sabe por que o paciente falta |
| Motivo de falta ou desmarcação | contagem por motivo classificado (R16) | tablet da recepção | mensal | onde agir (lembrete, transporte, horário) |

## Decisões de definição (as que mais cairiam numa entrevista)

- **Por que a taxa de faltas não usa todos os agendamentos no denominador?** Porque o cancelamento avisado libera o horário para outro paciente. A falta é o problema: o horário se perde. Com todos os agendamentos no denominador, a taxa ficaria menor e esconderia o problema.
- **Meta proporcional.** A meta é do semestre inteiro (ex.: 200 h em Psicologia). Em 31/10, o semestre 2026.2 está pela metade, então a meta comparada é a fração dos dias letivos já decorridos. O 2025.2 fica sem meta: os dados começam em novembro e as horas de agosto a outubro não estão na base.
- **Espera mediana, e não média.** Poucos pacientes que esperam meses puxariam a média para cima. A mediana diz quanto espera o paciente típico.
- **Faturamento sem os atendimentos sem prontuário.** Sem o prontuário não dá para saber se o paciente é isento; o valor fica em branco e o painel diz quantos são (110), em vez de supor que pagou.
- **Espera na recepção por posição no turno, separada por área.** A Odontologia tem 2 horários por turno e as outras áreas 4. Somando tudo, o 3º e o 4º horário pareceriam esperar menos só porque não têm Odontologia (efeito de mistura).
- **Ocupação x aproveitamento.** Uma agenda 95% ocupada com 23% de faltas atende menos do que parece. Por isso os dois aparecem lado a lado.
