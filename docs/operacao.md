# Operação

Como rodar, publicar e administrar o Studio: ambientes, NGINX e HTTPS, primeiro acesso, login, módulos e credenciais.


## Como rodar

Comandos PowerShell executados na raiz. Requisitos: Docker com containers Linux e
Compose 2.24.4+, ou Python 3.11+ e Node.js 22 para desenvolvimento direto.

| Arquivo | Uso |
| --- | --- |
| `compose.yaml` | Runtime: NGINX, web, worker e PostgreSQL |
| `compose.dev.yaml` | Overlay de desenvolvimento; precisa do arquivo principal |
| `compose.proxy-local.yaml` | Só NGINX, apontando para Python no host |

### Dados e configuração

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

### Runtime compartilhado

```powershell
New-Item -ItemType Directory -Force data/platform | Out-Null
if (-not (Test-Path data/platform/.env)) { Copy-Item .env.example data/platform/.env }
docker compose --profile shared up -d --build
```

Acesse [http://127.0.0.1:8765](http://127.0.0.1:8765), faça o
[primeiro acesso](operacao.md#primeiro-acesso-e-menus-ausentes) e ajuste o Brand Kit da loja.
O perfil `shared` inicia o worker: sem ele, o HTTP aceita campanhas mas elas ficam na fila.
Consultas de briefing e especialistas continuam síncronas no web.

```powershell
docker compose ps
docker compose logs -f nginx studio worker
## Depois de alterar código ou dependências:
docker compose --profile shared up -d --build
## Parar preservando o banco e os arquivos:
docker compose --profile shared down
```

`down -v` remove o volume PostgreSQL; não o use para uma parada normal. Alterações de
`.env` exigem recriar web e worker. O fechamento de produção concede 4810 s para drenar
trabalho; ajuste conforme o timeout configurado. Reiniciar só o web preserva jobs do worker.
Interromper o worker pode acionar recuperação por lease; montagem ausente é falha terminal.

### Desenvolvimento

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

### Backend local com proxy Docker

Configure uma instância PostgreSQL acessível no host; o banco do Compose não publica
porta por padrão. Em cada terminal Python, use o mesmo banco, raízes e origem pública:

```powershell
$env:DATABASE_URL = 'postgresql://studio:studio@127.0.0.1:5432/studio'
$env:REALCENTER_PUBLIC_HOST = '127.0.0.1:8765,localhost:8765'
## Terminal do web:
.\.venv\Scripts\python.exe scripts/run_backend.py --port 8766
## Em outro terminal, com o mesmo ambiente:
.\.venv\Scripts\python.exe scripts/worker.py
## Em um terceiro terminal:
docker compose -f compose.proxy-local.yaml up -d
```

NGINX aponta para `host.docker.internal:8766`; `STUDIO_BACKEND_PORT` altera a porta.
Veja [NGINX](operacao.md) para hosts, limites, TLS e diagnóstico.

### Standalone

`REALCENTER_DEPLOYMENT_MODE=auto` usa banco quando configurado; `shared` exige banco
válido; `standalone` o desliga explicitamente. No Docker, `STUDIO_MODE` fornece esse valor:

```powershell
$env:STUDIO_MODE = 'standalone'
docker compose up -d --build studio nginx
```

Esse modo usa `data/tenants/default` e não tem login. Exige ao menos um documento Markdown
em `brand/` para campanha. Shared falha no boot se não conseguir usar o banco; não troca
silenciosamente para standalone. Remova a variável de modo ao voltar ao deploy compartilhado.

### Migrar o diretório legado

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

### Migrações de schema e backup

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

Checks locais e de GitHub estão no [guia de validação](arquitetura.md).


## NGINX e operação

### Estrutura

`Navegador → NGINX:8080 → studio:8765 → banco / worker`

No Compose principal, o NGINX é a única entrada HTTP publicada (`127.0.0.1:8765` por padrão). O backend continua responsável por autenticação, permissões, rotas da SPA, downloads e isolamento de mídia por loja. Não há diretório público de arquivos de lojas nem cache compartilhado de respostas autenticadas no proxy.

Arquivos:

- `compose.yaml`: execução completa e healthchecks.
- `deploy/nginx/templates/default.conf.template`: servidor HTTP, destino do proxy e logs de acesso sem query string.
- `deploy/nginx/snippets/studio.conf`: cabeçalhos, limites de upload e timeouts.
- `compose.proxy-local.yaml`: apenas o NGINX, para um backend Python já aberto no Docker Desktop.

O backend é resolvido pelo DNS interno do Docker a cada 10 segundos. A configuração preserva `Host`, incluindo a porta, cookies e o token CSRF; o backend continua validando a origem. O NGINX não repete automaticamente uma requisição de geração quando o upstream falha.

O Compose define `REALCENTER_TRUSTED_PROXIES=nginx`. O backend só usa `X-Real-IP` para limitar tentativas de login quando o endereço da conexão pertence a esse serviço, resolvido pelo DNS; o NGINX sobrescreve o cabeçalho enviado pelo navegador. Sem configuração, cabeçalhos de IP são ignorados. Se outro ingress terminar a conexão antes do NGINX, configure também a confiança nesse ingress no NGINX para preservar o IP real.

### Execução completa

```powershell
docker compose config --quiet
docker compose --profile shared up --build -d
docker compose ps
docker compose exec nginx nginx -t
```

Acesse <http://127.0.0.1:8765>. Esse modo inicia a própria instância do backend **com login e PostgreSQL habilitados por padrão**. Para usar a instância já aberta no computador, use o próximo modo em vez deste.

`STUDIO_HTTP_PORT` altera a porta pública; `STUDIO_BIND_ADDRESS` mantém por padrão o acesso restrito à máquina local. O Compose adiciona os hosts locais com essa porta à lista aceita pelo backend.

Variáveis usadas na interpolação do Compose devem estar no ambiente, no `.env` da raiz ou em `--env-file`. O `env_file` dentro do serviço não fornece valores para `${...}` do Compose. A conexão padrão usa o serviço `db` e os campos `POSTGRES_DB`, `POSTGRES_USER` e `POSTGRES_PASSWORD`, sem exigir uma URL manual. Uma `DATABASE_URL` explícita pode apontar para outro banco. Para carregar variáveis do arquivo da plataforma e iniciar também o worker necessário à fila compartilhada:

```powershell
docker compose --env-file data/platform/.env --profile shared up --build -d
```

O worker e o backend compartilham `./data:/app/data`; a configuração privada fica em
`/app/data/platform` e os dados em `/app/data/tenants/<slug>`. Raízes de lojas registradas no banco devem ser caminhos válidos **dentro do container**; caminhos Windows absolutos de uma instalação local não são automaticamente convertidos ao migrar o banco para Docker.

Para uma instalação deliberadamente sem login, defina `STUDIO_MODE=standalone` antes de recriar o serviço. O modo compartilhado falha na inicialização se não conseguir conectar ao banco; nunca deve abrir o sistema sem autenticação por engano.

### Primeiro acesso e menus ausentes

“Ambiente local conectado” e ausência de Configurações/Administração indicam execução standalone. Confira `/api/config`: uma instalação compartilhada retorna `shared: true` e não entrega um token de acesso anônimo.

Um banco novo não contém usuários. Para cadastrar uma loja nova na sua própria raiz de dados e gerar um convite OWNER vinculado ao seu e-mail:

```powershell
docker compose exec studio python scripts/admin.py loja criar real-center "Real Center" --raiz /app/data/tenants/real-center
docker compose exec studio python scripts/admin.py convite criar --loja real-center --papel OWNER --email SEU_EMAIL --url http://127.0.0.1:8765
```

Esses comandos são para o operador do servidor na primeira instalação. Para dados antigos,
conclua a [migração](operacao.md#migrar-o-diretório-legado) antes de iniciar os serviços. Use o nome e identificador da sua loja; não repita o cadastro se ela já existir. Abra o link retornado, informe seu nome e defina a senha na tela. O convite dura sete dias e só pode ser usado uma vez. Configurações aparece para pessoas autenticadas; Administração, Consumo dos agentes e Logs exigem OWNER. Não remova a checagem de cargo para exibir esses menus.

### Apenas proxy para o backend local

Destinado ao Docker Desktop, que fornece `host.docker.internal`. Não sobe outro backend nem banco. O servidor Python deve aceitar a origem pública. Para o backend na porta 8766:

```powershell
$env:REALCENTER_PUBLIC_HOST = '127.0.0.1:8765,localhost:8765'
## Inicie o backend na porta 8766 com sua configuração compartilhada habitual.
docker compose -p studio-proxy-local -f compose.proxy-local.yaml up -d
docker compose -p studio-proxy-local -f compose.proxy-local.yaml exec nginx nginx -t
```

O site fica em <http://127.0.0.1:8765>. `STUDIO_BACKEND_PORT` permite escolher outra porta do backend; `STUDIO_HTTP_PORT` altera a porta externa e exige atualizar `REALCENTER_PUBLIC_HOST` antes de iniciar o backend.

Para parar somente esse proxy:

```powershell
docker compose -p studio-proxy-local -f compose.proxy-local.yaml down
```

O Docker Engine nativo em Linux exige um endereço do host alcançável pelo container e um listener adequado; esse arquivo local não configura isso automaticamente.

### Uploads e tempo de resposta

- Limite HTTP: **23 MiB por requisição**, igual ao backend. A resposta de excesso é um erro JSON com status 413.
- O limite individual existente de referências/produtos é 8 MiB. A futura implementação de logos usará o limite aprovado de 8 MiB por arquivo e cinco arquivos por loja, enviados individualmente.
- O NGINX recebe o corpo completo antes de repassá-lo ao backend. Isso também normaliza uploads HTTP em chunks para o servidor atual.
- Conexão ao backend: 5 segundos; espera de resposta e envio: 300 segundos de inatividade. Campanhas e imagens são iniciadas com resposta 202 e acompanhadas por consultas; não exigem uma conexão aberta por toda a geração.

### Domínio e HTTPS

O modo entregue é **HTTP local**. O NGINX não emite certificados automaticamente. Para publicar um domínio, configure a terminação TLS no proxy/ingress da hospedagem ou em um servidor HTTPS do NGINX com certificado válido; mantenha o backend sem porta pública.

No backend, defina `REALCENTER_PUBLIC_HOST=studio.seudominio.com` e `REALCENTER_PUBLIC_SCHEME=https`; essas variáveis controlam a validação de origem, cookies Secure e URLs de OAuth/convite. Não basta acrescentar `X-Forwarded-Proto`: o backend usa a configuração explícita. Registre no OAuth o callback do domínio final.

O `Caddyfile` anterior permanece como exemplo alternativo e não é iniciado pelo Compose. Não coloque Caddy e NGINX disputando a mesma porta. Caso o TLS termine antes deste NGINX, restrinja o acesso HTTP ao proxy confiável.

### Validação e diagnóstico

```powershell
docker compose logs --tail 100 nginx studio
docker build -t realcenter-studio:test .
docker pull nginx:stable-alpine
python scripts/smoke_nginx.py --image realcenter-studio:test --postgres
```

O teste sobe containers descartáveis com identidade e dados sintéticos em uma rede dedicada, publicando somente o proxy no loopback e sem chamar provedores. Com `--postgres`, usa PostgreSQL real e verifica que o pacote instalado inclui o schema SQL e consegue iniciar a autenticação. Verifica também SPA/assets, login, cookie, CSRF, rejeição de Host inválido, upload de 8 MiB, rejeição de requisição acima do limite, mídia, campanha demo, download, logout e proteção contra IP falsificado. O CI executa esse modo. Nenhum serviço ou volume já existente é removido por ele.

Após editar um **snippet**, valide antes de recarregar: `docker compose exec nginx nginx -t` e então `docker compose exec nginx nginx -s reload`. Se mudar o **template** ou suas variáveis, recrie o serviço para reaplicar a interpolação: `docker compose up -d --force-recreate nginx`; confira a configuração com `nginx -t` após a recriação. A simples recarga não gera novamente o arquivo do template.

Referências oficiais: [imagem Docker do NGINX](https://hub.docker.com/_/nginx), [proxy HTTP](https://nginx.org/en/docs/http/ngx_http_proxy_module.html) e [limites HTTP](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size).


## Administração, módulos e login

`/admin` reúne métricas de todas as lojas, pessoas e módulos. Requer uma sessão OWNER
no modo compartilhado. Migrações SQL versionadas mantêm o schema, incluindo os módulos
por loja em `tenants.modules` (JSONB).

O Compose usa o modo compartilhado por padrão, conectando ao serviço `db`. O modo sem
login exige `STUDIO_MODE=standalone`. Se “Ambiente local conectado” aparecer no rodapé,
o servidor está sem identidade: reconstruir a imagem sozinho não resolve uma configuração
antiga. Recrie o serviço com o Compose atualizado e conclua o primeiro convite OWNER;
veja [primeiro acesso](operacao.md#primeiro-acesso-e-menus-ausentes).

As flags de módulos são permissões administradas pela plataforma. São independentes de
`integrations.json`: habilitar uma conexão no formulário da loja não libera um módulo bloqueado.
Configurações e dados pessoais permanecem acessíveis, permitindo recuperação. A autorização é reavaliada pelo servidor
em cada chamada; uma aba antiga também recebe 403 após a desativação.

O único menu `...` de cada loja reúne Gerenciar acessos, Gerenciar módulos,
Gerenciar chaves dos modelos, Convidar pessoa e Suspender/Reativar. ERP e Meta Ads
podem ser ocultados individualmente. Alterações na loja da sessão atual atualizam
a navegação imediatamente; outras sessões recebem as novas flags ao recarregar.

### Chaves de modelos por loja

`GET /api/admin/tenants/model-keys?tenant_id=…` e o POST correspondente exigem OWNER.
O POST recebe `changes` por provedor (`openai` ou `nvidia`) com `action: replace` e
`key`, ou `action: inherit`. As respostas mostram somente origem e disponibilidade.
A herança usa as variáveis globais do servidor. Uma substituição afeta somente a
raiz da loja selecionada e é lida na próxima solicitação, sem reiniciar serviços.

As chaves ficam em `.model-keys/` sob `REALCENTER_ENV_ROOT` (por padrão, `data/platform`), separadas por identificador derivado da raiz registrada da loja.
Não são armazenadas em `tenant.json`, nem entregues por APIs de mídia ou logs.
O diretório é ignorado pelo Git. É configuração privada do servidor, armazenada
em arquivo sem criptografia adicional; seu acesso e backup devem seguir os mesmos
controles do `.env`. Em Linux, arquivos novos usam modo 0600. O registro central
injeta a raiz de configuração nas execuções HTTP e worker; `.env` da loja não
pode trocar a credencial ou redirecionar o endpoint de um provedor.

### Métricas

`GET /api/admin/metrics` agrega todas as raízes de lojas. Períodos: semana atual a partir
de segunda-feira, mês atual e geral, em UTC−03:00. Cadastros usam `created_at` do Postgres.
Journals novos guardam entradas de consumo com timestamp por resposta; o histórico legado
é associado ao início da execução e identificado no relatório. Uso sem data só entra em Geral.
Chamadas contam respostas de IA e imagens registradas; requisições HTTP administrativas,
tentativas sem resposta e consumo fora do Studio não são cobrados nesse contador.
Custos conhecidos são estimativas registradas, com registros sem preço destacados.
Exclusões de journals reduzem o histórico disponível; estes números não substituem a fatura.

### Meta Ads

A implementação anterior guardava configurações e tinha apenas um adaptador inativo.
A tela agora oferece **Validar conexão com a Meta**, para ler a conta e comprovar acesso
à listagem de campanhas. Preencha conta `act_…`, versão explícita da Graph API e token.
A consulta utiliza Authorization Bearer, destino fixo e não segue redirects.
Alterações nas configurações invalidam a validação anterior. Publicação de anúncios
continua indisponível; validar leitura não significa comprovar gerenciamento ou veiculação.

Referência técnica: [coleção oficial Meta Marketing API](https://www.postman.com/meta/facebook-marketing-api/documentation/0zr4mes/facebook-marketing-api-mapi).

### Convites de lojas

Em Lojas e acessos, o menu da loja abre **Convidar pessoa**. O administrador informa
e-mail e cargo e recebe um link de uso único, válido por 7 dias, para compartilhar.
A tela de aceite envia e-mail, nome e senha para `/api/invites/accept`. Convites antigos
sem destinatário continuam funcionando ao informar o e-mail no formulário.
Destinatários vinculados são comparados sem diferença entre maiúsculas e minúsculas.
Novas contas exigem senha de pelo menos 8 caracteres; contas existentes precisam da
senha atual, que nunca é alterada por um convite. Erros preservam o convite para nova
tentativa; aceite bem-sucedido consome o link. Tentativas de senha têm o mesmo limite do login.

### OAuth2 / OpenID Connect

O login descobre os provedores em `/api/config`. `OAuthProviders` renderiza apenas os
habilitados. O backend possui registro de provedores e rotas genéricas
`/api/auth/{provider}` e `/api/auth/{provider}/callback`; Google já implementa o contrato.
Um novo provedor precisa implementar `OAuthProvider` e ser registrado em `build_identity`.

Para Google, configure no servidor `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
`REALCENTER_PUBLIC_HOST` e `REALCENTER_PUBLIC_SCHEME=https`. Registre exatamente
`https://SEU_HOST/api/auth/google/callback` no console do Google. Nenhum segredo vai para
variáveis VITE. Authorization Code usa PKCE S256, state e cookie HttpOnly de curta duração.
Callback válido abre `/studio`; erro mantém `/login?erro=oauth` ou `sem-acesso`.
OAuth autentica: sem vínculo de loja e e-mail verificado, o acesso continua recusado.

Referência: [Google OAuth para aplicações web](https://developers.google.com/identity/protocols/oauth2/web-server).
