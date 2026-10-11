import shlex
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def gunicorn_arguments():
    entrypoint = (BACKEND_ROOT / 'entrypoint.sh').read_text()
    command = entrypoint[entrypoint.index('exec gunicorn') :].replace('\\\n', ' ')
    return shlex.split(command)


def option_value(arguments, option):
    index = arguments.index(option)
    return arguments[index + 1]


def test_gunicorn_runtime_disables_unused_control_and_protocol_surfaces():
    arguments = gunicorn_arguments()

    assert arguments[:2] == ['exec', 'gunicorn']
    assert option_value(arguments, '--worker-class') == 'sync'
    assert '--no-control-socket' in arguments
    assert option_value(arguments, '--http-protocols') == 'h1'
    assert option_value(arguments, '--http2-cleartext') == 'off'
    assert option_value(arguments, '--header-map') == 'drop'


def test_backend_startup_does_not_write_static_or_media_content():
    entrypoint = (BACKEND_ROOT / 'entrypoint.sh').read_text()

    assert 'collectstatic' not in entrypoint
    assert '/app/staticfiles' not in entrypoint
    assert '/app/media' not in entrypoint
