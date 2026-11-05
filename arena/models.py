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


class Evaluator(models.Model):
    """Avaliador / Jurado cadastrado na arena."""
    name = models.CharField("Nome do Avaliador", max_length=200)
    role = models.CharField("Cargo / Área / Unidade", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Avaliador"
        verbose_name_plural = "Avaliadores"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.role})" if self.role else self.name


class Evaluation(models.Model):
    """Nota atribuída por um avaliador a um grupo em uma categoria (0, 1 ou 2 pontos)."""
    SCORE_CHOICES = [
        (0, '0 — Não Atende'),
        (1, '1 — Atende Parcialmente'),
        (2, '2 — Atende Plenamente'),
    ]

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='evaluations', verbose_name="Grupo")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='evaluations', verbose_name="Categoria")
    evaluator = models.ForeignKey(
        Evaluator, on_delete=models.CASCADE,
        related_name='evaluations', verbose_name="Avaliador",
        null=True, blank=True
    )
    score = models.SmallIntegerField("Nota", choices=SCORE_CHOICES, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Avaliação"
        verbose_name_plural = "Avaliações"
        unique_together = [('group', 'category', 'evaluator')]
        ordering = ['group', 'category__order', 'created_at']

    def __str__(self):
        eval_name = f" [{self.evaluator.name}]" if self.evaluator else ""
        return f"{self.group.title} — {self.category.name}{eval_name}: {self.score} pts"



class RaffleLock(models.Model):
    """Linha única que serializa sorteios e importações."""
    version = models.PositiveBigIntegerField(default=0)


class RaffleParticipant(models.Model):
    identity = models.CharField(max_length=250, unique=True)
    name = models.CharField(max_length=250)
    unit = models.CharField(max_length=200)
    role = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Participante da planilha'
        verbose_name_plural = 'Participantes da planilha'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} — {self.unit}"


class RaffleWinner(models.Model):
    participant = models.OneToOneField(
        RaffleParticipant, on_delete=models.PROTECT, related_name='winner')
    name = models.CharField(max_length=250)
    unit = models.CharField(max_length=200)
    request_id = models.UUIDField(unique=True)
    drawn_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Sorteado'
        verbose_name_plural = 'Sorteados'

    def __str__(self):
        return f"{self.name} — {self.unit}"
