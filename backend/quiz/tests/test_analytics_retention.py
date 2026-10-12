import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'analytics_retention',
    Path(__file__).resolve().parents[3] / 'scripts/analytics_retention.py',
)
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)

WEBSITE_ID = 'b37781f1-2c12-4d98-88f7-48cf10f000fd'
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class FakeCursor:
    def __init__(self, website=('PCEP', 'pcep.micutu.com')):
        self.website = website
        self.rowcount = 0
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, parameters=None):
        self.calls.append((statement, parameters))
        if statement.startswith('SELECT name, domain'):
            self.rowcount = 1 if self.website else 0
        elif statement.lstrip().startswith('DELETE'):
            self.rowcount = len([call for call in self.calls if call[0].lstrip().startswith('DELETE')])
        else:
            self.rowcount = 0

    def fetchone(self):
        return self.website


class FakeConnection:
    def __init__(self, website=('PCEP', 'pcep.micutu.com')):
        self.cursor_instance = FakeCursor(website)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.mark.parametrize(
    'website_id,domain,days,message',
    [
        ('not-a-uuid', 'pcep.micutu.com', 180, 'canonical UUID'),
        (WEBSITE_ID.upper(), 'pcep.micutu.com', 180, 'canonical UUID'),
        (WEBSITE_ID, 'https://pcep.micutu.com', 180, 'domain is invalid'),
        (WEBSITE_ID, 'pcep.micutu.com', 29, 'between 30 and 730'),
        (WEBSITE_ID, 'pcep.micutu.com', 731, 'between 30 and 730'),
    ],
)
def test_retention_rejects_unbounded_or_ambiguous_scope(
    website_id, domain, days, message
):
    with pytest.raises(retention.AnalyticsRetentionError, match=message):
        retention.validate_inputs(website_id, domain, days)


def test_dry_run_deletes_every_scoped_table_then_rolls_back():
    connection = FakeConnection()

    result = retention.enforce_retention(
        connection,
        WEBSITE_ID,
        'pcep.micutu.com',
        180,
        now=datetime(2026, 10, 13, tzinfo=timezone.utc),
    )

    assert result['applied'] is False
    assert result['cutoff'] == '2026-04-16T00:00:00Z'
    assert set(result['deleted']) == {
        'event_data',
        'session_data',
        'session_replay_saved',
        'session_replay',
        'website_event',
        'session',
    }
    assert connection.commits == 0
    assert connection.rollbacks == 1
    deletes = [
        call for call in connection.cursor_instance.calls if call[0].lstrip().startswith('DELETE')
    ]
    assert len(deletes) == 6
    assert all(call[1][0] == WEBSITE_ID for call in deletes)


def test_apply_commits_only_after_domain_identity_matches():
    connection = FakeConnection()

    result = retention.enforce_retention(
        connection,
        WEBSITE_ID,
        'pcep.micutu.com',
        180,
        apply=True,
        now=datetime(2026, 10, 13, tzinfo=timezone.utc),
    )

    assert result['applied'] is True
    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_domain_mismatch_fails_closed_and_rolls_back():
    connection = FakeConnection(('PCEP', 'another.example'))

    with pytest.raises(retention.AnalyticsRetentionError, match='does not match'):
        retention.enforce_retention(
            connection,
            WEBSITE_ID,
            'pcep.micutu.com',
            180,
            apply=True,
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_missing_database_url_fails_without_connection(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(retention.AnalyticsRetentionError, match='required'):
        retention.database_connection()


def test_systemd_sandbox_exposes_the_uv_runtime_behind_the_virtualenv_symlink():
    service = (PROJECT_ROOT / 'ops/systemd/pcep-analytics-retention.service').read_text()

    assert 'ProtectHome=tmpfs' in service
    assert 'BindReadOnlyPaths=/home/micu/.local/share/uv/python\n' in service
    assert 'BindReadOnlyPaths=/home/micu/PCEP_webApp/backend/.venv\n' in service
    assert (
        'ExecStart=/home/micu/PCEP_webApp/backend/.venv/bin/python '
        '/home/micu/PCEP_webApp/scripts/analytics_retention.py '
    ) in service
