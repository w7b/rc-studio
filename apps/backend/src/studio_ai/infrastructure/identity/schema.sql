-- Identity, membership and metering. Campaign artefacts stay on the filesystem: media
-- ids are sha256 of a path relative to the tenant root, and moving them here would
-- destroy identifiers already handed out.

CREATE TABLE IF NOT EXISTS tenants (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    root_path   TEXT,
    status      TEXT NOT NULL DEFAULT 'active',
    plan        TEXT NOT NULL DEFAULT 'basico',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS modules JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS users (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email         TEXT NOT NULL,
    password_hash TEXT,
    name          TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);
-- Case-insensitive uniqueness without requiring the citext extension to be installed.
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_idx ON users (lower(email));
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT NOT NULL DEFAULT '';

-- Keyed on the provider's subject, never on the address: a person can change their
-- e-mail at the provider and must remain the same user here.
CREATE TABLE IF NOT EXISTS identities (
    provider  TEXT NOT NULL,
    subject   TEXT NOT NULL,
    user_id   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, subject)
);

CREATE TABLE IF NOT EXISTS memberships (
    user_id   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role      TEXT NOT NULL CHECK (role IN ('DEFAULT', 'PAID', 'OWNER')),
    PRIMARY KEY (user_id, tenant_id)
);

-- token_hash, never the token: a dump of this table must not grant a single session.
CREATE TABLE IF NOT EXISTS sessions (
    token_hash   TEXT PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id    BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role         TEXT NOT NULL,
    csrf         TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id);

CREATE TABLE IF NOT EXISTS invites (
    token_hash TEXT PRIMARY KEY,
    tenant_id  BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    email      TEXT NOT NULL DEFAULT '',
    expires_at TIMESTAMPTZ NOT NULL,
    used_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS login_attempts (
    key          TEXT PRIMARY KEY,
    window_start TIMESTAMPTZ NOT NULL,
    count        INTEGER NOT NULL DEFAULT 0
);

-- Countable units, not dollars: image_cost returns NULL for every canvas the studio
-- actually renders, so a spend limit would silently mean no limit at all.
CREATE TABLE IF NOT EXISTS quotas (
    tenant_id   BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    metric      TEXT NOT NULL,
    limit_value INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, metric)
);

CREATE TABLE IF NOT EXISTS usage_counters (
    tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    period    TEXT NOT NULL,
    metric    TEXT NOT NULL,
    used      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, period, metric)
);

-- Append-only, so a counter can always be re-derived and a reservation reversed.
CREATE TABLE IF NOT EXISTS usage_events (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    period    TEXT NOT NULL,
    metric    TEXT NOT NULL,
    delta     INTEGER NOT NULL,
    run_id    TEXT,
    at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Durable work queue. A run claimed here survives a restart of the web process, which is
-- the single failure that hurts most with paying customers: today a deploy kills a
-- campaign in flight and the store loses what was already spent.
CREATE TABLE IF NOT EXISTS jobs (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    tenant_slug  TEXT NOT NULL,
    root_path    TEXT,
    kind         TEXT NOT NULL,
    payload      JSONB NOT NULL,
    run_id       TEXT,
    status       TEXT NOT NULL DEFAULT 'queued'
                 CHECK (status IN ('queued', 'running', 'done', 'failed')),
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT,
    claimed_by   TEXT,
    claimed_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS jobs_pending_idx ON jobs (status, id) WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS jobs_tenant_idx ON jobs (tenant_id, status);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;
