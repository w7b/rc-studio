# Arquitetura e decisões

O Studio é um monólito modular com React e Python. A imagem `runtime` contém o build
React e o backend; no modo compartilhado, a mesma imagem atende HTTP e executa o worker.
NGINX é a entrada HTTP e PostgreSQL mantém identidade, cotas e fila. O modo standalone
continua disponível sem banco ou login, com uma raiz de dados local.

## Fronteiras

| Camada em `apps/backend/src/realcenter_marketing/` | Responsabilidade |
| --- | --- |
| `domain/` | Modelos e invariantes; não importa HTTP, SDK ou persistência |
| `application/` | Casos de uso e portas, sem I/O direto ou controle de threads |
| `infrastructure/` | SDK, provedores, arquivos, SQL, filas e integrações |
| `presentation/` | HTTP e CLI, usando comandos e consultas |
| `bootstrap/` | Configuração e montagem das dependências por processo/loja |

Frontend: `apps/frontend/src/app/`, `features/` e `shared/`. URLs ficam em
`shared/navigation/routes.js`; menus, permissões e breadcrumbs usam esse catálogo.
Os contratos HTTP continuam em `/api/*` e `/media/*`. Pydantic valida entradas e saídas.

## Decisões preservadas

- **Monólito modular (ADR 001, 10/09/2026):** separar responsabilidades sem microserviços,
  preservar os contratos públicos e os IDs de mídia. Caminhos de módulos Python internos
  puderam mudar; migração física de dados precisa de compatibilidade e reversão próprias.
- **PostgreSQL (ADR 002, ampliado em 20/09/2026):** identidade, sessões, vínculos, convites,
  cotas e jobs exigem operações transacionais. SQL parametrizado com psycopg, sem ORM;
  migrações SQL versionadas, transação, lock consultivo e `schema_migrations` no boot.
  A baseline adota instalações existentes e a migração de cargos converte os nomes antigos.
- **Arquivos para os artefatos:** Brand Kit, campanhas, mídia e journals continuam no disco.
  Preservar os caminhos relativos usados nos IDs SHA-256. Um ID não autoriza acesso:
  caminhos idênticos em lojas distintas produzem o mesmo ID, sempre resolvido pela sessão.
- **Um deploy compartilhado:** escolhido pelo operador em vez de SQLite ou um container
  por loja. Web e worker compartilham imagem, banco e caminhos de arquivos. Não há broker
  externo. Múltiplos nós exigiriam armazenamento compartilhado e coordenação adicional.

Os ADRs e históricos separados foram absorvidos aqui. Esta descrição substitui as
etapas antigas que ainda diziam que não havia login, banco, fila ou Docker.

## Agentes e campanhas

A aplicação executa **Director planeja → Social Media → Copywriter → Creative → Director
revisa**, normalmente cinco chamadas. A ordem é fixa no runtime; especialistas não são
mais tools do Director. Cada execução monta equipe e cliente de provedor próprios.
Entregas anteriores, fatos e documentos da marca compõem o contexto das próximas etapas.
Schemas, sequência e formatos são validados antes de compor a campanha; correção de
saída inválida pode exigir uma chamada adicional.

A produção de imagens é posterior aos textos. Fotos de produto são enviadas ao modelo
de imagem; agentes de texto não interpretam os pixels. Carrosséis preservam cards já
concluídos; edição salva uma cópia. Retomar uma campanha sem textos consolidados cria
outra execução. Se os textos já estão salvos, a tentativa refaz somente imagens pendentes.
Excluir uma campanha move seus arquivos para `campaigns/runs/.trash` e exige ausência
de trabalho ativo. Nenhum fluxo publica em redes sociais automaticamente.

Performance e Marketing Analyst rodam em [consultas separadas](../marketing-consultations.md).
Cada consulta consome uma unidade de `assists`; análise valida IDs de fontes e trechos
literais fornecidos, sem navegar nas URLs. A revisão editorial continua humana.

## Execução e consistência

