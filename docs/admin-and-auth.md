# Administração, módulos e login

`/admin` reúne métricas de todas as lojas, pessoas e módulos. Requer uma sessão OWNER
no modo compartilhado. Migrações SQL versionadas mantêm o schema, incluindo os módulos
por loja em `tenants.modules` (JSONB).

O Compose usa o modo compartilhado por padrão, conectando ao serviço `db`. O modo sem
login exige `STUDIO_MODE=standalone`. Se “Ambiente local conectado” aparecer no rodapé,
o servidor está sem identidade: reconstruir a imagem sozinho não resolve uma configuração
antiga. Recrie o serviço com o Compose atualizado e conclua o primeiro convite OWNER;
veja [primeiro acesso](nginx.md#primeiro-acesso-e-menus-ausentes).

As flags de módulos são permissões administradas pela plataforma. São independentes de
`integrations.json`: habilitar uma conexão no formulário da loja não libera um módulo bloqueado.
Configurações e dados pessoais permanecem acessíveis, permitindo recuperação. A autorização é reavaliada pelo servidor
em cada chamada; uma aba antiga também recebe 403 após a desativação.

O único menu `...` de cada loja reúne Gerenciar acessos, Gerenciar módulos,
Gerenciar chaves dos modelos, Convidar pessoa e Suspender/Reativar. ERP e Meta Ads
podem ser ocultados individualmente. Alterações na loja da sessão atual atualizam
a navegação imediatamente; outras sessões recebem as novas flags ao recarregar.

## Chaves de modelos por loja

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

## Métricas

`GET /api/admin/metrics` agrega todas as raízes de lojas. Períodos: semana atual a partir
de segunda-feira, mês atual e geral, em UTC−03:00. Cadastros usam `created_at` do Postgres.
Journals novos guardam entradas de consumo com timestamp por resposta; o histórico legado
é associado ao início da execução e identificado no relatório. Uso sem data só entra em Geral.
Chamadas contam respostas de IA e imagens registradas; requisições HTTP administrativas,
tentativas sem resposta e consumo fora do Studio não são cobrados nesse contador.
Custos conhecidos são estimativas registradas, com registros sem preço destacados.
Exclusões de journals reduzem o histórico disponível; estes números não substituem a fatura.

## Meta Ads

A implementação anterior guardava configurações e tinha apenas um adaptador inativo.
A tela agora oferece **Validar conexão com a Meta**, para ler a conta e comprovar acesso
à listagem de campanhas. Preencha conta `act_…`, versão explícita da Graph API e token.
A consulta utiliza Authorization Bearer, destino fixo e não segue redirects.
Alterações nas configurações invalidam a validação anterior. Publicação de anúncios
continua indisponível; validar leitura não significa comprovar gerenciamento ou veiculação.

Referência técnica: [coleção oficial Meta Marketing API](https://www.postman.com/meta/facebook-marketing-api/documentation/0zr4mes/facebook-marketing-api-mapi).

## Convites de lojas

Em Lojas e acessos, o menu da loja abre **Convidar pessoa**. O administrador informa
e-mail e cargo e recebe um link de uso único, válido por 7 dias, para compartilhar.
A tela de aceite envia e-mail, nome e senha para `/api/invites/accept`. Convites antigos
sem destinatário continuam funcionando ao informar o e-mail no formulário.
Destinatários vinculados são comparados sem diferença entre maiúsculas e minúsculas.
Novas contas exigem senha de pelo menos 8 caracteres; contas existentes precisam da
senha atual, que nunca é alterada por um convite. Erros preservam o convite para nova
tentativa; aceite bem-sucedido consome o link. Tentativas de senha têm o mesmo limite do login.

## OAuth2 / OpenID Connect

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
