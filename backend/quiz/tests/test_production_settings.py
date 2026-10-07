import os
from pathlib import Path
import subprocess
import sys

from django.conf import settings
from django.urls import resolve


def test_development_keeps_the_validated_admin_editor():
    assert settings.DJANGO_ADMIN_ENABLED is True
    assert 'django.contrib.admin' in settings.INSTALLED_APPS
    assert resolve('/admin/login/').url_name == 'login'


def test_production_does_not_install_or_route_django_admin():
    environment = os.environ.copy()
    environment.update(
        {
            'DJANGO_SETTINGS_MODULE': 'pcep_project.settings',
            'DJANGO_DEBUG': 'False',
            'DJANGO_SECRET_KEY': 'production-shape-test-key-that-is-long-enough-for-checks',
            'DJANGO_ALLOWED_HOSTS': 'pcep.example.test',
        }
    )
    code = """
import django
django.setup()
from django.conf import settings
from django.urls import Resolver404, resolve
assert settings.DJANGO_ADMIN_ENABLED is False
assert 'django.contrib.admin' not in settings.INSTALLED_APPS
try:
    resolve('/admin/login/')
except Resolver404:
    pass
else:
    raise AssertionError('production routed Django admin')
"""
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
