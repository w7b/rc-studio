# Contrato de interface do Studio AI

Público brasileiro, idioma pt-BR. Identidade e permissões seguem o ADR 002.
Somente OWNER administra toda a plataforma. DEFAULT e PAID não recebem acesso ao admin.

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Select/Listbox | select/datalist nativos; CategoryField | catálogo storeCategories.js | popup do sistema operacional | teclado e viewport estreita |
| Form | Form.jsx + Textarea.jsx + PasswordInput.jsx, labels/input nativos | contrato da API | criar/editar; validação local e servidor | sucesso, erro e preservação dos valores |
| Scrollbar | shared/styles/platform.css | shared/styles/tokens.css / DESIGN.md | geometria interna de tabelas e menus | computed style |
| Toast | status/alert inline junto da operação | resposta da API | sucesso/erro/processamento | live region |
| CRUD | cliente api/post e routes.js | API + URL | salvar no contexto; criar volta à lista | HTTP e navegador |
| Dialog | Modal.jsx | dialog.showModal() | formulário/confirmar | foco, Escape, centralização |
| Menu | ActionMenu.jsx | portal único por gatilho | direita/esquerda | setas, Escape, colisão |
| Categorias | StoreCategoriesModal.jsx | resources/catalog/store-categories.json + API | até três categorias por loja | limite na UI e servidor, persistência e combinação de regras |
| Biblioteca | Library.jsx | catálogo de mídia da loja | produtos e artes | upload, isolamento, filtro e reutilização |

## Navegação

- `/` e `/home` são a home pública; `/login` recebe senha e os provedores OAuth anunciados pelo servidor.
- Autenticado entra em `/studio`; URLs dos módulos são definidas por `routes.js`.
- `/studio/campaings` é a grafia solicitada; `/studio/campaigns` redireciona para ela.
- Campanhas selecionadas usam `?run=ID`, preservando reload e Voltar/Avançar.
- Visitantes em áreas privadas são redirecionados para `/`. Pessoas sem OWNER em `/admin` voltam a `/home`.
- Módulo bloqueado redireciona à conta. URLs inválidas voltam à home. A API continua respondendo 401/403.
- O modo standalone local permanece sem autenticação, conforme ADR 002.
- Clientes e Como funciona navegam por âncoras, com rolagem suave e compensação do menu fixo; movimento reduzido usa rolagem imediata.
- Studio AI no menu retorna suavemente ao topo da home. O único contato da home fica abaixo das garantias.
- O menu `...` da loja é o ponto de entrada das ações administrativas; a lista de pessoas mostra apenas informações e cargos.
- Desativar ERP ou Meta Ads oculta o item da navegação da loja após atualizar a sessão e bloqueia as rotas e APIs. Configurações de conta permanecem acessíveis.

## Chaves dos modelos

Somente OWNER pode consultar a origem das chaves e substituir chaves de provedores
de uma loja. GET e POST nunca devolvem o segredo. Campos vazios preservam as chaves.
Remover uma chave própria pede confirmação e explica a herança da chave global,
incluindo a indisponibilidade quando não existe chave global. Chaves de uma loja
não mudam a configuração de outra. O sistema não testa credenciais fazendo chamadas pagas.

## Produtos e campanhas

Referências aceita o tipo Imagem somente via arquivo PNG/JPEG validado. O produto
pertence ao Brand Kit da loja, aparece na Biblioteca e pode ser selecionado como
foto do produto na campanha, separado da referência de estilo. A Biblioteca não
mistura produtos com artes prontas. A visualização resumida da campanha não altera
as entregas geradas nem o consumo: detalhes continuam disponíveis sob demanda.

## Operações

