import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from test_auth_http import shared, sign_in


def post(base, cookie, csrf, payload):
    return urlopen(Request(base + '/api/consultations', data=json.dumps(payload).encode(), headers={
        'Content-Type': 'application/json', 'Origin': base,
        'Cookie': cookie, 'X-App-Token': csrf}))


@pytest.mark.parametrize('role', ['OWNER', 'PAID', 'DEFAULT'])
def test_consultation_uses_session_role_and_tenant_module(shared, monkeypatch, role):
    server, base, store = shared
    tenant = store.tenant_by_slug('mercado-central')
    user = store.user_by_email('dono@loja.com.br')
    store.grant(user.id, tenant.id, role)
    cookie, csrf, _ = sign_in(base)
    seen = []

    def consult(context, request):
        seen.append((context.slug, context.binding, request.role, request.model_id))
        return {'result': 'validated'}

    monkeypatch.setattr('realcenter_marketing.bootstrap.registry.TenantContext.consult', consult)
    payload = {'role': 'performance', 'request': 'Planeje', 'model_id': 'opaque:model'}
    store.set_module(tenant.id, 'marketing', False)
    with pytest.raises(HTTPError) as refused:
        post(base, cookie, csrf, payload)
    assert refused.value.code == 403
    assert seen == []
    store.set_module(tenant.id, 'marketing', True)
    # Campaign entitlement does not control this independent module.
    store.set_module(tenant.id, 'campaigns', False)
    assert json.load(post(base, cookie, csrf, payload)) == {'result': 'validated'}
    assert seen[0][0] == tenant.slug
    assert seen[0][1][1:] == (tenant.id, role)
    assert seen[0][2:] == ('performance', 'opaque:model')


def test_consultation_requires_session_csrf_and_valid_request(shared, monkeypatch):
    _, base, _ = shared
    payload = {'role': 'marketing_analyst', 'request': 'Analise'}
    with pytest.raises(HTTPError) as anonymous:
        post(base, '', '', payload)
    assert anonymous.value.code == 401
    cookie, csrf, _ = sign_in(base)
    with pytest.raises(HTTPError) as no_csrf:
        post(base, cookie, '', payload)
    assert no_csrf.value.code == 403
    for invalid in ({'role': 'marketing_director', 'request': 'Analise'},
                    {**payload, 'request': '  '}, {**payload, 'tenant_id': 999}):
        with pytest.raises(HTTPError) as bad:
            post(base, cookie, csrf, invalid)
        assert bad.value.code == 400
