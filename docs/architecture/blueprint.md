# Arquitetura aprovada — Real Center Studio

Monólito modular com Clean Architecture. Frontend React e backend Python permanecem no mesmo produto e no mesmo container de produção. O SDK atual e os contratos HTTP foram preservados.

## Estrutura implementada

```text
apps/
  backend/
    pyproject.toml
    src/realcenter_marketing/
      domain/                 modelos e invariantes
      application/
        campaigns/            serviço de comandos, composição e interfaces
        commands.py           entradas dos casos de uso
        orchestration.py      política de delegação
        images.py             geração em lote e retomada de cards
        queries.py            interface de consultas
        diagnostics.py        relatórios sem informações sensíveis
      infrastructure/
        agents_sdk/           montagem, runtime, hooks, correção e demonstração
        persistence/          implementação em arquivos
        integrations/         contratos e adaptadores ainda inativos
        resources.py          manifestos, instruções e aliases
        execution.py          execução local e fechamento
        process_lease.py      exclusão entre processos
        image_generation.py   integração de imagens
        references.py         importação e biblioteca de referências
        system_catalog.py     catálogo Graphify
      presentation/
        http/                 API e arquivos estáticos
        cli.py                entrada de linha de comando
      bootstrap/              configuração e composição das dependências
    tests/
  frontend/
    src/
      app/
      features/               campanhas, briefing, referências, revisões e sistema
      shared/                 cliente HTTP, componentes e estilos compartilhados
resources/
  agents/                     manifestos e prompts versionados
  policies/
  demo/
docs/
scripts/
```

Pastas têm conteúdo efetivo; não foram criadas estruturas vazias para funcionalidades futuras. O pacote Python mantém `realcenter_marketing`. Os módulos importáveis mudaram; HTTP e identificadores persistidos não mudaram.

## Dependências

- `domain` não importa aplicação, adaptadores, HTTP ou SDK.
- `application` depende de domínio e interfaces, sem acesso direto a arquivos, threads ou SDK.
- `infrastructure` implementa armazenamento, execução e fornecedores.
- O adaptador HTTP depende de comandos e consultas. Sua fábrica chama `bootstrap/container.py` para montar o processo.
- `bootstrap` conecta implementações. Não há contêiner de injeção global nem estado de campanha compartilhado entre equipes.

Pydantic permanece nos modelos para preservar as validações existentes. Os contratos de entrada são compartilhados quando a semântica é idêntica; não foram criadas cópias redundantes de cada modelo.

## Agentes

A sequência de papéis tem uma fonte no domínio. A aplicação mapeia saídas e habilitação; o adaptador do SDK executa essa política. Director continua coordenando Social Media → Copywriter → Creative, seguido pela revisão e composição validada da campanha. Cada execução constrói uma equipe nova.

`creative_producer` é a pasta do papel `creative`; `performance_marketing` é a pasta do papel `performance`. IDs de manifestos, nomes de tools e arquivos históricos são preservados. Performance e Marketing Analyst continuam planejados; os adaptadores comerciais continuam desabilitados.

Os eventos `agent_config` registram o hash de manifesto, instruções e política. O conteúdo dos prompts não é acrescentado ao log. A assistência de briefing mantém uma única chamada ao Creative Producer.

## Infraestrutura e execução

Um processo escritor por diretório de dados, com um slot de execução. A API obtém um bloqueio do sistema operacional antes de iniciar. O scheduler recusa trabalho novo durante o fechamento e aguarda o trabalho aceito. A configuração não suporta múltiplas réplicas compartilhando o mesmo diretório.

Estados continuam derivados dos eventos persistidos: execução iniciada sem evento terminal aparece como `interrupted` após reinício. Não há repetição automática de chamadas pagas. A retomada manual preserva o comportamento anterior: repete somente imagens quando a campanha está consolidada; antes disso, inicia uma nova campanha preservando a antiga.

Uma fila externa, múltiplos workers e deduplicação persistente de requisições HTTP são evoluções separadas. O bloqueio atual impede execuções concorrentes; não é uma garantia de processamento exatamente uma vez.

## Dados e caminhos

Campanhas, uploads, biblioteca, custos e Brand Kit continuam em `realcenter-marketing-ai/`. A migração física para `var/` está deliberadamente separada da reorganização do código. `REALCENTER_DATA_ROOT` configura essa raiz. Nunca renomear arquivos históricos ou recalcular IDs para aplicar somente uma mudança de organização.

Os IDs de mídia ainda usam SHA-256 do caminho relativo legado. O frontend continua usando `/api/*`, `/media/*`, `X-App-Token`, a mesma validação de origem e os mesmos formatos JSON.

Prompts e políticas ficam em `resources/`; Brand Kit editável e mídia do usuário ficam fora do Git. `REALCENTER_RESOURCES_ROOT` e `REALCENTER_STATIC_ROOT` permitem implantação fora do checkout. Diretórios legados de recursos em raízes explícitas continuam aceitos para integração e testes; não devem ser mantidas duas cópias no checkout normal.

## Validação e reversão

A suíte original foi portada para os novos imports. Testes adicionais verificam dependências, ausência de I/O na aplicação, ciclo de execução, bloqueio, caminhos, contratos HTTP e identidade da mídia antiga. Testes usam marca e imagens sintéticas, sem arquivos pessoais ou credenciais.

O build React produz `apps/frontend/dist`. Docker copia esse build para o runtime Python; o SDK e Node não são expostos ao navegador. Os volumes de dados conservam seus caminhos anteriores.

A cópia local `.architecture-work/before.zip` e os diretórios em `.architecture-work/original-tree/` permitem consultar o código anterior. Esses arquivos não são versionados nem enviados ao Docker. Não houve migração de dados ou publicação automática de conteúdo.
