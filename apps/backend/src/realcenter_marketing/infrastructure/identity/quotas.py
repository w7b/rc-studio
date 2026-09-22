"""Quota counters in Postgres.

The reservation is one statement with the limit in its WHERE clause, so two simultaneous
requests from the same store cannot both pass the ceiling. That is the whole reason this
lives in a database rather than in a JSON file: a counter is compare-and-increment, and
read-modify-write under ThreadingHTTPServer loses updates — which costs the operator real
money, since the operator is the one paying for the generation.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

# Stores bill by calendar month in their own timezone; a UTC boundary would roll over at
# nine in the evening and confuse the person reading the invoice.
TIMEZONE = ZoneInfo('America/Sao_Paulo')


def current_period():
    return datetime.now(TIMEZONE).strftime('%Y-%m')


class PostgresQuotaLedger:
    def __init__(self, database):
        self.database = database

    def reserve(self, tenant_id, period, amounts, limits):
        """True when every metric fit. Otherwise the first metric that did not, so the
        caller can say which allowance ran out.

        A refusal aborts the transaction, so a partially granted reservation is never
        left behind when one metric fits and the next does not."""
        try:
            return self._reserve(tenant_id, period, amounts, limits)
        except _Refused as refused:
            return refused.detail

    def _reserve(self, tenant_id, period, amounts, limits):
        with self.database.connection() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    for metric, count in amounts.items():
                        limit = limits.get(metric)
                        if limit is None:
                            continue
                        cursor.execute(
                            'INSERT INTO usage_counters (tenant_id, period, metric, used) '
                            'VALUES (%s, %s, %s, %s) '
                            'ON CONFLICT (tenant_id, period, metric) DO UPDATE SET used = usage_counters.used + %s '
                            'WHERE usage_counters.used + %s <= %s',
                            (tenant_id, period, metric, count, count, count, limit))
                        if cursor.rowcount == 0:
                            cursor.execute(
                                'SELECT used FROM usage_counters WHERE tenant_id = %s AND period = %s AND metric = %s',
                                (tenant_id, period, metric))
                            row = cursor.fetchone()
                            raise _Refused(metric, row[0] if row else 0, limit)
                    self._log(cursor, tenant_id, period, amounts)
        return True

    def _log(self, cursor, tenant_id, period, amounts, sign=1):
        for metric, count in amounts.items():
            cursor.execute(
                'INSERT INTO usage_events (tenant_id, period, metric, delta) VALUES (%s, %s, %s, %s)',
                (tenant_id, period, metric, sign * count))

    def record(self, tenant_id, period, amounts):
        """Count without enforcing, for an unmetered role."""
        with self.database.connection() as connection, connection.cursor() as cursor:
            for metric, count in amounts.items():
                cursor.execute(
                    'INSERT INTO usage_counters (tenant_id, period, metric, used) VALUES (%s, %s, %s, %s) '
                    'ON CONFLICT (tenant_id, period, metric) DO UPDATE SET used = usage_counters.used + %s',
                    (tenant_id, period, metric, count, count))
            self._log(cursor, tenant_id, period, amounts)

    def release(self, tenant_id, period, amounts):
        """Give back a reservation whose work never reached a provider."""
        with self.database.connection() as connection, connection.cursor() as cursor:
            for metric, count in amounts.items():
                cursor.execute(
                    'UPDATE usage_counters SET used = GREATEST(used - %s, 0) '
                    'WHERE tenant_id = %s AND period = %s AND metric = %s',
                    (count, tenant_id, period, metric))
            self._log(cursor, tenant_id, period, amounts, sign=-1)

    def used(self, tenant_id, period):
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT metric, used FROM usage_counters WHERE tenant_id = %s AND period = %s',
                           (tenant_id, period))
            return {row[0]: row[1] for row in cursor.fetchall()}


class _Refused(Exception):
    def __init__(self, metric, used, limit):
        self.detail = (metric, used, limit)
