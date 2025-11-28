# Arquitetura do Sistema

Este documento descreve a arquitetura do `cod-nowcast-ons`, incluindo o fluxo de dados, componentes principais e decisões de design.

## Visão Geral

O sistema implementa um pipeline de nowcasting de Cloud Optical Depth (COD) baseado em dados de satélite GOES. Utiliza técnicas de fluxo óptico para estimar movimento de nuvens e extrapolação Lagrangiana para gerar previsões de curto prazo (0-60 minutos).

## Diagrama de Fluxo

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              ENTRADA DE DADOS                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  Parquet Files: GOES_COD_BR_YYYYMMDD-HHMM.parquet                          │
│  Colunas: latitude, longitude, cod                                         │
│  Fonte: Local filesystem ou S3                                             │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                           CONFIGURAÇÃO                                     │
├────────────────────────────────────────────────────────────────────────────┤
│  config.jsonc                                                              │
│  ├─ mode: "inference"                                                      │
│  ├─ input: path ou s3://bucket/prefix                                      │
│  ├─ output: path ou s3://bucket/prefix                                     │
│  ├─ base_datetime: ISO 8601                                                │
│  ├─ num_past_samples: histórico para motion estimation                     │
│  ├─ num_future_samples: lead times da previsão                             │
│  ├─ subgrids[]: regiões geográficas                                        │
│  └─ postprocessing.plots: gerar visualizações                              │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                              MAIN.PY                                       │
│                           (Entry Point)                                    │
├────────────────────────────────────────────────────────────────────────────┤
│  1. Parse argumentos CLI (--config)                                        │
│  2. Carregar e validar configuração                                        │
│  3. Criar storage backend (local/S3)                                       │
│  4. Despachar para modo de execução                                        │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                           INFERENCE MODE                                   │
│                         (app/inference.py)                                 │
├────────────────────────────────────────────────────────────────────────────┤
│  Para cada subgrid:                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ 1. LEITURA DE DADOS (readers.py)                                     │  │
│  │    ├─ Carregar N arquivos Parquet históricos                         │  │
│  │    ├─ Filtrar por bounds do subgrid                                  │  │
│  │    └─ Converter para xarray.DataArray (time × lat × lon)             │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                              │                                             │
│                              ▼                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ 2. ESTIMAÇÃO DE MOVIMENTO (services/cloud_motion_forecast.py)        │  │
│  │    ├─ Aplicar Lucas-Kanade optical flow                              │  │
│  │    └─ Gerar campo de velocidade 2D (U, V)                            │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                              │                                             │
│                              ▼                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ 3. EXTRAPOLAÇÃO LAGRANGIANA (services/cloud_motion_forecast.py)      │  │
│  │    ├─ Usar último sample como condição inicial                       │  │
│  │    ├─ Advectar campo com motion field                                │  │
│  │    └─ Gerar previsões para N lead times                              │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                              │                                             │
│                              ▼                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ 4. ESCRITA DE RESULTADOS (writers.py)                                │  │
│  │    ├─ Exportar forecast como Parquet (flattened)                     │  │
│  │    └─ Gerar visualizações (se habilitado)                            │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                              SAÍDA                                         │
├────────────────────────────────────────────────────────────────────────────┤
│  output/                                                                   │
│  ├─ cod.parquet              # Previsões (time, lat, lon, cod)             │
│  └─ plots/                   # Se postprocessing.plots = true              │
│      ├─ {subgrid}_forecast.gif                                             │
│      └─ *.png                # Frames individuais                          │
└────────────────────────────────────────────────────────────────────────────┘
```

## Componentes Principais

### 1. Entry Point (`main.py`)

Ponto de entrada do sistema. Responsabilidades:

- Parsear argumentos de linha de comando
- Carregar e validar configuração
- Criar storage backend apropriado
- Despachar para modo de execução
- Tratamento de erros de alto nível

### 2. Configuração (`app/internal/config.py`)

Gerencia parsing e validação do arquivo de configuração.

| Função | Descrição |
|--------|-----------|
| `InferenceConfig` | Dataclass com configuração tipada |
| `parse_config()` | Interpreta e valida arquivo JSONC |
| Validação | Verifica tipos e valores obrigatórios |

### 3. Storage Layer (`app/storage/`)

Abstração para I/O transparente entre filesystem local e S3.

```
storage/
├─ base.py      # Interface abstrata StorageBackend
├─ local.py     # Implementação LocalStorage
├─ s3.py        # Implementação S3Storage
└─ factory.py   # Factory para criar backend apropriado
```

| Classe | Descrição |
|--------|-----------|
| `StorageBackend` | Interface abstrata com métodos read/write |
| `LocalStorage` | Implementação para filesystem local |
| `S3Storage` | Implementação com boto3/s3fs |
| `create_storage()` | Factory que detecta URI e cria backend |

### 4. Leitura de Dados (`app/readers.py`)

Carrega e prepara dados de entrada.

| Função | Descrição |
|--------|-----------|
| `read_cod_parquet()` | Lê arquivo Parquet de COD |
| `load_cod_sequence()` | Carrega sequência temporal de arquivos |
| `to_xarray()` | Converte para DataArray 3D |

### 5. Serviço de Previsão (`app/services/cloud_motion_forecast.py`)

Implementa o algoritmo de nowcasting.

```python
class CloudMotionForecast:
    TIME_STEP_MINUTES = 10
    MOTION_FIELD_METHOD = "LK"      # Lucas-Kanade
    NOWCAST_METHOD = "extrapolation"
    
    def __init__(self, cod: xr.DataArray): ...
    def forecast(self, n_leadtimes: int) -> xr.DataArray: ...
