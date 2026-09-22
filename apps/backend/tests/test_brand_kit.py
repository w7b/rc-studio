"""A new store has to be usable the moment it is created.

Before this, creating a store wrote tenant.json and nothing else. The first campaign then
died inside load_brand with "Brand Kit ausente" — after the owner had filled in the whole
form. Campaign run-c7905ba06c6f408abf8495dffaee3f26 is exactly that failure.
"""
import pytest

from realcenter_marketing.domain.tenant import TenantProfile
from realcenter_marketing.infrastructure import brand_kit
from realcenter_marketing.infrastructure.resources import load_brand


def profile(**fields):
    return TenantProfile(**{'brand_name': 'Petshop Amigo', 'segment': 'petshop',
                            'city': 'Paranavaí - PR', **fields})


def test_a_seeded_store_can_immediately_load_its_brand(tmp_path):
    """The assertion that matters: load_brand no longer raises."""
    with pytest.raises(ValueError, match='Brand Kit ausente'):
        load_brand(tmp_path, 'copywriter')

    created = brand_kit.seed(tmp_path, profile())
    assert set(created) == set(brand_kit.FILES)
    assert load_brand(tmp_path, 'copywriter')
    assert load_brand(tmp_path, 'creative')


def test_the_base_carries_the_store_identity_not_another_store(tmp_path):
    """Copying Real Center's kit would hand every new shop its colours, its supermarket
    art direction and its language — the problem the per-segment work removed."""
    brand_kit.seed(tmp_path, profile(address='Rua Exemplo, 100', instagram='@petshopamigo'))
    text = '\n'.join((tmp_path / 'brand' / name).read_text(encoding='utf-8')
                     for name in brand_kit.FILES)
    assert 'Petshop Amigo' in text
    assert 'petshop' in text
    assert 'Rua Exemplo, 100' in text
    assert 'Real Center' not in text
    assert 'Minas Gerais' not in text
    # Placeholders must never survive into a file the owner will read and edit.
    assert '{{' not in text


def test_an_empty_field_removes_its_line_instead_of_leaving_a_gap(tmp_path):
    """A line reading "Endereço aprovado:" with nothing after it invites the model to
    invent one, which agent-policy.md forbids."""
    brand_kit.seed(tmp_path, TenantProfile(brand_name='Loja Nova'))
    identity = (tmp_path / 'brand' / 'brand.md').read_text(encoding='utf-8')
    assert 'Loja Nova' in identity
    assert 'Endereço aprovado' not in identity
    assert 'Instagram:' not in identity


def test_seeding_never_overwrites_edited_text_unless_asked(tmp_path):
    brand_kit.seed(tmp_path, profile())
    edited = (tmp_path / 'brand' / 'tone-of-voice.md')
    edited.write_text('# Tom de voz\n\nEscrito à mão pelo dono.', encoding='utf-8')

    assert brand_kit.seed(tmp_path, profile()) == []
    assert 'Escrito à mão' in edited.read_text(encoding='utf-8')

    # Only an explicit restore replaces it.
    assert set(brand_kit.seed(tmp_path, profile(), overwrite=True)) == set(brand_kit.FILES)
    assert 'Escrito à mão' not in edited.read_text(encoding='utf-8')


def test_reading_reports_what_is_missing(tmp_path):
    empty = brand_kit.read(tmp_path)
    assert empty['complete'] is False
    assert all(entry['exists'] is False for entry in empty['files'])
    assert [entry['name'] for entry in empty['files']] == list(brand_kit.FILES)

    brand_kit.seed(tmp_path, profile())
    filled = brand_kit.read(tmp_path)
    assert filled['complete'] is True
    assert all(entry['content'].strip() for entry in filled['files'])


def test_extra_files_are_listed_because_the_agents_still_read_them(tmp_path):
    brand_kit.seed(tmp_path, profile())
    (tmp_path / 'brand' / 'promocoes.md').write_text('# Regras de promoção', encoding='utf-8')
    # READMEs and the checklist are excluded from prompts, so they are not listed either.
    (tmp_path / 'brand' / 'README.md').write_text('# Pasta', encoding='utf-8')
    extras = brand_kit.read(tmp_path)['extras']
    assert extras == ['promocoes.md']


def test_writing_refuses_an_unknown_file_or_empty_content(tmp_path):
    brand_kit.seed(tmp_path, profile())
    with pytest.raises(ValueError, match='desconhecido'):
        brand_kit.write(tmp_path, '../../escape.md', 'conteúdo')
    with pytest.raises(ValueError, match='vazio'):
        brand_kit.write(tmp_path, 'colors.md', '   ')
    # The refused writes left the kit intact.
    assert brand_kit.read(tmp_path)['complete'] is True


def test_writing_replaces_one_file_and_keeps_the_rest(tmp_path):
    brand_kit.seed(tmp_path, profile())
    state = brand_kit.write(tmp_path, 'colors.md', '# Cores\n\nRoxo e branco.')
    assert state['complete'] is True
    assert (tmp_path / 'brand' / 'colors.md').read_text(encoding='utf-8').endswith('Roxo e branco.')
    assert 'Petshop Amigo' in (tmp_path / 'brand' / 'brand.md').read_text(encoding='utf-8')
