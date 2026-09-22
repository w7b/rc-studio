"""Validate actual frontend serialization against Pydantic, never a copied field list."""
import json
from pathlib import Path
import re
import subprocess

from realcenter_marketing.application.commands import RunRequest


REPO = Path(__file__).resolve().parents[3]


def test_campaign_form_payloads_match_run_request():
    form = (REPO / 'apps/frontend/src/features/campaigns/CampaignForm.jsx').read_text(encoding='utf-8')
    # Keep the tested serializer at the submission boundary. Wrapping it in another
    # object would allow an untested extra key to escape this contract.
    assert len(re.findall(r'await onSubmit\(', form)) == 1
    assert re.search(r'await onSubmit\(\s*buildRunRequest\(\{[\s\S]*?\}\)\s*\);', form)
    completed = subprocess.run(['node', 'apps/frontend/tests/campaign-payloads.js'],
                               cwd=REPO, capture_output=True, text=True, check=True)
    payloads = json.loads(completed.stdout)
    assert len(payloads) == 16
    fields = RunRequest.model_fields
    required = {key for key, field in fields.items() if field.is_required()}
    for payload in payloads:
        assert set(payload) <= fields.keys(), f'Frontend sent unknown fields: {set(payload) - fields.keys()}'
        assert required <= payload.keys()
        validated = RunRequest.model_validate(payload)
        assert validated.confirmed_facts == ['Confirmado', 'Outro fato']
        if validated.mode == 'demo':
            assert not validated.generate_image
            assert validated.model_id is None and validated.image_model_id is None
        if validated.upload:
            assert validated.product_id is None
        if validated.reference_upload:
            assert validated.reference_id is None
