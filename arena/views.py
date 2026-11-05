import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET

from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response

from .models import Category, Group, Evaluator, Evaluation
from .serializers import (
    CategorySerializer, GroupSerializer, EvaluatorSerializer,
    EvaluationSubmitSerializer
)


VALID_MODALITIES = ('CATEGORIA_1', 'CATEGORIA_2', 'CATEGORIA_4')
MODALITY_LABELS = {
    'CATEGORIA_1': 'Categoria 1: Educação Inovadora — Geral',
    'CATEGORIA_2': 'Categoria 2: Prática Pedagógica Integradora Coletiva',
    'CATEGORIA_4': 'Categoria 4: Projeto Integrador Individual',
}


def index(request):
    """Serve o frontend SPA."""
    return render(request, 'arena/index.html')


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class EvaluatorViewSet(viewsets.ModelViewSet):
    queryset = Evaluator.objects.prefetch_related('evaluations').all()
    serializer_class = EvaluatorSerializer


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.prefetch_related('evaluations').all()
    serializer_class = GroupSerializer

    def get_queryset(self):
        # Remove automaticamente quaisquer projetos antigos cadastrados em modalidades anteriores
        if Group.objects.exclude(unit__in=VALID_MODALITIES).exists():
            Group.objects.exclude(unit__in=VALID_MODALITIES).delete()
            Evaluator.objects.filter(evaluations__isnull=True).delete()
        return Group.objects.prefetch_related('evaluations', 'evaluations__evaluator').all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        Evaluator.objects.filter(evaluations__isnull=True).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _col_letters_to_index(cell_ref: str) -> int:
    """Converte referência de célula Excel (ex: 'A1', 'H2', 'AA1') em índice 0-based."""
    letters = ''.join(ch for ch in cell_ref if ch.isalpha()).upper()
    if not letters:
        return 0
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord('A') + 1)
    return idx - 1


def _read_xlsx_bytes(file_bytes: bytes) -> list[list[str]]:
    """Lê qualquer arquivo .xlsx (Microsoft Forms / Excel) usando bibliotecas nativas do Python."""
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        shared_strings = []
        if 'xl/sharedStrings.xml' in zf.namelist():
            ss_root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
            for si in ss_root.iter():
                if si.tag.endswith('}si') or si.tag == 'si':
                    texts = [
                        (t.text or '')
                        for t in si.iter()
                        if t.tag.endswith('}t') or t.tag == 't'
                    ]
                    shared_strings.append(''.join(texts))

        sheet_names = sorted(
            name for name in zf.namelist()
            if name.startswith('xl/worksheets/sheet') and name.endswith('.xml')
        )
        if not sheet_names:
            raise ValueError('Nenhuma aba encontrada no arquivo .xlsx.')

        sheet_root = ET.fromstring(zf.read(sheet_names[0]))
        rows = []
        for row_el in sheet_root.iter():
            if not (row_el.tag.endswith('}row') or row_el.tag == 'row'):
                continue
            row_map = {}
            next_col = 0
            for cell_el in row_el:
                if not (cell_el.tag.endswith('}c') or cell_el.tag == 'c'):
                    continue
                ref = cell_el.attrib.get('r', '')
                col_idx = _col_letters_to_index(ref) if ref else next_col
                next_col = col_idx + 1
                cell_type = cell_el.attrib.get('t', '')

                val_str = ''
                if cell_type == 'inlineStr':
                    texts = [
                        (t.text or '')
                        for t in cell_el.iter()
                        if t.tag.endswith('}t') or t.tag == 't'
                    ]
                    val_str = ''.join(texts)
                else:
                    v_el = None
                    for child in cell_el:
                        if child.tag.endswith('}v') or child.tag == 'v':
                            v_el = child
                            break
                    if v_el is not None and v_el.text is not None:
                        raw_v = v_el.text
                        if cell_type == 's':
                            try:
                                val_str = shared_strings[int(raw_v)]
                            except (ValueError, IndexError):
                                val_str = raw_v
                        else:
                            val_str = raw_v
                row_map[col_idx] = val_str

            if row_map:
                max_col = max(row_map.keys())
                row_list = [row_map.get(i, '') for i in range(max_col + 1)]
                if any(str(c).strip() for c in row_list):
                    rows.append(row_list)
        return rows


