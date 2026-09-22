"""The product must stop assuming a supermarket.

These are correctness tests, not cosmetics. Before them, the Copywriter of every store was
instructed to write a specific street address in Paranavaí and a specific set of brand
hashtags, and every campaign was forced to produce a leaflet. A pet shop would have
published a supermarket's address.
"""
import json

import pytest

from realcenter_marketing.domain.campaigns import AssetBrief, CreativeBrief
from realcenter_marketing.domain.tenant import DEFAULT_CLAIM_PACK, TenantProfile
from realcenter_marketing.infrastructure.resources import (
    load_claims, load_instructions, load_policy, load_profile, render,
)


def write_profile(root, **fields):
    (root / 'tenant.json').write_text(json.dumps(fields), encoding='utf-8')
    return load_profile(root)


def asset(fmt):
    return AssetBrief(format=fmt, dimensions='1080x1080', layout='Layout', hierarchy=['Topo'])


def test_no_store_inherits_the_original_brand(root):
    """The most important assertion in the file: a different store must never see the
    first store's name, address or hashtags."""
    write_profile(root, brand_name='Petshop Amigo', segment='petshop', city='Paranavaí - PR',
                  cta_hint='convide a conhecer a loja', hashtags=['#PetshopAmigo'],
                  claim_pack='varejo_geral', deliverables=['stories', 'feed'])
    text = load_policy(root) + load_instructions(root, 'copywriter') + load_instructions(root, 'creative')
    assert 'Real Center' not in text
    assert 'Minas Gerais' not in text
    assert 'RealCenter' not in text
    assert 'Petshop Amigo' in text


def test_a_missing_address_removes_the_instruction_instead_of_blanking_it(root):
    """A line reading 'include the address:' with nothing after it is an invitation to
    invent one, which agent-policy.md explicitly forbids."""
    write_profile(root, brand_name='Barbearia Central', segment='barbearia', claim_pack='servico')
    instructions = load_instructions(root, 'copywriter')
    assert '📍' not in instructions
    assert 'endereço confirmado' not in instructions
    # Placeholders must never survive into the prompt.
    assert '{{' not in instructions


def test_hashtags_and_cta_follow_the_store(root):
    write_profile(root, brand_name='Ótica Visão', segment='ótica', hashtags=['#OticaVisao', '#Paranavai'],
                  cta_hint='convide a agendar um exame de vista')
    instructions = load_instructions(root, 'copywriter')
    assert '#OticaVisao #Paranavai' in instructions
    assert 'agendar um exame de vista' in instructions


def test_a_pharmacy_gets_health_guardrails_not_food_ones(root):
    """Food rules are the wrong rules for a pharmacy: the regulated claims are different
    and stricter, and inheriting the grocery pack would be worse than having none."""
    write_profile(root, brand_name='Farmácia Bem Estar', segment='farmácia', claim_pack='saude')
    policy = load_policy(root)
    assert 'cura' in policy and 'prescrição' in policy
    assert 'sem açúcar' not in policy

    write_profile(root, brand_name='Mercado Central', segment='supermercado', claim_pack='alimento')
    grocery = load_policy(root)
    assert 'sem açúcar' in grocery
    assert 'prescrição' not in grocery


def test_every_declared_claim_pack_exists():
    from realcenter_marketing.domain.tenant import CLAIM_PACKS
    for pack in CLAIM_PACKS:
        assert load_claims(pack), pack


def test_an_unknown_claim_pack_falls_back_to_the_strictest_generic(root):
    profile = write_profile(root, brand_name='Loja Nova', claim_pack='inventado')
    assert profile.pack == DEFAULT_CLAIM_PACK
    assert load_claims(profile.pack)


def test_leaflet_is_required_only_where_the_store_publishes_one():
    common = dict(visual_direction='Direção', brand_pending=[])
    without = CreativeBrief.model_validate(
        {**common, 'assets': [asset('stories').model_dump(), asset('feed').model_dump()]})
    assert without.leaflet_brief is None

    with pytest.raises(ValueError, match='leaflet'):
        CreativeBrief.model_validate(
            {**common, 'assets': [asset('stories').model_dump(), asset('feed').model_dump()]},
            context={'deliverables': ['stories', 'feed', 'leaflet']})


def test_a_store_without_tenant_json_gets_an_empty_profile_not_a_neighbours(root):
    profile = load_profile(root)
    assert profile.brand_name == ''
    assert not profile.complete
    assert profile.deliverables == ['stories', 'feed']
    # It still renders: the prompts simply stop asserting things nobody confirmed.
    assert '{{' not in load_instructions(root, 'copywriter')


def test_profile_values_cannot_inject_new_placeholders(root):
    """A store edits its own tenant.json, so its values are input, not template."""
    write_profile(root, brand_name='{{address}}', address='Rua Verdadeira, 1')
    rendered = render('Loja: {{brand_name}}', load_profile(root))
    assert rendered == 'Loja: {{address}}'
    assert 'Rua Verdadeira' not in rendered


def test_the_image_prompt_describes_the_store_trade(root):
    from realcenter_marketing.infrastructure.image_prompt import compact_image_prompt
    from realcenter_marketing.domain.publications import Publication
    profile = write_profile(root, brand_name='Auto Peças Norte', segment='autopeças')
    prompt, _ = compact_image_prompt('Headline', 'CTA', 'Direção', Publication(kind='feed'),
                                     {}, 1500, profile.described)
    assert 'autopeças Auto Peças Norte' in prompt
    assert 'supermercado' not in prompt


def test_up_to_three_categories_combine_rules_and_persist(root):
    from realcenter_marketing.infrastructure.tenant_profile import save, options
    assert len(options()['categories']) == 56
    selected = ['Padaria', 'Farmácia', 'Serviços locais']
    saved = save(root, {'categories': selected})
    assert saved.categories == selected
    assert load_profile(root).categories == selected
    policy = load_policy(root)
    for pack in ('alimento', 'saude', 'servico'):
        assert load_claims(pack) in policy
    assert saved.placeholders()['segment'] == ', '.join(selected)


@pytest.mark.parametrize('selected', [['Padaria'] * 2, ['Inventada'], 'Padaria',
                                    ['Padaria', 'Farmácia', 'Petshop', 'Ótica']])
def test_invalid_categories_do_not_replace_the_saved_profile(root, selected):
    from realcenter_marketing.infrastructure.tenant_profile import save
    save(root, {'brand_name': 'Loja intacta', 'categories': ['Farmácia']})
    with pytest.raises(ValueError):
        save(root, {'brand_name': 'Não salvar', 'categories': selected})
    assert load_profile(root).brand_name == 'Loja intacta'
    assert load_profile(root).categories == ['Farmácia']


def test_editing_legacy_profile_preserves_its_existing_rules(root):
    from realcenter_marketing.infrastructure.tenant_profile import save
    write_profile(root, claim_pack='saude')
    saved = save(root, {'brand_name': 'Farmácia', 'categories': []})
    assert saved.pack == 'saude'
