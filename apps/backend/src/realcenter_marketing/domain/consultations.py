"""Independent advisory deliveries, never campaign pipeline steps."""
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from .campaigns import StructuredModel, Text


class EvidenceSource(StructuredModel):
    id: Text = Field(max_length=80)
    title: Text = Field(max_length=200)
    url: HttpUrl | None = None
    content: Text = Field(max_length=20000)


class ConsultationRequest(StructuredModel):
    role: Literal['performance', 'marketing_analyst']
    request: Text = Field(max_length=12000)
    confirmed_facts: list[Text] = Field(default_factory=list, max_length=100)
    sources: list[EvidenceSource] = Field(default_factory=list, max_length=30)
    model_id: Text | None = None

    @model_validator(mode='after')
    def unique_sources(self):
        if len({source.id for source in self.sources}) != len(self.sources):
            raise ValueError('Cada fonte deve ter um identificador único')
        return self


class Audience(StructuredModel):
    name: Text
    hypothesis: Text
    targeting: list[Text] = Field(min_length=1)
    exclusions: list[Text]


class MediaTest(StructuredModel):
    hypothesis: Text
    variants: list[Text] = Field(min_length=2)
    success_criterion: Text


class SuggestedBudget(StructuredModel):
    amount_brl: float | None = Field(ge=0, allow_inf_nan=False)
    period: Text
    rationale: Text
    approval_required: Literal[True]


class PaidMediaPlan(StructuredModel):
    objective: Text
    audiences: list[Audience] = Field(min_length=1)
    channels: list[Text] = Field(min_length=1)
    tests: list[MediaTest] = Field(min_length=1)
    suggested_budget: SuggestedBudget
    measurement_plan: list[Text] = Field(min_length=1)
    missing_data: list[Text]


class SourcedFinding(StructuredModel):
    source_id: Text
    evidence: Text
    analysis: Text


class CompetitorFinding(SourcedFinding):
    competitor: Text


class SEORecommendation(StructuredModel):
    action: Text
    rationale: Text
    priority: Literal['alta', 'media', 'baixa']
    verification: Text


class MarketingAnalysis(StructuredModel):
    summary: Text
    findings: list[SourcedFinding]
    competitors: list[CompetitorFinding]
    seo_recommendations: list[SEORecommendation] = Field(min_length=1)
    missing_data: list[Text]


OUTPUT_SCHEMAS = {'performance': PaidMediaPlan, 'marketing_analyst': MarketingAnalysis}


def validated_delivery(request, value):
    """Only supplied evidence can support a factual finding; URLs are never fetched."""
    schema = OUTPUT_SCHEMAS[request.role]
    result = schema.model_validate(value.model_dump() if isinstance(value, StructuredModel) else value)
    if isinstance(result, MarketingAnalysis):
        sources = {source.id: source for source in request.sources}
        for finding in [*result.findings, *result.competitors]:
            source = sources.get(finding.source_id)
            if source is None or finding.evidence not in source.content:
                raise ValueError('A análise citou fonte ou trecho não fornecido')
        if not sources and not result.missing_data:
            raise ValueError('Informe que não recebeu dados verificáveis')
    return result
