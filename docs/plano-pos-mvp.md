# Plano pós-MVP

Proposta de 10/11/2026 para as atividades que faltam (S5.6). As horas são as do cronograma original. As datas dependem do novo prazo, que ainda precisa ser combinado com a orientação.

## Situação

Das 54 atividades do cronograma, 42 estão concluídas. Faltam 12, que somam cerca de 35 horas planejadas.

## Decisões necessárias antes de começar

1. **Novo prazo de entrega.** O cronograma original terminava em 6/9/2026.
2. **Hardware para a diversidade.** A semana 7 pede pelo menos três receptores. Cada receptor e o CubeSat precisam de uma placa LION, um ESP32 e uma antena, ou seja, pelo menos 4 conjuntos. Hoje há 2 funcionando.
3. **Diversidade de frequência.** O CubeSat tem um único RFM95, que transmite em uma frequência de cada vez. As opções são o CubeSat alternar as frequências ou usar um segundo transmissor.

## Sequência proposta

| Etapa | Atividades | Horas | Depende de |
|---|---|---|---|
| 1. Fechar o MVP | S5.5 demonstração, S5.6 este plano | 5 | Nada |
| 2. Estabilidade | S8.5 teste de 2 horas, S8.6 correções | 4 | Nada; o teste está em andamento |
| 3. Diversidade de antenas | S7.1 preparar receptores, S7.2 antenas | 8 | Decisão 2 |
| 4. Diversidade de frequência | S7.3 frequências | 4 | Decisões 2 e 3 |
| 5. Comparação | S7.5 RSSI e SNR por receptor | 3 | Etapas 3 e 4 |
| 6. Validação final | S9.3 campanha, S9.4 relatório, S9.5 demonstração final, S9.6 revisão do repositório | 13 | Etapas 3 a 5 |

As etapas 1 e 2 podem ser feitas já. O software das etapas 3 a 5 está pronto e testado com receptores simulados: falta montar o hardware e medir.

## Já adiantado

- Consolidação de pacotes de vários receptores e cálculo do ganho de diversidade (S7.4).
- Configuração de receptor e frequência na gravação de cada placa, e documentação para operar mais de um receptor (S7.6).
- Estatísticas por receptor, frequência e hora, com filtros no dashboard (S8.1 a S8.4).
- Protocolo e instalação documentados (S9.1, S9.2).
- Rascunho do relatório de testes (S9.4), em [relatorio-testes.md](relatorio-testes.md).
