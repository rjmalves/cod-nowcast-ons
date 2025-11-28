# cod-nowcast-ons

[![Tests](https://github.com/rjmalves/cod-nowcast-ons/actions/workflows/tests.yml/badge.svg)](https://github.com/rjmalves/cod-nowcast-ons/actions/workflows/tests.yml)
[![Lint](https://github.com/rjmalves/cod-nowcast-ons/actions/workflows/lint.yaml/badge.svg)](https://github.com/rjmalves/cod-nowcast-ons/actions/workflows/lint.yaml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![pySTEPS](https://img.shields.io/badge/pySTEPS-1.18.1+-green.svg)](https://pysteps.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Nowcasting de Cloud Optical Depth usando imagens do satélite GOES e extrapolação baseada em fluxo óptico**

`cod-nowcast-ons` é uma ferramenta especializada de nowcasting para Cloud Optical Depth (COD) derivado de dados do satélite GOES. Fornece previsões de curto prazo aplicando técnicas de detecção de movimento por fluxo óptico e extrapolação da biblioteca [pySTEPS](https://pysteps.readthedocs.io/) em propriedades de nuvens derivadas de satélite.

Desenvolvido pelo [Operador Nacional do Sistema Elétrico (ONS)](https://www.ons.org.br/) para uso em previsão de geração solar fotovoltaica.

---

## 📋 Visão Geral

Este projeto implementa um pipeline de nowcasting que:

1. **Lê dados históricos** de COD em formato Parquet (local ou S3)
2. **Estima campos de movimento** usando fluxo óptico Lucas-Kanade
3. **Extrapola o campo de COD** usando advecção Lagrangiana
4. **Gera previsões** para múltiplos lead times (default: 6 × 10min = 60min)
5. **Exporta resultados** em Parquet e visualizações em GIF

### Casos de Uso

- Previsão de cobertura de nuvens para estimativa de irradiância solar
- Nowcasting para sistemas de previsão de geração fotovoltaica
- Análise de padrões de movimento de nuvens em tempo real
- Suporte a operações de despacho do sistema elétrico

---

## 🏗️ Arquitetura

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              ENTRADA DE DADOS                              │
├─────────────────┬──────────────────────────────────────────────────────────┤
│ GOES COD        │ Parquet: GOES_COD_BR_YYYYMMDD-HHMM.parquet               │
│ (histórico)     │ Colunas: latitude, longitude, cod                        │
└────────┬────────┴──────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         ESTIMAÇÃO DE MOVIMENTO                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ Lucas-Kanade Optical Flow (pySTEPS)                                  │  │
│  │ Entrada: N frames históricos → Saída: Campo de velocidade (U, V)     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                       EXTRAPOLAÇÃO LAGRANGIANA                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ Semi-Lagrangian Advection (pySTEPS)                                  │  │
│  │ COD(t+Δt) = COD(x - u·Δt, y - v·Δt, t)                               │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                              SAÍDA                                         │
├─────────────────┬──────────────────────────────────────────────────────────┤
│ Previsões COD   │ Parquet: cod.parquet (times, latitude, longitude, value) │
│ Visualizações   │ GIF animado + frames PNG (opcional)                      │
└─────────────────┴──────────────────────────────────────────────────────────┘
```

### Componentes Principais

| Módulo                                  | Descrição                                    |
| --------------------------------------- | -------------------------------------------- |
| `main.py`                               | Entry point e CLI                            |
| `app/inference.py`                      | Pipeline de inferência                       |
| `app/services/cloud_motion_forecast.py` | Algoritmos de nowcasting (LK + extrapolação) |
| `app/readers.py`                        | Leitura de dados COD                         |
| `app/writers.py`                        | Escrita de resultados                        |
| `app/storage/`                          | Abstração de storage (local/S3)              |
| `app/utils/plots.py`                    | Geração de visualizações                     |

---

## 🚀 Quick Start

### Pré-requisitos

- Python >= 3.11
- Linux (testado em Ubuntu/Debian)
- Dados GOES COD em formato Parquet

### Instalação

```bash
# Clone o repositório
git clone https://github.com/rjmalves/cod-nowcast-ons.git
cd cod-nowcast-ons

# Instale com uv (recomendado)
uv sync

# Ou com pip tradicional
python -m venv venv
source venv/bin/activate
pip install -e .
```

### Execução Rápida

```bash
# 1. Prepare o arquivo de configuração
cp config.example.jsonc config.jsonc
# Edite config.jsonc com seus parâmetros

# 2. Prepare dados de entrada
# Coloque arquivos GOES_COD_BR_YYYYMMDD-HHMM.parquet em data/input/

# 3. Execute a previsão
cod-nowcast-ons --config config.jsonc

# 4. Verifique os resultados em data/output/
```

### Usando Docker

```bash
# Build da imagem
docker build -t cod-nowcast-ons .

# Execução com volumes montados
docker run -v $(pwd)/data:/app/data -v $(pwd)/config.jsonc:/app/config.jsonc \
  cod-nowcast-ons --config /app/config.jsonc
```

---

## 📖 Uso Detalhado

### Linha de Comando

```bash
cod-nowcast-ons --config <ARQUIVO_CONFIG>
```

| Argumento  | Descrição                                  | Default     |
| ---------- | ------------------------------------------ | ----------- |
| `--config` | Caminho para arquivo de configuração JSONC | Obrigatório |

### Arquivo de Configuração (`config.jsonc`)

```jsonc
{
  // Modo de execução (atualmente apenas "inference")
  "mode": "inference",

  // Caminhos de entrada/saída (local ou s3://)
  "input": "data/input",
  "output": "data/output",

  // Data/hora base da previsão (ISO 8601)
  "base_datetime": "2024-08-01T10:00:00",

  // Número de amostras históricas para motion estimation
  "num_past_samples": 6,

  // Número de lead times de previsão (cada um = 10 min)
  "num_future_samples": 6,

  // Regiões geográficas para processamento
  "subgrids": [
    {
      "name": "SE",
      "lat": [-23.0, -2.0],
      "lon": [-53.0, -35.0]
    }
  ],

  // Opções de pós-processamento
  "postprocessing": {
    "plots": true
  }
}
```

### Variáveis de Ambiente (S3)

```bash
# Para uso com S3
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"

cod-nowcast-ons --config config.jsonc
```

---

## 📁 Dados de Entrada

### Formato dos Arquivos

| Arquivo                             | Formato | Descrição               |
| ----------------------------------- | ------- | ----------------------- |
| `GOES_COD_BR_YYYYMMDD-HHMM.parquet` | Parquet | Dados COD por timestamp |

### Schema de Entrada

```
time        datetime[UTC]  Instante de aquisição da imagem
latitude    float64        Latitude em graus decimais
longitude   float64        Longitude em graus decimais
cod         float64        Cloud Optical Depth
```

### Exemplo
```
┌────────────────────────────────┬──────────┬───────────┬──────────┐
│ time                           ┆ latitude ┆ longitude ┆ cod      │
│ ---                            ┆ ---      ┆ ---       ┆ ---      │
│ datetime[μs, UTC]              ┆ f64      ┆ f64       ┆ f32      │
╞════════════════════════════════╪══════════╪═══════════╪══════════╡
│ 2024-08-01 00:00:20.773033 UTC ┆ -40.0    ┆ -80.0     ┆ NaN      │
│ 2024-08-01 00:00:20.773033 UTC ┆ -40.0    ┆ -79.96    ┆ NaN      │
│ 2024-08-01 00:00:20.773033 UTC ┆ -40.0    ┆ -79.92    ┆ NaN      │
│ 2024-08-01 00:00:20.773033 UTC ┆ -40.0    ┆ -79.88    ┆ NaN      │
│ 2024-08-01 00:00:20.773033 UTC ┆ -40.0    ┆ -79.84    ┆ NaN      │
│ …                              ┆ …        ┆ …         ┆ …        │
│ 2024-08-01 00:00:20.773033 UTC ┆ 10.0     ┆ -30.16    ┆ 7.223562 │
│ 2024-08-01 00:00:20.773033 UTC ┆ 10.0     ┆ -30.12    ┆ 6.842261 │
│ 2024-08-01 00:00:20.773033 UTC ┆ 10.0     ┆ -30.08    ┆ 7.985351 │
│ 2024-08-01 00:00:20.773033 UTC ┆ 10.0     ┆ -30.04    ┆ 6.811799 │
│ 2024-08-01 00:00:20.773033 UTC ┆ 10.0     ┆ -30.0     ┆ 6.366376 │
└────────────────────────────────┴──────────┴───────────┴──────────┘
```

### Requisitos

- Arquivos nomeados: `GOES_COD_BR_YYYYMMDD-HHMM.parquet`
- Grid regular lat/lon
- Valores faltantes como NaN

---

## 📊 Saídas

### Arquivo de Previsão

**Arquivo**: `<output>/cod.parquet`

| Coluna              | Tipo     | Descrição                    |
| ------------------- | -------- | -----------------------------|
| `data_hora_rodada`  | datetime | Data de referência da rodada |
| `data_hora_previsao`| datetime | Tempo válido da previsão     |
| `latitude`          | float    | Latitude em graus decimais   |
| `longitude`         | float    | Longitude em graus decimais  |
| `valor`             | float    | COD previsto                 |

### Visualizações

**Diretório**: `<output>/plots/`

- `<subgrid>_forecast.gif` - Animação da previsão
- `<subgrid>_*.png` - Frames individuais com vetores de movimento

---

## 🔬 Metodologia

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

## 🧪 Testes

```bash
# Executar testes unitários
uv run pytest tests/unit/

# Executar testes de integração
uv run pytest tests/integration/

# Com cobertura
uv run pytest tests/unit/ --cov=app --cov-report=term

# Linting
uv run ruff check app/ tests/

# Type checking
uv run mypy app/
```

---

## 🤝 Contribuindo

Contribuições são bem-vindas! Por favor, leia o [CONTRIBUTING.md](CONTRIBUTING.md) para detalhes sobre:

- Configuração do ambiente de desenvolvimento
- Padrões de código e estilo
- Processo de submissão de Pull Requests

---

## 📜 Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

---

## 📚 Documentação Adicional

- [ARCHITECTURE.md](ARCHITECTURE.md) - Detalhes da arquitetura do sistema
- [CONTRIBUTING.md](CONTRIBUTING.md) - Guia de contribuição
- [CHANGELOG.md](CHANGELOG.md) - Histórico de versões

---

## 📞 Contato

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
