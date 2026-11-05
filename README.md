# cod-nowcast-ons

[![CI](https://github.com/rjmalves/cod-nowcast-ons/actions/workflows/ci.yml/badge.svg)](https://github.com/rjmalves/cod-nowcast-ons/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![pySTEPS](https://img.shields.io/badge/pySTEPS-1.18.1+-green.svg)](https://pysteps.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Nowcasting de Cloud Optical Depth usando imagens do satélite GOES e extrapolação baseada em fluxo óptico**

`cod-nowcast-ons` é uma ferramenta especializada de nowcasting para Cloud Optical Depth (COD) derivado de dados do satélite GOES. Fornece previsões de curto prazo aplicando técnicas de detecção de movimento por fluxo óptico e extrapolação da biblioteca [pySTEPS](https://pysteps.readthedocs.io/) em propriedades de nuvens derivadas de satélite.

Desenvolvido pelo [Operador Nacional do Sistema Elétrico (ONS)](https://www.ons.org.br/) para uso em previsão de geração solar fotovoltaica.

---

## Status

Até a primeira publicação do nwp-core no PyPI, valem estas limitações:

- A ferramenta obtém o nwp-core de um repositório git privado, fixado por commit em `pyproject.toml` (`[tool.uv.sources]`).
- Sem acesso de leitura ao nwp-core, ninguém consegue instalar a ferramenta nem construir a sua imagem.
- O CI falha em pull requests vindos de forks, porque eles não recebem o token de leitura `NWP_CORE_READ_TOKEN`.
- Toda rota de instalação usa uv (`uv sync --locked`, `setup.sh` e a imagem). O pip não é suportado neste período, porque ignora a fonte fixada e procuraria o nwp-core no PyPI. O `sudo ./setup.sh` exige uv e esse acesso de leitura também para o root.
- Esta seção será removida quando o nwp-core for publicado.

---

## Visão geral

Uma execução do `cod-nowcast-ons` lê quadros recentes de Cloud Optical Depth (COD) do GOES em um local de armazenamento, estima o movimento das nuvens por fluxo óptico de Lucas-Kanade e extrapola o último quadro observado de forma lagrangiana, usando a biblioteca [pySTEPS](https://pysteps.readthedocs.io/). O resultado é uma previsão de curto prazo de COD para cada sub-região (subgrade) configurada, gravada em um arquivo Parquet e, opcionalmente, em gráficos.

O caso de uso é alimentar a previsão de geração solar fotovoltaica com a nebulosidade das próximas horas. A ferramenta roda uma vez por `base_datetime`: um agendador externo a chama a cada ciclo de 10 minutos.

---

## Instalação

A partir de um clone, com o [uv](https://docs.astral.sh/uv/) instalado:

```bash
uv sync --locked
```

Para instalar o comando `cod-nowcast-ons` no sistema ou no usuário, use os alvos do Makefile, que chamam o `setup.sh`:

```bash
make install        # para todos os usuários (usa sudo)
make install-user   # só para o usuário atual
```

Para construir a imagem Docker `cod-nowcast-ons:local`:

```bash
make image
```

O acesso de leitura ao nwp-core é necessário em todas as rotas. Veja a seção [Status](#status).

---

## Uso

```bash
cod-nowcast-ons nowcast --config CAMINHO
cod-nowcast-ons --version
```

- `nowcast` executa uma previsão. O caminho do arquivo TOML vem de `--config` ou da variável `COD_NOWCAST_ONS_CONFIG`.
- `--version` imprime `cod-nowcast-ons <versão>`.
- A saída padrão (stdout) traz um único documento JSON `nwp.run-summary/1`, com o resumo da execução.
- A saída de erro (stderr) traz as linhas de log em JSON, uma por evento.
- O código de saída segue a tabela de [Códigos de saída](#códigos-de-saída).

Exemplo com Docker, que roda `nowcast --config` sobre um caminho absoluto dentro do contêiner e grava a saída em uma pasta do hospedeiro:

```bash
mkdir -p "$PWD/saida"
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/config.toml:/config/config.toml:ro" \
  -v "$PWD/saida:/data/output" \
  cod-nowcast-ons:local nowcast --config /config/config.toml
```

O `output.uri` do arquivo de configuração deve ser `/data/output`, o caminho da montagem dentro do contêiner.

Se o `[input]` ou o `[output]` for um local S3, o contêiner obtém as credenciais pela cadeia padrão do AWS SDK, por exemplo um papel IAM da instância ou da tarefa. Não passe chaves de acesso pela linha de comando.

---

## Configuração

A configuração vem de um arquivo TOML, de variáveis de ambiente e da linha de comando. A precedência é: opção da linha de comando, depois variável de ambiente, depois arquivo, depois o valor padrão.

- As variáveis de ambiente se chamam `COD_NOWCAST_ONS_<CHAVE>`, em maiúsculas. Chaves aninhadas se unem por `__`: `COD_NOWCAST_ONS_INPUT__URI` define `input.uri` e `COD_NOWCAST_ONS_OUTPUT__URI` define `output.uri`.
- A lista `subgrids` entra por uma única variável, `COD_NOWCAST_ONS_SUBGRIDS`, que contém um array JSON.
- Locais de armazenamento locais precisam ser caminhos absolutos. Um caminho relativo é um erro de configuração e encerra a execução com o código 2.
- O arquivo [`config.example.toml`](config.example.toml) documenta cada chave.

Exemplo mínimo:

```toml
base_datetime = "2024-08-01T10:00:00Z"
num_past_samples = 36
num_future_samples = 6
max_input_staleness = "PT10M"

[input]
uri = "s3://example-bucket/gold"

[output]
uri = "/data/output"

[[subgrids]]
name = "SE"
lat = [-23.0, -2.0]
lon = [-53.0, -35.0]

[postprocessing]
plots = false
```

### Chaves

| Chave                                            | Padrão               | Descrição                                                                                                                                  |
| ------------------------------------------------ | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `base_datetime`                                  | obrigatória          | Instante base da previsão, em UTC, alinhado a um múltiplo de 10 minutos e com segundos zero. Escreva entre aspas.                                  |
| `num_past_samples`                               | obrigatória          | Quadros passados usados para estimar o movimento. No mínimo 2.                                                                              |
| `num_future_samples`                             | obrigatória          | Quadros futuros a prever. No mínimo 1.                                                                                                      |
| `max_input_staleness`                            | `PT10M`              | Atraso máximo do quadro mais recente em relação ao `base_datetime`: duração ISO 8601 que é múltiplo positivo de 10 minutos.                |
| `min_input_frames`                               | `num_past_samples`   | Menor número de quadros aceito, de 2 até `num_past_samples`.                                                                                |
| `[input]`                                        | obrigatória          | Local de armazenamento do nwp-core de onde os quadros são lidos. Campos: `uri`, `anonymous`, `endpoint_url`, `provider_source`, `storage_class`. |
| `[output]`                                       | obrigatória          | Local de armazenamento do nwp-core onde as saídas são gravadas, com os mesmos campos do `[input]`.                                          |
| `[[subgrids]]`                                   | obrigatória          | Sub-regiões a prever. Cada uma tem `name` (único), `lat` (sul, depois norte, entre -90 e 90) e `lon` (oeste, depois leste, entre -180 e 180). |
| `[postprocessing] plots`                         | `false`              | Liga os gráficos. Veja [Gráficos](#gráficos).                                                                                               |
| `[postprocessing.shapefile]`                     | ausente              | Contornos extras para os gráficos: `key` (objeto `.shp`) e `location` (local de armazenamento).                                             |
| `[storage]`                                      | valores abaixo       | Tentativas, tempos limite e conexões do cliente de armazenamento do nwp-core.                                                               |

Para credenciais, nenhuma chave guarda segredos. Em locais S3, as credenciais vêm da **cadeia padrão de credenciais do AWS SDK**.

### Armazenamento (`[storage]`)

| Chave                  | Padrão | Variável de ambiente                          |
| ---------------------- | ------ | --------------------------------------------- |
| `max_attempts`         | 5      | `COD_NOWCAST_ONS_STORAGE__MAX_ATTEMPTS`        |
| `connect_timeout_s`    | 10.0   | `COD_NOWCAST_ONS_STORAGE__CONNECT_TIMEOUT_S`   |
| `read_timeout_s`       | 60.0   | `COD_NOWCAST_ONS_STORAGE__READ_TIMEOUT_S`      |
| `max_pool_connections` | 10     | `COD_NOWCAST_ONS_STORAGE__MAX_POOL_CONNECTIONS` |

---

## Dados de entrada

O `[input]` é a raiz do layout: a ferramenta lê cada quadro em **`goes_processed/GOES_COD_BR_`**`AAAAMMDD-HHMM.parquet` abaixo dela. O carimbo `AAAAMMDD-HHMM` é o instante do quadro em UTC, em intervalos de 10 minutos.

| Coluna      | Tipo Arrow              | Significado                                                       |
| ----------- | ----------------------- | ----------------------------------------------------------------- |
| `time`      | `timestamp[us, tz=UTC]` | Instante do quadro.                                               |
| `latitude`  | `float64`               | Latitude do pixel, em graus, em uma grade regular de 0,04 grau.   |
| `longitude` | `float64`               | Longitude do pixel, em graus, na mesma grade.                     |
| `cod`       | `float32`               | Cloud Optical Depth. `NaN` marca valor ausente.                   |

Regras de seleção dos quadros:

1. A ferramenta procura o quadro mais recente, do `base_datetime` menos 10 minutos para trás, até o limite de `max_input_staleness`.
2. A partir dele, toma os quadros contíguos anteriores, até `num_past_samples`.
3. Se achar menos de `min_input_frames` quadros contíguos, ou nenhum quadro dentro da janela, a execução termina com o código de saída 4.

---

## Saídas

A ferramenta grava `cod.parquet` na raiz do `[output]`, e o reescreve a cada execução (modo `replace`).

| Coluna               | Tipo Arrow       | Nulo? | Significado                                                                                                        |
| -------------------- | ---------------- | ----- | ------------------------------------------------------------------------------------------------------------------ |
| `data_hora_rodada`   | `timestamp[us]`  | não   | Instante de emissão: o intervalo do quadro mais recente usado mais 10 minutos. Igual ao `base_datetime` com entrada atual. |
| `data_hora_previsao` | `timestamp[us]`  | não   | Instante previsto.                                                                                                 |
| `latitude`           | `float64`        | não   | Latitude do pixel, em graus.                                                                                       |
| `longitude`          | `float64`        | não   | Longitude do pixel, em graus.                                                                                      |
| `valor`              | `float32`        | sim   | COD previsto. Nulo onde não há valor.                                                                              |

Com `plots = true`, cada sub-região também gera `plots/<subgrade>_NNNN.png`, um por passo da previsão, e `plots/<subgrade>_forecast.gif`, que anima os passos.

**A pasta raiz de saída precisa existir antes da execução**: o cod-nowcast-ons não cria a raiz de nenhum local de armazenamento, e uma pasta local de saída que não existe encerra a execução com o **código 2**.

Em um local de armazenamento local, os arquivos são gravados com o modo **0600**, e só o usuário que executou a ferramenta consegue lê-los. Quem lê a saída deve rodar com o mesmo UID; no Docker, use **`--user "$(id -u):$(id -g)"`**.

---

## Gráficos

Os gráficos são opcionais e ficam desligados por padrão. Para ligá-los, defina `plots = true` em `[postprocessing]`.

Para desenhar contornos extras, como divisas estaduais, configure `[postprocessing.shapefile]` com `key` (o objeto `.shp`) e `location` (o local de armazenamento que o contém). Sem ele, a ferramenta desenha só a costa e as fronteiras entre países.

Os gráficos precisam de acesso à rede, para baixar os dados do **Natural Earth** no primeiro uso, de uma pasta de dados do cartopy com permissão de escrita (**`$XDG_DATA_HOME/cartopy`**, por padrão **`~/.local/share/cartopy`**) e de uma pasta temporária com permissão de escrita (**`TMPDIR`**). Para rodar sem rede, aponte **`CARTOPY_DATA_DIR`** para uma pasta com os dados já baixados.

A imagem Docker define `HOME` e as pastas `XDG_*` sob `/tmp`, que tem permissão de escrita.

---

## Códigos de saída

O comando `cod-nowcast-ons nowcast` termina com um dos códigos abaixo. Os significados seguem o contrato de códigos de saída do nwp-core (`nwp_core.errors`).

| Código | Significado                                    | Quando o cod-nowcast-ons retorna                                                                                                                                                                 |
| ------ | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 0      | Sucesso                                        | A previsão terminou e os artefatos foram gravados. A saída padrão traz só o resumo `nwp.run-summary/1`.                                                                                          |
| 1      | Erro interno                                   | Uma exceção inesperada escapou da API ou da CLI. A saída padrão fica vazia e a saída de erro traz um evento `internal.error`.                                                                    |
| 2      | Erro de configuração ou erro fatal da execução | A configuração é inválida, falta o subcomando ou um local de armazenamento não pode ser usado, como uma pasta de saída local que não existe. Tentar de novo sem corrigir o problema não resolve. |
| 3      | Itens com falha                                | A previsão ou a gravação de um artefato falhou, por exemplo, por causa de um quadro de entrada ilegível. Uma nova tentativa pode resolver.                                                       |
| 4      | Entrada não pronta                             | Os quadros GOES estão atrasados ou em número insuficiente para o `base_datetime`. Tente de novo quando os quadros chegarem.                                                                      |

---

## Metodologia

### Lucas-Kanade Optical Flow

Estima campo de movimento entre frames consecutivos assumindo:

- Constância de brilho: intensidades permanecem constantes
- Movimento pequeno: deslocamento entre frames é limitado
- Coerência espacial: pixels vizinhos têm movimento similar

### Extrapolação Lagrangiana

Projeta o último campo observado usando o campo de movimento estimado:

$$
\text{COD}(x, y, t + \Delta t) \approx \text{COD}(x - u\Delta t, y - v\Delta t, t)
$$

### Limitações

- Acurácia da previsão degrada além de ~60 minutos
- Não modela ciclo de vida das nuvens (formação/dissipação)
- Previsão determinística (sem quantificação de incerteza)

---

## Verificação de regressão

Estes números são uma **verificação de regressão**, não uma avaliação de desempenho do modelo: vêm de uma **cena noturna de cinco quadros**, o recorte de **2024-02-07** das 00:00 às 00:40 UTC sobre a região de 23° S a 20° S e de 50° O a 47° O, e só mudam quando o modelo muda.

Eles comparam o RMSE do modelo com o da persistência (repetir o último quadro observado):

| Antecedência (lead) | Pixels válidos | RMSE do modelo | RMSE da persistência |
| ------------------- | -------------- | -------------- | -------------------- |
| 1                   | 5481           | 0.751667       | 0.927640             |
| 2                   | 5333           | 1.131668       | 1.344372             |
| 3                   | 5184           | 1.265378       | 1.483563             |
| média               |                | 1.049571       | 1.251858             |

Para imprimir os números:

```bash
uv run --no-sync pytest tests/regression/test_persistence_baseline.py -q -s --no-cov
```

---

## Desenvolvimento

```bash
make test       # todos os testes
make lint       # ruff
make typecheck  # mypy
make test-cov   # testes com cobertura
```

Veja o [CONTRIBUTING.md](CONTRIBUTING.md) para o fluxo completo de contribuição.

---

## Contribuindo

Contribuições são bem-vindas! Por favor, leia o [CONTRIBUTING.md](CONTRIBUTING.md) para detalhes sobre:

- Configuração do ambiente de desenvolvimento
- Padrões de código e estilo
- Processo de submissão de Pull Requests

---

## Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

---

## Documentação adicional

- [ARCHITECTURE.md](ARCHITECTURE.md) - Detalhes da arquitetura do sistema
- [CONTRIBUTING.md](CONTRIBUTING.md) - Guia de contribuição
- [CHANGELOG.md](CHANGELOG.md) - Histórico de versões

---

## Contato

- **Organização**: [ONS - Operador Nacional do Sistema Elétrico](https://www.ons.org.br/)
- **Issues**: [GitHub Issues](https://github.com/rjmalves/cod-nowcast-ons/issues)

---

## Citação

```bibtex
@software{cod_nowcast_ons,
  title={cod-nowcast-ons: Cloud Optical Depth nowcasting using GOES satellite imagery and optical flow-based extrapolation},
  author={Farias, William and Alves, Rogerio},
  year={2025},
  url={https://github.com/rjmalves/cod-nowcast-ons}
}
```

---

**Agradecimentos**:

- [pySTEPS](https://pysteps.readthedocs.io/) - Framework Python para sistemas de previsão de curto prazo
- [GOES Satellite Program](https://www.goes.noaa.gov/) - Imagens do satélite geoestacionário
