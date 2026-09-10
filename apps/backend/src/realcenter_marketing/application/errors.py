class BusyError(Exception):
    pass

def public_error(exc):
    kind = type(exc).__name__
    return {'RateLimitError': 'A API atingiu um limite. Verifique os limites e créditos do projeto OpenAI.',
            'AuthenticationError': 'A API recusou a chave configurada no .env.',
            'PermissionDeniedError': 'A conta não tem permissão para esse recurso ou modelo.',
            'TimeoutError': 'O tempo de execução foi excedido.',
            'APITimeoutError': 'A API excedeu o tempo de resposta.',
            'ModelBehaviorError': 'Um agente retornou uma entrega fora do formato esperado.',
            'BadRequestError': 'A API recusou os parâmetros. Confira o modelo configurado.'}.get(kind, 'A execução falhou. As entregas já concluídas foram preservadas.')