def _read_csv_bytes(file_bytes: bytes) -> list[list[str]]:
    """Lê arquivo .csv exportado."""
    text = None
    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            text = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = file_bytes.decode('utf-8', errors='replace')

    first_line = text.splitlines()[0] if text.splitlines() else ''
    delimiter = ';' if first_line.count(';') > first_line.count(',') else ','
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [row for row in reader if any(str(c).strip() for c in row)]


def _parse_rubric_score(raw_val: str):
    """Extrai a pontuação (0, 1 ou 2) de respostas do Forms como '1 - atende parcialmente (...)'."""
    s = str(raw_val or '').strip()
    if not s:
        return None
    m = re.match(r'^\s*([012])(?:\b|\s|-)', s)
    if m:
        return int(m.group(1))
    lower = s.lower()
    if 'não atende' in lower or 'nao atende' in lower:
        return 0
    if 'parcialmente' in lower:
        return 1
    if 'atende' in lower:
        return 2
    return None


def _clean_evaluator_name(raw_name: str) -> tuple[str, str]:
    """Extrai (nome, cargo) do avaliador (ex: '1. Daniela Papelbaum – Gerente...' -> ('Daniela Papelbaum', 'Gerente...'))."""
    s = ' '.join(str(raw_name or '').strip().split())
    s = re.sub(r'^\d+[\.\)\-\s]+', '', s).strip()
    parts = re.split(r'\s+[–—-]\s+', s, maxsplit=1)
    name = parts[0].strip()
    role = parts[1].strip() if len(parts) > 1 and parts[1].strip() else ''
    return name, role


