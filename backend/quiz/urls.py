from django.urls import path

from . import views

urlpatterns = [
    path('quiz-set/', views.quiz_set, name='quiz-set'),
    path('questions/<int:pk>/', views.QuestionDetailView.as_view(), name='question-detail'),
    path('questions/<int:question_id>/answer/', views.submit_answer, name='submit-answer'),
]
