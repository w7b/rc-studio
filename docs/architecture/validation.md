# Validação

O [workflow Validate application](../../.github/workflows/tests.yml) é o ponto central
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

## Verificação local sob demanda

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

## Revisão manual da interface

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
