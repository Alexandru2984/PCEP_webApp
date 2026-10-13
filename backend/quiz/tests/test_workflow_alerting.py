from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = PROJECT_ROOT / '.github/workflows/production-smoke.yml'


def test_production_alert_names_and_assigns_the_repository_owner():
    workflow = WORKFLOW.read_text()

    assert 'ALERT_ASSIGNEE: ${{ github.repository_owner }}' in workflow
    assert 'body="@$ALERT_ASSIGNEE is the named responder.' in workflow
    assert '--assignee "$ALERT_ASSIGNEE"' in workflow
    assert '--add-assignee "$ALERT_ASSIGNEE"' in workflow


def test_issue_write_permission_remains_scoped_to_alert_and_recovery_jobs():
    workflow = WORKFLOW.read_text()

    assert workflow.count('issues: write') == 2
    assert workflow.count('contents: read') == 3
    assert workflow.index('issues: write') > workflow.index('  alert:')
    assert workflow.rindex('issues: write') > workflow.index('  recover:')
