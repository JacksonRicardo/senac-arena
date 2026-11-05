from django.contrib import admin
from django.db.models import Exists, OuterRef, Sum
from django.utils.html import format_html
from .models import Category, Group, Evaluator, Evaluation, RaffleParticipant, RaffleWinner


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['order', 'name', 'description_short', 'evaluations_count', 'total_points_badge', 'points_by_group']
    list_display_links = ['name']
    list_editable = ['order']
    search_fields = ['name', 'description']
    ordering = ['order', 'id']

    def description_short(self, obj):
        return obj.description[:60] + '...' if len(obj.description) > 60 else obj.description
    description_short.short_description = 'Descrição'

    def evaluations_count(self, obj):
        return obj.evaluations.count()
    evaluations_count.short_description = 'Qtd. Votos'

    def total_points_badge(self, obj):
        total = obj.evaluations.aggregate(s=Sum('score'))['s'] or 0
        return format_html(
            '<span style="background:#002D72;color:#fff;padding:3px 10px;border-radius:10px;font-weight:bold">{} pts</span>',
            total
        )
    total_points_badge.short_description = 'Somatório Geral'

    def points_by_group(self, obj):
        rows = (
            obj.evaluations.values('group__title')
            .annotate(total=Sum('score'))
            .order_by('-total')
        )
        if not rows:
            return '-'
        badges = [
            format_html(
                '<span style="display:inline-block;background:#F1F5F9;border:1px solid #CBD5E1;color:#0F172A;padding:2px 8px;border-radius:8px;margin:2px;font-size:11px">'
                '<strong>{}</strong>: {} pts</span>',
                r['group__title'], r['total']
            )
            for r in rows
        ]
        return format_html(''.join(badges))
    points_by_group.short_description = 'Somatório por Grupo'


@admin.register(Evaluator)
class EvaluatorAdmin(admin.ModelAdmin):
    list_display = ['name', 'role', 'groups_evaluated_count', 'total_points_given', 'created_at']
    search_fields = ['name', 'role']
    ordering = ['name']

    def groups_evaluated_count(self, obj):
        return obj.evaluations.values('group').distinct().count()
    groups_evaluated_count.short_description = 'Grupos Avaliados'

    def total_points_given(self, obj):
        total = obj.evaluations.aggregate(s=Sum('score'))['s'] or 0
        return f"{total} pts"
    total_points_given.short_description = 'Total de Pontos Atribuídos'


