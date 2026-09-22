"""Monthly allowances, counted in units the server decides.

Not in dollars. IMAGE_PRICES only knows gpt-image-2 at 1024x1536, while generate_feed
renders 1152x1440, 1088x1088, 1536x800, 1152x1536 and 1152x2048 — so image_cost returns
None for practically every image the studio produces, and text_cost returns None for every
NVIDIA model. A spend ceiling built on that would quietly mean no ceiling at all.

So the gate counts campaigns, images and assists, which are known at admission time. Money
is tracked alongside as an alarm for the operator, never as the thing that blocks a run.
"""
from dataclasses import dataclass

CAMPAIGNS, IMAGES, ASSISTS = 'campaigns', 'images', 'assists'
METRICS = (CAMPAIGNS, IMAGES, ASSISTS)

# A DEFAULT store is trying the product; PAID has bought it. OWNER runs the platform and
# is not metered, because metering the operator protects nobody.
PLANS = {
    'DEFAULT': {CAMPAIGNS: 6, IMAGES: 20, ASSISTS: 15},
    'PAID': {CAMPAIGNS: 60, IMAGES: 300, ASSISTS: 200},
    'OWNER': {},
}


class QuotaError(Exception):
    """The allowance for this period is spent."""

    def __init__(self, metric, used, limit, period):
        super().__init__(f'Limite de {limit} {LABELS.get(metric, metric)} deste mês atingido.')
        self.metric, self.used, self.limit, self.period = metric, used, limit, period

    def details(self):
        return {'error': str(self), 'quota': {'metric': self.metric, 'used': self.used,
                                              'limit': self.limit, 'period': self.period}}


LABELS = {CAMPAIGNS: 'campanhas', IMAGES: 'artes', ASSISTS: 'consultas'}


def limits_for(role):
    return PLANS.get(role, PLANS['DEFAULT'])


@dataclass
class Ticket:
    """A reservation that can be handed back when nothing was ever spent."""
    ledger: object
    tenant_id: int
    period: str
    amounts: dict

    def void(self):
        if self.amounts:
            self.ledger.release(self.tenant_id, self.period, self.amounts)
            self.amounts = {}


class UsageQuota:
    """Reserves before the work starts, because a provider call that already happened
    cannot be un-billed."""

    def __init__(self, ledger, tenant_id, role, clock):
        self.ledger, self.tenant_id, self.role, self.clock = ledger, tenant_id, role, clock

    def reserve(self, **amounts):
        wanted = {metric: int(count) for metric, count in amounts.items() if int(count) > 0}
        if not wanted:
            return Ticket(self.ledger, self.tenant_id, self.clock(), {})
        limits = limits_for(self.role)
        period = self.clock()
        if not limits:
            # No allowance configured means unmetered, which is only ever the operator.
            self.ledger.record(self.tenant_id, period, wanted)
            return Ticket(self.ledger, self.tenant_id, period, {})
        granted = self.ledger.reserve(self.tenant_id, period, wanted, limits)
        if granted is not True:
            metric, used, limit = granted
            raise QuotaError(metric, used, limit, period)
        return Ticket(self.ledger, self.tenant_id, period, wanted)

    def summary(self):
        period = self.clock()
        limits = limits_for(self.role)
        used = self.ledger.used(self.tenant_id, period)
        return {'period': period, 'role': self.role,
                'metrics': {metric: {'used': used.get(metric, 0), 'limit': limits.get(metric)}
                            for metric in METRICS}}
