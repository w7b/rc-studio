# SGCloud — análise de liberação para Marketing

Data: 08/09/2026. Fonte: [API SG — Terceiros](https://api-doc.sgsistemas.com.br/), coleção pública Postman consultada diretamente. Análise documental, sem autenticação no ambiente fornecido e sem verificação das permissões dessa credencial. Nenhuma integração foi implementada nesta etapa.

O usuário confirmou que o endereço fornecido é de homologação, para testes antes da solicitação de liberação da integração na base. Não é a base de produção da Real Center. A confirmação de URL/transporte de produção é uma tarefa posterior e não bloqueia este levantamento de rotas.

Atualização de escopo: o usuário autorizou incluir na solicitação o POST de cadastro de ofertas, para uso futuro. Isso altera a lista de permissões solicitadas, mas não habilita escrita pelos agentes nesta fase. O adapter e a política de execução do MVP continuam read-only.

## Recomendação

Liberar métodos e caminhos específicos. As pastas Produtos e Ofertas contêm escrita e consultas fora do escopo. Acrescentar autenticação e identificação da filial; tabelas de apoio são opcionais. Vendas pode ser liberada numa fase posterior.

O prefixo dos exemplos do ambiente informado é `/integracao/sgsistemas/v1`. A descrição de autenticação também menciona `/public/integracao/sgsistemas/v1/autorizacao` para ambiente SG Cloud. Confirmar com o fornecedor qual prefixo vale para a instância; não inserir `/public` em todas as rotas por suposição.

## Núcleo inicial

| Método | Caminho após o prefixo | Papel | Necessidade |
|---|---|---|---|
| POST | `/autorizacao` | Obter JWT. Não altera cadastro, estoque ou oferta. | Necessário para consumir a API. |
| GET | `/produtos` | Identificação, descrição, unidade, classificação, ativo e estoqueAtual por filial. | Principal consulta de apoio. |
| GET | `/filiais` | Identificar o código de filial correto. | Recomendado; pode ser dispensado se o fornecedor entregar o código fixo confirmado. |

Autenticação: body com `usuario` e `senha`. A documentação informa JWT com duração atual de uma hora; o exemplo contém `token`, `routes` e `expire_time`. O campo `routes` do exemplo não comprova as permissões da credencial recebida. Após autenticação em conexão apropriada, verificar a lista efetivamente concedida.

Produtos: `filial` é obrigatório na descrição dos parâmetros. Há filtros `id`, `ativo` e paginação `pagina`/`itensPorPagina`. A resposta documenta `estoqueAtual`; não é necessário consumir acertos ou movimentos de estoque apenas para conhecer esse saldo. Confirmar se esse saldo corresponde ao disponível para venda, se desconta reservas e com qual frequência é atualizado. A unidade precisa acompanhar quantidades; o adapter inicial de mock usa inteiros e deve ser revisto para produtos fracionados quando ocorrer a integração real.

## Ofertas — liberação adicional para a fase promocional

| Método | Caminho após o prefixo | O que a documentação descreve |
|---|---|---|
| GET | `/ofertas` | Tipos de oferta, descrição, prioridade, tipo de regra e indicação de fidelização. Não é a lista dos produtos promovidos. |
| GET | `/ofertas/produtos` | Ofertas normais vigentes, agrupadas por oferta, com seus produtos. Filial obrigatória e filtro opcional idOferta. |
| GET | `/produtos/ofertas` | Ofertas normais vigentes, agrupadas por produto; permite idProduto. Alternativa útil para consultar um item específico. |

Para listar itens das ofertas vigentes, `/ofertas` + `/ofertas/produtos` são o conjunto de partida. `/produtos/ofertas` é opcional; não liberar as duas orientações apenas por existirem.

Ambos os endpoints de itens em oferta documentam datas, preço e restrições relacionadas a fidelização/GTIN. A documentação de `/ofertas` enumera outras modalidades, inclusive quantidade e controle por CPF/dia, mas isso não comprova que os endpoints de itens as retornem: eles se descrevem como limitados ao tipo normal vigente.

Confirmar com SG Sistemas: como consultar ofertas futuras/agendadas, encerradas e por quantidade; como interpretar elegibilidade de fidelização, GTIN, prioridade e vigência; qual fuso é usado. Esses casos importam para preparar uma campanha antes da oferta começar. Não inventar filtros nem afirmar suporte sem resposta do fornecedor.

## Limite de preços do projeto

Mantida a decisão atual: não implementar consulta de preço. Não solicitar `/produtos/precos`.

A resposta geral de `/produtos` também contém preços e custos, enquanto as respostas de itens em oferta contêm `preco`. Logo, negar somente `/produtos/precos` não impede o servidor de devolver valores monetários em outras consultas. O adapter futuro deve projetar somente os campos autorizados e não expor nem persistir esses valores para os agentes. Se a exigência for não receber preços sequer no backend, pedir projeção/omissão de campos na origem; a documentação analisada não demonstra esse recurso.

Liberar uma rota não significa habilitar a leitura de preços pela aplicação. O consumo promocional de `/ofertas/produtos` fica condicionado à definição desse recorte. Publicar ofertas completas com valores trazidos do SGCloud exigiria revisão explícita da regra atual.

## Apoios opcionais

| GET após o prefixo | Quando solicitar |
|---|---|
| `/produtos/gtins` | Relacionar código de barras/embalagem ao cadastro e ao acervo de imagens; necessário se a integração usar GTIN ou ofertas restritas a um GTIN. |
| `/marcas` | Traduzir ID de marca para descrição, quando fizer falta ao briefing. |
| `/departamentos/nivel1` | Traduzir classificação principal para categoria legível. Outros níveis só com necessidade demonstrada. |
| `/unidadesmedida` | Resolver descrição das unidades, quando o código já retornado por Produtos não bastar. |
| `/produtos/vendas` | Fase futura de seleção por giro e análise, usando quantidades por produto e período. |

Vendas exige filial e datas (`filtroDataInicial`, `filtroDataFinal`) e admite idProduto e paginação. Retorna também valores, preço médio, impostos e custos: projetar somente quantidades no adapter sem preços. Não é necessário liberar a pasta Vendas inteira, cartões ou dados financeiros. Para o MVP criativo atual, vendas é adiável.

Não encontrei campo de imagem nem rota de foto na resposta documentada de Produtos. Isso não comprova inexistência de outro serviço; confirmar com o fornecedor. Até lá, manter acervo próprio com vínculo produto/GTIN validado.

## Não solicitar

- POST e DELETE `/produtos/gtins`: alteram GTIN.
- `/produtos/precos`, custos, tributação, fornecedores, clientes, financeiro, notas, pedidos, perdas, trocas e acertos/movimentos de estoque: fora do objetivo imediato.
- Wildcards do tipo Produtos/* ou Ofertas/*.

## Escrita solicitada para fase futura

- `POST /integracao/sgsistemas/v1/ofertas/produtos`: cadastrar ofertas a partir de produtos, filiais e tipos de oferta já existentes. É o único POST de negócio necessário para esse fluxo identificado na documentação; o outro POST é o de autenticação.
- Pedir a permissão antecipadamente, mantendo a execução bloqueada na aplicação atual. Preferir permissão separável para ativação posterior em produção.
- Antes de implementar: definir aprovação, regras de valores/condições/vigência, tratamento de duplicidade e confirmar com SG como corrigir ou cancelar ofertas. Não presumir endpoints de atualização/cancelamento.
- Não há necessidade de cadastrar GTINs, clientes ou pedidos para produzir e cadastrar ofertas de produtos existentes.

## Texto para encaminhar ao fornecedor

> Precisamos de uma integração de apoio ao Marketing, inicialmente somente leitura e com cadastro de ofertas previsto para uma fase futura. Favor habilitar autenticação em POST /integracao/sgsistemas/v1/autorizacao e leitura em GET /integracao/sgsistemas/v1/produtos e GET /integracao/sgsistemas/v1/filiais, restritas às filiais autorizadas da Real Center. Se o código de filial for fixo, podem fornecê-lo para dispensar a listagem.
>
> Para a etapa de identificação das promoções, solicitamos GET /integracao/sgsistemas/v1/ofertas e GET /integracao/sgsistemas/v1/ofertas/produtos. Solicitamos também POST /integracao/sgsistemas/v1/ofertas/produtos, destinado ao futuro cadastro de ofertas pelo sistema. Essa escrita não será utilizada na fase atual. Não solicitamos cadastro/alteração de produtos ou GTINs. O projeto não fará consulta de preços neste momento: confirmem se é possível omitir campos de preço e custo das respostas gerais.
>
> Confirmem também: suporte a ofertas futuras/agendadas e por quantidade; semântica e atualização de estoqueAtual; parâmetros e limites de paginação; IDs de filial; URL HTTPS e prefixo correto para esse ambiente, pois o material cita exemplos HTTP e um prefixo /public para SG Cloud. Informem se existe serviço de imagens de produtos. Rotas de GTIN, classificação e vendas poderão ser solicitadas depois conforme necessidade.

As credenciais recebidas não constam deste documento. A documentação pública usa HTTP nos exemplos; não foi enviado usuário/senha ao endpoint para realizar esta análise. Confirmar transporte e URL de integração antes do teste autenticado.

## Referências diretas

- [Autenticação](https://api-doc.sgsistemas.com.br/#f52b7e1f-e81b-432e-af25-5dcebb3aa0a6)
- [Produtos e estoqueAtual](https://api-doc.sgsistemas.com.br/#e5f97335-1941-46de-ba8f-63f5ddc46607)
- [Tipos de oferta](https://api-doc.sgsistemas.com.br/#a4f22963-ad88-43d8-9a42-99a602caf8ab)
- [Produtos por oferta](https://api-doc.sgsistemas.com.br/#243c9d55-aeb2-44d0-b419-d40ef608cc79)
- [Ofertas por produto](https://api-doc.sgsistemas.com.br/#67f3f2df-17aa-4b28-9b68-4620bd897617)
- [GTINs](https://api-doc.sgsistemas.com.br/#39d5c464-13d1-49e4-95cc-d6082bb6275a)
- [Vendas por produto](https://api-doc.sgsistemas.com.br/#e8d34e95-bbd4-462e-86b8-3c735858018d)
