# Decisões técnicas

Cada decisão com o problema, a escolha, a alternativa e o porquê.

## D1. Dados simulados, com a verdade guardada
**Problema.** Dados reais de clínica são sensíveis (saúde, LGPD) e não podem ir para um repositório público.
**Escolha.** Uma simulação dia a dia (`simulacao.py`): pacientes entram na fila, a recepção chama para os horários livres, cada sessão marca a próxima, e a falta depende do serviço, do dia, do mês, da espera e do histórico do paciente. A "verdade" fica em `data/verdade/` (fora do git).
**Por quê.** Com a verdade guardada, dá para **provar** que a padronização funciona: os testes comparam a base tratada com a simulação linha a linha. Com dados reais, só daria para dizer "parece certo".

## D2. Bagunçar os dados de propósito
**Escolha.** `fontes.py` transforma a verdade nas fontes que um analista recebe: CSV do sistema em Windows-1252 com meses sobrepostos, coluna nova a partir de maio, planilhas com uma aba por mês e 13 tipos de problema de digitação, fila com unidade e serviço escritos de vários jeitos. Cada problema é contado no `manifesto.json`.
**Por quê.** É o trabalho real da vaga ("tratar e integrar dados de planilhas e sistemas", "identificar inconsistências").

## D3. Padronização em Python, não só no Power Query
**Alternativa.** Fazer toda a limpeza no Power Query.
**Escolha.** Python padroniza; o Power Query cuida de tipos, chaves e mesclagem.
**Por quê.** O Looker Studio não lê o Power Query: a limpeza teria de ser feita duas vezes, com risco de as duas darem números diferentes. Uma regra só, testada, serve às duas ferramentas.

## D4. Na dúvida, sinalizar em vez de adivinhar
- Situação escrita de um jeito que o dicionário não conhece: o programa **para** e diz arquivo, aba e linha (não chuta "Realizado").
- Prontuário em branco: recuperado pelo nome **só quando o nome é único** no cadastro. A primeira versão desempatava homônimos pelo prontuário presente na planilha e errou 7 de 2.046; agora os homônimos ficam sinalizados (159) e a conferência dá **0 erros** em 2.041.
- Ano digitado errado: corrigido pelo mês da aba só quando o dia e o mês batem.

## D5. A ordem das correções importa
A fila corrige os atendimentos e os atendimentos corrigem a fila. A primeira versão deduzia o tipo de atendimento (1ª consulta ou retorno) usando a data da fila **antes** de corrigir as datas erradas da fila, e errou 5 linhas. Invertida a ordem (primeiro R15, depois R13b), sobraram 2, que são linhas sem prontuário: não há como saber.

## D6. Minimização (LGPD)
A base tratada não leva nome nem data de nascimento do paciente: só prontuário, sexo e faixa etária. Os nomes ficam só nas fontes, onde são necessários para recuperar o prontuário. Há um teste para isso.

## D7. Taxa de faltas sem os cancelamentos
Faltas / (realizados + faltas). Ver `docs/INDICADORES.md`.

## D8. Power BI em PBIP gerado por código, conferido no motor do Power BI
O relatório é um projeto PBIP (TMDL + PBIR) gerado por `powerbi/gerar_pbip.py`: tudo revisável no git. Para conferir, `scripts/conferir_powerbi.py` conecta na porta local do Analysis Services do Power BI Desktop (biblioteca ADOMD), atualiza os dados e roda as medidas em DAX; o resultado é comparado com o Python. Todos os números conferem (totais, 10 clínicas, 10 cruzamentos dia x turno, 4 faixas de espera, alunos na meta).

## D9. Cultura en-US no Power Query
O CSV usa ponto decimal e data ISO. Com a cultura pt-BR, "1.5" viraria 15 e a data poderia inverter dia e mês. Por isso o `Table.TransformColumnTypes` recebe "en-US".

## D10. Calibração da simulação
A procura de cada clínica é calculada a partir dos horários ofertados e de quantos agendamentos um paciente gera (medido numa primeira rodada), para a ocupação ficar perto de 85%. A simulação começa em agosto de 2025 (aquecimento) para novembro não sair vazio. Uma primeira versão deixava o mesmo aluno com dois pacientes no mesmo horário (6.154 conflitos achados pela própria padronização); corrigido, sobraram exatamente os 138 plantados.

## D11. Arquivos reproduzíveis
Mesma semente, mesmos arquivos: o teste compara os hashes com o `manifesto.json` versionado. O `.xlsx` guarda a data de gravação dentro do zip, então o hash dele é do conteúdo das células. As quebras de linha são fixas (`\r\n` na exportação do "sistema Windows", `\n` no resto) e o `.gitattributes` impede o git de convertê-las.
