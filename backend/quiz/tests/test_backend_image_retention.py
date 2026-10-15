import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'backend_image_retention',
    Path(__file__).resolve().parents[3] / 'scripts/backend_image_retention.py',
)
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)


def image_id(character):
    return f'sha256:{character * 64}'


def candidate(stamp, release, character):
    tag = f'{stamp}-release-{release}'
    return retention.RollbackImage(
        tag,
        f'{retention.ROLLBACK_REPOSITORY}:{tag}',
        image_id(character),
    )


def metadata(item, **overrides):
    config = {
        'User': 'appuser',
        'Env': ['PATH=/usr/bin', f'PCEP_RELEASE={item.tag.rsplit("-release-", 1)[1]}'],
        'Labels': {
            'org.opencontainers.image.revision': item.tag.rsplit('-release-', 1)[1]
        },
    }
    config.update(overrides)
    return {'Id': item.image_id, 'Config': config}


def candidates(count=7):
    return [
        candidate(f'202610{i:02d}T010000Z', f'{i:012x}', hex(i)[2:])
        for i in reversed(range(1, count + 1))
    ]


def test_plan_keeps_newest_verified_images_and_selects_old_tags():
    images = candidates()
    plan = retention.retention_plan(
        images,
        lambda reference: metadata(next(i for i in images if i.reference == reference)),
        set(),
        keep=5,
    )

    assert plan['keep'] == images[:5]
    assert plan['remove'] == images[5:]
    assert not plan['invalid']


def test_invalid_new_tag_does_not_consume_the_rollback_floor():
    images = candidates(4)
    invalid = images[0]

    def inspect(reference):
        item = next(i for i in images if i.reference == reference)
        return metadata(item, User='root') if item == invalid else metadata(item)

    plan = retention.retention_plan(images, inspect, set(), keep=2)

    assert invalid in plan['remove']
    assert invalid.reference in plan['invalid']
    assert plan['keep'] == images[1:3]


def test_refuses_pruning_without_two_verified_images():
    images = candidates(2)

    with pytest.raises(retention.ImageRetentionError, match='Only 1 rollback'):
        retention.retention_plan(
            images,
            lambda reference: (
                metadata(images[0])
                if reference == images[0].reference
                else metadata(images[1], Labels={})
            ),
            set(),
            keep=2,
        )


def test_refuses_removing_an_image_used_by_any_container():
    images = candidates(3)

    with pytest.raises(retention.ImageRetentionError, match='used by containers'):
        retention.retention_plan(
            images,
            lambda reference: metadata(next(i for i in images if i.reference == reference)),
            {images[-1].image_id},
            keep=2,
        )


@pytest.mark.parametrize(
    ('overrides', 'message'),
    [
        ({'User': 'root'}, 'appuser'),
        ({'Env': ['PCEP_RELEASE=wrong']}, 'does not match'),
        ({'Env': ['PCEP_RELEASE=000000000001', 'DJANGO_SECRET_KEY=secret']}, 'secret'),
        ({'Labels': {}}, 'does not match'),
    ],
)
def test_image_validation_rejects_unsafe_runtime_metadata(overrides, message):
    item = candidates(1)[0]
    with pytest.raises(retention.ImageRetentionError, match=message):
        retention.validate_rollback_image(item, metadata(item, **overrides))


def test_discovery_accepts_only_the_exact_repository_and_safe_ids():
    item = candidates(1)[0]
    payload = json.dumps({
        'Repository': retention.ROLLBACK_REPOSITORY,
        'Tag': item.tag,
        'ID': item.image_id,
    })
    assert retention.discover_rollback_tags(lambda _command: payload) == [item]

    changed = json.loads(payload)
    changed['Repository'] = 'unrelated'
    with pytest.raises(retention.ImageRetentionError, match='outside'):
        retention.discover_rollback_tags(lambda _command: json.dumps(changed))


def test_container_inventory_tolerates_only_a_confirmed_disappearance():
    disappearing = 'a' * 64
    calls = 0

    def runner(command):
        nonlocal calls
        if command[:4] == ['docker', 'container', 'ls', '--all']:
            calls += 1
            return disappearing if calls == 1 else ''
        if command[:3] == ['docker', 'container', 'inspect']:
            raise retention.ImageRetentionError('No such container')
        raise AssertionError(command)

    assert retention.container_image_ids(runner) == set()

    def persistent_runner(command):
        if command[:4] == ['docker', 'container', 'ls', '--all']:
            return disappearing
        raise retention.ImageRetentionError('inspect permission denied')

    with pytest.raises(retention.ImageRetentionError, match='permission denied'):
        retention.container_image_ids(persistent_runner)


def test_apply_rechecks_tag_identity_before_removal(tmp_path):
    images = candidates(3)
    calls = []

    def runner(command, **_kwargs):
        calls.append(command)
        if command[:3] == ['docker', 'image', 'ls']:
            return '\n'.join(json.dumps({
                'Repository': retention.ROLLBACK_REPOSITORY,
                'Tag': item.tag,
                'ID': item.image_id,
            }) for item in images)
        if command[:4] == ['docker', 'container', 'ls', '--all']:
            return ''
        if command[:3] == ['docker', 'image', 'inspect']:
            item = next(i for i in images if i.reference == command[3])
            if command[-2:] == ['--format', '{{.Id}}']:
                return item.image_id
            return json.dumps([metadata(item)])
        if command[:3] == ['docker', 'image', 'rm']:
            return 'untagged'
        raise AssertionError(command)

    retention.execute(
        keep=2,
        apply=True,
        runner=runner,
        lock_root=tmp_path / 'locks',
    )

    assert ['docker', 'image', 'rm', images[-1].reference] in calls
    assert not any('--force' in command for command in calls)


def test_retention_refuses_a_concurrent_backend_deployment(tmp_path):
    lock_root = tmp_path / 'locks'

    with retention.exclusive_operation_lock(
        'backend-maintenance',
        root=lock_root,
    ):
        with pytest.raises(retention.ImageRetentionError, match='already running'):
            retention.execute(
                keep=2,
                runner=lambda *_args, **_kwargs: pytest.fail(
                    'Locked retention must not inspect Docker.'
                ),
                lock_root=lock_root,
            )
