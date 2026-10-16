from studio_ai.infrastructure.process_lease import ProcessLease
from studio_ai.bootstrap.paths import AppPaths
import argparse
import asyncio
from pathlib import Path
from uuid import uuid4

from agents import AgentsException
from openai import OpenAIError

from studio_ai.infrastructure.agents_sdk.demo import DemoModel
from studio_ai.domain.campaigns import CampaignBrief
from studio_ai.bootstrap.settings import Settings
from studio_ai.bootstrap.campaigns import create_campaign, save_campaign
from studio_ai.infrastructure.observability.journal import RunJournal, error_details


def main():
    parser = argparse.ArgumentParser(description="Cria rascunhos de campanhas da loja configurada")
    parser.add_argument("request", nargs="?", default="Crie uma campanha para o final de semana da loja.")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--brief", type=Path, help="Briefing JSON com request e confirmed_facts")
    parser.add_argument("--demo", action="store_true", help="Executa roteiro fixo offline, sem geração por IA")
    args = parser.parse_args()
    journal = None
    lease = None
    def progress(event):
        labels = {"started": "INICIO", "thinking": "PROCESSANDO", "completed": "CONCLUIDO", "failed": "FALHOU"}
        print(f"{labels.get(event['event'], event['event'])}: {event['agent'] or 'campanha'}", flush=True)

    try:
        settings = Settings.load(args.project_root)
        lease = ProcessLease(settings.project_root).acquire()
        brief = (CampaignBrief.model_validate_json(args.brief.read_text(encoding="utf-8"))
                 if args.brief else CampaignBrief(request=args.request))
        model = DemoModel(AppPaths.discover(settings.project_root).demo_responses) if args.demo else None
        journal = RunJournal(settings.project_root / "campaigns" / "runs" / f"run-{uuid4().hex}", progress)
        print(f"Entregas e progresso: {journal.directory}", flush=True)
        journal.emit("run_started", mode="demo" if args.demo else "live")
        campaign = asyncio.run(create_campaign(brief, settings, model=model, journal=journal))
        target = save_campaign(campaign, settings.project_root / "campaigns" / "runs")
        journal.save("campaign", campaign)
        journal.emit("run_completed")
    except (ValueError, OSError, RuntimeError, TimeoutError, AgentsException, OpenAIError) as exc:
        if journal:
            journal.emit("run_failed", journal.current_agent, **error_details(exc))
            print(f"Diagnostico: {type(exc).__name__}. Etapa: {journal.current_agent}.\nEntregas parciais: {journal.directory}", flush=True)
        # Mensagens de SDK/provedor podem conter entrada ou detalhes sensíveis.
        if isinstance(exc, OpenAIError):
            parser.exit(1, "Falha na API OpenAI. Verifique credencial, modelo, conectividade e limites da conta.\n")
        if isinstance(exc, AgentsException):
            parser.exit(1, "Fluxo de agentes interrompido. Verifique outputs e limite de turnos.\n")
        if isinstance(exc, TimeoutError):
            parser.exit(1, "Tempo limite excedido; campanha não salva.\n")
        parser.exit(1, f"Não foi possível gerar a campanha: {exc}\n")
    finally:
        if lease:
            lease.close()
    mode = "DEMONSTRAÇÃO FIXA, SEM IA" if args.demo else "GERAÇÃO COM IA"
    print(f"{mode} | DRAFT\n{target}")


if __name__ == "__main__":
    main()
