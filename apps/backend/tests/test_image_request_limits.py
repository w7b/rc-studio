import asyncio
import json
from types import SimpleNamespace

import pytest
from openai import BadRequestError

from realcenter_marketing.application.diagnostics import error_details
from realcenter_marketing.application.errors import ImageRequestLimitError, public_error
from realcenter_marketing.bootstrap.campaigns import create_campaign
from realcenter_marketing.domain.campaigns import CampaignBrief
from realcenter_marketing.infrastructure.image_generation import generate_feed
from realcenter_marketing.infrastructure.image_prompt import fit_image_prompt


def test_small_prompt_keeps_complete_brand():
    brand = {'brand.md': '# Marca\n\nDireção.', 'colors.md': '# Cores\n\nAzul.'}
    prompt, compacted = fit_image_prompt('Fatos exatos.', brand, ['Logo'])
    assert not compacted
    assert '\n'.join(brand.values()) in prompt
    assert prompt.startswith('Fatos exatos.')
    assert json.loads(prompt.split('Imagens de entrada, em ordem: ')[1]) == ['Logo']


def test_large_brand_keeps_all_guides_facts_revision_and_whole_paragraphs():
    brand = {name: f'# {name}\n\nRegra essencial {name}.\n\n' + '\n\n'.join(
        f'Parágrafo {i}: ' + 'exemplo ' * 100 + 'FIM.' for i in range(40))
        for name in ('brand', 'colors', 'typography', 'visual')}
    fixed = 'Produto exato, preço R$ 1,89. REVISÃO: preservar o rótulo.'
    prompt, compacted = fit_image_prompt(fixed, brand, ['Imagem base', 'Produto', 'Logo'])
    assert compacted and len(prompt) <= 32_000
    assert prompt.startswith(fixed)
    assert all(f'Regra essencial {name}.' in prompt for name in brand)
    brand_text = prompt.split('\nImagens de entrada, em ordem: ')[0]
    assert all(block.endswith('FIM.') for block in brand_text.split('\n\n') if block.startswith('Parágrafo'))
    assert json.loads(prompt.split('Imagens de entrada, em ordem: ')[1]) == ['Imagem base', 'Produto', 'Logo']


def test_essential_prompt_over_limit_is_not_truncated():
    with pytest.raises(ImageRequestLimitError) as caught:
        fit_image_prompt('fato ' * 7_000, {'brand': 'Preservar logo.'}, [])
    assert caught.value.param == 'prompt'
    assert 'instruções essenciais' in public_error(caught.value)


def test_exact_character_boundary_and_empty_brand():
    overhead = len(fit_image_prompt('', {}, [])[0])
    assert len(fit_image_prompt('x' * (32_000 - overhead), {}, [])[0]) == 32_000
    with pytest.raises(ImageRequestLimitError):
        fit_image_prompt('x' * (32_001 - overhead), {}, [])


def test_adapter_sends_bounded_request_and_saves_diagnostics(settings, demo, tmp_path):
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Campanha'), settings, model=demo))
    (settings.project_root / 'brand/visual-guidelines.md').write_text(
        '# Diretrizes\n\nPreservar produto.\n\n' + '\n\n'.join('Exemplo. ' * 200 for _ in range(40)), encoding='utf-8')
    captured = {}
    class Captured(Exception):
        pass
    def edit(**kwargs):
        captured.update(kwargs)
        raise Captured()
    with pytest.raises(Captured):
        generate_feed(campaign, settings, tmp_path, client=SimpleNamespace(images=SimpleNamespace(edit=edit)),
                      changes='Manter título e trocar o fundo.', base_image=settings.project_root / 'brand/references/fixture.png')
    assert len(captured['prompt']) <= 32_000
    assert campaign.copywriting.headline in captured['prompt']
    assert campaign.creative.visual_direction in captured['prompt']
    assert 'Manter título e trocar o fundo.' in captured['prompt']
    metadata = json.loads((tmp_path / 'image-request.json').read_text())
    assert metadata['brand_compacted'] is True
    assert metadata['prompt_characters'] == len(captured['prompt'])


def test_excess_references_rejected_before_provider_call(settings, demo, tmp_path):
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Campanha'), settings, model=demo))
    directory = settings.project_root / 'brand/references'
    for i in range(16):
        (directory / f'extra-{i}.png').write_bytes((directory / 'fixture.png').read_bytes())
    # Only declared references are attached, so the extras join the same family.
    declared = {'fixture.png': 'produto', **{f'extra-{i}.png': 'produto' for i in range(16)}}
    (directory / 'families.json').write_text(json.dumps({'files': declared}), encoding='utf-8')
    with pytest.raises(ImageRequestLimitError) as caught:
        generate_feed(campaign, settings, tmp_path, client=SimpleNamespace())
    assert error_details(caught.value)['request_limit'] == {'param': 'image', 'actual': 17, 'limit': 16}


@pytest.mark.parametrize('nested', [False, True])
def test_provider_diagnostics_keep_identifiers_without_private_payload(nested):
    body = {'param': 'prompt', 'code': 'string_above_max_length', 'type': 'invalid_request_error',
            'message': 'private prompt sk-secret', 'input': 'private customer data'}
    exc = BadRequestError('private error', response=SimpleNamespace(status_code=400, request=SimpleNamespace(), headers={}),
                          body={'error': body} if nested else body)
    details = error_details(exc)
    assert details['provider_error'] == {key: body[key] for key in ('param', 'code', 'type')}
    assert 'private' not in json.dumps(details) and 'sk-secret' not in json.dumps(details)
    body['param'], body['code'] = 'private_prompt', 'sk-secret'
    assert error_details(exc)['provider_error'] == {'type': 'invalid_request_error'}
