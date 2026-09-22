"""Measure whether a model can actually run the campaign pipeline.

This studio twice registered a model on the strength of its documentation and twice
shipped a dropdown entry that could not finish a campaign. The Hugging Face gateway
makes that risk worse, not better: it is a proxy over many inference providers, and the
same model id behaves differently depending on which one serves it. So a model earns its
place here by running the real pipeline against the real endpoint, one stage at a time,
and the output says exactly which stage failed.

    HF_TOKEN=... python scripts/probe_model.py --id huggingface:Qwen/Qwen3.8-27B:novita

Costs one campaign's worth of tokens. Nothing is written to any store.
"""
import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/backend/src'))

from realcenter_marketing.bootstrap.paths import AppPaths  # noqa: E402
from realcenter_marketing.bootstrap.model_catalog import resolve_text, text_models  # noqa: E402
from realcenter_marketing.bootstrap.settings import Settings  # noqa: E402
from realcenter_marketing.domain.campaigns import CampaignBrief  # noqa: E402
from realcenter_marketing.infrastructure.agents_sdk.runtime import execute_campaign  # noqa: E402
from realcenter_marketing.infrastructure.observability.journal import RunJournal  # noqa: E402

BRIEF = ('Campanha institucional de final de semana para uma loja de bairro. '
         'Sem ofertas, sem precos e sem datas: o objetivo e lembranca de marca.')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Sonda de capacidade de um modelo de texto')
    parser.add_argument('--id', required=True, help='id do catalogo, como huggingface:Qwen/Qwen3.8-27B:novita')
    parser.add_argument('--root', default=None, help='raiz de dados da loja usada como cenario')
    args = parser.parse_args(argv)

    paths = AppPaths.discover(Path(args.root) if args.root else None)
    settings = Settings.load(paths.data_root)
    option = resolve_text(settings, args.id)
    if option is None:
        known = '\n  '.join(item.id for item in text_models(settings))
        raise SystemExit(f'Modelo fora do catalogo: {args.id}\nDisponiveis:\n  {known}')

    print(f'Sondando {option.label}')
    print(f'  provedor : {option.provider}')
    print(f'  modelo   : {option.model}')

    # A journal is not optional here. The SDK redacts the cause of a validation failure
    # before it surfaces, and DiagnosticOutputSchema — which only exists when a journal
    # does — is what captures the real errors first. Probing without one reports
    # "Invalid JSON" and nothing about which field was wrong.
    with tempfile.TemporaryDirectory() as scratch:
        journal = RunJournal(Path(scratch) / 'probe')
        try:
            result = asyncio.run(execute_campaign(CampaignBrief(request=BRIEF), settings,
                                                  option=option, journal=journal))
        except Exception as exc:
            credencial = isinstance(exc, ValueError) and 'Preencha' in str(exc)
            print(f'\n{"NAO SONDADO" if credencial else "REPROVADO"}: {type(exc).__name__}: {exc}')
            if not credencial:
                _explicar(journal)
            return 1

        entregues = list(result.outputs)
        print('\nAPROVADO')
        print('  plano            : aceito')
        print(f'  especialistas    : {", ".join(entregues)}')
        print(f'  revisao final    : {type(result.director).__name__}')
        print('\nO modelo respeitou o schema em todas as etapas e pode entrar no catalogo.')
        return 0


def _explicar(journal):
    """Read back what the diagnostic schema captured before the SDK redacted it."""
    caminho = journal.directory / 'events.jsonl'
    if not caminho.is_file():
        print('\nNenhum evento registrado.')
        return
    falhas = [json.loads(linha) for linha in caminho.read_text(encoding='utf-8').splitlines()
              if '"validation_failed"' in linha]
    if not falhas:
        print('\nO modelo nao chegou a devolver uma saida invalida; o erro e anterior '
              'a validacao (rede, credenciais ou recusa do provedor).')
        return
    for falha in falhas:
        print(f'\nEtapa que falhou : {falha.get("agent")}  (schema {falha.get("schema")})')
        for erro in falha.get('validation_errors') or []:
            print(f'  - {erro}')
        rejeitado = falha.get('rejected_output')
        if rejeitado:
            print(f'  saida rejeitada  : {str(rejeitado)[:300]}')
    print('\nSe os campos acima existem mas vieram no formato errado, o provedor nao esta '
          'respeitando json_schema estrito; fixe outro no id, por exemplo :novita ou :cerebras.')


if __name__ == '__main__':
    raise SystemExit(main())