```

#### Algoritmo Lucas-Kanade

Estima campo de movimento entre frames consecutivos:

```
∇I · v + ∂I/∂t = 0

onde:
- I = intensidade (valores COD)
- v = (u, v) vetor velocidade
- ∇I = gradiente espacial
```

#### Extrapolação Lagrangiana

Projeta o último campo observado usando o campo de movimento:

```
COD(x, y, t+Δt) ≈ COD(x - u·Δt, y - v·Δt, t)
```

### 6. Escrita de Resultados (`app/writers.py`)

Exporta previsões e visualizações.

| Função | Descrição |
|--------|-----------|
| `write_forecast_parquet()` | Exporta previsões em Parquet |
| `flatten_dataarray()` | Converte 3D para tabular |

### 7. Visualização (`app/utils/plots.py`)

Gera visualizações das previsões.

| Função | Descrição |
|--------|-----------|
| `create_forecast_plot()` | Gera frame PNG |
| `create_animation()` | Combina frames em GIF |
| `plot_motion_vectors()` | Sobrepõe vetores de movimento |

### 8. Inferência (`app/inference.py`)

Orquestra o pipeline de previsão.

| Função | Descrição |
|--------|-----------|
| `run_inference()` | Pipeline completo de inferência |
| `process_subgrid()` | Processa uma região geográfica |

## Fluxo de Dados

### Entrada

```
input/
├── GOES_COD_BR_20240801-0900.parquet
├── GOES_COD_BR_20240801-0910.parquet
├── GOES_COD_BR_20240801-0920.parquet
├── GOES_COD_BR_20240801-0930.parquet
├── GOES_COD_BR_20240801-0940.parquet
└── GOES_COD_BR_20240801-0950.parquet
```

### Processamento Interno

```
Parquet Files (N timestamps)
    │
    ▼
polars.DataFrame (lat, lon, cod)
    │
    ▼
xarray.DataArray (time × lat × lon)
    │
    ▼
numpy.ndarray para pySTEPS
    │
    ▼
xarray.DataArray (forecast)
    │
    ▼
polars.DataFrame (flattened)
    │
    ▼
Parquet output
```

### Saída

```
output/
├── cod.parquet                    # Previsões consolidadas
└── plots/
    ├── SE_forecast.gif            # Animação por subgrid
    ├── 0000.png                   # Frames individuais
    ├── 0001.png
    └── ...
```

## Decisões de Design

### Por que pySTEPS?

- Biblioteca especializada em nowcasting meteorológico
- Implementações otimizadas de Lucas-Kanade
- Comunidade ativa e documentação extensa
- Validada em aplicações operacionais

### Por que xarray?

- Representação natural de dados N-dimensionais com coordenadas
- Integração nativa com NetCDF e outros formatos meteorológicos
- Operações vetorizadas eficientes
- Metadados preservados através do pipeline

### Por que Polars?

- Performance superior para I/O de Parquet
- Menor consumo de memória que Pandas
- API lazy evaluation para datasets grandes
- Suporte nativo a S3

### Por que abstração de Storage?

- Transparência entre local e cloud
- Facilita testes (mock S3)
- Permite extensão para outros backends (GCS, Azure Blob)
- Configuração única via URI

### Por que subgrids?

- Processamento paralelo por região
- Reduz consumo de memória
- Permite configuração específica por área
- Isolamento de falhas

## Extensibilidade

### Adicionar novo método de motion estimation

1. Criar wrapper em `cloud_motion_forecast.py`
2. Registrar método em pySTEPS (se necessário)
3. Atualizar `MOTION_FIELD_METHOD`

### Adicionar novo backend de storage

1. Implementar interface `StorageBackend` em novo arquivo
2. Registrar no factory em `storage/factory.py`
3. Definir padrão de URI para detecção

### Adicionar novo formato de saída

1. Implementar writer em `writers.py`
2. Expor configuração em `config.jsonc`
3. Chamar no pipeline de inferência

## Dependências Externas

```
pySTEPS (>= 1.18.1)
├── Motion estimation (Lucas-Kanade)
├── Extrapolation nowcast
└── Utilities meteorológicas

xarray (>= 2025.7.1)
├── Representação N-dimensional
└── Coordenadas e metadados

polars (>= 1.31.0)
├── I/O Parquet eficiente
└── Transformações tabulares

cartopy (>= 0.25.0)
├── Projeções geográficas
└── Features de mapa

boto3 (>= 1.35.0)
└── Acesso a S3
```

## Performance

### Complexidade

| Operação | Complexidade |
|----------|--------------|
| Leitura de dados | O(N × pixels) |
| Motion estimation | O(N × pixels × janela) |
| Extrapolação | O(leadtimes × pixels) |
| Escrita Parquet | O(leadtimes × pixels) |

### Gargalos Conhecidos

1. **Leitura sequencial de Parquet**: Pode ser paralelizado
2. **Motion estimation em CPU**: pySTEPS não usa GPU
3. **Geração de plots**: I/O intensivo para GIF

### Otimizações Implementadas

- Storage backends com streaming
- Lazy loading onde possível
- Processamento por subgrid para reduzir memória
- Reutilização de motion field entre subgrids (se aplicável)

### Otimizações Futuras

- Paralelização de subgrids com multiprocessing
- Cache de motion fields para re-runs
- Suporte a GPU via cupy/dask (se pySTEPS suportar)
