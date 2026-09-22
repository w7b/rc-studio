import re
import traceback
from pathlib import Path
"""Diagnostics without prompts, model output, secrets, or exception payloads."""
from pydantic import ValidationError
from realcenter_marketing.application.errors import ImageRequestLimitError

RULES = {
    'missing': 'Campo obrigatório ausente.',
    'too_short': 'Texto ou lista abaixo do tamanho mínimo exigido.',
    'too_long': 'Texto ou lista acima do tamanho máximo permitido.',
    'string_too_short': 'Texto abaixo do tamanho mínimo exigido.',
    'string_too_long': 'Texto acima do tamanho máximo permitido.',
    'string_type': 'Era esperado um texto.',
    'int_type': 'Era esperado um número inteiro.',
    'list_type': 'Era esperada uma lista.',
    'literal_error': 'Valor fora das opções permitidas.',
    'extra_forbidden': 'Campo adicional não previsto no formato.',
    'json_invalid': 'A resposta não é um JSON completo e válido.',
    'value_error': 'Uma regra de consistência da aplicação não foi atendida.',
}


def validation_details(exc):
    return [{'location': [part if isinstance(part, int) else str(part)[:80] for part in e['loc']],
             'type': e['type'], 'explanation': RULES.get(e['type'], 'Valor incompatível com o formato esperado.')}
            for e in exc.errors(include_input=False, include_context=False, include_url=False)[:30]]


def report(run_id, events, usage, outputs):
    failures = [event for event in events if event.get('event') in ('failed', 'run_failed', 'image_failed', 'validation_failed')]
    if not failures:
        return None
    last = failures[-1]
    # Ordered by position, not by timestamp: a repair that finishes inside the same clock
    # tick as the failure carries an identical ISO string, and a strict > then reported a
    # recovered run as unrecovered. The journal is append-only, so index is the truth.
    last_index = len(events) - 1 - events[::-1].index(last)
    recovered = any(event.get('event') == 'repair_completed' and event.get('agent') == last.get('agent')
                    for event in events[last_index + 1:])
    validation = next((e for e in reversed(failures) if e.get('validation_errors') and e.get('agent') == last.get('agent')), {})
    response = next((e for e in reversed(events) if e.get('event') == 'response_received' and e.get('agent') == last.get('agent')), {})
    saved = [role for role in ('social_media', 'copywriter', 'creative', 'marketing_director', 'campaign') if role in outputs]
    return {'version': 1, 'run_id': run_id, 'recovered': recovered, 'time': last.get('time'), 'agent': last.get('agent'),
            'error_type': last.get('error_type', 'UnknownError'), 'schema': validation.get('schema'),
            'validation_errors': validation.get('validation_errors', []),
            'details_available': bool(validation or last.get('stack')),
            'stack': last.get('stack', []), 'exception_chain': last.get('exception_chain', []),
            'request_id': last.get('request_id'), 'http_status': last.get('http_status'),
            'provider_error': last.get('provider_error'), 'request_limit': last.get('request_limit'),
            'response_id': response.get('response_id'), 'response_summary': response.get('summary'),
            'model': (usage or {}).get('text', {}).get('model'), 'usage': usage,
            'saved_outputs': saved, 'failure_events': failures,
            'retry_scope': 'image_only' if 'campaign' in outputs else 'full_campaign',
            'guidance': 'Confira os campos e o schema indicados antes de repetir. As entregas salvas podem ser baixadas. Uma nova chamada pode consumir mais tokens.',
            'historical_note': None if validation or last.get('stack') else 'Este log antigo não registrou detalhes suficientes para determinar a causa exata. Não é possível reconstruir a resposta rejeitada.'}

def error_details(exc):
    """Keep schema locations/types, without model inputs or exception payloads."""
    details = {"error_type": type(exc).__name__}
    details['stack'] = [{'file': Path(frame.filename).name, 'function': frame.name, 'line': frame.lineno}
                        for frame in traceback.extract_tb(exc.__traceback__)[-12:]]
    details['exception_chain'] = []
    request_id = getattr(exc, 'request_id', None)
    if isinstance(request_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,150}', request_id):
        details['request_id'] = request_id
    status = getattr(exc, 'status_code', None)
    if isinstance(status, int):
        details['http_status'] = status
    if isinstance(exc, ImageRequestLimitError):
        details['request_limit'] = {'param': exc.param, 'actual': exc.actual, 'limit': exc.limit}
    # Allow only known machine identifiers. Provider messages and arbitrary body
    # strings can echo prompts or secrets and must not be copied into diagnostics.
    body = getattr(exc, 'body', None)
    if isinstance(body, dict):
        error = body.get('error', body)
        if isinstance(error, dict):
            allowed = {
                'param': {'prompt', 'image', 'images', 'model', 'size', 'quality', 'n',
                          'output_format', 'input_fidelity', 'background', 'mask'},
                'code': {'string_above_max_length', 'string_too_long', 'invalid_value',
                         'invalid_parameter', 'invalid_image', 'invalid_image_format',
                         'invalid_image_size', 'model_not_found', 'unsupported_parameter',
                         'unsupported_value', 'context_length_exceeded', 'content_policy_violation'},
                'type': {'invalid_request_error', 'image_generation_user_error'},
            }
            identifiers = {key: value for key, values in allowed.items()
                           if isinstance(value := error.get(key), str) and value in values}
            if identifiers:
                details['provider_error'] = identifiers
    cause = exc
    seen = set()
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        details['exception_chain'].append(type(cause).__name__)
        if isinstance(cause, ValidationError):
            details["validation_errors"] = validation_details(cause)
            break
        cause = cause.__cause__ or (None if cause.__suppress_context__ else cause.__context__)
    return details
