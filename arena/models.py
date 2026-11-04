from django.db import models


class Category(models.Model):
    """Critério de avaliação (ex: Recursos Visuais, Fundamentação Teórica)."""
    name = models.CharField("Nome da Categoria", max_length=200)
    description = models.TextField("Descrição para o Avaliador", blank=True)
    order = models.PositiveIntegerField("Ordem de Exibição", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Categoria"
        verbose_name_plural = "Categorias"
        ordering = ['order', 'id']

    def __str__(self):
        return self.name


class Group(models.Model):
    """Grupo/projeto participante da arena."""
    title = models.CharField("Título do Projeto", max_length=300)
    authors = models.CharField("Integrantes / Autores", max_length=400)
    unit = models.CharField("Unidade / Eixo", max_length=200, blank=True)
    notes = models.TextField("Observações do Avaliador", blank=True)
    is_revealed = models.BooleanField("Revelado na Cerimônia", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Grupo"
        verbose_name_plural = "Grupos"
        ordering = ['title']

    def __str__(self):
        return self.title

    def total_score(self):
        return sum(e.score for e in self.evaluations.all())

    def evaluations_count(self):
        """Quantidade de avaliações (jurados) recebidas pelo grupo."""
        cat_count = Category.objects.count()
        if cat_count == 0:
            return 0
        from django.db.models import Count, Max
        max_per_cat = (
            self.evaluations.values('category')
            .annotate(total=Count('id'))
            .aggregate(max_total=Max('total'))['max_total']
        )
        return max_per_cat or 0

    def max_possible_score(self):
        evals = max(1, self.evaluations_count())
        return Category.objects.count() * 2 * evals


class Evaluation(models.Model):
    """Nota atribuída por um avaliador a um grupo em uma categoria (0, 1 ou 2 pontos)."""
    SCORE_CHOICES = [
        (0, '0 — Não Atende'),
        (1, '1 — Atende Parcialmente'),
        (2, '2 — Atende Plenamente'),
    ]

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='evaluations', verbose_name="Grupo")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='evaluations', verbose_name="Categoria")
    score = models.SmallIntegerField("Nota", choices=SCORE_CHOICES, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Avaliação"
        verbose_name_plural = "Avaliações"
        ordering = ['group', 'category__order', 'created_at']

    def __str__(self):
        return f"{self.group.title} — {self.category.name}: {self.score} pts"