- Standalone usa scheduler local e bloqueio de processo para um escritor por raiz.
  Trabalho em voo é drenado no fechamento; interrupções abruptas ficam visíveis no journal.
- Em shared, HTTP valida, reserva cota e grava run/job; o worker consome PostgreSQL com
  `FOR UPDATE SKIP LOCKED`. Reiniciar apenas o web preserva o trabalho do worker.
- O worker renova heartbeat a cada 20 s, com lease de 120 s e até três tentativas após
  perda do worker. Conclusão exige o dono do claim. Falha real de execução é terminal;
  montagem ausente também. `BusyError` re-enfileira. Isso não garante execução única.
- Web e worker possuem pools separados; um worker executa jobs serialmente. Consultas
  síncronas no web podem coexistir com campanhas no worker. Cota é reservada na admissão,
  sem nova cobrança pelo worker; o limite do web não é teto global entre processos.
- A admissão consulta jobs pendentes, sem índice único parcial por loja. Dois POSTs
  simultâneos ainda exigem atenção. A API sobrepõe estado da fila ao snapshot do disco.
- Cotas usam unidades de campanhas/imagens/assists por mês em `America/Sao_Paulo`.
  Preço desconhecido não vira zero; USD é estimativa, não bloqueio confiável. Reserva de
  carrossel pode exceder imagens realmente geradas numa retomada; faturamento deve usar eventos.

## Identidade e isolamento

`REALCENTER_DEPLOYMENT_MODE`: `shared` exige banco válido; `standalone` o desliga;
`auto` usa banco quando configurado. Em Docker, o padrão é shared. Não remover login
como fallback quando banco falha. OWNER administra a plataforma; DEFAULT e PAID têm
acesso e cotas por vínculo com a loja. Assinatura por vínculo, em vez de por loja,
permanece uma escolha a revisar antes de automatizar cobrança.

Sessões/convites são guardados por hash; senhas usam scrypt com limite de concorrência.
Cookie é HttpOnly/SameSite=Lax e Secure quando o esquema público é HTTPS. A sessão
expira por tempo absoluto e ociosidade e perde validade com suspensão/revogação.
CSRF pertence à sessão autenticada, sem token anônimo em `/api/config` no modo shared.
OAuth autentica pessoas já autorizadas, exige e-mail verificado e usa PKCE/state.

A raiz registrada da loja governa toda leitura de mídia/configuração. Credenciais vêm
somente da plataforma (`REALCENTER_ENV_ROOT`, incluindo `.model-keys/`); `.env` de loja
não pode redirecionar endpoints. Overrides de agentes/políticas por raiz ficam desligados
por padrão. Rate limit em memória e coordenação entre réplicas são limitações conhecidas.
Detalhes operacionais: [administração e login](../admin-and-auth.md).

## Dados e operação

Por padrão, `data/tenants/default` atende standalone, `data/tenants/<slug>` guarda cada
loja e `data/platform` guarda a configuração privada. `REALCENTER_DATA_ROOT` configura os dados; `REALCENTER_TENANTS_ROOT`, as lojas;
`REALCENTER_ENV_ROOT`, a configuração privada; `REALCENTER_RESOURCES_ROOT`, os prompts
versionados; `REALCENTER_STATIC_ROOT`, o build. Nunca remova Markdown de `resources/`
ou dos kits como se fosse documentação.

Backup inclui banco primeiro, depois arquivos das lojas e `.model-keys/`. A cópia de
arquivos ativos não é snapshot transacional global; recuperação precisa ser ensaiada.
Standalone continua lendo campanhas sem banco, mas não substitui sessões, cotas ou jobs.
O servidor HTTP atual usa a biblioteca padrão; exposição pública exige a topologia
HTTPS e os controles descritos no [guia NGINX](../nginx.md).

[Validação](validation.md) define os checks de CI e a inspeção manual.
[ROADMAP](../../ROADMAP.md) registra somente pendências e decisões ainda não implementadas.
