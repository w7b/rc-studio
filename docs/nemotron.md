# Testar Nemotron 3 Ultra

O seletor de modelo da equipe inclui **Nemotron 3 Ultra · NVIDIA**, pela API
remota da NVIDIA. A integração é experimental: os testes automatizados validam
o contrato HTTP e a orquestração com respostas simuladas; qualidade, disponibilidade e
saída estruturada no endpoint precisam de validação real.

## Preparação

1. Configure a chave NVIDIA nas configurações de modelos da aplicação, ou defina
   `NVIDIA_API_KEY` no ambiente do backend (`data/platform/.env` em uma
   instalação local). Não coloque a chave no frontend.
2. Reinicie o backend após atualizar o código e recarregue a página.
3. No briefing, selecione **Nemotron 3 Ultra · NVIDIA** como modelo da equipe.
4. Para o primeiro teste, desative a geração de imagens. A execução textual
   precisa apenas da chave NVIDIA; as imagens usam seu próprio modelo e chave.

O modelo usa `nvidia/nemotron-3-ultra-550b-a55b` em
`https://integrate.api.nvidia.com/v1/chat/completions`. O identificador interno é
`nvidia:nvidia/nemotron-3-ultra-550b-a55b`: o primeiro prefixo identifica o
provedor e o segundo faz parte do nome oficial do modelo.

O modelo padrão continua sendo o configurado anteriormente. A assistência
“Melhorar briefing” respeita o modelo selecionado no formulário, assim como a
execução da equipe. Com Nemotron selecionado, a consulta usa a API NVIDIA e
não exige chave OpenAI. Na demonstração, a assistência paga fica desabilitada.

## Primeira campanha

Use um briefing sintético, por exemplo:

> Crie uma campanha institucional de fim de semana em português brasileiro,
> com uma legenda para o feed e uma sequência de Stories. Não há preços,
> descontos, estoque ou prazos promocionais confirmados. Convide o público
> a conhecer a loja sem inventar ofertas.

Confira no acompanhamento e nas entregas:

- Social Media, Copywriter e Creative foram consultados nessa ordem;
- o Director concluiu a revisão e a campanha aparece como concluída;
- todas as entregas estruturadas estão presentes;
- os textos não inventam preços, descontos ou fatos comerciais;
- português, aderência à marca, duração e consumo são aceitáveis.

Se o endpoint rejeitar `response_format` ou produzir saída inválida, preserve o
diagnóstico. O runtime coordena cinco chamadas sequenciais (planejamento, três
especialistas e revisão), sem exigir tool calling do modelo. O teste offline não
demonstra suporte ou qualidade da saída estruturada no serviço real. Não há troca automática de provedor
nem alteração nas restrições já registradas para o Kimi K3.

## Verificação offline

Com as dependências de desenvolvimento do backend instaladas:

```powershell
python -m pytest apps/backend/tests/test_nemotron.py apps/backend/tests/test_model_catalog.py apps/backend/tests/test_migration_contracts.py
```

O teste de transporte usa o SDK real, intercepta HTTP e simula as cinco respostas
da equipe. Não envia briefings, não usa credenciais reais e não consome API.

Referências: [modelo](https://build.nvidia.com/nvidia/nemotron-3-ultra-550b-a55b/modelcard)
e [API](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-ultra-550b-a55b-infer).
