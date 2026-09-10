# Validação da reorganização

Verificação local em 10/09/2026.

- Base anterior: 72 testes passando.
- Estrutura reorganizada: 83 testes passando, incluindo contratos, direção das dependências, ausência de acesso direto a arquivos na aplicação e ciclo de execução.
- Frontend: build concluído; arquivos JavaScript e CSS têm os mesmos SHA-256 do build anterior.
- Dados reais: comparação somente de leitura entre os adaptadores anterior e novo, com resultados idênticos para 10 campanhas e 32 mídias, incluindo IDs e URLs.
- Pacote Python: instalação editável atualizada para `apps/backend`; entrada `python -m realcenter_marketing` verificada.
- Docker: imagem `realcenter-studio:architecture-review` construída; configuração Compose validada.
- Teste completo local e no container com rede desabilitada: frontend e assets, API, campanha demo com os quatro agentes, persistência, briefing salvo, download e catálogo Graphify.

Nenhuma chamada paga de modelo foi necessária. A qualidade de respostas live e disponibilidade das credenciais não foram reavaliadas; prompts e comportamento editorial foram preservados. A versão de prompt agora é identificada por hash nos eventos.

O teste Docker usou dados temporários sintéticos e não substituiu o serviço em execução do usuário. A migração física de campanhas e Brand Kit permanece separada. A implementação atual aceita um processo escritor por diretório de dados e uma execução por vez.

O repositório Git foi consolidado na raiz, preservando sua configuração. O repositório original ainda não possuía commit; alterações estão locais, sem commit ou push. Código anterior e artefatos de verificação estão em `.architecture-work/`, ignorados pelo Git e pelo Docker.
