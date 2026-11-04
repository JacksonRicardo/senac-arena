from django.contrib import admin
from django.utils.html import format_html
from .models import Category, Group, Evaluation


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['order', 'name', 'description_short', 'evaluations_count']
    list_display_links = ['name']
    list_editable = ['order']
    search_fields = ['name', 'description']
    ordering = ['order', 'id']

    def description_short(self, obj):
        return obj.description[:80] + '...' if len(obj.description) > 80 else obj.description
    description_short.short_description = 'Descrição'

    def evaluations_count(self, obj):
        return obj.evaluations.count()
    evaluations_count.short_description = 'Avaliações'


class EvaluationInline(admin.TabularInline):
    model = Evaluation
    extra = 0
    fields = ['category', 'score']
    autocomplete_fields = ['category']


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['title', 'authors', 'unit', 'score_badge', 'is_revealed', 'updated_at']
    list_display_links = ['title']
    list_filter = ['is_revealed', 'unit']
    search_fields = ['title', 'authors', 'unit']
    list_editable = ['is_revealed']
    inlines = [EvaluationInline]
    readonly_fields = ['total_score_display', 'created_at', 'updated_at']
    fieldsets = (
        ('Informações do Projeto', {
            'fields': ('title', 'authors', 'unit')
        }),
        ('Avaliação', {
            'fields': ('notes', 'is_revealed', 'total_score_display')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

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
    score_badge.short_description = 'Pontuação'

    def total_score_display(self, obj):
        return f"{obj.total_score()} / {obj.max_possible_score()} pontos"
    total_score_display.short_description = 'Pontuação Total'


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ['group', 'category', 'score_display', 'updated_at']
    list_filter = ['score', 'category']
    search_fields = ['group__title', 'category__name']
    autocomplete_fields = ['group', 'category']

    def score_display(self, obj):
        colors = {0: '#EF4444', 1: '#F59E0B', 2: '#10B981'}
        labels = {0: 'Não Atende', 1: 'Parcial', 2: 'Plenamente'}
        return format_html(
            '<span style="color:{};font-weight:bold">{} — {}</span>',
            colors[obj.score], obj.score, labels[obj.score]
        )
    score_display.short_description = 'Nota'

