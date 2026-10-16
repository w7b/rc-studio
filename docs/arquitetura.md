# Arquitetura

Camadas, contratos e decisões do Studio, e os checks automáticos que as mantêm de pé.


## Arquitetura e decisões

O Studio é um monólito modular com React e Python. A imagem `runtime` contém o build
React e o backend; no modo compartilhado, a mesma imagem atende HTTP e executa o worker.
NGINX é a entrada HTTP e PostgreSQL mantém identidade, cotas e fila. O modo standalone
continua disponível sem banco ou login, com uma raiz de dados local.

### Fronteiras

| Camada em `apps/backend/src/studio_ai/` | Responsabilidade |
| --- | --- |
| `domain/` | Modelos e invariantes; não importa HTTP, SDK ou persistência |
| `application/` | Casos de uso e portas, sem I/O direto ou controle de threads |
| `infrastructure/` | SDK, provedores, arquivos, SQL, filas e integrações |
| `presentation/` | HTTP e CLI, usando comandos e consultas |
| `bootstrap/` | Configuração e montagem das dependências por processo/loja |

Frontend: `apps/frontend/src/app/`, `features/` e `shared/`. URLs ficam em
`shared/navigation/routes.js`; menus, permissões e breadcrumbs usam esse catálogo.
Os contratos HTTP continuam em `/api/*` e `/media/*`. Pydantic valida entradas e saídas.

### Decisões preservadas

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

### Agentes e campanhas

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

Performance e Marketing Analyst rodam em [consultas separadas](marketing-consultations.md).
Cada consulta consome uma unidade de `assists`; análise valida IDs de fontes e trechos
literais fornecidos, sem navegar nas URLs. A revisão editorial continua humana.

### Execução e consistência

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

### Identidade e isolamento

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
Detalhes operacionais: [administração e login](operacao.md).

### Dados e operação

Por padrão, `data/tenants/default` atende standalone, `data/tenants/<slug>` guarda cada
loja e `data/platform` guarda a configuração privada. `REALCENTER_DATA_ROOT` configura os dados; `REALCENTER_TENANTS_ROOT`, as lojas;
`REALCENTER_ENV_ROOT`, a configuração privada; `REALCENTER_RESOURCES_ROOT`, os prompts
versionados; `REALCENTER_STATIC_ROOT`, o build. Nunca remova Markdown de `resources/`
ou dos kits como se fosse documentação.

Backup inclui banco primeiro, depois arquivos das lojas e `.model-keys/`. A cópia de
arquivos ativos não é snapshot transacional global; recuperação precisa ser ensaiada.
Standalone continua lendo campanhas sem banco, mas não substitui sessões, cotas ou jobs.
O servidor HTTP atual usa a biblioteca padrão; exposição pública exige a topologia
HTTPS e os controles descritos no [guia NGINX](operacao.md).

[Validação](#validação) define os checks de CI e a inspeção manual.
[ROADMAP](../ROADMAP.md) registra somente pendências e decisões ainda não implementadas.


## Validação

O [workflow Validate application](../.github/workflows/tests.yml) é o ponto central
para verificações repetíveis. Roda em push, pull request e execução manual, sem chaves
reais de modelos. Execuções antigas da mesma branch são canceladas.

| Job | O que verifica |
| --- | --- |
| Frontend | Prettier, testes Node de rotas/contratos/renderização e build Vite |
| Backend | Regras, segurança, isolamento, persistência, APIs, fila e migrações com PostgreSQL descartável |
| Container | Build runtime, smoke sem rede e NGINX com PostgreSQL, login, CSRF, uploads, mídia e demo |
| `test` | Só aprova se os três jobs acima passarem |

O smoke da aplicação roda uma vez, dentro da imagem instalada; o teste NGINX acrescenta
os contratos de proxy e autenticação. Não há publicação de imagem, release ou deploy
automático. A execução remota começa depois do push; editar o workflow localmente não
significa que a CI rodou.

### Verificação local sob demanda

Na raiz, com dependências instaladas:

```powershell
node --test apps/frontend/tests/*.test.js
npm --prefix apps/frontend run format:check
npm --prefix apps/frontend run build
python -m pytest
```

Sem `TEST_DATABASE_URL`, casos PostgreSQL são ignorados. Para verificá-los, use banco
**descartável exclusivo de teste** e configure essa variável. No Windows, se um diretório
temporário antigo negar acesso, use `--basetemp=.test-work/local-novo -p no:cacheprovider`.
O backend de teste também precisa de Node para conferir o serializer real do formulário.

Para investigar empacotamento ou HTTP local:

```powershell
python scripts/package_frontend.py
python scripts/smoke.py
```

Não execute toda a suíte repetidamente por mudanças cosméticas. Preserve testes que
protegem contratos, segurança e comportamento; amplie um arquivo existente quando surgir
uma regressão relevante. Não crie um smoke de navegador por ajuste de layout.

### Revisão manual da interface

Construa o frontend e use uma loja descartável do ambiente Dev. Para revisar login,
menus e administração sem dados pessoais ou banco, também está disponível:

```powershell
python apps/frontend/tests/preview_server.py
```

Abra [a fixture local](http://127.0.0.1:8767/login), entre com `owner@example.test` ou
`member@example.test` e senha `senha-de-teste-123`. São identidades fictícias em memória;
os dados temporários são removidos ao encerrar. A porta 8767 precisa estar livre.
Essa fixture não configura modelos: use demo para campanha e não insira credenciais reais.

Conferir a área alterada em desktop e a 390 × 844, além de navegação por teclado:

- **Navegação:** pais expandem ao clicar; subitens e breadcrumbs abrem as URLs corretas.
  Recarregar, voltar e avançar preservam a página; links antigos chegam ao destino canônico.
  Módulos desabilitados e cargos continuam restringindo os destinos.
- **Campanha:** trocar origem de produto/referência entre nenhuma, biblioteca e upload;
  usar ambos, só um e nenhum. Remover upload não abre o seletor de arquivos. Salvar produto
  mostra feedback e permite reutilização. Modelo/demo, briefing, fatos e formato persistem
  na edição; demo não inicia geração paga. Não executar live apenas para validar o layout.
- **Biblioteca/referências:** upload por mouse e teclado, importação, busca e estados vazios;
  reutilização em campanha; recorte, fundo uniforme e 2× salvam cópias e preservam o original.
  Qwen sem configuração informa indisponibilidade. Exportações e detalhes de campanha abrem.
- **Conta/administração:** abas de pessoa, segurança, loja e Brand Kit; mensagens de sucesso
  e erro; modais com foco, Escape e retorno ao acionador; menus por teclado; cargos,
  suspensão e módulos atualizam permissões. Chaves salvas nunca reaparecem como texto.
- **Aparência:** nada corta ou transborda horizontalmente; textos não colidem; ações principais
  são encontráveis; estado de carregamento/erro/vazio é legível; foco e movimento reduzido
  funcionam. Home navega às seções e volta ao topo sem recarregar desnecessariamente.
- **Consultas/briefing:** modelo selecionado acompanha a ação; ausência de credencial tem
  orientação clara; resultado e formulário permanecem ao trocar abas. Qualidade das respostas
  e provedores externos precisam de avaliação live separada, explicitamente autorizada.

Os antigos runners Playwright específicos de telas dependiam de Edge e de rótulos/rotas
antigos. Foram substituídos por este checklist; contratos Node/Python e a fixture segura
continuam. Registre no pull request quais telas e estados foram realmente inspecionados,
sem tratar build ou testes offline como evidência visual ou de qualidade editorial.
