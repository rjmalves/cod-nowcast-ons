---
name: Bug Report
about: Reportar um problema ou comportamento inesperado
title: '[BUG] '
labels: bug
assignees: ''
---

## Descrição do bug

Uma descrição clara e concisa do problema.

## Passos para reproduzir

Informe o comando executado e os passos até o problema.

```bash
cod-nowcast-ons nowcast --config config.toml
```

## Comportamento esperado

O que você esperava que acontecesse.

## Comportamento observado

O que aconteceu de fato.

## Código de saída

O código de saída do comando (0, 1, 2, 3 ou 4):

```text

```

## Resumo da execução

O JSON `nwp.run-summary/1` que a ferramenta imprime na saída padrão, quando houver:

```json

```

## Logs

As linhas JSON que a ferramenta imprime na saída de erro:

```text

```

## Ambiente

- Saída de `cod-nowcast-ons --version`:
- Versão do Python:
- Sistema operacional:
- Tag ou digest da imagem, se usar Docker:
- Armazenamento (local ou S3):

## Configuração

O arquivo de configuração TOML, sem credenciais, nomes de bucket nem caminhos internos:

```toml

```

Variáveis `COD_NOWCAST_ONS_*` definidas, com os valores sensíveis removidos:

## Dados de entrada

- Quadros presentes (quantidade e horários):
- Subgrade usada:

## Contexto adicional

Qualquer outra informação relevante.

## Checklist

- [ ] Verifiquei que não existe uma issue similar
- [ ] Removi credenciais, nomes de bucket e caminhos internos da configuração e dos logs
