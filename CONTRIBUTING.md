# Contribuindo para o cod-nowcast-ons

Obrigado pelo interesse em contribuir! Este documento fornece diretrizes para contribuições ao projeto.

## 📋 Índice

- [Como Contribuir](#como-contribuir)
- [Configuração do Ambiente](#configuração-do-ambiente)
- [Padrões de Código](#padrões-de-código)
- [Testes](#testes)
- [Documentação](#documentação)
- [Processo de Pull Request](#processo-de-pull-request)

---

## 🤝 Como Contribuir

### Reportando Bugs

1. Verifique se o bug já não foi reportado nas [Issues](https://github.com/rjmalves/cod-nowcast-ons/issues)
2. Se não encontrar, crie uma nova issue usando o template de bug report
3. Inclua:
   - Descrição clara do problema
   - Passos para reproduzir
   - Comportamento esperado vs. observado
   - Versão do Python e do pacote
   - Logs de erro (se aplicável)

### Sugerindo Melhorias

1. Abra uma issue usando o template de feature request
2. Descreva:
   - O problema que a melhoria resolve
   - A solução proposta
   - Alternativas consideradas

### Contribuindo com Código

1. Fork o repositório
2. Crie uma branch para sua feature (`git checkout -b feature/minha-feature`)
3. Faça commits atômicos com mensagens descritivas
4. Escreva/atualize testes para suas mudanças
5. Garanta que todos os testes passam
6. Abra um Pull Request

---

## 🛠️ Configuração do Ambiente

### Pré-requisitos

- Python >= 3.11
- [uv](https://github.com/astral-sh/uv) (gerenciador de pacotes recomendado)
- Git

### Setup Inicial

```bash
# Clone seu fork
git clone https://github.com/SEU_USUARIO/cod-nowcast-ons.git
cd cod-nowcast-ons

# Adicione o upstream
git remote add upstream https://github.com/rjmalves/cod-nowcast-ons.git

# Instale as dependências com uv
uv sync --all-extras --dev

# Ou com pip tradicional
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### Verificando a Instalação

```bash
# Executar testes
uv run pytest tests/

# Verificar linting
uv run ruff check .

# Verificar tipos
uv run mypy
```

---

## 📐 Padrões de Código

### Estilo

Seguimos as convenções PEP 8 com algumas customizações definidas em `pyproject.toml`.

### Verificação de Estilo

```bash
# Executar linter
uv run ruff check .

# Formatar código automaticamente
uv run ruff format .

# Verificar formatação sem modificar
uv run ruff format --check .
```

### Boas Práticas Python

Seguimos os princípios de código limpo e tipagem estática:

#### 1. Type Hints Obrigatórios

```python
# ✅ Bom: função com type hints completos
def calcular_mae(observado: np.ndarray, previsto: np.ndarray) -> float:
    """Calcula o erro médio absoluto."""
    return float(np.mean(np.abs(observado - previsto)))

# ❌ Evitar: funções sem type hints
def calcular_mae(observado, previsto):
    return np.mean(np.abs(observado - previsto))
```

#### 2. Docstrings Claras

```python
# ✅ Bom: docstring informativa
def forecast(self, n_leadtimes: int) -> xr.DataArray:
    """
    Gera previsão de COD usando extrapolação Lagrangiana.

    Args:
        n_leadtimes: Número de passos de tempo à frente para prever.

    Returns:
        DataArray com dimensões (latitude, longitude, time).

    Raises:
        ValueError: Se n_leadtimes <= 0.
    """
    ...
```

#### 3. Validação de Entrada

```python
# ✅ Bom: validar tipos e valores
def processar_dados(df: pl.DataFrame, coluna: str) -> pl.DataFrame:
    if coluna not in df.columns:
        raise ValueError(f"Coluna '{coluna}' não encontrada no DataFrame")
    # ...
```

#### 4. Evitar Efeitos Colaterais

```python
# ✅ Bom: função pura
def normalizar(valores: np.ndarray) -> np.ndarray:
    return (valores - valores.min()) / (valores.max() - valores.min())

# ❌ Evitar: modificar entrada in-place sem documentar
def normalizar(valores: np.ndarray) -> None:
    valores[:] = (valores - valores.min()) / (valores.max() - valores.min())
```

---

## 🧪 Testes

### Estrutura de Testes

```
tests/
├── conftest.py              # Fixtures compartilhadas
├── fixtures/                # Dados de teste
│   └── generate_test_data.py
├── unit/                    # Testes unitários
│   ├── test_config.py
│   ├── test_cloud_motion_forecast.py
│   ├── test_readers.py
│   └── test_storage.py
└── integration/             # Testes de integração
    └── test_pipeline.py
```

### Escrevendo Testes

```python
import pytest
import numpy as np

def test_motion_field_estimation_with_valid_data():
    """Testa estimação de campo de movimento com dados válidos."""
    # Arrange: preparar dados
    cod_data = create_sample_cod_data()
    forecast = CloudMotionForecast(cod_data)

    # Act: executar função
    result = forecast.forecast(n_leadtimes=6)

    # Assert: verificar resultado
    assert result.dims == ("latitude", "longitude", "time")
    assert len(result.time) == 6
    assert not np.any(np.isnan(result.values))
```

### Executando Testes

```bash
# Todos os testes
uv run pytest tests/

# Apenas testes unitários
uv run pytest tests/unit/

# Testes de integração
uv run pytest tests/integration/

# Com cobertura
uv run pytest tests/unit/ --cov=app --cov-report=term

# Teste específico
uv run pytest tests/unit/test_config.py -v
```

### Requisitos de Cobertura

- Novas funções públicas devem ter testes
- Casos de borda (NaN, vazios, tipos errados) devem ser testados
- Testes devem ser independentes e reprodutíveis

---

## 📝 Documentação

### Docstrings

Todas as funções e classes públicas devem ter documentação completa:

```python
class CloudMotionForecast:
    """
    Previsão de movimento de nuvens usando fluxo óptico.

    Esta classe implementa nowcasting de Cloud Optical Depth (COD)
    usando o método Lucas-Kanade para estimação de movimento e
    extrapolação Lagrangiana para projeção temporal.

    Attributes:
        cod: DataArray com histórico de COD (time × lat × lon).
        motion_field: Campo de velocidade estimado (2 × lat × lon).
        cod_forecast: Previsão gerada pelo último forecast().

    Example:
        >>> cod_history = load_cod_data()
        >>> forecast = CloudMotionForecast(cod_history)
        >>> prediction = forecast.forecast(n_leadtimes=6)
    """
```

### Atualizando Documentação

- Atualize o README se adicionar funcionalidades visíveis ao usuário
- Atualize ARCHITECTURE.md se modificar a estrutura do sistema
- Atualize CHANGELOG.md para mudanças relevantes

---

## 🔄 Processo de Pull Request

### Antes de Abrir o PR

1. **Sincronize com upstream**

   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Execute verificações locais**

   ```bash
   uv run ruff check .               # Linting
   uv run ruff format .              # Formatação
   uv run mypy                       # Type checking
   uv run pytest tests/              # Testes
   ```

3. **Commits organizados**
   - Mensagens descritivas em português ou inglês
   - Um commit por mudança lógica
   - Formato: `tipo: descrição curta`
     - `feat:` nova funcionalidade
     - `fix:` correção de bug
     - `docs:` documentação
     - `test:` testes
     - `refactor:` refatoração

### Template do PR

```markdown
## Descrição

Breve descrição das mudanças.

## Tipo de Mudança

- [ ] Bug fix
- [ ] Nova feature
- [ ] Breaking change
- [ ] Documentação

## Checklist

- [ ] Testes adicionados/atualizados
- [ ] Documentação atualizada
- [ ] CI passa sem erros
- [ ] Código segue os padrões do projeto

## Issues Relacionadas

Closes #123
```

### Revisão

- PRs requerem pelo menos 1 aprovação
- CI deve passar (testes, lint, type check)
- Discussões devem ser resolvidas antes do merge

---

## 🏷️ Versionamento

Seguimos [Semantic Versioning](https://semver.org/):

- **MAJOR**: mudanças incompatíveis na API
- **MINOR**: novas funcionalidades compatíveis
- **PATCH**: correções de bugs compatíveis

Atualize o `app/__init__.py` e `CHANGELOG.md` ao lançar versões.

---

## ❓ Dúvidas?

- Abra uma [Discussion](https://github.com/rjmalves/cod-nowcast-ons/discussions) para perguntas gerais
- Use [Issues](https://github.com/rjmalves/cod-nowcast-ons/issues) para bugs e features
- Consulte a documentação existente

Obrigado por contribuir! 🎉