def _split_authors_and_title(raw_group: str) -> tuple[str, str]:
    """Separa 'Autores | Título' ou 'Autores, com a prática Título' vindo da coluna de grupo do Forms."""
    s = ' '.join(str(raw_group or '').strip().split())
    if '|' in s:
        parts = [p.strip() for p in s.split('|', 1)]
        authors = parts[0] or 'Participante'
        title = parts[1] or parts[0]
        return authors, title
    parts = re.split(r',?\s+com\s+a\s+pr[áa]tica\s+', s, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return 'Participante', s


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def import_spreadsheet(request):
    """Importa a planilha do Microsoft Forms (Categoria 1, Categoria 2 ou Categoria 4) e computa os resultados."""
    modality = str(request.data.get('modality', '')).strip().upper()
    if modality not in VALID_MODALITIES:
        return Response(
            {'detail': 'Categoria inválida. Informe CATEGORIA_1, CATEGORIA_2 ou CATEGORIA_4.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return Response(
            {'detail': 'Nenhum arquivo enviado.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    file_bytes = uploaded_file.read()
    filename = (uploaded_file.name or '').lower()

    try:
        if filename.endswith('.csv'):
            rows = _read_csv_bytes(file_bytes)
        else:
            try:
                rows = _read_xlsx_bytes(file_bytes)
            except zipfile.BadZipFile:
                rows = _read_csv_bytes(file_bytes)
    except Exception as exc:
        return Response(
            {'detail': f'Não foi possível ler a planilha: {exc}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if len(rows) < 2:
        return Response(
            {'detail': 'A planilha está vazia ou não possui linhas de respostas.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    headers = [' '.join(str(h or '').strip().split()) for h in rows[0]]
    data_rows = rows[1:]
    modality_label = MODALITY_LABELS.get(modality, modality)

    # Remove grupos antigos desta modalidade e grupos legados
    Group.objects.filter(unit__iexact=modality).delete()
    Group.objects.exclude(unit__in=VALID_MODALITIES).delete()

    rows_processed = 0

    if modality in ('CATEGORIA_2', 'CATEGORIA_4'):
        # Votação direta: cada linha da planilha representa 1 voto para o grupo selecionado
        group_col_idx = None
        for idx, h in enumerate(headers):
            hl = h.lower()
            if any(k in hl for k in ('categoria', 'prática', 'pratica', 'projeto', 'grupo', 'trabalho', 'coletiva', 'individual')):
                group_col_idx = idx
                break
        if group_col_idx is None:
            group_col_idx = len(headers) - 1

        votes_by_project = {}
        for row in data_rows:
            if len(row) <= group_col_idx:
                continue
            raw_group = str(row[group_col_idx] or '').strip()
            if not raw_group:
                continue
            authors, title = _split_authors_and_title(raw_group)
            key = title.lower()
            if key not in votes_by_project:
                votes_by_project[key] = {
                    'title': title,
                    'authors': authors,
                    'votes': 0,
                }
            votes_by_project[key]['votes'] += 1
            rows_processed += 1

        if not votes_by_project:
            return Response(
                {'detail': 'Nenhum voto válido encontrado na coluna de projetos da planilha.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        for info in votes_by_project.values():
            Group.objects.create(
                title=info['title'],
                authors=info['authors'],
                unit=modality,
                notes=str(info['votes']),
                is_revealed=False
            )
    else:
        # CATEGORIA_1: Avaliação por critérios/rúbricas (0 a 2 pontos por critério)
        eval_col_idx = None
        for idx, h in enumerate(headers):
            hl = h.lower()
            if 'avaliador' in hl or 'jurado' in hl:
                eval_col_idx = idx
                break
        if eval_col_idx is None:
            eval_col_idx = 5 if len(headers) > 6 else 0

        group_col_idx = eval_col_idx + 1
        for idx in range(eval_col_idx + 1, len(headers)):
            hl = headers[idx].lower()
            if any(k in hl for k in ('categoria', 'prática', 'pratica', 'projeto', 'grupo', 'trabalho', 'coletiva', 'individual')):
                group_col_idx = idx
                break

        rubric_cols = []
        for idx in range(group_col_idx + 1, len(headers)):
            col_name = headers[idx]
            if col_name:
                rubric_cols.append((idx, col_name))

        if not rubric_cols:
            return Response(
                {'detail': 'Não foram encontradas as colunas de critérios/rúbricas na planilha da Categoria 1.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        col_to_category = {}
        active_category_ids = []
        for order_idx, (col_idx, col_name) in enumerate(rubric_cols, start=1):
            cat = Category.objects.filter(name__iexact=col_name).first()
            if not cat:
                cat = Category.objects.create(
                    name=col_name,
                    description='Critério oficial importado da planilha Microsoft Forms (0 a 2 pontos).',
                    order=order_idx
                )
            else:
                if cat.order != order_idx:
                    cat.order = order_idx
                    cat.save(update_fields=['order'])
            col_to_category[col_idx] = cat
            active_category_ids.append(cat.id)

        Category.objects.exclude(id__in=active_category_ids).filter(evaluations__isnull=True).delete()

        for row in data_rows:
            if len(row) <= group_col_idx:
                continue
            raw_eval = row[eval_col_idx] if eval_col_idx < len(row) else ''
            raw_group = row[group_col_idx] if group_col_idx < len(row) else ''

            eval_name, eval_role = _clean_evaluator_name(raw_eval)
            if not eval_name or not str(raw_group).strip():
                continue

            authors, title = _split_authors_and_title(raw_group)

            evaluator = Evaluator.objects.filter(name__iexact=eval_name).first()
            if not evaluator:
                evaluator = Evaluator.objects.create(
                    name=eval_name,
                    role=eval_role or modality_label
                )
            elif eval_role and evaluator.role != eval_role:
                evaluator.role = eval_role
                evaluator.save(update_fields=['role'])

            group = Group.objects.filter(title__iexact=title, unit=modality).first()
            if not group:
                group = Group.objects.create(
                    title=title,
                    authors=authors,
                    unit=modality,
                    is_revealed=False
                )

            row_has_score = False
            for col_idx, cat in col_to_category.items():
                cell_val = row[col_idx] if col_idx < len(row) else ''
                score = _parse_rubric_score(cell_val)
                if score is not None:
                    Evaluation.objects.update_or_create(
                        group=group,
                        category=cat,
                        evaluator=evaluator,
                        defaults={'score': score}
                    )
                    row_has_score = True

            if row_has_score:
                rows_processed += 1

    Evaluator.objects.filter(evaluations__isnull=True).delete()

    categories_qs = Category.objects.all()
    groups_qs = Group.objects.prefetch_related('evaluations', 'evaluations__evaluator').all()
    evaluators_qs = Evaluator.objects.prefetch_related('evaluations').all()

    unit_word = 'voto(s) computado(s)' if modality in ('CATEGORIA_2', 'CATEGORIA_4') else 'avaliação(ões) processada(s)'
    return Response({
        'detail': f'Planilha de {modality_label} importada com sucesso ({rows_processed} {unit_word}).',
        'modality': modality,
        'rows_processed': rows_processed,
        'categories': CategorySerializer(categories_qs, many=True).data,
        'groups': GroupSerializer(groups_qs, many=True).data,
        'evaluators': EvaluatorSerializer(evaluators_qs, many=True).data,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
def clear_modality(request):
    """Remove os grupos e avaliações de uma modalidade específica (CATEGORIA_1, CATEGORIA_2, CATEGORIA_4 ou ALL)."""
    modality = str(request.data.get('modality', '')).strip().upper()
    if modality not in (*VALID_MODALITIES, 'ALL'):
        return Response({'detail': 'Modalidade inválida.'}, status=status.HTTP_400_BAD_REQUEST)

    if modality == 'ALL':
        Group.objects.all().delete()
        Evaluator.objects.all().delete()
    else:
        Group.objects.filter(unit__iexact=modality).delete()
        Group.objects.exclude(unit__in=VALID_MODALITIES).delete()
        Evaluator.objects.filter(evaluations__isnull=True).delete()

    categories_qs = Category.objects.all()
    groups_qs = Group.objects.prefetch_related('evaluations', 'evaluations__evaluator').all()
    evaluators_qs = Evaluator.objects.prefetch_related('evaluations').all()

    return Response({
        'detail': f'Dados da modalidade {modality} removidos.',
        'categories': CategorySerializer(categories_qs, many=True).data,
        'groups': GroupSerializer(groups_qs, many=True).data,
        'evaluators': EvaluatorSerializer(evaluators_qs, many=True).data,
    })


@api_view(['POST'])
def submit_evaluation(request):
    """Recebe as notas de um avaliador para um grupo e soma no banco (1 voto por avaliador/grupo)."""
    ser = EvaluationSubmitSerializer(data=request.data)
    if not ser.is_valid():
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

    data = ser.validated_data
    group = Group.objects.filter(id=data['group_id']).first()
    if not group:
        return Response({'detail': 'Grupo não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    evaluator = Evaluator.objects.filter(id=data['evaluator_id']).first()
    if not evaluator:
        return Response({'detail': 'Avaliador não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    if Evaluation.objects.filter(group=group, evaluator=evaluator).exists():
        return Response(
            {'detail': f'O avaliador "{evaluator.name}" já votou no grupo "{group.title}"! Cada avaliador só pode votar uma vez por grupo.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    new_note = data.get('notes', '').strip()
    if new_note:
        formatted_note = f"• [{evaluator.name}]: {new_note}"
        if group.notes and group.notes.strip():
            group.notes = f"{group.notes.strip()}\n{formatted_note}"
        else:
            group.notes = formatted_note
        group.save()

    for cat_id_str, score in data['scores'].items():
        cat_id = int(cat_id_str)
        Evaluation.objects.create(
            group=group,
            category_id=cat_id,
            evaluator=evaluator,
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
    """Reseta is_revealed dos grupos (opcionalmente filtrado por modalidade/unit)."""
    modality = str(request.data.get('modality', '')).strip().upper() if isinstance(request.data, dict) else ''
    if modality in VALID_MODALITIES:
        Group.objects.filter(unit__iexact=modality).update(is_revealed=False)
    else:
        Group.objects.all().update(is_revealed=False)
    return Response({'detail': 'Cerimônia reiniciada.'})


