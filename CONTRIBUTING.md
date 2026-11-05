# Contribuindo para o cod-nowcast-ons

Obrigado pelo interesse em contribuir! Este documento descreve como configurar o ambiente, o padrão de código, os testes e o fluxo de pull requests. Os textos de documentação e os templates do GitHub são em pt-BR.

---

## Índice

- [Como contribuir](#como-contribuir)
- [Configuração do ambiente](#configuração-do-ambiente)
- [Estrutura do pacote](#estrutura-do-pacote)
- [Padrões de código](#padrões-de-código)
- [Testes](#testes)
- [Documentação](#documentação)
- [Processo de pull request](#processo-de-pull-request)
- [Versionamento](#versionamento)
- [Dúvidas](#dúvidas)

---

## Como contribuir

### Reportando bugs

1. Procure nas [Issues](https://github.com/rjmalves/cod-nowcast-ons/issues) para ver se o bug já foi reportado.
2. Se não encontrar, abra uma issue com o template de bug report.
3. Preencha o template com:
   - os passos para reproduzir, com o comando executado;
   - o comportamento esperado e o observado;
   - o código de saída do comando `cod-nowcast-ons nowcast`;
   - o resumo da execução (`nwp.run-summary/1`), que a ferramenta imprime na saída padrão;
   - os logs em JSON, que a ferramenta imprime na saída de erro;
   - a saída de `cod-nowcast-ons --version`, a versão do Python e o sistema operacional;
   - o arquivo de configuração TOML e as variáveis `COD_NOWCAST_ONS_*` definidas, sem credenciais, nomes de bucket nem caminhos internos.

### Sugerindo melhorias

1. Abra uma issue com o template de feature request.
2. Descreva o problema que a melhoria resolve, a solução proposta e as alternativas consideradas.
3. Marque se a mudança altera o schema do `cod.parquet`, a saída da CLI ou os códigos de saída.

### Contribuindo com código

1. Faça um fork do repositório.
2. Crie uma branch a partir da `main` (`git checkout -b feat/minha-mudanca`).
3. Faça commits pequenos, um por mudança lógica.
4. Escreva ou atualize os testes das suas mudanças.
5. Rode `make lint typecheck test` e `make gate`.
6. Abra um pull request, conforme a seção [Processo de pull request](#processo-de-pull-request).

---

## Configuração do ambiente

### Pré-requisitos

- Python 3.11 ou mais novo.
- [uv](https://github.com/astral-sh/uv) 0.9.22 ou mais novo.
- Acesso de leitura ao repositório do nwp-core, como a seção `## Status` do [README.md](README.md) explica. Sem ele, ninguém consegue instalar a ferramenta.
- Git.
- Docker, somente para construir a imagem (`make image`).

### Configuração inicial

```bash
# Clone o seu fork
git clone https://github.com/SEU_USUARIO/cod-nowcast-ons.git
cd cod-nowcast-ons

# Adicione o upstream
git remote add upstream https://github.com/rjmalves/cod-nowcast-ons.git

# Instale as dependências, com o grupo dev, exatamente como o uv.lock fixa
uv sync --locked
```

### Verificando a instalação

```bash
make lint typecheck test
```

Os três alvos precisam terminar sem erro antes de você começar a alterar o código.

### Atualizando dependências

#### Atualizando o `uv.lock` manualmente

Enquanto o nwp-core vem de um repositório git privado, o Dependabot não recebe token de leitura e não consegue resolver o `uv.lock`. Por isso não há entrada `uv` em `.github/dependabot.yml` e o lock é atualizado à mão. A atualização usa o uv 0.9.22, a versão fixada no CI, para que o lock seja escrito pelo mesmo uv que o verifica:

```bash
uvx uv@0.9.22 lock --upgrade
uv sync --locked
make lint typecheck test
```

Faça o commit do `uv.lock` em um commit `chore:`. O `rev` do nwp-core é um SHA de commit e permanece como está. Se o teste golden falhar depois da atualização, não o regenere no mesmo commit: um novo baseline é uma mudança revisada, com entrada no `CHANGELOG.md`.

O `build-constraint-dependencies` do `pyproject.toml` fixa, com `==`, todo pacote instalado em um ambiente de build: o fecho do hatchling, do editables e dos requisitos de build do pysteps e do jsmin, que publicam apenas sdists. Ao atualizar o lock, mantenha o `numpy` do `build.in` igual ao `numpy` do `uv.lock`, para que as extensões do pysteps sejam compiladas contra o numpy que usam em execução. A lista inteira é atualizada resolvendo o `build.in` (`hatchling==1.33.0`, `editables~=0.3`, `setuptools>=40.8.0`, `wheel`, `cython>=0.29.2` e o `numpy` do lock, um por linha) com `uvx uv@0.9.22 pip compile --no-header --no-annotate --python-version 3.12 -o build-312.txt build.in`, que usa o uv 0.9.22, a versão fixada no CI. Repita o comando com `--python-version 3.11`, confirme com `cmp` que as duas saídas são idênticas e copie as linhas de `build-312.txt` para o `pyproject.toml`, na ordem do arquivo. Faça isso em um diretório fora do repositório.

#### Verificando um PR do Dependabot (actions ou imagem)

O CI desses PRs falha no `uv sync`, porque as execuções iniciadas pelo Dependabot não recebem secrets. Um mantenedor faz checkout do branch do PR, cria um commit vazio e envia para o mesmo branch:

```bash
git commit --allow-empty -m "ci: run the checks with the repository secrets"
git push
```

Essa execução tem o mantenedor como ator e recebe o token de leitura (`NWP_CORE_READ_TOKEN`) e a lista de bloqueio do gate (`NWP_GATE_DENYLIST`). Faça o merge somente com ela verde.

Nenhum secret é criado para o Dependabot, nem o token de leitura nem a lista de bloqueio do gate.

---

## Estrutura do pacote

O código fica em `src/cod_nowcast_ons/`:

| Arquivo        | Papel                                                                    |
| -------------- | ------------------------------------------------------------------------ |
| `__init__.py`  | Superfície pública da API: `nowcast`, `NowcastConfig` e os demais nomes de `__all__`. |
| `cli.py`       | Comando `cod-nowcast-ons`, a segunda parte pública (`cod_nowcast_ons.cli`). |
| `_api.py`      | Orquestra uma execução.                                                  |
| `_config.py`   | Leitura e validação da configuração.                                     |
| `_frames.py`   | Leitura dos quadros de entrada.                                          |
| `_guard.py`    | Verificação de que a entrada está pronta.                                |
| `_forecast.py` | Cálculo da previsão.                                                     |
| `_output.py`   | Gravação dos artefatos e do resumo da execução.                          |
| `_plots.py`    | Geração dos gráficos.                                                    |

Os módulos com prefixo `_` são privados: podem mudar sem aviso e nenhum código externo deve importá-los. A superfície pública é `cod_nowcast_ons`, `cod_nowcast_ons.cli`, as opções e os nomes de ambiente da CLI, o resumo da execução e o `cod.parquet`. O [ARCHITECTURE.md](ARCHITECTURE.md) explica o fluxo de dados entre os módulos.

---

## Padrões de código

- Formatação e lint: `ruff format` e `ruff check`, com linha de até 80 caracteres e alvo `py311`. Rode `make format` e `make lint`.
- Tipos: `mypy` em modo `strict` sobre `src` e `tests`. Rode `make typecheck`.
- Todo módulo começa com `from __future__ import annotations`, e todas as funções têm type hints.
- Idioma: a documentação em Markdown e os templates do GitHub são em pt-BR. O código, as docstrings, a ajuda da CLI, as mensagens de exceção e de log e os comentários do `config.example.toml` são em inglês.
- Siga também o DOC-DIRECTIVES.md distribuído com o nwp-core, que a seção [Documentação](#documentação) mostra como ler.

---

## Testes

Os testes ficam em `tests/`:

- `tests/unit`: testes unitários de cada módulo.
- `tests/integration`: a execução completa com armazenamento local e com S3 simulado (moto).
- `tests/cli`: a CLI executada em processos filhos.
- `tests/surface`: snapshots do schema da configuração, das opções da CLI, dos nomes de ambiente e do resumo da execução, o teste do diff da API, a verificação do wheel e o teste da tabela de códigos de saída.
- `tests/regression`: o golden, o determinismo, a procedência da fixture e a linha de base de persistência.
- `tests/fixtures/goes_cod`: o recorte de regressão, escrito como texto em `tests/fixtures/goes_cod/frames.toml` e convertido em Parquet durante o teste.

Comandos:

```bash
make test              # todos os testes
make test-unit         # tests/unit
make test-integration  # tests/integration
make test-cov          # testes com relatório de cobertura em htmlcov/

# Um único arquivo
uv run --no-sync pytest tests/unit/test_config.py -q
```

Regras:

- Não versione fixtures binárias. O gate de identificadores não consegue examinar binários, por isso o recorte vive como texto em `frames.toml`.
- Os snapshots de `tests/surface` só são regenerados com `NWP_UPDATE_SNAPSHOTS=1`, e a mudança é revisada no diff do pull request.
- O golden só é reescrito por `pytest --update-golden`, que falha de propósito ao terminar. Um novo golden exige entrada no `CHANGELOG.md`.

---

## Documentação

- O [README.md](README.md) é a referência do usuário. A seção `## Códigos de saída` é fixada por um teste: se você mudar um código de saída, atualize a tabela e o teste juntos.
- O [ARCHITECTURE.md](ARCHITECTURE.md) descreve a estrutura do pacote e o fluxo de dados. Atualize-o ao mudar essa estrutura.
- O [CHANGELOG.md](CHANGELOG.md) lista as mudanças relevantes de cada versão.
- Siga o DOC-DIRECTIVES.md distribuído com o nwp-core (`nwp_core/standards/DOC-DIRECTIVES.md`), o padrão de documentação e de release do programa. Este comando imprime a revisão instalada:

  ```bash
  uv run --no-sync python -c "from importlib.resources import files; print(files('nwp_core').joinpath('standards/DOC-DIRECTIVES.md').read_text(encoding='utf-8'))"
  ```

---

## Processo de pull request

### Antes de abrir o pull request

1. Sincronize com o upstream:

   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. Rode as verificações locais:

   ```bash
   make lint typecheck test
   make gate
   ```

   O `make gate` examina os commits desde a `main` à procura de identificadores internos e falha se achar algum.

3. Use commits convencionais, um por mudança lógica: `feat:` para funcionalidade nova, `fix:` para correção, `docs:` para documentação, `test:` para testes, `refactor:` para refatoração e `chore:` para manutenção.

4. Preencha o [template do pull request](.github/PULL_REQUEST_TEMPLATE.md), que o GitHub carrega ao abrir o PR.

### Revisão

- O pull request precisa de pelo menos uma aprovação.
- O CI precisa passar: testes, lint, verificação de tipos e gate. Pull requests de forks não recebem o token de leitura do nwp-core, e o CI deles falha até que um mantenedor reexecute as verificações.
- Os comentários da revisão precisam estar resolvidos antes do merge.

---

## Versionamento

Seguimos o [Semantic Versioning](https://semver.org/):

- **MAJOR**: mudanças incompatíveis na superfície pública.
- **MINOR**: funcionalidades novas compatíveis.
- **PATCH**: correções compatíveis.

Enquanto a versão for 0.x, uma quebra da superfície pública (`cod_nowcast_ons`, `cod_nowcast_ons.cli`, as opções e os nomes de ambiente da CLI, o resumo da execução e o `cod.parquet`) sobe a versão minor. A quebra entra em `## [Unreleased]` do `CHANGELOG.md`, sob `### Breaking`, e cada item começa com o caminho pontuado, entre crases, do que quebrou. O teste `tests/surface/test_api_diff.py` lê esses itens quando uma tag `v*` está visível.

A versão fica em um só lugar: `project.version` no `pyproject.toml`. O `cod_nowcast_ons.__version__` lê os metadados instalados com `importlib.metadata`. Para subir a versão, edite somente o `pyproject.toml` e rode `uv lock`, que atualiza a linha da versão do próprio projeto no `uv.lock`.

Os mantenedores criam a tag anotada `vX.Y.Z` na `main` depois do merge.

---

## Dúvidas

- Use as [Issues](https://github.com/rjmalves/cod-nowcast-ons/issues) para bugs, funcionalidades e perguntas.
- Consulte antes o [README.md](README.md) e o [ARCHITECTURE.md](ARCHITECTURE.md).

Obrigado por contribuir!
