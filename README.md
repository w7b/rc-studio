# Real Center Studio

Aplicação para planejar campanhas de marketing com uma equipe de agentes de IA, produzir textos e artes e acompanhar resultados em uma interface web.

O projeto reúne **React**, **Python** e o **OpenAI Agents SDK** em um monólito modular com **Clean Architecture**. O backend coordena os agentes, valida suas entregas e preserva campanhas, referências visuais e registros de execução.

## Conteúdo

- [Funcionalidades](#funcionalidades)
- [Equipe de agentes](#equipe-de-agentes)
- [Arquitetura](#arquitetura)
- [Requisitos](#requisitos)
- [Configuração inicial](#configuração-inicial)
- [Executar com Docker](#executar-com-docker)
- [Desenvolvimento local](#desenvolvimento-local)
- [Testes e integração contínua](#testes-e-integração-contínua)
- [Dados e operação](#dados-e-operação)
- [Enviar o projeto ao GitHub](#enviar-o-projeto-ao-github)
- [Documentação complementar](#documentação-complementar)

## Funcionalidades

- Criação de campanhas a partir de briefing e fatos confirmados.
- Assistência de briefing com o Creative Producer antes de executar a equipe.
- Estratégia social, calendário, textos para Stories, legendas e direção criativa.
- Geração de imagens para Feed, Stories, carrosséis e capas de Reels.
- Revisão de imagens com instruções e referências visuais.
- Biblioteca de referências com upload, importação por URL e download.
- Histórico de campanhas, entregas por agente, diagnóstico de falhas e consumo estimado.
- Modo de demonstração offline com respostas fixas.
- Catálogo do código e suas relações por meio do Graphify.

As entregas são **rascunhos para revisão humana**. A aplicação não publica automaticamente em redes sociais. Capas de Reels são imagens estáticas; não há geração de vídeo neste fluxo.

## Equipe de agentes

| Agente | Responsabilidade | Estado |
| --- | --- | --- |
| Marketing Director | Coordenar a equipe, orientar a campanha e revisar o resultado | Ativo |
| Social Media Senior | Estratégia orgânica, calendário e planejamento de conteúdo | Ativo |
| Copywriter Senior | Headlines, CTAs, legendas e demais textos | Ativo |
| Creative Producer | Direção visual, briefing criativo e assistência de briefing | Ativo |
| Performance Marketing Manager | Planejamento de mídia paga | Planejado |
| Marketing Analyst + SEO | Análise de resultados e presença digital | Planejado |

O Director coordena a sequência **Social Media → Copywriter → Creative**. As saídas são validadas antes de compor a campanha. Cada execução recebe sua própria equipe e contexto.

Os contratos de SG Sistemas e Meta Ads estão preparados para evolução, mas as integrações permanecem desabilitadas.

## Arquitetura

```text
.
├── apps/
│   ├── backend/
│   │   ├── src/realcenter_marketing/
│   │   │   ├── domain/          # Modelos e regras de negócio
│   │   │   ├── application/     # Casos de uso e interfaces
│   │   │   ├── infrastructure/  # SDK, arquivos e integrações
│   │   │   ├── presentation/    # HTTP e CLI
│   │   │   └── bootstrap/       # Configuração e montagem das dependências
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── frontend/
│       ├── src/
│       │   ├── app/             # Composição da interface
│       │   ├── features/        # Funcionalidades
│       │   └── shared/          # Cliente HTTP, componentes e estilos
│       └── package.json
├── resources/
│   ├── agents/                 # Manifestos e instruções
│   ├── policies/               # Políticas compartilhadas
│   └── demo/                   # Respostas de demonstração
├── realcenter-marketing-ai/    # Raiz dos dados locais
├── docs/
├── evals/                     # Avaliações editoriais
├── scripts/
├── .github/workflows/
├── .env.example
├── Dockerfile
└── compose.yaml
```

O domínio não depende de HTTP, SDK ou armazenamento. A aplicação usa interfaces implementadas pelos adaptadores. O frontend se comunica com o backend pelas rotas `/api/*` e `/media/*`.

O nome `realcenter-marketing-ai/` foi mantido para a raiz de dados por compatibilidade com campanhas e identificadores de mídia existentes. O código fica em `apps/`.

## Requisitos

| Forma de execução | Requisitos |
| --- | --- |
| Docker | Git, Docker com containers Linux e Docker Compose 2.24+ |
| Desenvolvimento local | Git, Python 3.11+ e Node.js 22 com npm |
| Geração com IA | Chave de API configurada e acesso aos modelos selecionados |

Os exemplos de preparação e desenvolvimento abaixo usam **PowerShell no Windows**. Execute os comandos na raiz do repositório, onde estão este README e o `compose.yaml`.

## Configuração inicial

### 1. Obter o código

Após o projeto estar publicado, substitua `SEU_USUARIO` e `SEU_REPOSITORIO` pelos valores do GitHub:

```powershell
git clone https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
cd SEU_REPOSITORIO
```

Se você já tem o projeto no computador, use a pasta existente.

### 2. Preparar os diretórios e o ambiente

```powershell
New-Item -ItemType Directory -Force -Path realcenter-marketing-ai/campaigns, realcenter-marketing-ai/brand | Out-Null
if (-not (Test-Path realcenter-marketing-ai/.env)) {
    Copy-Item .env.example realcenter-marketing-ai/.env
}
```

Edite `realcenter-marketing-ai/.env`:

| Variável | Uso | Padrão |
| --- | --- | --- |
| `OPENAI_API_KEY` | Credencial para execução live | Vazio |
| `OPENAI_MODEL` | Modelo de texto utilizado pelos agentes | Vazio |
| `OPENAI_IMAGE_MODEL` | Modelo de geração de imagens | `gpt-image-2` |
| `MAX_TURNS` | Limite de turnos do fluxo principal | `12` |
| `REQUEST_TIMEOUT_SECONDS` | Timeout configurado, em segundos | `4800` (80 minutos) |

O modo **demo** não exige chave nem faz chamadas ao provedor, mas utiliza respostas fixas e não gera imagens. A assistência de briefing usa a API mesmo quando o seletor de campanha está em demo.

As variáveis do processo têm precedência sobre o `.env`. Credenciais ficam no backend; o frontend não recebe a chave da API.

### 3. Fornecer o Brand Kit

Os arquivos de marca são locais e não acompanham o clone. Organize-os assim:

```text
realcenter-marketing-ai/brand/
├── brand.md               # Contexto e informações confirmadas da marca
├── colors.md              # Paleta
├── typography.md          # Tipografia
├── visual-guidelines.md   # Diretrizes visuais
├── logo/
│   └── logo.png
├── references/            # Imagens de referência visual
└── products/
    └── reference-only/    # Fotos de produtos
```

Para executar uma campanha, inclusive em demo, é necessário pelo menos um arquivo Markdown de marca. Os demais arquivos enriquecem o contexto e a produção visual. Preencha somente informações confirmadas; registre as lacunas como pendentes.

Sem Brand Kit, a interface e a biblioteca de referências podem abrir, mas a criação de campanhas será bloqueada.

## Executar com Docker

Depois de preparar os dados e a configuração:

```powershell
docker compose up --build -d
```

Acesse **[Real Center Studio](http://127.0.0.1:8765)**.

O build compila o React e o backend Python serve a interface e a API na mesma origem. Node.js é usado apenas na etapa de build. A porta é publicada somente em `127.0.0.1`.

Comandos de operação:

```powershell
# Ver o estado do serviço
docker compose ps

# Acompanhar logs
docker compose logs -f studio

# Parar a aplicação, preservando os diretórios locais
docker compose down
```

Após alterar código ou dependências, execute novamente `docker compose up --build -d`. Após editar o `.env`, recrie o container com `docker compose up -d --force-recreate`.

Em Linux, o diretório de campanhas precisa permitir escrita pelo usuário do container, UID `1000`. O Brand Kit é montado somente para leitura.

## Desenvolvimento local

### Instalar e iniciar

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e './apps/backend[dev]'
npm --prefix apps/frontend ci
npm --prefix apps/frontend run build
.\.venv\Scripts\python.exe scripts/run_backend.py
```

Abra [http://127.0.0.1:8765](http://127.0.0.1:8765).

Para trabalhar no React com atualização automática, mantenha o backend aberto e execute em outro terminal:

```powershell
npm --prefix apps/frontend run dev
```

Use o endereço mostrado pelo Vite. O proxy encaminha `/api` e `/media` para a porta `8765` e preserva a origem exigida pelo backend.

### Linha de comando

Para executar uma campanha de demonstração pelo terminal:

```powershell
.\.venv\Scripts\realcenter-marketing.exe --demo "Crie uma campanha de final de semana"
```

O servidor também pode ser iniciado com `realcenter-studio`, após ativar o ambiente virtual, ou com `python -m realcenter_marketing`. A entrada `python -m realcenter_marketing.dashboard` continua disponível por compatibilidade.

Se você usa o ambiente anterior à reorganização, substitua `.\.venv\Scripts\python.exe` por `.\realcenter-marketing-ai\.venv\Scripts\python.exe` nos comandos correspondentes.

## Testes e integração contínua

```powershell
.\.venv\Scripts\python.exe -m pytest
npm --prefix apps/frontend run build
.\.venv\Scripts\python.exe scripts/package_frontend.py
.\.venv\Scripts\python.exe scripts/smoke.py
```

A suíte verifica regras de domínio, integração dos agentes, contratos HTTP, persistência, referências, revisões de imagem, diagnóstico e limites entre camadas. O smoke test verifica o app com dados sintéticos temporários e uma campanha demo; execute-o após compilar o frontend.

O [workflow do GitHub Actions](.github/workflows/tests.yml) executa testes, build do frontend, smoke test, build Docker e teste do container sem acesso à rede em pushes e pull requests. Essas verificações não precisam de credenciais de modelos.

Avaliações de qualidade editorial com modelos reais estão descritas em [evals/README.md](evals/README.md).

Se o pytest encontrar uma pasta temporária do Windows sem permissão, indique uma pasta nova para aquela execução:

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp=.test-tmp-local-01 -p no:cacheprovider
```

## Dados e operação

### Persistência

| Conteúdo | Local padrão | Versionado |
| --- | --- | --- |
| Código e testes | `apps/` | Sim |
| Prompts, manifestos e políticas | `resources/` | Sim |
| Exemplo de configuração | `.env.example` | Sim |
| Credenciais | `realcenter-marketing-ai/.env` | Não |
| Campanhas, uploads, referências e registros | `realcenter-marketing-ai/campaigns/` | Não |
| Brand Kit e imagens da marca | `realcenter-marketing-ai/brand/` | Não |
| Builds, dependências, caches e backups locais | Diretórios gerados | Não |

O clone do repositório não é um backup das campanhas. Para transferir uma instalação, copie os dados locais separadamente. Preserve os caminhos relativos internos: os IDs de mídia dependem deles.

### Caminhos personalizados

Configure estas variáveis no ambiente do processo antes de iniciar o backend:

| Variável | Finalidade |
| --- | --- |
| `REALCENTER_DATA_ROOT` | Raiz que contém `campaigns/`, `brand/` e `.env` |
| `REALCENTER_RESOURCES_ROOT` | Raiz que contém `agents/`, `policies/` e `demo/` |
| `REALCENTER_STATIC_ROOT` | Diretório que contém o frontend compilado |

No Docker, use caminhos internos do container e ajuste os volumes correspondentes. O `compose.yaml` já mantém os diretórios padrão.

### Limites atuais

- Um processo escritor por diretório de dados e uma execução por vez. Encerre o servidor manual antes de iniciar o Docker com os mesmos dados.
- O fechamento aguarda trabalho aceito. O Compose concede `4810s`; ajuste `stop_grace_period` conforme os timeouts e a duração das etapas, principalmente em carrosséis.
- Interrupções abruptas preservam entregas e aparecem como interrompidas após reinício. Não há repetição automática de chamadas pagas.
- Custos apresentados são estimativas; modelos sem preço conhecido mantêm o consumo sem inventar valores.
- A configuração atual atende ao uso local. Enviar o código ao GitHub não disponibiliza automaticamente o backend na internet.

## Enviar o projeto ao GitHub

### Primeiro envio

Este projeto já possui Git na raiz. Crie um repositório **vazio** no GitHub, com a visibilidade desejada, sem gerar README, licença ou `.gitignore` pelo site. O procedimento segue a [documentação oficial do GitHub](https://docs.github.com/pt/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github).

Na pasta que contém este README, prepare o primeiro commit:

```powershell
git status
git add .
git diff --cached --name-only
```

Confira os arquivos preparados: `.env`, campanhas, Brand Kit, dependências e backups locais não devem aparecer. O `.env.example` deve acompanhar o código.

Depois, substitua os campos da URL pelo usuário ou organização e pelo nome do repositório:

```powershell
git commit -m "chore: estrutura inicial do Real Center Studio"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
git remote -v
git push -u origin main
```

É necessário autenticar o Git no GitHub. Se `origin` já existir, confira sua URL com `git remote -v` antes de configurar o destino. Após o push, acompanhe as verificações na aba **Actions**.

### Próximas alterações

```powershell
git switch -c minha-alteracao
# Edite os arquivos e execute as verificações locais.
git add .
git diff --cached --name-only
git commit -m "feat: descreva a alteração"
git push -u origin minha-alteracao
```

Abra um pull request para `main`, descreva a mudança e confira os resultados do CI antes de integrar.

## Documentação complementar

- [Blueprint da arquitetura](docs/architecture/blueprint.md)
- [Decisão pelo monólito modular](docs/decisions/001-modular-monolith.md)
- [Validação da reorganização](docs/architecture/validation.md)
- [Backend](apps/backend/README.md)
- [Frontend](apps/frontend/README.md)
- [Avaliação editorial](evals/README.md)
- [Fluxos de trabalho](docs/workflows/)
- [Integrações planejadas](docs/integrations/)

Os documentos em [`docs/history/`](docs/history/) registram etapas anteriores; seus caminhos e decisões podem ter sido substituídos pela documentação atual.
