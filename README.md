# Senac Arena — Educação Inovadora 2026

Sistema de avaliação e ranking para o evento **Melhores Práticas 2026** do Senac Brasil.

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Backend | Django 4.2 LTS |
| API | Django REST Framework |
| Admin | django-jazzmin |
| Banco | PostgreSQL |
| Frontend | Tailwind CSS (CDN) + Vanilla JS |

---

## Configuração Rápida (Desenvolvimento)

### 1. Pré-requisitos
- Python 3.10+
- PostgreSQL rodando localmente
- pip / venv

### 2. Instalação

```bash
# Clone ou entre na pasta
cd senac_arena

# Crie e ative o virtualenv
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

# Instale as dependências de dev
pip install -r requirements/dev.txt

# Configure o .env
cp .env.example .env
# Edite .env com suas credenciais do PostgreSQL
```

### 3. Banco de Dados

Crie o banco no PostgreSQL:
```sql
CREATE DATABASE senac_arena;
```

### 4. Migrations e Superusuário

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 5. Rodando

```bash
python manage.py runserver
```

Acesse:
- **Frontend**: http://localhost:8000/
- **Admin (Jazzmin)**: http://localhost:8000/admin/
- **API (DRF)**: http://localhost:8000/api/

---

## Endpoints da API

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/categories/` | Lista categorias |
| POST | `/api/categories/` | Cria categoria |
| PATCH | `/api/categories/{id}/` | Edita categoria |
| DELETE | `/api/categories/{id}/` | Remove categoria |
| GET | `/api/groups/` | Lista grupos com scores |
| POST | `/api/groups/` | Cria grupo |
| DELETE | `/api/groups/{id}/` | Remove grupo |
| POST | `/api/evaluate/` | Submete avaliação |
| POST | `/api/groups/{id}/reveal/` | Revela grupo na cerimônia |
| POST | `/api/ceremony/reset/` | Reseta cerimônia |

---

## Deploy (Produção)

```bash
pip install -r requirements/prod.txt
export DJANGO_SETTINGS_MODULE=config.settings.prod
python manage.py collectstatic --noinput
gunicorn config.wsgi:application
```

---

## Estrutura

```
senac_arena/
├── config/          # Projeto Django (settings, urls, wsgi, asgi)
├── arena/           # App principal (models, views, serializers, admin)
├── requirements/    # base.txt | dev.txt | prod.txt
├── manage.py
└── .env.example
```

