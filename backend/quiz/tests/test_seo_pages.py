import importlib.util
from pathlib import Path

import pytest


path = Path(__file__).resolve().parents[3] / 'scripts' / 'pcep-seo-pages.py'
spec = importlib.util.spec_from_file_location('seo_pages', path)
seo_pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seo_pages)


def question(identifier, module):
    return {
        'id': identifier,
        'text': f'Question {identifier}',
        'difficulty': ('easy', 'medium', 'hard')[identifier % 3],
        'module': module,
        'objective': '1.1',
        'code': 'print(1)',
        'updated': '2026-10-11',
        'choices': [
            {'id': identifier * 10 + choice, 'text': f'Choice {choice}'}
            for choice in range(1, 5)
        ],
    }


def valid_questions():
    modules = [key for key, *_rest in seo_pages.MODULES]
    return [question(identifier, modules[(identifier - 1) % 4]) for identifier in range(1, 53)]


def test_static_question_page_does_not_render_answer_metadata():
    rendered = seo_pages.render_question(1, {
        'text': '<script>alert(1)</script>', 'difficulty': 'easy',
        'objective': '3.4', 'code': 'print("<")',
        'choices': [{
            'text': '<option>', 'correct': True, 'is_correct': True,
            'explanation': 'SECRET_CANARY',
        }],
    })
    assert 'SECRET_CANARY' not in rendered
    assert 'class="correct"' not in rendered
    assert '<script>' not in rendered
    assert '&lt;option&gt;' in rendered
    assert '3.4 · easy' in rendered
    assert 'is_correct' not in seo_pages.EXTRACT
    assert 'explanation' not in seo_pages.EXTRACT
    assert 'QuestionSerializer(q)' in seo_pages.EXTRACT


@pytest.mark.parametrize('field', ['is_correct', 'explanation', 'correct_choice'])
def test_validation_refuses_answer_metadata(field):
    questions = valid_questions()
    questions[0]['choices'][0][field] = 'SECRET_CANARY'

    with pytest.raises(seo_pages.SeoPublishError, match='raspuns interzise'):
        seo_pages.validate_questions(questions)


def test_validation_allows_questions_without_code_snippets():
    questions = valid_questions()
    questions[0]['code'] = ''

    seo_pages.validate_questions(questions)


def test_failed_generation_keeps_the_complete_live_tree(tmp_path):
    live = tmp_path / 'seo'
    live.mkdir()
    marker = live / 'existing.html'
    marker.write_text('known-good', encoding='utf-8')
    questions = valid_questions()
    questions[0]['choices'] = []

    with pytest.raises(seo_pages.SeoPublishError, match='exact patru'):
        seo_pages.publish_questions(questions, live)

    assert marker.read_text(encoding='utf-8') == 'known-good'
    assert list(tmp_path.glob('.seo.release-*')) == []


def test_publication_replaces_the_live_tree_as_one_validated_release(
    tmp_path, monkeypatch
):
    live = tmp_path / 'seo'
    live.mkdir()
    (live / 'stale-answer-key.html').write_text('secret', encoding='utf-8')
    events = []
    real_exchange = seo_pages.exchange_directories

    monkeypatch.setattr(
        seo_pages,
        'fsync_tree',
        lambda path: events.append(('tree', Path(path).name)),
    )
    monkeypatch.setattr(
        seo_pages,
        'fsync_directory',
        lambda path: events.append(('directory', Path(path).name)),
    )

    def exchange(first, second):
        events.append(('exchange', Path(first).name, Path(second).name))
        real_exchange(first, second)

    monkeypatch.setattr(seo_pages, 'exchange_directories', exchange)

    assert seo_pages.publish_questions(valid_questions(), live) == 52

    assert events[0][0] == 'tree'
    assert events[0][1].startswith('.seo.release-')
    assert events[1][0] == 'exchange'
    assert events[2:] == [('directory', tmp_path.name)] * 2
    assert not (live / 'stale-answer-key.html').exists()
    seo_pages.validate_release(live)
    assert (live / 'practice/index.html').stat().st_mode & 0o777 == 0o644
    assert live.stat().st_mode & 0o777 == 0o755
    assert not any(path.is_symlink() for path in live.rglob('*'))


def test_seo_flush_failure_keeps_live_tree_and_prevents_exchange(
    tmp_path, monkeypatch
):
    live = tmp_path / 'seo'
    live.mkdir()
    marker = live / 'existing.html'
    marker.write_text('known-good', encoding='utf-8')
    monkeypatch.setattr(
        seo_pages,
        'fsync_tree',
        lambda _path: (_ for _ in ()).throw(OSError('storage failure')),
    )
    monkeypatch.setattr(
        seo_pages,
        'exchange_directories',
        lambda *_args: pytest.fail('exchange must not run after a flush failure'),
    )

    with pytest.raises(OSError, match='storage failure'):
        seo_pages.publish_questions(valid_questions(), live)

    assert marker.read_text(encoding='utf-8') == 'known-good'
    assert list(tmp_path.glob('.seo.release-*')) == []


def test_seo_parent_flush_failure_after_exchange_preserves_both_generations(
    tmp_path, monkeypatch
):
    live = tmp_path / 'seo'
    live.mkdir()
    marker = live / 'existing.html'
    marker.write_text('known-good', encoding='utf-8')
    monkeypatch.setattr(seo_pages, 'fsync_tree', lambda _path: None)
    monkeypatch.setattr(
        seo_pages,
        'fsync_directory',
        lambda _path: (_ for _ in ()).throw(OSError('parent storage failure')),
    )

    with pytest.raises(OSError, match='parent storage failure'):
        seo_pages.publish_questions(valid_questions(), live)

    seo_pages.validate_release(live)
    retained = list(tmp_path.glob('.seo.release-*'))
    assert len(retained) == 1
    assert (retained[0] / 'existing.html').read_text(encoding='utf-8') == 'known-good'


def test_publication_rejects_symlinked_live_root(tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    live = tmp_path / 'seo'
    live.symlink_to(real, target_is_directory=True)

    with pytest.raises(seo_pages.SeoPublishError, match='director real'):
        seo_pages.publish_questions(valid_questions(), live)


def test_extract_uses_absolute_docker_path_and_validates_before_returning():
    questions = valid_questions()
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return type('Result', (), {
            'returncode': 0,
            'stdout': 'noise\n---JSON-START---\n' + __import__('json').dumps(questions),
            'stderr': '',
        })()

    assert seo_pages.extract_questions(runner) == questions
    assert calls[0][0][0] == '/usr/bin/docker'
    assert calls[0][0][1:5] == ['exec', '--interactive', '--user', 'appuser']
    assert calls[0][1]['check'] is False


def test_seo_systemd_service_is_non_root_and_sandboxed():
    unit = (
        Path(__file__).resolve().parents[3]
        / 'ops/systemd/pcep-seo-pages.service'
    ).read_text(encoding='utf-8')

    for directive in (
        'User=micu',
        'NoNewPrivileges=true',
        'PrivateNetwork=true',
        'ProtectSystem=strict',
        'ProtectHome=true',
        'ReadWritePaths=/var/www/pcep',
        'CapabilityBoundingSet=',
        'RestrictAddressFamilies=AF_UNIX',
    ):
        assert directive in unit
    assert '\nUser=root\n' not in unit
