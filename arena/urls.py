from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'categories', views.CategoryViewSet, basename='category')
router.register(r'groups', views.GroupViewSet, basename='group')
router.register(r'evaluators', views.EvaluatorViewSet, basename='evaluator')

urlpatterns = [
    path('', views.index, name='index'),
    path('api/', include(router.urls)),
    path('api/evaluate/', views.submit_evaluation, name='submit_evaluation'),
    path('api/import-spreadsheet/', views.import_spreadsheet, name='import_spreadsheet'),
    path('api/clear-modality/', views.clear_modality, name='clear_modality'),
    path('api/groups/<int:pk>/reveal/', views.reveal_group, name='reveal_group'),
    path('api/ceremony/reset/', views.reset_ceremony, name='reset_ceremony'),
]

