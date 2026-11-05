# Arquitetura do cod-nowcast-ons

Esta página é para quem mantém ou estende o cod-nowcast-ons e quer entender como a ferramenta funciona por dentro. Para configurar e usar a ferramenta, veja o [README.md](README.md).

---

## Visão geral

Cada execução do `cod-nowcast-ons nowcast` produz uma previsão (nowcast) para um instante, o `base_datetime`. A ferramenta lê quadros GOES de densidade óptica de nuvem (COD) em Parquet, de 10 em 10 minutos, estima o campo de movimento das nuvens com o método Lucas-Kanade do pySTEPS e o extrapola para os próximos `num_future_samples` passos de 10 minutos, uma vez por sub-região (subgrid). A saída é o arquivo `cod.parquet` e, se pedido, gráficos PNG e GIF.

A ferramenta usa o nwp-core como base para a configuração, o armazenamento, o contrato de execução (`RunContext`, `run_items`, resumo e códigos de saída) e a linha de comando. O código próprio cuida só da lógica do nowcast.

---

## Fluxo de dados

```text
linha de comando: cod-nowcast-ons nowcast --config CAMINHO
        |
        v
cli.py (cli, main) ---- run_cli (nwp-core)
        |
        v
load_config(NowcastConfig, env_prefix="COD_NOWCAST_ONS")   _config.py
        |
        v
nowcast(config)                                            _api.py
   |-- RunContext + open_storage (entrada, saída, shapefile)
   v
run_items([base_datetime])  -- um item, executado na thread de trabalho
        |
        v
guarda de quadros                                          _guard.py
   |-- quadros em goes_processed/ (chaves de _frames.py)
   v
previsão por subgrid (pySTEPS)                             _forecast.py
        |
        v
escritores                                                 _output.py
   |-- cod.parquet
   |-- plots/ (renderizados por _plots.py, se habilitado)
        |
        v
resumo da execução: nwp.run-summary/1 na saída padrão
```

A linha de comando é um grupo click que entrega o controle ao `run_cli` do nwp-core. O subcomando `nowcast` carrega a configuração com `load_config`, registra os segredos para a redação dos logs e chama `nowcast`. A função `nowcast` abre os locais de armazenamento e passa o `base_datetime` como único item para `run_items`. O item aplica a guarda de quadros, lê os quadros por `_frames.py`, prevê cada subgrid em `_forecast.py` e grava os resultados por `_output.py`, que usa `_plots.py` para os gráficos. Ao fim, o `run_cli` imprime o resumo da execução.

---

## Pacote e módulos

O pacote fica em `src/cod_nowcast_ons/`. Há um arquivo por responsabilidade:

| Arquivo        | Papel                                                                                                                  |
| -------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `__init__.py`  | Superfície pública do pacote: reexporta a configuração e `nowcast`, e lê `__version__` dos metadados instalados.       |
| `cli.py`       | Grupo click `cod-nowcast-ons`, subcomando `nowcast` e o ponto de entrada `main`, que chama `run_cli`.                  |
| `_api.py`      | A função `nowcast`: cria o contexto da execução, abre o armazenamento uma vez e roda o único item com `run_items`.     |
| `_config.py`   | Modelos pydantic imutáveis da configuração; `NowcastConfig` estende o `ToolConfig` do nwp-core.                        |
| `_frames.py`   | Nomes das chaves dos quadros de entrada e leitura deles com polars, recortados por subgrid em arrays xarray.          |
| `_guard.py`    | Guarda de entrada: escolhe os quadros mais recentes e contíguos e decide se a entrada está pronta.                     |
| `_forecast.py` | Carrega o pySTEPS uma só vez, estima o campo de movimento e extrapola a previsão de cada subgrid.                      |
| `_output.py`   | Grava `cod.parquet` e os gráficos, e devolve os recibos de escrita do nwp-core.                                        |
| `_plots.py`    | Renderiza os gráficos PNG e GIF com matplotlib e cartopy, e lê o shapefile opcional.                                   |

A superfície pública é pequena e estável:

- `cod_nowcast_ons`: `NowcastConfig`, `Postprocessing`, `Shapefile`, `Subgrid`, `nowcast` e `__version__`.
- `cod_nowcast_ons.cli`: `cli` e `main`.

Os módulos cujo nome começa com `_` são privados: o que há dentro deles pode mudar sem aviso, e nenhum código externo deve importá-los.

---

## Linha de comando

A interface é um grupo click chamado `cod-nowcast-ons`, montado sobre o `run_cli` do nwp-core. O script de console `cod-nowcast-ons` aponta para `cod_nowcast_ons.cli:main`. Sem argumentos, o grupo mostra a ajuda.

```bash
cod-nowcast-ons nowcast --config CAMINHO
cod-nowcast-ons --version
```

A opção `--config CAMINHO` é uma das opções comuns do nwp-core e aponta para o arquivo TOML de configuração. O contrato dos fluxos de saída é:

- A saída padrão traz um único documento JSON, o resumo `nwp.run-summary/1`.
- A saída de erro traz os logs, uma linha JSON por evento.

Os códigos de saída estão descritos no [README.md](README.md#códigos-de-saída).

---

## Configuração

`NowcastConfig` estende o `ToolConfig` do nwp-core. O `load_config` lê a configuração com o prefixo de variáveis de ambiente `COD_NOWCAST_ONS`. A precedência, da mais forte para a mais fraca, é: opção da linha de comando, variável de ambiente, arquivo e valor padrão.

A seção `[input]` é a raiz do layout de entrada: sob ela ficam os quadros, na pasta `goes_processed/`, com nomes no formato `GOES_COD_BR_AAAAMMDD-HHMM.parquet`. A seção `[output]` é a raiz onde a previsão é gravada. A tabela de chaves fica no [README.md](README.md#configuração).

---

## Execução

A função `nowcast` segue estes passos:

1. Cria o `RunContext` do nwp-core, com o identificador da execução e o instante de início.
2. Abre a entrada e a saída uma única vez, com `config.storage`. Abre também o local do shapefile, mas só quando os gráficos estão ligados e há um shapefile configurado.
3. Roda um único item, o `base_datetime`, com `run_items`. O identificador do item é o token do ciclo, como `20240207T0040Z`.
4. Devolve o resultado depois de `raise_for_status()`, que converte itens com falha em exceções e, portanto, em códigos de saída.

Dentro do item, a guarda de quadros procura, de `base_datetime` menos 10 minutos para trás, até o limite de `max_input_staleness`, o quadro mais recente que existe. A partir dele, junta quadros anteriores contíguos, até `num_past_samples`. Se houver menos quadros que `min_input_frames` (por padrão, `num_past_samples`), ou nenhum quadro na janela, a entrada não está pronta e a execução termina com o código 4.

O instante de emissão (issue time) é o do quadro mais novo usado mais 10 minutos. Quando ele é anterior ao `base_datetime`, o item é marcado com `stale_input` no resumo.

Cada escritor devolve um recibo (`WriteReceipt`) do nwp-core. Os recibos alimentam `bytes_written` e `artifacts_written` no resumo da execução.

---

## Armazenamento

O acesso aos dados passa pelo `open_storage` e pelo `StorageSettings` do nwp-core. Um local de armazenamento é um caminho local absoluto ou uma URI S3, como `s3://example-bucket/entrada`.

- As credenciais S3 vêm da cadeia padrão do SDK da AWS; a ferramenta não as lê da configuração.
- O bloco opcional `[storage]` ajusta tentativas, tempos limite e o pool de conexões.
- O nwp-core grava arquivos locais com modo `0600`.
- A ferramenta nunca cria a raiz de um local. Se a pasta de saída local não existe, a execução falha com o código 2.

---

## Saídas

A ferramenta grava na raiz de `[output]`:

- `cod.parquet`, em modo `replace`: cada execução substitui o arquivo anterior. Ele traz todas as sub-regiões, com um esquema Arrow explícito:

| Coluna               | Tipo Arrow       | Aceita nulo | Significado                                                |
| -------------------- | ---------------- | ----------- | ---------------------------------------------------------- |
| `data_hora_rodada`   | `timestamp[us]`  | não         | Instante de emissão da previsão, em UTC.                   |
| `data_hora_previsao` | `timestamp[us]`  | não         | Instante previsto, em UTC.                                 |
| `latitude`           | `float64`        | não         | Latitude do ponto de grade, em graus.                      |
| `longitude`          | `float64`        | não         | Longitude do ponto de grade, em graus.                     |
| `valor`              | `float32`        | sim         | Densidade óptica de nuvem prevista; valores NaN viram nulo. |

- Com os gráficos ligados, duas chaves sob `plots/`: `plots/<subgrid>_NNNN.png`, um PNG por passo da previsão, e `plots/<subgrid>_forecast.gif`, a animação deles.

---

## Gráficos

Os gráficos são opcionais: ficam desligados até que `[postprocessing] plots` seja `true`.

A renderização usa a API orientada a objetos do matplotlib, com `Figure` sobre o `FigureCanvasAgg`, e nunca importa `matplotlib.pyplot`. O motivo é que o `pyplot` guarda estado global e escolhe backends, e os itens rodam na thread de trabalho do `run_items`, onde isso não é seguro. Os PNG saem de `savefig` e o GIF sai de `FuncAnimation` com `PillowWriter`. As funções de renderização devolvem bytes, e uma só função grava no armazenamento.

O cartopy desenha a costa e as fronteiras com dados do Natural Earth, que ele baixa na primeira vez que precisa deles. Um ambiente sem rede precisa ter esses dados em cache antes de ligar os gráficos. O shapefile opcional, configurado em `[postprocessing.shapefile]`, é copiado do seu local de armazenamento para uma pasta temporária e desenhado por cima.

---

## Decisões de design

- **pySTEPS.** É uma biblioteca estabelecida de nowcasting. A ferramenta usa só a estimativa de movimento Lucas-Kanade e a extrapolação, e o carregamento é feito uma vez, sob um lock, porque o import é caro e imprime um banner.
- **nwp-core como base compartilhada.** Configuração, armazenamento, contrato de execução e códigos de saída ficam iguais em todas as ferramentas da família, e este pacote não duplica essa lógica.
- **polars para ler, xarray para prever.** O polars lê e recorta os quadros Parquet com rapidez; o xarray guarda os arrays rotulados por tempo, latitude e longitude que o pySTEPS e os escritores consomem.
- **Esquema Arrow explícito.** O `cod.parquet` tem colunas, tipos e nulabilidade fixos, para que os consumidores não dependam da inferência de tipos.
- **Fixtures construídas na hora do teste.** Os testes montam os quadros a partir de texto versionado, sem arquivos binários no repositório.
- **Gráficos desligados por padrão.** Eles custam tempo e exigem dados do cartopy; quem precisa só da previsão não paga esse preço.

---

## Dependências externas

| Dependência             | Papel                                                                         |
| ----------------------- | ----------------------------------------------------------------------------- |
| nwp-core                | Configuração, armazenamento, contrato de execução, logs e linha de comando.   |
| pySTEPS                 | Campo de movimento Lucas-Kanade e extrapolação da previsão.                   |
| numpy                   | Arrays numéricos da previsão.                                                 |
| polars                  | Leitura e recorte dos quadros Parquet de entrada.                             |
| pyarrow                 | Esquema Arrow e escrita do `cod.parquet`.                                     |
| pandas                  | Ponte entre o polars, o xarray e a tabela de saída.                           |
| xarray                  | Arrays rotulados de COD por tempo, latitude e longitude.                      |
| matplotlib              | Renderização dos gráficos PNG e da animação GIF.                              |
| cartopy                 | Costa, fronteiras e projeção dos mapas.                                       |
| pillow                  | Escrita do GIF animado.                                                       |
| opencv-python-headless  | Requisito do método de fluxo óptico Lucas-Kanade do pySTEPS.                  |
| pydantic                | Modelos validados e imutáveis da configuração.                                |
| click                   | Grupo de comandos e opções da linha de comando.                               |

As versões mínimas ficam em `pyproject.toml`.
