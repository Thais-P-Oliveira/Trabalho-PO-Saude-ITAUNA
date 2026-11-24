# Investimento de construção, apresentado separadamente

O modelo de localização foi restaurado sem investimento de construção na função
objetivo e na folga de 2%. Desde 15/11/2026, com custos de pessoal com encargos
e piso dos ACS de 2026, o plano de referência tem 12 novas UBS (11 rurais e 1
urbana), 43 eSF, 136 ACS e cobertura de 99,86%. O custo operacional anual dessa
rede é R$ 29.367.808. A etapa especializada continua usando esse plano primário fixo.

## Estimativa do investimento

Referência: Ministério da Saúde, Manual de Formalização Novo PAC Saúde 2025,
páginas 10–11, região Sudeste. Valores nominais de 2025, sem atualização.

| Porte | eSF de referência | Construção por UBS (R$) |
|---|---:|---:|
| I | 1 | 1.988.000 |
| II | 2 | 2.542.000 |
| III | 3 | 3.307.000 |
| IV | 4 | 4.306.000 |

As 12 novas UBS do plano têm uma eSF cada. Assim:

**Investimento de construção = 12 × R$ 1.988.000 = R$ 23.856.000.**

O cálculo lê o plano salvo e associa o porte ao número de eSF de cada nova UBS.
Não altera decisões, equipes, ACS ou encaminhamentos. Os projetos referenciais
também preveem saúde bucal; o modelo não dimensiona sua operação. O investimento
não inclui terrenos, equipamentos ou mobiliário, e não é uma cotação local.

## Repasse federal e pagamento da obra são operações diferentes

No Novo PAC, o repasse fundo a fundo para obras de UBS é feito em parcela única,
após o cumprimento da ação preparatória. Isso é a transferência do Ministério
da Saúde para o município, e não o pagamento integral à construtora.

A prefeitura paga a empresa conforme os critérios de medição, recebimento,
liquidação e pagamento estabelecidos no edital e contrato. Em regra, o pagamento
ocorre após a execução e o ateste das etapas. Antecipações são excepcionais e
exigem justificativa e previsão expressa; não foram presumidas neste estudo.

A duração da obra é definida no edital e no contrato. Ela pode ultrapassar um
exercício financeiro, observando disponibilidade de créditos e previsão no PPA.
O cronograma físico-financeiro define a execução e os desembolsos em cada ano.
Se uma despesa já foi empenhada em um ano e permanece a pagar no seguinte,
pode haver inscrição em restos a pagar, conforme os requisitos aplicáveis.
Assim, pagar em outro ano não significa necessariamente usar uma nova dotação
daquele ano; depende da execução orçamentária e da situação de cada despesa.

**Não há uma regra geral de pagamento da construção em cinco anos.**
Distribuir matematicamente o valor por cinco anos não cria uma condição
contratual e não comprova a possibilidade de financiar a obra nesse prazo.

A referência Novo PAC é usada para estimar valores; não foi identificada
habilitação ou aprovação de repasse para as 12 unidades propostas. A seleção
2025 previa limite de uma proposta de UBS por ente. A fonte de financiamento
das unidades do plano precisa, portanto, ser definida no planejamento real.
A portaria não exige contrapartida financeira obrigatória para o investimento,
mas o repasse não aumenta automaticamente se a licitação exceder o valor
previsto. A diferença é de responsabilidade municipal.

## Apresentação do investimento entre anos

Sem contratos e cronogramas das 12 obras, não se pode afirmar um calendário real.
Como exemplo de execução, 50% no primeiro ano e 50% no segundo resultam em:

| Ano relativo | Parcela ilustrativa da execução | Desembolso de construção (R$) |
|---|---:|---:|
| Ano 1 | 50% | 11.928.000 |
| Ano 2 | 50% | 11.928.000 |
| Total | 100% | 23.856.000 |

Esse é um cenário ilustrativo de avanço das obras e desembolsos, não um
parcelamento autorizado ou um cronograma aprovado. Percentuais reais devem
seguir o cronograma físico-financeiro e as autorizações orçamentárias.
Não se presumem juros ou reajustes nessa ilustração.

O custo operacional de R$ 29.367.808 por ano corresponde à rede completa após
implantação. Durante a construção, a despesa operacional depende da entrada
em funcionamento de cada unidade. Por isso, não se soma automaticamente todo
o investimento e um ano de operação ao orçamento de um único ano.
O indicador de 58,87% do orçamento inicial da atenção básica continua sendo
apenas a comparação do custo operacional anual com o orçamento de 2026.

## Executar

Na pasta principal:

```
python executar.py --investimento
python executar.py --investimento --percentuais 50 50 --saida resultados/investimento_construcao_2anos
```

O código em `codigos/calcular_investimento.py` gera tabela por UBS e relatório.
Os percentuais são opcionais, precisam somar 100 e servem somente à ilustração.
O cálculo de construção é separado da otimização. A página `ABRIR_RESULTADOS.html`
mostra o investimento do plano atual, com 12 novas UBS. Versões anteriores foram
preservadas no backup externo em `../historico_organizacao/`.

## Fontes oficiais consultadas em 11/11/2026

- Valores, portes e terreno: [Manual Novo PAC Saúde 2025](https://www.gov.br/saude/pt-br/centrais-de-conteudo/publicacoes/guias-e-manuais/2025/manual-de-formalizacao-de-propostas-novo-pac-saude.pdf), páginas 10–11.
- Repasse em parcela única e custo excedente: [FAQ do Ministério da Saúde](https://www.gov.br/saude/pt-br/assuntos/novo-pac-saude/faq/faq), seção Execução de obras.
- Seleção, contrapartida, equipamentos e limites: [Portaria GM/MS 6.640/2025](https://bvsms.saude.gov.br/bvs/saudelegis/gm/2025/prt6640_20_02_2025.html), arts. 7–8 e Anexo I.
- Etapas executadas e condições de pagamento: [TCU, critérios de medição e pagamento](https://licitacoesecontratos.tcu.gov.br/4-3-7-criterios-de-medicao-e-de-pagamento-2/), com base na Lei 14.133/2021, arts. 92 e 145.
- Contratos em mais de um exercício e restos a pagar: [TCU, duração](https://licitacoesecontratos.tcu.gov.br/5-11-5-duracao/), art. 105 e referência à ON AGU 101/2025. A aplicação ao caso concreto depende das regras orçamentárias pertinentes.
