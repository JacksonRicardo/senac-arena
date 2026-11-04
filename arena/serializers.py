from rest_framework import serializers
from .models import Category, Group, Evaluation


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'order']


class EvaluationSerializer(serializers.ModelSerializer):
    category_id = serializers.IntegerField(source='category.id', read_only=True)

    class Meta:
        model = Evaluation
        fields = ['id', 'category_id', 'score']


class GroupSerializer(serializers.ModelSerializer):
    scores = serializers.SerializerMethodField()
    total_score = serializers.SerializerMethodField()
    max_possible_score = serializers.SerializerMethodField()
    evaluations_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ['id', 'title', 'authors', 'unit', 'notes', 'is_revealed',
                  'scores', 'total_score', 'max_possible_score', 'evaluations_count']

    def get_scores(self, obj):
        scores = {}
        for e in obj.evaluations.select_related('category').all():
            key = str(e.category_id)
            scores[key] = scores.get(key, 0) + e.score
        return scores

    def get_total_score(self, obj):
        return obj.total_score()

    def get_max_possible_score(self, obj):
        return obj.max_possible_score()

    def get_evaluations_count(self, obj):
        return obj.evaluations_count()


class EvaluationSubmitSerializer(serializers.Serializer):
    """Recebe {group_id, scores: {cat_id: 0|1|2}, notes}"""
    group_id = serializers.IntegerField()
    scores = serializers.DictField(child=serializers.IntegerField(min_value=0, max_value=2))
    notes = serializers.CharField(allow_blank=True, default='')

