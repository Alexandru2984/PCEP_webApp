from django.conf import settings
from django.urls import include, path

urlpatterns = [
    path('api/', include('quiz.urls')),
]

if settings.DJANGO_ADMIN_ENABLED:
    from django.contrib import admin

    urlpatterns.insert(0, path('admin/', admin.site.urls))
