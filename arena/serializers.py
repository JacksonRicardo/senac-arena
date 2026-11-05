from rest_framework import serializers
from .models import Category, Group, Evaluator, Evaluation


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'order']


class EvaluatorSerializer(serializers.ModelSerializer):
    evaluated_group_ids = serializers.SerializerMethodField()

    class Meta:
        model = Evaluator
        fields = ['id', 'name', 'role', 'evaluated_group_ids']

    def get_evaluated_group_ids(self, obj):
        seen = []
        for e in obj.evaluations.all():
            if e.group_id not in seen:
                seen.append(e.group_id)
        return seen


class EvaluationSerializer(serializers.ModelSerializer):
    category_id = serializers.IntegerField(source='category.id', read_only=True)
    evaluator_id = serializers.IntegerField(source='evaluator.id', read_only=True, allow_null=True)

    class Meta:
        model = Evaluation
        fields = ['id', 'category_id', 'evaluator_id', 'score']


class GroupSerializer(serializers.ModelSerializer):
    scores = serializers.SerializerMethodField()
    total_score = serializers.SerializerMethodField()
    max_possible_score = serializers.SerializerMethodField()
    evaluations_count = serializers.SerializerMethodField()
    evaluated_by_ids = serializers.SerializerMethodField()
    evaluator_names = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ['id', 'title', 'authors', 'unit', 'notes', 'is_revealed',
                  'scores', 'total_score', 'max_possible_score', 'evaluations_count',
                  'evaluated_by_ids', 'evaluator_names']

    def get_scores(self, obj):
        scores = {}
        for e in obj.evaluations.select_related('category').all():
            key = str(e.category_id)
            scores[key] = scores.get(key, 0) + e.score
        return scores

    def get_total_score(self, obj):
        if obj.unit in ('CATEGORIA_2', 'CATEGORIA_4'):
            try:
                return int(str(obj.notes or '0').strip())
            except ValueError:
                return 0
        return obj.total_score()

    def get_max_possible_score(self, obj):
        if obj.unit in ('CATEGORIA_2', 'CATEGORIA_4'):
            try:
                return int(str(obj.notes or '0').strip())
            except ValueError:
                return 0
        return obj.max_possible_score()

    def get_evaluations_count(self, obj):
        if obj.unit in ('CATEGORIA_2', 'CATEGORIA_4'):
            try:
                return int(str(obj.notes or '0').strip())
            except ValueError:
                return 0
        return obj.evaluations_count()

    def get_evaluated_by_ids(self, obj):
        seen = []
        for e in obj.evaluations.all():
            if e.evaluator_id and e.evaluator_id not in seen:
                seen.append(e.evaluator_id)
        return seen

    def get_evaluator_names(self, obj):
        seen = []
        for e in obj.evaluations.select_related('evaluator').all():
            if e.evaluator and e.evaluator.name not in seen:
                seen.append(e.evaluator.name)
        return seen


class EvaluationSubmitSerializer(serializers.Serializer):
    """Recebe {group_id, evaluator_id, scores: {cat_id: 0|1|2}, notes}"""
    group_id = serializers.IntegerField()
    evaluator_id = serializers.IntegerField()
    scores = serializers.DictField(child=serializers.IntegerField(min_value=0, max_value=2))
    notes = serializers.CharField(allow_blank=True, default='')


