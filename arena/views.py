from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Category, Group, Evaluation
from .serializers import (
    CategorySerializer, GroupSerializer,
    EvaluationSubmitSerializer
)


def index(request):
    """Serve o frontend SPA."""
    return render(request, 'arena/index.html')


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.prefetch_related('evaluations').all()
    serializer_class = GroupSerializer

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
def submit_evaluation(request):
    """Recebe as notas de um avaliador para um grupo e soma no banco."""
    ser = EvaluationSubmitSerializer(data=request.data)
    if not ser.is_valid():
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

    data = ser.validated_data
    group = Group.objects.filter(id=data['group_id']).first()
    if not group:
        return Response({'detail': 'Grupo não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    new_note = data.get('notes', '').strip()
    if new_note:
        if group.notes and group.notes.strip():
            group.notes = f"{group.notes.strip()}\n• {new_note}"
        else:
            group.notes = f"• {new_note}"
        group.save()

    for cat_id_str, score in data['scores'].items():
        cat_id = int(cat_id_str)
        Evaluation.objects.create(
            group=group,
            category_id=cat_id,
            score=score
        )

    return Response(GroupSerializer(group).data, status=status.HTTP_200_OK)


@api_view(['POST'])
def reveal_group(request, pk):
    """Marca o grupo como revelado na cerimônia."""
    group = Group.objects.filter(pk=pk).first()
    if not group:
        return Response({'detail': 'Grupo não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
    group.is_revealed = True
    group.save()
    return Response(GroupSerializer(group).data)


@api_view(['POST'])
def reset_ceremony(request):
    """Reseta is_revealed de todos os grupos."""
    Group.objects.all().update(is_revealed=False)
    return Response({'detail': 'Cerimônia reiniciada.'})

