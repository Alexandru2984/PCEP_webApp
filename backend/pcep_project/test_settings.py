import os

os.environ.setdefault('DJANGO_SECRET_KEY', 'test-secret-key-not-used-in-production')
os.environ.setdefault('DJANGO_DEBUG', 'True')
os.environ.setdefault('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver')

from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'test.sqlite3',
    }
}

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]
