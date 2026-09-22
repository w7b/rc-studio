# NGINX e operação

## Estrutura

`Navegador → NGINX:8080 → studio:8765 → banco / worker`

No Compose principal, o NGINX é a única entrada HTTP publicada (`127.0.0.1:8765` por padrão). O backend continua responsável por autenticação, permissões, rotas da SPA, downloads e isolamento de mídia por loja. Não há diretório público de arquivos de lojas nem cache compartilhado de respostas autenticadas no proxy.

Arquivos:

- `compose.yaml`: execução completa e healthchecks.
- `deploy/nginx/templates/default.conf.template`: servidor HTTP, destino do proxy e logs de acesso sem query string.
- `deploy/nginx/snippets/studio.conf`: cabeçalhos, limites de upload e timeouts.
- `compose.proxy-local.yaml`: apenas o NGINX, para um backend Python já aberto no Docker Desktop.

O backend é resolvido pelo DNS interno do Docker a cada 10 segundos. A configuração preserva `Host`, incluindo a porta, cookies e o token CSRF; o backend continua validando a origem. O NGINX não repete automaticamente uma requisição de geração quando o upstream falha.

O Compose define `REALCENTER_TRUSTED_PROXIES=nginx`. O backend só usa `X-Real-IP` para limitar tentativas de login quando o endereço da conexão pertence a esse serviço, resolvido pelo DNS; o NGINX sobrescreve o cabeçalho enviado pelo navegador. Sem configuração, cabeçalhos de IP são ignorados. Se outro ingress terminar a conexão antes do NGINX, configure também a confiança nesse ingress no NGINX para preservar o IP real.

## Execução completa

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

## Primeiro acesso e menus ausentes

“Ambiente local conectado” e ausência de Configurações/Administração indicam execução standalone. Confira `/api/config`: uma instalação compartilhada retorna `shared: true` e não entrega um token de acesso anônimo.

Um banco novo não contém usuários. Para cadastrar uma loja nova na sua própria raiz de dados e gerar um convite OWNER vinculado ao seu e-mail:

```powershell
docker compose exec studio python scripts/admin.py loja criar real-center "Real Center" --raiz /app/data/tenants/real-center
docker compose exec studio python scripts/admin.py convite criar --loja real-center --papel OWNER --email SEU_EMAIL --url http://127.0.0.1:8765
```

Esses comandos são para o operador do servidor na primeira instalação. Para dados antigos,
conclua a [migração](como-rodar.md#migrar-o-diretório-legado) antes de iniciar os serviços. Use o nome e identificador da sua loja; não repita o cadastro se ela já existir. Abra o link retornado, informe seu nome e defina a senha na tela. O convite dura sete dias e só pode ser usado uma vez. Configurações aparece para pessoas autenticadas; Administração, Consumo dos agentes e Logs exigem OWNER. Não remova a checagem de cargo para exibir esses menus.

## Apenas proxy para o backend local

Destinado ao Docker Desktop, que fornece `host.docker.internal`. Não sobe outro backend nem banco. O servidor Python deve aceitar a origem pública. Para o backend na porta 8766:

```powershell
$env:REALCENTER_PUBLIC_HOST = '127.0.0.1:8765,localhost:8765'
# Inicie o backend na porta 8766 com sua configuração compartilhada habitual.
docker compose -p studio-proxy-local -f compose.proxy-local.yaml up -d
docker compose -p studio-proxy-local -f compose.proxy-local.yaml exec nginx nginx -t
```

O site fica em <http://127.0.0.1:8765>. `STUDIO_BACKEND_PORT` permite escolher outra porta do backend; `STUDIO_HTTP_PORT` altera a porta externa e exige atualizar `REALCENTER_PUBLIC_HOST` antes de iniciar o backend.

Para parar somente esse proxy:

```powershell
docker compose -p studio-proxy-local -f compose.proxy-local.yaml down
```

O Docker Engine nativo em Linux exige um endereço do host alcançável pelo container e um listener adequado; esse arquivo local não configura isso automaticamente.

## Uploads e tempo de resposta

- Limite HTTP: **23 MiB por requisição**, igual ao backend. A resposta de excesso é um erro JSON com status 413.
- O limite individual existente de referências/produtos é 8 MiB. A futura implementação de logos usará o limite aprovado de 8 MiB por arquivo e cinco arquivos por loja, enviados individualmente.
- O NGINX recebe o corpo completo antes de repassá-lo ao backend. Isso também normaliza uploads HTTP em chunks para o servidor atual.
- Conexão ao backend: 5 segundos; espera de resposta e envio: 300 segundos de inatividade. Campanhas e imagens são iniciadas com resposta 202 e acompanhadas por consultas; não exigem uma conexão aberta por toda a geração.

## Domínio e HTTPS

O modo entregue é **HTTP local**. O NGINX não emite certificados automaticamente. Para publicar um domínio, configure a terminação TLS no proxy/ingress da hospedagem ou em um servidor HTTPS do NGINX com certificado válido; mantenha o backend sem porta pública.

No backend, defina `REALCENTER_PUBLIC_HOST=studio.seudominio.com` e `REALCENTER_PUBLIC_SCHEME=https`; essas variáveis controlam a validação de origem, cookies Secure e URLs de OAuth/convite. Não basta acrescentar `X-Forwarded-Proto`: o backend usa a configuração explícita. Registre no OAuth o callback do domínio final.

O `Caddyfile` anterior permanece como exemplo alternativo e não é iniciado pelo Compose. Não coloque Caddy e NGINX disputando a mesma porta. Caso o TLS termine antes deste NGINX, restrinja o acesso HTTP ao proxy confiável.

## Validação e diagnóstico

```powershell
docker compose logs --tail 100 nginx studio
docker build -t realcenter-studio:test .
docker pull nginx:stable-alpine
python scripts/smoke_nginx.py --image realcenter-studio:test --postgres
```

O teste sobe containers descartáveis com identidade e dados sintéticos em uma rede dedicada, publicando somente o proxy no loopback e sem chamar provedores. Com `--postgres`, usa PostgreSQL real e verifica que o pacote instalado inclui o schema SQL e consegue iniciar a autenticação. Verifica também SPA/assets, login, cookie, CSRF, rejeição de Host inválido, upload de 8 MiB, rejeição de requisição acima do limite, mídia, campanha demo, download, logout e proteção contra IP falsificado. O CI executa esse modo. Nenhum serviço ou volume já existente é removido por ele.

Após editar um **snippet**, valide antes de recarregar: `docker compose exec nginx nginx -t` e então `docker compose exec nginx nginx -s reload`. Se mudar o **template** ou suas variáveis, recrie o serviço para reaplicar a interpolação: `docker compose up -d --force-recreate nginx`; confira a configuração com `nginx -t` após a recriação. A simples recarga não gera novamente o arquivo do template.

Referências oficiais: [imagem Docker do NGINX](https://hub.docker.com/_/nginx), [proxy HTTP](https://nginx.org/en/docs/http/ngx_http_proxy_module.html) e [limites HTTP](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size).
