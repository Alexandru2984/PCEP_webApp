#!/usr/bin/env python3
"""Delete only expired analytics rows for one verified Umami website."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import uuid

import psycopg2


DOMAIN_PATTERN = re.compile(
    r'(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}'
)
MIN_RETENTION_DAYS = 30
MAX_RETENTION_DAYS = 730

DELETE_STATEMENTS = (
    (
        'event_data',
        'DELETE FROM event_data WHERE website_id = %s '
        'AND (created_at IS NULL OR created_at < %s)',
    ),
    (
        'session_data',
        'DELETE FROM session_data WHERE website_id = %s '
        'AND (created_at IS NULL OR created_at < %s)',
    ),
    (
        'session_replay_saved',
        'DELETE FROM session_replay_saved WHERE website_id = %s '
        'AND (created_at IS NULL OR created_at < %s)',
    ),
    (
        'session_replay',
        'DELETE FROM session_replay WHERE website_id = %s AND ended_at < %s',
    ),
    (
        'website_event',
        'DELETE FROM website_event WHERE website_id = %s '
        'AND (created_at IS NULL OR created_at < %s)',
    ),
)

SESSION_DELETE = '''
DELETE FROM session AS current_session
WHERE current_session.website_id = %s
  AND (current_session.created_at IS NULL OR current_session.created_at < %s)
  AND NOT EXISTS (
      SELECT 1 FROM website_event AS recent_event
      WHERE recent_event.session_id = current_session.session_id
        AND recent_event.website_id = current_session.website_id
        AND recent_event.created_at >= %s
  )
  AND NOT EXISTS (
      SELECT 1 FROM session_data AS recent_data
      WHERE recent_data.session_id = current_session.session_id
        AND recent_data.website_id = current_session.website_id
        AND recent_data.created_at >= %s
  )
  AND NOT EXISTS (
      SELECT 1 FROM session_replay AS recent_replay
      WHERE recent_replay.session_id = current_session.session_id
        AND recent_replay.website_id = current_session.website_id
        AND recent_replay.ended_at >= %s
  )
'''


class AnalyticsRetentionError(RuntimeError):
    pass


def fsync_directory(path):
    flags = os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0)
    if hasattr(os, 'O_DIRECTORY'):
        flags |= os.O_DIRECTORY
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def remove_temporary_durably(path, parent):
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    fsync_directory(parent)
    return True


def write_success_status(path, now=None):
    status = Path(path).absolute()
    parent = status.parent
    if parent.is_symlink() or not parent.is_dir():
        raise AnalyticsRetentionError(
            'Analytics retention status directory must be a real directory.'
        )
    parent_details = parent.stat()
    if parent_details.st_uid != os.getuid() or parent_details.st_mode & 0o022:
        raise AnalyticsRetentionError(
            'Analytics retention status directory must be owned by the invoking '
            'user and not writable by group or others.'
        )
    if status.exists() or status.is_symlink():
        if status.is_symlink() or not status.is_file():
            raise AnalyticsRetentionError(
                'Existing analytics retention status must be a real file.'
            )
        if status.stat().st_uid != os.getuid():
            raise AnalyticsRetentionError(
                'Existing analytics retention status has the wrong owner.'
            )

    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise AnalyticsRetentionError(
            'Analytics retention completion time must include a timezone.'
        )
    payload = {
        'completed_at': moment.astimezone(timezone.utc).strftime(
            '%Y-%m-%dT%H:%M:%SZ'
        ),
        'schema': 1,
    }
    temporary = parent / f'.{status.name}.partial-{uuid.uuid4().hex}'
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_CLOEXEC', 0)
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    published = False
    try:
        with os.fdopen(descriptor, 'w') as output:
            json.dump(payload, output, separators=(',', ':'), sort_keys=True)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, status)
        published = True
        status.chmod(0o600)
        fsync_directory(parent)
    except BaseException as error:
        if not published and os.path.lexists(temporary):
            try:
                remove_temporary_durably(temporary, parent)
            except Exception as cleanup_error:
                note = (
                    'Failed to durably remove analytics retention status '
                    f'temporary {temporary}: {cleanup_error}'
                )
                error.add_note(note)
                print(
                    f'Analytics retention cleanup warning: {note}',
                    file=sys.stderr,
                )
        raise
    return payload


def record_applied_success(result, status_file, now=None):
    if status_file is None:
        return None
    if not isinstance(result, dict) or result.get('applied') is not True:
        raise AnalyticsRetentionError(
            'A retention preview must not publish an applied-success marker.'
        )
    return write_success_status(status_file, now=now)


def validate_inputs(website_id, expected_domain, retention_days):
    try:
        normalized_id = str(uuid.UUID(str(website_id)))
    except (ValueError, TypeError, AttributeError) as error:
        raise AnalyticsRetentionError('Website ID must be a canonical UUID.') from error
    if normalized_id != str(website_id):
        raise AnalyticsRetentionError('Website ID must be a canonical UUID.')
    normalized_domain = str(expected_domain).lower()
    if DOMAIN_PATTERN.fullmatch(normalized_domain) is None:
        raise AnalyticsRetentionError('Expected domain is invalid.')
    if (
        isinstance(retention_days, bool)
        or not isinstance(retention_days, int)
        or not MIN_RETENTION_DAYS <= retention_days <= MAX_RETENTION_DAYS
    ):
        raise AnalyticsRetentionError(
            f'Retention days must be between {MIN_RETENTION_DAYS} and '
            f'{MAX_RETENTION_DAYS}.'
        )
    return normalized_id, normalized_domain


def enforce_retention(
    connection,
    website_id,
    expected_domain,
    retention_days,
    *,
    apply=False,
    now=None,
):
    website_id, expected_domain = validate_inputs(
        website_id, expected_domain, retention_days
    )
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise AnalyticsRetentionError('Current time must be timezone-aware.')
    cutoff = current.astimezone(timezone.utc) - timedelta(days=retention_days)
    deleted = {}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext('pcep-analytics-retention'))"
            )
            cursor.execute(
                'SELECT name, domain FROM website WHERE website_id = %s',
                (website_id,),
            )
            website = cursor.fetchone()
            if website is None:
                raise AnalyticsRetentionError('Configured Umami website does not exist.')
            name, actual_domain = website
            if actual_domain.lower() != expected_domain:
                raise AnalyticsRetentionError(
                    'Configured Umami website domain does not match the expected domain.'
                )

            for table, statement in DELETE_STATEMENTS:
                cursor.execute(statement, (website_id, cutoff))
                deleted[table] = cursor.rowcount
            cursor.execute(
                SESSION_DELETE,
                (website_id, cutoff, cutoff, cutoff, cutoff),
            )
            deleted['session'] = cursor.rowcount

        if apply:
            connection.commit()
        else:
            connection.rollback()
        return {
            'applied': bool(apply),
            'website_id': website_id,
            'website_name': name,
            'domain': expected_domain,
            'retention_days': retention_days,
            'cutoff': cutoff.isoformat().replace('+00:00', 'Z'),
            'deleted': deleted,
        }
    except Exception:
        connection.rollback()
        raise


def database_connection():
    database_url = os.environ.get('DATABASE_URL', '')
    if not database_url:
        raise AnalyticsRetentionError('DATABASE_URL is required.')
    try:
        return psycopg2.connect(
            database_url,
            connect_timeout=10,
            application_name='pcep-analytics-retention',
        )
    except psycopg2.Error as error:
        raise AnalyticsRetentionError('Could not connect to the Umami database.') from error


def main():
    parser = argparse.ArgumentParser(
        description='Apply bounded retention to one verified Umami website.'
    )
    parser.add_argument('--website-id', required=True)
    parser.add_argument('--expected-domain', required=True)
    parser.add_argument('--retention-days', type=int, default=180)
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Commit deletions. Without this flag the transaction is rolled back.',
    )
    parser.add_argument('--status-file', type=Path)
    args = parser.parse_args()
    try:
        with database_connection() as connection:
            result = enforce_retention(
                connection,
                args.website_id,
                args.expected_domain,
                args.retention_days,
                apply=args.apply,
            )
        record_applied_success(result, args.status_file)
        print(json.dumps(result, sort_keys=True))
    except (AnalyticsRetentionError, psycopg2.Error) as error:
        parser.exit(1, f'Analytics retention refused: {error}\n')


if __name__ == '__main__':
    main()
