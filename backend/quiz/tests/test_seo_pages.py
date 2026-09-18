import importlib.util
from pathlib import Path


def test_static_question_page_does_not_render_answer_metadata():
    path = Path(__file__).resolve().parents[3] / 'scripts' / 'pcep-seo-pages.py'
    spec = importlib.util.spec_from_file_location('seo_pages', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rendered = module.render_question(1, {
        'text': '<script>alert(1)</script>', 'difficulty': 'easy', 'code': 'print("<")',
        'choices': [{
            'text': '<option>', 'correct': True, 'is_correct': True,
            'explanation': 'SECRET_CANARY',
        }],
    })
    assert 'SECRET_CANARY' not in rendered
    assert 'class="correct"' not in rendered
    assert '<script>' not in rendered
    assert '&lt;option&gt;' in rendered
    assert 'is_correct' not in module.EXTRACT
    assert 'explanation' not in module.EXTRACT
    assert 'QuestionSerializer(q)' in module.EXTRACT
