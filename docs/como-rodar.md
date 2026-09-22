# Como rodar

Comandos PowerShell executados na raiz. Requisitos: Docker com containers Linux e
Compose 2.24.4+, ou Python 3.11+ e Node.js 22 para desenvolvimento direto.

| Arquivo | Uso |
| --- | --- |
| `compose.yaml` | Runtime: NGINX, web, worker e PostgreSQL |
| `compose.dev.yaml` | Overlay de desenvolvimento; precisa do arquivo principal |
| `compose.proxy-local.yaml` | Só NGINX, apontando para Python no host |

## Dados e configuração

```text
data/
  platform/               .env e .model-keys/ privados da plataforma
  tenants/
    default/              loja standalone padrão
    <slug>/               tenant.json, brand/, campaigns/, configurações da loja
.venv/                    ambiente Python local; fora dos dados das lojas
```

Produção monta `./data:/app/data`. Dev monta `./.dev-data:/app/data`, com credenciais
em `.dev-data/platform/.env`; não compartilha dados, banco ou chaves com produção.
`REALCENTER_DATA_ROOT`, `REALCENTER_TENANTS_ROOT` e `REALCENTER_ENV_ROOT` permitem
sobrescrever os caminhos. Web e worker precisam usar os mesmos valores e enxergar os
arquivos pelos mesmos caminhos. Recursos de agentes continuam versionados em `resources/`.

Um `--root`/`REALCENTER_DATA_ROOT` explícito aceita instalações legadas; nesse caso,
defina também `REALCENTER_ENV_ROOT` para manter as credenciais na plataforma.

## Runtime compartilhado

```powershell
New-Item -ItemType Directory -Force data/platform | Out-Null
if (-not (Test-Path data/platform/.env)) { Copy-Item .env.example data/platform/.env }
docker compose --profile shared up -d --build
```

