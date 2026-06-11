from django.urls import path
from .views import RatingCreate, RatingList

urlpatterns = [
    path('ratings/', RatingCreate.as_view()),
    path('ratings/list/', RatingList.as_view()),
]
