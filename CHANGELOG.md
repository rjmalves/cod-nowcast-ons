# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Added

- Documentação completa do projeto (CONTRIBUTING, ARCHITECTURE, CHANGELOG)
- GitHub Actions para CI/CD (lint, test, type check, docker)
- Templates de issues e pull requests
- Suporte a múltiplos subgrids para processamento paralelo

### Changed

- Reorganização da documentação seguindo padrões de projeto aberto

---

## [1.0.0] - 2025-11-28

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

---

## Tipos de Mudanças

- **Added**: para novas funcionalidades
- **Changed**: para mudanças em funcionalidades existentes
- **Deprecated**: para funcionalidades que serão removidas em breve
- **Removed**: para funcionalidades removidas
- **Fixed**: para correções de bugs
- **Security**: para correções de vulnerabilidades