class EvaluationInline(admin.TabularInline):
    model = Evaluation
    extra = 0
    fields = ['evaluator', 'category', 'score']
    autocomplete_fields = ['evaluator', 'category']


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['title', 'authors', 'unit', 'category_sums_display', 'score_badge', 'is_revealed', 'updated_at']
    list_display_links = ['title']
    list_filter = ['is_revealed', 'unit']
    search_fields = ['title', 'authors', 'unit']
    list_editable = ['is_revealed']
    inlines = [EvaluationInline]
    readonly_fields = ['total_score_display', 'category_sums_display', 'created_at', 'updated_at']
    fieldsets = (
        ('Informações do Projeto', {
            'fields': ('title', 'authors', 'unit')
        }),
        ('Avaliação e Somatório por Categoria', {
            'fields': ('notes', 'is_revealed', 'category_sums_display', 'total_score_display')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def category_sums_display(self, obj):
        rows = (
            obj.evaluations.values('category__name', 'category__order')
            .annotate(total=Sum('score'))
            .order_by('category__order', 'category__name')
        )
        if not rows:
            return '-'
        badges = [
            format_html(
                '<span style="display:inline-block;background:#EFF6FF;border:1px solid #BFDBFE;color:#1E40AF;padding:2px 8px;border-radius:8px;margin:2px;font-size:11px">'
                '<strong>{}</strong>: {} pts</span>',
                r['category__name'], r['total']
            )
            for r in rows
        ]
        return format_html(''.join(badges))
    category_sums_display.short_description = 'Somatório por Categoria'

    def score_badge(self, obj):
        total = obj.total_score()
        max_s = obj.max_possible_score()
        pct = (total / max_s * 100) if max_s > 0 else 0
        color = '#10B981' if pct >= 75 else '#F59E0B' if pct >= 50 else '#EF4444'
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;border-radius:12px;font-weight:bold">'
            '{} / {} pts</span>',
            color, total, max_s
        )
    score_badge.short_description = 'Pontuação Total'

    def total_score_display(self, obj):
        return f"{obj.total_score()} / {obj.max_possible_score()} pontos"
    total_score_display.short_description = 'Pontuação Total'


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ['group', 'category', 'evaluator', 'score_display', 'category_sum_badge', 'group_total_badge', 'updated_at']
    list_filter = ['group', 'category', 'evaluator', 'score']
    search_fields = ['group__title', 'category__name', 'evaluator__name']
    autocomplete_fields = ['group', 'category', 'evaluator']

    def score_display(self, obj):
        colors = {0: '#EF4444', 1: '#F59E0B', 2: '#10B981'}
        labels = {0: 'Não Atende', 1: 'Parcial', 2: 'Plenamente'}
        return format_html(
            '<span style="color:{};font-weight:bold">{} — {}</span>',
            colors[obj.score], obj.score, labels[obj.score]
        )
    score_display.short_description = 'Nota do Avaliador'

    def category_sum_badge(self, obj):
        cat_sum = (
            Evaluation.objects.filter(group_id=obj.group_id, category_id=obj.category_id)
            .aggregate(s=Sum('score'))['s'] or 0
        )
        return format_html(
            '<span style="background:#EFF6FF;border:1px solid #93C5FD;color:#1D4ED8;padding:2px 8px;border-radius:8px;font-weight:bold">'
            '{} pts na categoria</span>',
            cat_sum
        )
    category_sum_badge.short_description = 'Soma da Categoria (Grupo)'

    def group_total_badge(self, obj):
        grp_sum = (
            Evaluation.objects.filter(group_id=obj.group_id)
            .aggregate(s=Sum('score'))['s'] or 0
        )
        return format_html(
            '<span style="background:#F37021;color:#fff;padding:2px 8px;border-radius:8px;font-weight:bold">'
            '{} pts total</span>',
            grp_sum
        )
    group_total_badge.short_description = 'Total do Grupo'




class RaffleDrawnFilter(admin.SimpleListFilter):
    title = 'Situação no sorteio'
    parameter_name = 'drawn'

    def lookups(self, request, model_admin):
        return [('yes', 'Sorteados'), ('no', 'Ainda não sorteados')]

    def queryset(self, request, queryset):
        if self.value() in ('yes', 'no'):
            return queryset.filter(has_won=self.value() == 'yes')
        return queryset


@admin.register(RaffleParticipant)
class RaffleParticipantAdmin(admin.ModelAdmin):
    list_display = ['participant_name', 'participant_unit', 'participant_role', 'active', 'drawn']
    search_fields = ['name', 'unit', 'role']
    list_filter = ['is_active', 'unit', RaffleDrawnFilter]
    ordering = ['name']
    readonly_fields = ['identity', 'name', 'unit', 'role', 'is_active']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            has_won=Exists(RaffleWinner.objects.filter(participant_id=OuterRef('pk'))))

    @admin.display(description='Nome', ordering='name')
    def participant_name(self, obj):
        return obj.name

    @admin.display(description='Unidade', ordering='unit')
    def participant_unit(self, obj):
        return obj.unit

    @admin.display(description='Cargo', ordering='role')
    def participant_role(self, obj):
        return obj.role

    @admin.display(description='Na lista ativa', boolean=True, ordering='is_active')
    def active(self, obj):
        return obj.is_active

    @admin.display(description='Sorteado', boolean=True, ordering='has_won')
    def drawn(self, obj):
        return obj.has_won

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RaffleWinner)
class RaffleWinnerAdmin(admin.ModelAdmin):
    list_display = ['winner_name', 'winner_unit', 'draw_date']
    search_fields = ['name', 'unit']
    list_filter = ['unit', 'drawn_at']
    ordering = ['-drawn_at', '-id']
    date_hierarchy = 'drawn_at'
    readonly_fields = ['participant', 'name', 'unit', 'request_id', 'drawn_at']

    @admin.display(description='Nome', ordering='name')
    def winner_name(self, obj):
        return obj.name

    @admin.display(description='Unidade no sorteio', ordering='unit')
    def winner_unit(self, obj):
        return obj.unit

    @admin.display(description='Data do sorteio', ordering='drawn_at')
    def draw_date(self, obj):
        return obj.drawn_at

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
