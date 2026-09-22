# Roadmap

Objetivo: atender lojas de diferentes segmentos a partir de um deploy compartilhado,
com custo mensurável, dados isolados e revisão humana das entregas. O produto não deve
presumir supermercado, preço promocional, endereço ou alegação não fornecida pela loja.

A arquitetura vigente está em [docs/architecture/blueprint.md](docs/arquitetura.md);
operação e verificação estão no [README](README.md). Este arquivo concentra pendências e
decisões aprovadas que ainda precisam de implementação, sem duplicar histórico de sessões.

## Estado entregue

- Campanhas com Director, Social Media, Copywriter e Creative; Performance e Analyst
  disponíveis em consultas separadas, com evidências fornecidas pelo usuário.
- Identidade PostgreSQL, convites, OAuth Google, cargos, isolamento por loja, módulos,
  credenciais privadas, cotas e administração de consumo.
- Fila durável integrada ao HTTP, worker separado, heartbeat e migrações SQL versionadas.
- Ambientes Dev e runtime separados; NGINX, backup de banco/arquivos/chaves e checks de CI.
- Perfil e kit base por loja, edição dos documentos de marca, biblioteca, upload de produtos,
  referências e ferramentas de edição de imagem. O assistente completo de Brand Kit abaixo
  permanece pendente.

## Próximas prioridades

| Prioridade | Trabalho | Critério de aceite |
| --- | --- | --- |
| P1 | Admissão idempotente e teto de execução entre web/workers | POSTs concorrentes não duplicam campanha; limite pago vale entre processos; recuperação por lease comprovada |
| P1 | Homologação e promoção da imagem aprovada | Mesmo runtime validado chega à produção; migrações, rollback e restauração ensaiados com dados sintéticos |
| P1 | Operação pública | Topologia HTTPS única, segredos de produção explícitos, saúde/alertas e avaliação do servidor HTTP; sem fallback silencioso para standalone |
| P2 | Brand Kit completo | Rascunho, publicação, logos e versões conforme decisões abaixo |
| P2 | Rascunhos e recuperação | Recarregar/perder sessão não apaga briefing silenciosamente; recuperação é isolada por loja e pessoa |
| P2 | Navegação, filtros e falhas | Navegação móvel utilizável; filtros da Biblioteca restaurados por URL; rede, sessão e execução pendente têm mensagens próprias |
| P2 | Medição e custo | Latência, fila, aprovação editorial e consumo por loja; custo desconhecido sinalizado; preços não estimados por analogia |
| P2 | Dados e desempenho | Retenção de runs/lixeira; catálogo paginado no servidor; polling e leitura do acervo medidos antes de otimizar |
| P3 | Evolução de UI | Logo por loja no shell, tema claro completo, consolidação das regras responsivas e títulos por rota |
| P3 | Gestão comercial | Decidir assinatura por loja em vez de cargo do vínculo; revogação individual de convite |

Antes de escalar para múltiplos nós, definir armazenamento compartilhado e coordenação
persistente de limites/locks. O número de lojas suportadas e custo de campanha dependem
de medição; projeções históricas não são garantias de capacidade ou preço.

## Brand Kit: decisões aprovadas, ainda não entregues integralmente

O cadastro já cria documentos base e existe editor. Faltam assistente, uploads de logos,
seleção múltipla, estado de publicação, versionamento e geração guiada com kit incompleto.
Dados de outra loja nunca podem preencher o kit por fallback.

### Conteúdo e publicação

Qualquer pessoa autenticada com acesso ativo (DEFAULT, PAID ou OWNER) poderá publicar
o kit da própria loja; sem cargo adicional de aprovador. Cada versão registra autor,
loja e data. O editor terá as seguintes etapas e campos obrigatórios para **Pronto**:

| Etapa | Conteúdo |
| --- | --- |
| Identidade | Nome, descrição, público, região e uma a três categorias |
| Logo e cores | Um ou mais logos válidos selecionados; cores principal, apoio e fundo |
| Tipografia | Fontes de títulos e textos; anexo somente quando houver licença |
| Voz e conteúdo | Tom, termos preferidos, exemplos aprovados, alegações e restrições |
| Referências | Exemplo aprovado e exemplo a evitar, com descrição e finalidade |
| Revisão | Pendências verificadas e confirmação explícita de publicação |

Para alegações/restrições sem conteúdo, oferecer declaração explícita **Não se aplica**,
sem preenchê-la automaticamente. Cor da interface é distinta da paleta das artes.
Limites de anexos de fontes e referências ainda precisam ser definidos; não herdar os
formatos de imagem para fontes. Prévia paga e assistência de IA não são campos obrigatórios.

Salvar incompleto mantém **Rascunho** e lista pendências. Gerar com kit incompleto deverá
ser permitido com o aviso antes e no resultado: “Brand Kit incompleto. Esta campanha é
um rascunho; revise as pendências antes de usar.” A campanha registra estado e versão.
O bloqueio atual por ausência de documentos será substituído ao implementar esse fluxo.

### Logos e arquivos

- Até **5 logos por loja**, cada um de até **8 MiB** (8 × 1024 × 1024 bytes), nos formatos
  PNG, SVG, JPG ou JPEG. Não exigir um arquivo de cada tipo.
- Selecionar um ou mais logos; ao menos um válido selecionado para publicar como Pronto.
- Validar conteúdo e tamanho no servidor; SVG precisa de sanitização ou conversão segura,
  sem scripts, eventos, referências externas ou conteúdo ativo. Não servir original inseguro.
- Enviar cada arquivo separadamente: cinco uploads em base64 excedem o limite HTTP de 23 MiB.
- Falha/cancelamento preserva uploads e seleção anteriores. Remover logo em uso preserva
  a versão referenciada por campanhas antigas. Fotos de produtos continuam separadas.

### Aceite

Testar os três cargos autorizados e rejeição de visitante/outra loja; salvar e gerar
rascunho com pendências; aceitar exatamente 8 MiB e rejeitar excesso, sexto logo,
extensão disfarçada e SVG ativo; persistir seleção múltipla; nova versão nunca altera
campanhas existentes. Primeiro entregar edição, uploads, revisão e versões. Assistência
para extrair uma proposta de kit de documentos enviados vem depois, com revisão humana.
