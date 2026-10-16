class BusyError(Exception):
    pass


class ImageRequestLimitError(ValueError):
    """Locally detected image request limit; contains no user content."""

    def __init__(self, param, actual, limit):
        self.param, self.actual, self.limit = param, actual, limit
        super().__init__('Image request exceeds a provider limit')


def public_error(exc):
    if isinstance(exc, ImageRequestLimitError):
        if exc.param == 'prompt':
            return ('As instruções essenciais da imagem excedem o limite de caracteres. '
                    'Reduza o briefing ou as instruções da revisão e tente gerar somente a imagem.')
        return 'Há imagens de referência demais. Reduza as referências e tente gerar somente a imagem.'
    kind = type(exc).__name__
    return {'RateLimitError': 'A API atingiu um limite. Verifique os limites e créditos do projeto OpenAI.',
            'AuthenticationError': 'A API recusou a chave configurada no .env.',
            'PermissionDeniedError': 'A conta não tem permissão para esse recurso ou modelo.',
            'TimeoutError': 'O tempo de execução foi excedido.',
            'APITimeoutError': 'A API excedeu o tempo de resposta.',
            'ModelBehaviorError': 'Um agente retornou uma entrega fora do formato esperado.',
            'BadRequestError': 'A API recusou o pedido. Consulte o parâmetro e o código no diagnóstico; as entregas já concluídas foram preservadas.'}.get(kind, 'A execução falhou. As entregas já concluídas foram preservadas.')
