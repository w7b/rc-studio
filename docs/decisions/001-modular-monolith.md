# ADR 001 — Monólito modular com fronteiras explícitas

Status: aprovado pelo usuário.

O crescimento de campanhas, agentes, imagens e referências concentrou orquestração e persistência no serviço web. A decisão é separar regras, casos de uso e adaptadores e manter um único backend implantável.

A reorganização preserva React, SDK, rotas, formatos de dados e a persistência em arquivos. As pastas seguem responsabilidades existentes e crescem quando recebem conteúdo. Interfaces ficam próximas do caso de uso consumidor. Não há adoção de microserviços, banco de dados ou framework HTTP nesta mudança.

Consequências: módulos Python têm novos caminhos; automações que importavam módulos internos precisam atualizar imports. CLI pública, modo demo e API permanecem disponíveis. A estrutura de armazenamento antiga permanece configurável, pois IDs de mídia dependem de caminhos relativos. Migração física de dados exige uma etapa própria com compatibilidade de identidade e reversão.
