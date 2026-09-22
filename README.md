# Real Center Studio

Studio web para lojas de diferentes segmentos planejarem campanhas com agentes de IA,
produzirem textos e artes e organizarem referências. React + Python + OpenAI Agents SDK,
em um monólito modular; PostgreSQL cuida de identidade, cotas e fila no modo compartilhado.

As entregas são rascunhos para revisão humana. O Studio não publica conteúdo ou anúncios
automaticamente. Reels recebem capas estáticas, não vídeos.

## O que está disponível

- Campanhas: Director planeja, Social Media, Copywriter e Creative produzem as entregas,
  e Director revisa; geração e revisão de imagens seguem o briefing aprovado.
- Consultas individuais a Performance Marketing e Marketing Analyst, com fontes
  fornecidas pelo usuário e sem aumentar a equipe da campanha.
- Biblioteca de produtos e artes, referências e edição de imagens preservando originais.
- Login por loja, convites, cargos DEFAULT/PAID/OWNER, módulos e cotas de uso.
- Perfil e Brand Kit por loja, chaves de modelos privadas e métricas administrativas.
- Demonstração offline, sem chamadas a provedores ou geração de imagens.

Meta Ads permite validar acesso de leitura; publicação permanece indisponível.
SG Sistemas tem contratos preparados e aguarda homologação.

## Começar

Requisitos: Docker com containers Linux e Compose 2.24.4+, ou Python 3.11+ e Node.js 22
para desenvolvimento local. Comandos abaixo usam PowerShell na raiz do repositório.
Instalações legadas devem seguir a [migração de dados](docs/como-rodar.md#migrar-o-diretório-legado) antes de usar o novo layout.

```powershell
New-Item -ItemType Directory -Force data/platform | Out-Null
if (-not (Test-Path data/platform/.env)) {
    Copy-Item .env.example data/platform/.env
}
docker compose --profile shared up --build -d
```

Abra [o Studio](http://127.0.0.1:8765) e siga o [primeiro acesso OWNER](docs/nginx.md#primeiro-acesso-e-menus-ausentes).
O perfil `shared` inicia o worker que consome a fila; sem ele, campanhas compartilhadas
ficam aguardando. Credenciais de modelos ficam no backend, conforme `.env.example`.

Para desenvolvimento local sem login:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e './apps/backend[dev]'
npm --prefix apps/frontend ci
npm --prefix apps/frontend run build
$env:REALCENTER_DEPLOYMENT_MODE = 'standalone'
.\.venv\Scripts\python.exe scripts/run_backend.py
```

O modo standalone precisa de documentos de marca em `data/tenants/default/brand/`
para executar campanhas, inclusive demo. Use `brand.md`, `colors.md`, `typography.md`,
`tone-of-voice.md` e `visual-guidelines.md` com informações confirmadas; logos e fotos
ficam em `brand/logo/`, `brand/references/` e `brand/products/reference-only/`.
No modo compartilhado, o cadastro da loja cria um kit base editável.

Para atualizar React automaticamente, execute `npm --prefix apps/frontend run dev` em
outro terminal e abra a URL do Vite. CLI demo: `realcenter-marketing --demo "Campanha institucional"`
com o ambiente virtual ativado. O servidor também aceita `realcenter-studio` e
`python -m realcenter_marketing`; a entrada `realcenter_marketing.dashboard` mantém compatibilidade.

## Validação e GitHub

O [GitHub Actions](.github/workflows/tests.yml) executa contratos e build do frontend,
testes Python com PostgreSQL e smoke da imagem/NGINX em jobs separados. Não precisa de
chaves de IA. O check agregado `test` só passa quando todos passam.

Mudanças visuais são conferidas manualmente em desktop e celular. Use o
[guia de validação](docs/architecture/validation.md) para comandos e checklist.
Preserve testes de regras, segurança e contratos; ajustes cosméticos não precisam
de novos arquivos de teste. Qualidade editorial com modelos reais segue [evals/README.md](evals/README.md).

Após revisar o diff e os dados incluídos, envie uma branch ao remoto e abra um pull
request. Aguarde os checks antes de integrar. O workflow valida o projeto; não faz
deploy, release ou publicação automática.

## Organização e dados

| Local | Responsabilidade |
| --- | --- |
| `apps/backend/src/realcenter_marketing/` | Domínio, aplicação, adaptadores, HTTP/CLI e composição |
| `apps/frontend/src/` | App, funcionalidades, componentes e estilos |
| `resources/` | Manifestos, instruções de agentes, políticas, catálogos e respostas demo |
| `data/platform/` e `data/tenants/<slug>/` | Configuração privada da plataforma e dados isolados das lojas |
| `scripts/` | Inicialização, administração, worker, backup e smoke |

Markdown em `resources/` e nos Brand Kits é entrada da aplicação, não documentação
descartável. Dados, `.env`, `.model-keys/`, dependências e builds não devem ir ao Git.
O clone não substitui backup de banco e arquivos; preserve caminhos relativos e IDs de mídia.

## Documentação

- [Como rodar, ambientes, migrações e backup](docs/como-rodar.md)
- [NGINX, primeiro acesso e HTTPS](docs/nginx.md)
- [Administração, login, módulos e credenciais](docs/admin-and-auth.md)
- [Arquitetura e decisões](docs/architecture/blueprint.md)
- [Validação automática e revisão manual](docs/architecture/validation.md)
- [Consultoria e contratos de campanha](docs/marketing-consultations.md)
- [Edição de referências e Qwen](docs/reference-editor.md)
- [Nemotron](docs/nemotron.md) e [escopo SGCloud](docs/integrations/sgcloud/README.md)
- [Próximas entregas e decisões de Brand Kit](ROADMAP.md)
- [Design](DESIGN.md) e [comportamentos de interface](UX-CONTRACT.md)
