# Fixture de regressão GOES COD

Esta nota pré-registra a fixture de regressão do produto `GOES_COD_BR`: a linha
de base de persistência, os critérios de seleção e a ordem dos candidatos. Ela
e `criteria.py` são commitados antes de qualquer triagem de candidato e antes
de qualquer execução do modelo sobre um candidato.

## Proveniência

A fixture é um recorte de 5 quadros `GOES_COD_BR` consecutivos, com 10 minutos
de intervalo, sobre uma grade de 76x76 pontos com passo de 0,04 grau. O
operador fornece os quadros candidatos fora do repositório, a partir da fonte
de produção.

O repositório registra apenas o nome do produto, os horários de varredura, a
extensão e os digests sha256. Ele nunca registra o nome do armazenamento de
origem, a URL, a conta nem o caminho da fonte.

O primeiro recorte (2024-08-01 00:10 a 00:50 UTC, commitado em `f126428`)
falhou no critério 3 e não é mais a fixture de regressão. A verificação
prévia, feita sem executar o modelo, deu:

- melhores deslocamentos por par: `(0, 0)`, `(0, 0)`, `(0, 0)` e `(0, 0)`;
- picos de Pearson por par: `0.877`, `0.847`, `0.880` e `0.912`;
- pixels finitos às 00:30, 00:40 e 00:50: `638`, `663` e `698`.

## Configuração da linha de base

- `P = 2` quadros passados e `L = 3` antecedências;
- `base_datetime` no terceiro slot nominal do recorte, ou seja, o primeiro
  quadro verificador;
- um subgrid cobrindo toda a extensão de 76x76 pontos.

## Definição da persistência

- A persistência é o quadro em `base - 10 min`, o mais recente dos quadros
  usados, com os valores não finitos trocados por 0 e repetido para cada
  antecedência.
- Os alvos são os quadros observados em `base`, `base + 10 min` e
  `base + 20 min`.
- A máscara compartilhada é a posição em que alvo, modelo e persistência são
  finitos, aplicada antes de `nwp_core.metrics.skill.rmse`.
- O teste informa o RMSE por antecedência, a média entre antecedências e a
  contagem da máscara por antecedência, e exige contagem maior que 0 em todas.
- O teste passa quando a média do modelo é menor que a da persistência.

## Critérios de seleção

`criteria.py` calcula os três critérios sobre uma janela de quadros, com
`P = 2`, `L = 3`, `WINDOW = P + L = 5`, `STEP = 10 min`, `MIN_FINITE = 500` e
`MAX_SHIFT = 5`:

1. **Contiguidade.** A janela tem `WINDOW` slots, cada um a `STEP` do anterior.
2. **Tamanho da amostra.** Cada um dos `L` quadros verificadores, nos slots
   `base`, `base + STEP` e `base + 2 * STEP`, tem ao menos `MIN_FINITE` pixels
   finitos. A contagem usa `np.isfinite` sobre a grade bruta.
3. **Translação.** Para cada um dos `WINDOW - 1` pares de quadros
   consecutivos, a busca percorre os deslocamentos inteiros `(dy, dx)` com
   `|dy|` e `|dx|` até `MAX_SHIFT`. O escore é a correlação de Pearson entre
   `a[i, j]` e `b[i + dy, j + dx]` sobre a sobreposição sem dobra, com NaN
   trocado por 0.
   - O melhor deslocamento tem o maior escore. Empates vão para o menor
     `dy * dy + dx * dx` e, depois, para o menor `(dy, dx)`.
   - Um escore indefinido, de uma sobreposição com variância zero, vale `-inf`:
     nunca vence e nunca gera erro. Uma janela assim falha no critério 3.
   - A janela tem translação quando todo deslocamento está estritamente dentro
     da janela de busca (`|dy|` e `|dx|` menores que `MAX_SHIFT`), tem
     `max(|dy|, |dx|) >= 1` e tem produto escalar positivo com cada um dos
     outros vetores de deslocamento.

A janela passa quando atende aos três critérios.

## Ordem dos candidatos

- Todo recorte candidato cobre latitude -23 a -20 e longitude -50 a -47, ambas
  inclusivas: uma grade de 76x76 pontos com passo de 0,04 grau, a mesma
  extensão do recorte anterior.
- Os candidatos são janelas de 5 quadros consecutivos de 10 minutos, triadas
  em ordem crescente de horário inicial.
- O slot nominal de cada quadro fornecido inicia uma janela, formada por esse
  slot mais `k` vezes 10 minutos, para `k` de 0 a 4. Uma janela com slot
  ausente falha no critério 1.
- Os candidatos são triados um por vez, em ordem crescente de horário inicial,
  e o primeiro que passa vira a fixture. O resultado de cada candidato triado é
  registrado. Os candidatos depois do primeiro que passa não são triados, e só
  o número deles é registrado.
- Uma janela cujo escore é indefinido, por exemplo com um quadro constante,
  falha no critério 3, e a triagem segue para o próximo candidato.
- Se nenhum candidato passar, o trabalho para.
- Nenhum modelo roda sobre candidato algum antes da captura do golden.

## Triagem

A triagem foi feita em 2026-11-04. Dos arquivos fornecidos pelo operador, 432
têm nome na chave do produto, `GOES_COD_BR_YYYYMMDD-HHMM.parquet`, e só eles
foram lidos. Nenhum modelo foi executado. Os candidatos foram triados em ordem
crescente de horário inicial até o primeiro que passa, e o primeiro candidato
que passa vira a fixture.

Saída de `python -m tests.fixtures.goes_cod.cut screen SRC_DIR`, copiada sem
alteração:

| start | contiguous | finite counts | shifts | translation | passed |
| --- | --- | --- | --- | --- | --- |
| 2024-02-07T00:00Z | yes | 5776, 5776, 5776 | (0,2) 0.876, (0,2) 0.850, (0,2) 0.887, (0,2) 0.857 | yes | yes |
not screened: 431
first passing: 2024-02-07T00:00Z
