"""Importação e sorteio persistente de participantes."""
import io
import re
import secrets
import unicodedata
import uuid
import zipfile

from django.db import transaction
from django.db.models import F
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from .models import RaffleParticipant, RaffleWinner, RaffleLock
from .views import _read_csv_bytes, _read_xlsx_bytes


def normalize(value):
    value = unicodedata.normalize('NFKD', str(value))
    return ' '.join(''.join(c for c in value if not unicodedata.combining(c)).upper().split())


def identity(name):
    return re.sub(r'[^A-Z0-9]', '', normalize(name))


def parse_participants(rows):
    columns = None
    for index, row in enumerate(rows):
        headers = [normalize(cell) for cell in row]
        name = next((i for i, h in enumerate(headers) if h in ('EDUCADOR', 'NOME', 'NOME COMPLETO')), None)
        unit = next((i for i, h in enumerate(headers) if h.startswith('UNIDADE')), None)
        role = next((i for i, h in enumerate(headers) if h == 'CARGO'), None)
        if None not in (name, unit, role):
            columns = (name, unit, role)
            break
    if columns is None:
        raise ValueError('Cabeçalho não encontrado. Inclua as colunas EDUCADOR (ou NOME), UNIDADE e CARGO.')
    people, rejected, duplicates, blocked = {}, 0, 0, set()
    for row in rows[index + 1:]:
        if not any(str(c).strip() for c in row):
            continue
        values = [' '.join(str(row[i]).split()) if i < len(row) else '' for i in columns]
        name, unit, role = values
        key = identity(name)
        if 'SAIU DO SENAC' in normalize(' '.join(row)):
            if key:
                # A anotação de saída não faz parte da identidade da pessoa.
                clean_name = re.split(r'\s*\(?\s*SAIU DO SENAC', normalize(name))[0]
                blocked.add(identity(clean_name))
            rejected += 1
            continue
        missing = ('', 'SELECIONAR', 'SELECIONE', 'NAO INFORMADO', '-', 'N/A')
        if any(normalize(v) in missing for v in values) or not key:
            rejected += 1
            continue
        if len(name) > 250 or len(unit) > 200 or len(role) > 200:
            raise ValueError('Nome, unidade ou cargo excede o tamanho permitido (250/200/200 caracteres).')
        if key in people:
            duplicates += 1
            continue
        people[key] = {'name': name, 'unit': unit, 'role': role}
    for key in blocked:
        if key in people:
            del people[key]
            rejected += 1
    return people, rejected, duplicates


def lock_raffle():
    # UPDATE obtém bloqueio de escrita também no SQLite; no PostgreSQL,
    # serializa importações e sorteios pela mesma linha, até o commit.
    RaffleLock.objects.filter(pk=1).update(version=F('version') + 1)


def winner_data(winner):
    return {'id': winner.pk, 'name': winner.name, 'unit': winner.unit,
            'drawn_at': winner.drawn_at.isoformat()}


@api_view(['GET'])
def raffle_state(request):
    participants = RaffleParticipant.objects.filter(is_active=True)
    available = participants.filter(winner__isnull=True)
    return Response({
        'total': participants.count(),
        'remaining': available.count(),
        'participants': list(available.values('id', 'name', 'unit')),
        'winners': [winner_data(w) for w in RaffleWinner.objects.order_by('-id')],
    })


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def raffle_import(request):
    uploaded = request.FILES.get('file')
    if not uploaded:
        return Response({'detail': 'Selecione uma planilha CSV ou XLSX.'}, status=400)
    if uploaded.size > 5 * 1024 * 1024:
        return Response({'detail': 'A planilha deve ter no máximo 5 MB.'}, status=400)
    extension = uploaded.name.rsplit('.', 1)[-1].lower()
    if extension not in ('csv', 'xlsx'):
        return Response({'detail': 'Formato inválido. Use CSV ou XLSX.'}, status=400)
    try:
        contents = uploaded.read()
        if extension == 'xlsx':
            with zipfile.ZipFile(io.BytesIO(contents)) as archive:
                if sum(info.file_size for info in archive.infolist()) > 25 * 1024 * 1024:
                    raise ValueError('O conteúdo descompactado da planilha é muito grande.')
            rows = _read_xlsx_bytes(contents)
        else:
            rows = _read_csv_bytes(contents)
        people, rejected, duplicates = parse_participants(rows)
    except Exception as exc:
        # Erros de leitura nunca alteram a base previamente importada.
        return Response({'detail': f'Não foi possível importar a planilha: {exc}'}, status=400)
    if not people:
        return Response({'detail': 'Nenhum participante apto encontrado. A base anterior foi mantida.'}, status=400)
    with transaction.atomic():
        lock_raffle()
        RaffleParticipant.objects.update(is_active=False)
        RaffleParticipant.objects.bulk_create(
            [RaffleParticipant(identity=key, **values, is_active=True)
             for key, values in people.items()],
            update_conflicts=True,
            unique_fields=['identity'],
            update_fields=['name', 'unit', 'role', 'is_active'],
            batch_size=500,
        )
    return Response({'imported': len(people), 'excluded': rejected, 'duplicates': duplicates,
                     'detail': 'Base atualizada. O histórico de sorteados foi preservado.'})


@api_view(['POST'])
def raffle_draw(request):
    try:
        request_id = uuid.UUID(str(request.data.get('request_id', '')))
    except (ValueError, TypeError, AttributeError):
        return Response({'detail': 'Informe um request_id UUID válido.'}, status=400)
    with transaction.atomic():
        lock_raffle()
        existing = RaffleWinner.objects.filter(request_id=request_id).first()
        if existing:
            return Response(winner_data(existing))
        candidates = list(RaffleParticipant.objects.filter(
            is_active=True, winner__isnull=True).values_list('pk', flat=True))
        if not candidates:
            return Response({'detail': 'Todos os participantes aptos já foram sorteados. Importe novos participantes para continuar.'}, status=409)
        person = RaffleParticipant.objects.get(pk=secrets.choice(candidates))
        winner = RaffleWinner.objects.create(
            participant=person, name=person.name, unit=person.unit, request_id=request_id)
    return Response(winner_data(winner), status=201)


@api_view(['POST'])
def raffle_reset(request):
    """Reinicia os sorteios mantendo a lista de participantes importada."""
    with transaction.atomic():
        lock_raffle()
        RaffleWinner.objects.all().delete()
    return Response({'detail': 'Sorteios reiniciados. Todos os participantes ativos podem concorrer novamente.'})
