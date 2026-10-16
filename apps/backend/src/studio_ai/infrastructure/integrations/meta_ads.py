"""Read-only Meta connection diagnostics. Ad publishing remains unavailable."""
import json
import re
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class MetaAdsAdapter:
    async def _pending(self, *args, **kwargs):
        raise NotImplementedError('Publicação no Meta Ads ainda não está disponível')

    account = campaigns = insights = create_draft = _pending


def graph_get(version, path, token, params):
    # Fixed destination and no redirects: bearer credentials never leave graph.facebook.com.
    request = Request(f'https://graph.facebook.com/{version}/{path}?{urlencode(params)}',
                      headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'})
    with build_opener(NoRedirect()).open(request, timeout=15) as response:
        return json.loads(response.read(1_000_000))


def validate_connection(settings, get=graph_get):
    result = {'checked_at': datetime.now(timezone.utc).isoformat(), 'publishing_available': False}
    def finish(status, message, **extra):
        return {**result, 'status': status, 'message': message, **extra}
    if not settings.get('enabled'):
        return finish('disabled', 'A conexão está desativada nas configurações da loja.')
    account = str(settings.get('ad_account_id', '')).removeprefix('act_')
    version, token = settings.get('api_version', ''), settings.get('access_token', '')
    if not re.fullmatch(r'\d+', account) or not re.fullmatch(r'v\d+\.\d+', version) or not token:
        return finish('incomplete', 'Informe uma conta válida, a versão da API e o token de acesso.')
    try:
        data = get(version, f'act_{account}', token, {'fields': 'id,name,account_status,currency'})
        campaigns = get(version, f'act_{account}/campaigns', token, {'fields': 'id', 'limit': 1})
        if not isinstance(data, dict) or data.get('id') != f'act_{account}' or not isinstance(campaigns, dict) or not isinstance(campaigns.get('data'), list):
            return finish('error', 'A Meta não retornou a conta solicitada ou o acesso às campanhas.')
        active = data.get('account_status') == 1
        return finish('connected' if active else 'restricted',
                      'Conta e leitura de campanhas validadas. Publicação ainda indisponível.' if active
                      else 'A leitura funciona, mas a conta de anúncios está restrita ou inativa.',
                      account={'id': data['id'], 'name': str(data.get('name', ''))[:200],
                               'currency': str(data.get('currency', ''))[:10],
                               'account_status': data.get('account_status')}, can_read_campaigns=True)
    except HTTPError as error:
        # Never return raw provider responses: they may echo tokens or request details.
        try:
            code = json.loads(error.read(16000)).get('error', {}).get('code')
        except (ValueError, AttributeError):
            code = None
        message = ('Token expirado ou inválido. Atualize o token e valide novamente.' if code == 190
                   else 'Acesso recusado. Confira a conta e as permissões ads_read ou ads_management.'
                   if code in (10, 200, 294) else 'A Meta recusou a consulta. Confira a versão da API, a conta e tente novamente.')
        return finish('error', message, error_code=code if isinstance(code, int) else None)
    except (OSError, ValueError, TypeError, KeyError):
        return finish('error', 'Não foi possível consultar a Meta. Tente novamente em instantes.')