Salvar bloqueia envio duplicado. Falha preserva valores e apresenta mensagem textual.
Alterações de cargos, suspensão e remoção de acesso exigem confirmação dentro do produto.
Módulos podem ser ligados/desligados no modal da loja com efeito imediato na API.
Configurações de conta permanecem acessíveis; desativar módulo não apaga arquivos nem interrompe trabalho em andamento.
Busca de lojas é local, transitória e não persiste nomes no URL. O período das métricas é compartilhável no URL.
Busca, totais, lojas, criação e paginação pertencem ao mesmo `StoreAccessPanel`.
Convidar pessoa abre um formulário de destinatário e cargo; gerar entrega um link para
compartilhar manualmente. O aceite solicita e-mail, nome, senha e confirmação. Convites
vinculados só aceitam o destinatário informado; links antigos abertos aceitam o e-mail
fornecido no formulário. Conta existente precisa comprovar a senha atual ou perfil OAuth
verificado; convite não redefine senha nem ignora o estado da conta. Novas senhas exigem
12 caracteres, e o servidor limita tentativas. Link usado, expirado ou loja suspensa é recusado.

## Métricas e integrações

Semana e mês correntes usam UTC−03:00. Clientes = lojas, usuários = pessoas, sem duplicar vínculos.
Consumo cobre journals de campanhas e assistências; respostas novas possuem timestamp individual.
Legado usa início da execução; ausência de data entra somente em Geral. Custos são estimativas em USD;
ausência de preço nunca vira custo conhecido igual a zero. Journals apagados não são recuperáveis.
Gráfico cobre até 30 dias e sempre tem alternativa tabular.
Validar Meta realiza leitura da conta e campanhas. Não cria anúncios nem comprova publicação.
Atualizar credenciais invalida a última validação; tokens nunca voltam pela API.

## Recuperação e acessibilidade

### Referências e tratamento de imagens

`UploadField` permite ativar o seletor por toda a área visível e pelo teclado;
o botão Remover tem ação independente. Arrastar arquivos mantém a validação PNG/JPEG de 8 MB.
`ReferenceEditor` usa os endpoints autenticados `/api/references/editor-options` e
`/api/references/edit`, com escopo da loja atual. Cada edição salva uma nova referência
e preserva o original; falhas mantêm a seleção e os parâmetros. Recorte usa pixels
da imagem; nitidez/ampliação locais não prometem reconstrução de detalhes. Remover
fundo local destina-se a fundos uniformes e conserva transparência em PNG.
Qwen só é habilitado com endpoint configurado no servidor; configuração não prova
conectividade. Resultado generativo requer revisão e não garante transparência.

Criar campanha apresenta o modelo no topo, briefing como conteúdo principal e formato
e geração de arte ao lado (empilhados no celular). Assistência e campanha compartilham
estado de ocupação do servidor; ações de envio ficam bloqueadas enquanto ocupado.

Erro de métricas tem nova tentativa; erro de formulário é exibido dentro do modal.
Modal prende foco nativamente, fecha com Escape fora do processamento e restaura o gatilho.
Menu usa setas/Home/End/Escape, fecha ao sair e aparece fora de contêineres com overflow.
Foco visível, layout estreito, scrollbars operáveis, movimento reduzido e campos com labels são obrigatórios.

## Navegação e fontes visuais

URLs canônicas seguem a hierarquia: `/studio/library/references`, `/studio/meta-ads/consultations` e `/studio/settings/{account,security,store,brand-kit}`. Endereços antigos redirecionam com os parâmetros preservados. Clicar no módulo pai abre seus filhos; a flecha recolhe/expande sem navegar. Breadcrumbs usam o mesmo mapa das rotas.

Produto e referência têm fontes independentes (biblioteca/arquivo/nenhuma), sem override invisível. Apenas a fonte ativa é enviada. Upload de produto para uso pontual e salvar no Brand Kit são ações explícitas. O atalho para enviar produto fica sempre disponível na Biblioteca. Tooltips e seletores com busca são compartilhados e operáveis por teclado.

Seletores de imagens mostram miniatura e nome na lista e na escolha atual. Apagar em
Biblioteca ou Referências pede confirmação com a imagem, preserva o item em caso de
falha e move arquivo/metadados para `.trash/library` da loja. Fotos de produto e
referências já copiadas para campanhas permanecem; apagar uma arte gerada também
a remove da campanha de origem. A operação respeita sessão, CSRF, módulo e ocupação.
