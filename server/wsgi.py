"""gunicorn entrypoint: `gunicorn server.wsgi:app`. Tests must not import this."""
from server.app import create_app_from_env

app = create_app_from_env()
