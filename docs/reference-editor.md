# Tratamento de imagens nas referências

A seção **Recortar e melhorar** trabalha sobre uma referência já importada. Cada
resultado é salvo na biblioteca sem sobrescrever a imagem original. Produtos
continuam disponíveis no Brand Kit e podem ser usados na criação da campanha.

- **Enquadramento:** recorte por coordenadas em pixels, sem geração de conteúdo.
- **Fundo uniforme:** remoção local do fundo conectado às bordas, com tolerância
  ajustável. O PNG mantém transparência. Revise bordas e produtos de cor parecida
  com o fundo; esta opção não é segmentação por inteligência artificial.
- **Qualidade:** ajuste de nitidez e ampliação opcional de 2×. A ampliação local
  interpola pixels; não recupera detalhes que não existem no original.
- **Qwen-Image-Edit:** edição por instrução usando um servidor NVIDIA NIM
  configurado pelo administrador. A saída generativa pode modificar rótulos,
  detalhes do produto e textos; confira antes de usar na campanha. O modelo
  não garante canal alfa transparente.

## Conectar o Qwen

A documentação da NVIDIA disponibiliza o modelo para hospedagem própria.
Uma chave da API de modelos de texto não basta para ativar este endpoint.
O Studio não instala ou executa os pesos do Qwen na máquina local.

No arquivo de configuração `data/platform/.env`, configure:

```dotenv
QWEN_IMAGE_EDIT_URL=http://endereco-do-servidor:8000/v1/infer
# Opcional, somente se seu servidor exigir autenticação:
QWEN_IMAGE_EDIT_API_KEY=
```

O endereço deve apontar para o servidor de inferência, acessível **a partir do
container do Studio**. Para um serviço no host do Docker Desktop, use
`host.docker.internal` em vez de `localhost`. Para outra máquina da casa, use o
endereço dela na rede. Recrie o serviço após alterar variáveis:

```powershell
docker compose up -d --no-deps --force-recreate studio
```

O protocolo é `POST /v1/infer` com `prompt`, `image` em data URL e `seed`;
a imagem é lida de `artifacts[0].base64`. A chave fica no servidor. A configuração
não confirma saúde ou compatibilidade do serviço; uma chamada real valida isso.
Sem endereço configurado, as ferramentas locais funcionam e a edição Qwen
permanece indisponível na interface.

Referências oficiais: [NVIDIA NIM: Qwen-Image-Edit](https://docs.nvidia.com/nim/visual-genai/latest/getting-started.html)
e [implantação do modelo](https://build.nvidia.com/qwen/qwen-image-edit/deploy).
