# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

---

## [Unreleased]

---

## [0.2.0] - 2026-11-05

### Breaking

- `app` foi removido: o código está no pacote `cod_nowcast_ons`, em `src/`. A API pública é `cod_nowcast_ons` (`NowcastConfig`, `Subgrid`, `Postprocessing`, `Shapefile`, `nowcast` e `__version__`) e `cod_nowcast_ons.cli`; os módulos com prefixo `_` são privados.
- `main` foi removido com o `main.py`: a ferramenta roda com `cod-nowcast-ons nowcast --config CAMINHO`. A saída padrão traz um único resumo `nwp.run-summary/1` em JSON, a saída de erro traz os logs em linhas JSON e os códigos de saída 0 a 4 estão no README; quadros atrasados ou insuficientes terminam a execução com o código 4.
- `cod_nowcast_ons.NowcastConfig` lê TOML em vez de JSONC, sem a chave `mode`, com a precedência opção, variável de ambiente, arquivo, padrão, e variáveis `COD_NOWCAST_ONS_<CHAVE>`, com `__` entre chaves aninhadas. Caminhos locais precisam ser absolutos, e o `[input]` é a raiz do layout: os quadros são lidos em `goes_processed/GOES_COD_BR_AAAAMMDD-HHMM.parquet` abaixo dela.
- `cod_nowcast_ons.Postprocessing` troca `shapefile_path` por `[postprocessing.shapefile]`, com `key` e `location`.
- `cod.parquet` segue um schema Arrow explícito (`valor` em `float32`, horários em `timestamp[us]`), e `data_hora_rodada` passa a ser o horário de emissão, o quadro mais novo usado mais 10 minutos, em vez do `base_datetime`. Em um local de armazenamento local, os arquivos são gravados com o modo 0600, e quem lê a saída roda com o mesmo UID da ferramenta (no Docker, `--user "$(id -u):$(id -g)"`). A pasta raiz de saída precisa existir antes da execução; sem ela, a execução termina com o código 2.

### Added

- Chaves de proteção da entrada `max_input_staleness` e `min_input_frames`
- Configurações de `[storage]`
- `config.example.toml`
- `bytes_written` e `artifacts_written` no resumo da execução
- Tabela de códigos de saída no README e o teste que a verifica

### Changed

- Armazenamento pelo nwp-core, local ou S3, com credenciais da cadeia padrão do AWS SDK
- Os gráficos usam a API orientada a objetos do matplotlib, sem `matplotlib.pyplot`, e são gravados no local de saída
- Os gráficos precisam de acesso à rede para os dados do Natural Earth, uma pasta de dados do cartopy gravável e uma pasta temporária gravável
- A versão fica em um só lugar, o `pyproject.toml`
- Os dados de teste são gerados a partir de uma fonte de texto, sem fixture binária versionada

### Removed

- As dependências plotly, statsmodels, requests, python-dotenv, pyjson5, s3fs e boto3
- `install.sh`, `config.example.jsonc` e `DOC-DIRECTIVES.md` (agora empacotado com o nwp-core)

---

## [0.1.0] - 2025-11-28

### Added

- Implementação inicial do pipeline de nowcasting de COD
- Estimação de campo de movimento usando Lucas-Kanade (pySTEPS)
- Extrapolação Lagrangiana para geração de previsões
- Suporte a storage local e Amazon S3
- Configuração via arquivo JSONC com comentários
- Geração de visualizações (PNG frames + GIF animado)
- Exportação de resultados em formato Parquet
- CLI com argumento `--config`
- Dockerfile para containerização
- Testes unitários e de integração com pytest
- Linting com ruff e type checking com mypy
- Documentação completa do projeto (CONTRIBUTING, ARCHITECTURE, CHANGELOG)
- GitHub Actions para CI/CD (lint, test, type check, docker)
- Templates de issues e pull requests

---

## Tipos de Mudanças

- **Breaking**: para mudanças incompatíveis na superfície pública; enquanto a versão for 0.x, elas sobem a versão minor
- **Added**: para novas funcionalidades
- **Changed**: para mudanças em funcionalidades existentes
- **Deprecated**: para funcionalidades que serão removidas em breve
- **Removed**: para funcionalidades removidas
- **Fixed**: para correções de bugs
- **Security**: para correções de vulnerabilidades
