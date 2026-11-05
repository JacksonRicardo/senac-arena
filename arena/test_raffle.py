import io
import uuid
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import RaffleParticipant, RaffleWinner
from .raffle import parse_participants


class RaffleTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def upload(self, text):
        file = SimpleUploadedFile('experts.csv', text.encode('utf-8-sig'), content_type='text/csv')
        return self.client.post('/api/raffle/import/', {'file': file}, format='multipart')

    def draw(self, request_id=None):
        return self.client.post('/api/raffle/draw/',
                                {'request_id': str(request_id or uuid.uuid4())}, format='json')

    def test_actual_header_and_exclusions_and_deduplication(self):
        response = self.upload('Título;;;;\nCamisetas;;;;\nID;EDUCADOR;UNIDADE - SENAC;CARGO;STATUS\n'
                               '1;José Silva;CENTRO;INSTRUTOR;CONCLUÍDO\n'
                               '2; JOSE  SILVA ;CENTRO;INSTRUTOR;CONCLUÍDO\n'
                               '3;Maria;CENTRO;;PENDENTE\n'
                               '4;Joana ( SAIU DO SENAC);CENTRO;INSTRUTOR;CONCLUÍDO\n'
                               '5;Luiza;CENTRO;SELECIONAR;PENDENTE\n'
                               '6;Pedro;;INSTRUTOR;CONCLUÍDO\n')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['imported'], 1)
        self.assertEqual(response.data['excluded'], 4)
        self.assertEqual(response.data['duplicates'], 1)
        self.assertEqual(RaffleParticipant.objects.get().name, 'José Silva')

    def test_departure_in_any_column(self):
        people, rejected, _ = parse_participants([
            ['NOME', 'UNIDADE', 'CARGO', 'STATUS'],
            ['Ana', 'Centro', 'Instrutor', 'saiu do senac'],
        ])
        self.assertFalse(people)
        self.assertEqual(rejected, 1)

    def test_departure_overrides_duplicate_valid_row(self):
        people, _, _ = parse_participants([
            ['NOME', 'UNIDADE', 'CARGO'],
            ['Ana', 'Centro', 'Instrutor'],
            ['Ana (SAIU DO SENAC)', '', ''],
        ])
        self.assertFalse(people)

    def test_never_repeat_and_reimport_preserves_history(self):
        self.upload('NOME;UNIDADE;CARGO\nJosé;Centro;Instrutor\nAna;Zona Sul;Analista\n')
        first, second = self.draw(), self.draw()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.data['name'], second.data['name'])
        self.assertEqual(self.draw().status_code, 409)
        self.upload('NOME;UNIDADE;CARGO\nJOSE;Mossoró;Instrutor\nANA;Centro;Analista\n')
        self.assertEqual(self.draw().status_code, 409)
        self.assertEqual(RaffleWinner.objects.count(), 2)
        self.assertEqual(set(RaffleWinner.objects.values_list('unit', flat=True)), {'Centro', 'Zona Sul'})

    def test_repeated_request_returns_original_winner(self):
        self.upload('NOME;UNIDADE;CARGO\nAna;Centro;Instrutor\nBia;Centro;Instrutor\n')
        request_id = uuid.uuid4()
        first = self.draw(request_id)
        again = self.draw(request_id)
        self.assertEqual(first.data, again.data)
        self.assertEqual(RaffleWinner.objects.count(), 1)

    def test_replacement_deactivates_removed_people(self):
        self.upload('NOME;UNIDADE;CARGO\nAna;Centro;Instrutor\nBia;Centro;Instrutor\n')
        self.upload('NOME;UNIDADE;CARGO\nAna (SAIU DO SENAC);Centro;Instrutor\nBia;Centro;Instrutor\n')
        self.assertEqual(self.draw().data['name'], 'Bia')
        self.assertEqual(self.draw().status_code, 409)

    def test_invalid_or_empty_import_keeps_existing_list(self):
        self.upload('NOME;UNIDADE;CARGO\nAna;Centro;Instrutor\n')
        for text in ('NOME;UNIDADE\nAna;Centro\n', 'NOME;UNIDADE;CARGO\nBia;Centro;\n'):
            self.assertEqual(self.upload(text).status_code, 400)
            self.assertTrue(RaffleParticipant.objects.get().is_active)

    def test_new_participants_allow_more_draws(self):
        self.upload('NOME;UNIDADE;CARGO\nAna;Centro;Instrutor\n')
        self.draw()
        self.upload('NOME;UNIDADE;CARGO\nAna;Centro;Instrutor\nBia;Centro;Instrutor\n')
        state = self.client.get('/api/raffle/').data
        self.assertEqual((state['total'], state['remaining'], len(state['winners'])), (2, 1, 1))
        self.assertEqual(self.draw().data['name'], 'Bia')

    def test_missing_file_invalid_format_and_bad_uuid(self):
        self.assertEqual(self.client.post('/api/raffle/import/', {}, format='multipart').status_code, 400)
        file = SimpleUploadedFile('file.xls', b'bad')
        self.assertEqual(self.client.post('/api/raffle/import/', {'file': file}, format='multipart').status_code, 400)
        self.assertEqual(self.client.post('/api/raffle/draw/', {}, format='json').status_code, 400)

    def test_cp1252_csv(self):
        file = SimpleUploadedFile('experts.csv', 'NOME;UNIDADE;CARGO\nJosé;Mossoró;Instrutor\n'.encode('cp1252'))
        self.assertEqual(self.client.post('/api/raffle/import/', {'file': file}, format='multipart').status_code, 200)
        self.assertEqual(RaffleParticipant.objects.get().unit, 'Mossoró')

    def test_xlsx_upload(self):
        output = io.BytesIO()
        sheet = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        for row in (['NOME', 'UNIDADE', 'CARGO'], ['Ana', 'Centro', 'Instrutor']):
            sheet += '<row>' + ''.join('<c t="inlineStr"><is><t>' + cell + '</t></is></c>' for cell in row) + '</row>'
        sheet += '</sheetData></worksheet>'
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('xl/worksheets/sheet1.xml', sheet)
        file = SimpleUploadedFile('experts.xlsx', output.getvalue())
        self.assertEqual(self.client.post('/api/raffle/import/', {'file': file}, format='multipart').status_code, 200)
        self.assertEqual(RaffleParticipant.objects.get().name, 'Ana')

    def test_reset_clears_history_and_releases_active_participants(self):
        self.upload('NOME;UNIDADE;CARGO\nAna;Centro;Instrutor\nBia;Centro;Instrutor\n')
        self.draw()
        self.upload('NOME;UNIDADE;CARGO\nAna;Centro;Instrutor\n')
        self.assertEqual(self.client.post('/api/raffle/reset/', {}, format='json').status_code, 200)
        self.assertEqual(RaffleWinner.objects.count(), 0)
        self.assertEqual(RaffleParticipant.objects.count(), 2)
        state = self.client.get('/api/raffle/').data
        self.assertEqual((state['total'], state['remaining'], state['winners']), (1, 1, []))
        self.assertEqual(self.draw().data['name'], 'Ana')
        self.assertEqual(self.draw().status_code, 409)

    def test_reset_is_post_only_and_can_be_repeated(self):
        self.assertEqual(self.client.get('/api/raffle/reset/').status_code, 405)
        for _ in range(2):
            self.assertEqual(self.client.post('/api/raffle/reset/', {}, format='json').status_code, 200)
        self.assertEqual(self.client.get('/api/raffle/').data['remaining'], 0)

    def test_home_includes_new_tab(self):
        response = self.client.get('/')
        self.assertContains(response, 'tab-raffle')
        self.assertContains(response, 'raffle.js')

    def test_participant_import_is_in_import_tab(self):
        response = self.client.get('/')
        html = response.content.decode('utf-8')
        import_tab = html.split('id="tab-import"', 1)[1].split('</section>', 1)[0]
        raffle_tab = html.split('id="tab-raffle"', 1)[1].split('</section>', 1)[0]
        self.assertIn('id="raffle-file"', import_tab)
        self.assertIn('id="raffle-reset"', import_tab)
        self.assertNotIn('id="raffle-file"', raffle_tab)
        self.assertIn('Sua chance continua até a sua vitória chegar.', raffle_tab)


class RaffleAdminTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_superuser(
            username='raffle-admin', email='admin@example.com', password='test-password'))
        self.ana = RaffleParticipant.objects.create(
            identity='ANA', name='Ana', unit='Centro', role='Instrutora')
        self.bia = RaffleParticipant.objects.create(
            identity='BIA', name='Bia', unit='Zona Sul', role='Analista', is_active=False)
        self.winner = RaffleWinner.objects.create(
            participant=self.ana, name='Ana', unit='Centro', request_id=uuid.uuid4())

    def test_admin_lists_all_imported_participants_and_filters_winners(self):
        response = self.client.get('/admin/arena/raffleparticipant/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context['cl'].queryset), {self.ana, self.bia})
        self.assertContains(response, 'Participantes da planilha')
        for value, person in [('yes', self.ana), ('no', self.bia)]:
            response = self.client.get('/admin/arena/raffleparticipant/', {'drawn': value})
            self.assertEqual(list(response.context['cl'].queryset), [person])
        response = self.client.get('/admin/arena/raffleparticipant/', {'q': 'Zona Sul'})
        self.assertEqual(list(response.context['cl'].queryset), [self.bia])

    def test_admin_winners_keep_original_details_after_reimport(self):
        self.ana.unit = 'Mossoró'
        self.ana.save()
        response = self.client.get('/admin/arena/rafflewinner/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sorteados')
        self.assertContains(response, 'Centro')
        self.assertNotContains(response, 'Mossoró')
        self.assertEqual(list(response.context['cl'].queryset), [self.winner])

    def test_admin_records_are_read_only_and_require_login(self):
        for model, obj in [('raffleparticipant', self.ana), ('rafflewinner', self.winner)]:
            url = f'/admin/arena/{model}/'
            self.assertEqual(self.client.get(url + 'add/').status_code, 403)
            self.assertEqual(self.client.get(url + f'{obj.pk}/delete/').status_code, 403)
            response = self.client.post(url + f'{obj.pk}/change/', {'name': 'Alterado'})
            self.assertEqual(response.status_code, 302)
            obj.refresh_from_db()
            self.assertEqual(obj.name, 'Ana')
        self.client.logout()
        self.assertEqual(self.client.get('/admin/arena/rafflewinner/').status_code, 302)