Acesse [http://127.0.0.1:8765](http://127.0.0.1:8765), faça o
[primeiro acesso](nginx.md#primeiro-acesso-e-menus-ausentes) e ajuste o Brand Kit da loja.
O perfil `shared` inicia o worker: sem ele, o HTTP aceita campanhas mas elas ficam na fila.
Consultas de briefing e especialistas continuam síncronas no web.

```powershell
docker compose ps
docker compose logs -f nginx studio worker
# Depois de alterar código ou dependências:
docker compose --profile shared up -d --build
# Parar preservando o banco e os arquivos:
docker compose --profile shared down
```

`down -v` remove o volume PostgreSQL; não o use para uma parada normal. Alterações de
`.env` exigem recriar web e worker. O fechamento de produção concede 4810 s para drenar
trabalho; ajuste conforme o timeout configurado. Reiniciar só o web preserva jobs do worker.
Interromper o worker pode acionar recuperação por lease; montagem ausente é falha terminal.

## Desenvolvimento

```powershell
docker compose -f compose.yaml -f compose.dev.yaml --profile shared watch
```

Acesse [http://127.0.0.1:8767](http://127.0.0.1:8767). Projeto `studio-ai-dev`, volume
`studio-dev-db`, banco/usuário `studio_dev`, senha local `studio-dev` substituível por
`DEV_POSTGRES_PASSWORD`. Cadastre lojas fictícias; não copie dados de clientes.

| Alteração | Efeito |
| --- | --- |
| Python, resources ou scripts | Sync e reinício do serviço com instalação editável |
| Frontend | Vite recompila no dist compartilhado; atualizar o navegador |
| pyproject.toml ou package-lock.json | Rebuild da imagem |

Salvar Python também reinicia worker. Dev concede só 10 s ao fechar. `Ctrl+C` encerra
watch; para parar os containers use:

```powershell
docker compose -f compose.yaml -f compose.dev.yaml --profile shared down
```

Para rodar Python/React diretamente, siga o [README](../README.md#começar).

## Backend local com proxy Docker

Configure uma instância PostgreSQL acessível no host; o banco do Compose não publica
porta por padrão. Em cada terminal Python, use o mesmo banco, raízes e origem pública:

```powershell
$env:DATABASE_URL = 'postgresql://studio:studio@127.0.0.1:5432/studio'
$env:REALCENTER_PUBLIC_HOST = '127.0.0.1:8765,localhost:8765'
# Terminal do web:
.\.venv\Scripts\python.exe scripts/run_backend.py --port 8766
# Em outro terminal, com o mesmo ambiente:
.\.venv\Scripts\python.exe scripts/worker.py
# Em um terceiro terminal:
docker compose -f compose.proxy-local.yaml up -d
```

NGINX aponta para `host.docker.internal:8766`; `STUDIO_BACKEND_PORT` altera a porta.
Veja [NGINX](nginx.md) para hosts, limites, TLS e diagnóstico.

## Standalone

`REALCENTER_DEPLOYMENT_MODE=auto` usa banco quando configurado; `shared` exige banco
válido; `standalone` o desliga explicitamente. No Docker, `STUDIO_MODE` fornece esse valor:

```powershell
$env:STUDIO_MODE = 'standalone'
docker compose up -d --build studio nginx
```

Esse modo usa `data/tenants/default` e não tem login. Exige ao menos um documento Markdown
em `brand/` para campanha. Shared falha no boot se não conseguir usar o banco; não troca
silenciosamente para standalone. Remova a variável de modo ao voltar ao deploy compartilhado.

## Migrar o diretório legado

Instalações anteriores usavam `realcenter-marketing-ai/`. A migração é uma ação operacional
separada da mudança de código: não execute o novo deploy sobre dados antigos sem planejá-la.

1. Faça backup do banco, diretório legado e chaves privadas. Pare web e worker antes da cópia.
2. Inspecione o plano sem escrita, usando o slug real da loja legada:
   `python scripts/migrate_data.py --legacy-tenant real-center`.
3. Revise origem/destino e contagens; aplique com o mesmo comando mais `--apply`.
   O script copia e compara SHA-256, é idempotente e preserva a origem.
4. Atualize manualmente as raízes registradas no banco, incluindo caminhos internos do
   Docker; o script não altera PostgreSQL. Preserve a identidade dos caminhos relativos e os vínculos das chaves por loja.
5. Suba o runtime e verifique login, mídia antiga, Brand Kit, fila/worker e uma campanha demo.
   Mantenha a origem e o backup até validar a instalação e a estratégia de reversão.

Com web/worker parados e sem jobs `running`, confira os registros no banco:

```sql
SELECT id, slug, root_path FROM tenants ORDER BY id;
SELECT id, tenant_id, tenant_slug, root_path, status FROM jobs
WHERE status IN ('queued', 'running');
```

Exemplo de atualização para o slug `real-center`, após confirmar sua identidade e a cópia:

```sql
BEGIN;
UPDATE tenants SET root_path = NULL
WHERE slug = 'real-center' AND root_path = '/app/realcenter-marketing-ai';
UPDATE jobs SET root_path = '/app/data/tenants/real-center'
WHERE tenant_id = (SELECT id FROM tenants WHERE slug = 'real-center')
  AND tenant_slug = 'real-center' AND root_path = '/app/realcenter-marketing-ai';
COMMIT;
```

`root_path = NULL` passa a resolver `data/tenants/<slug>` na nova instalação. Para outras
lojas com raiz explícita, repita com slug/caminho corretos; jobs existentes também precisam
do novo caminho. Instalações Python no host usam seus caminhos locais, não `/app`.
Não ajuste registros que apontem a raízes externas sem incluí-las na cópia e no backup.

Opções: `--legacy-root` (padrão `realcenter-marketing-ai`), `--data-root` (padrão `data`),
`--old-runtime-root` (padrão `/app/realcenter-marketing-ai`) e `--runtime-data-root`
(padrão `/app/data`). Recrie a venv em `.venv` na raiz; ambiente virtual não é dado de loja.

## Migrações de schema e backup

O boot aplica SQL pendente de `infrastructure/identity/migrations/` em ordem, dentro de
transação e lock entre web e worker. `schema_migrations` registra versões; baseline adota
instalações existentes e a migração de cargos converte `owner/manager/editor` para os atuais.

```powershell
python scripts/backup.py --destino C:/backups/studio --manter 14
```

Requer `pg_dump` no PATH e configuração de banco/raízes da instalação. Backup faz banco
primeiro, depois arquivos das lojas (incluindo consultas), `.model-keys/` e `.env` da
plataforma; revise avisos de arquivos ignorados.
Restaure banco e arquivos compatíveis, mantendo/reconciliando caminhos registrados e hashes
de raiz das credenciais. Não é snapshot atômico entre banco e disco; ensaie a restauração.

Checks locais e de GitHub estão no [guia de validação](architecture/validation.md).
