import gettext
import logging.config
import os
import re

import falcon

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import (scoped_session, sessionmaker)

# We import this so it registers its JSON encoder function
from .api import (
    RootRoute, StatusRoute, ServicesRoute, ServiceRoute, ServiceStatusRoute,
    EventsRoute, EventRoute, PermissionsRoute, PermissionRoute, UserPermissionsRoute, APIKeyRoute,
)
from .middleware import SQLAlchemySessionManager


# Configure some things via environment variables
DB_URL = os.environ.get(
    'DB_URL',
    '{db_driver}://{db_username}:{db_password}@{db_host}:{db_port}/{db_name}'.format(
        db_driver=os.environ.get('DB_DRIVER', 'postgresql'),
        db_username=os.environ.get('DB_USER', 'postgres'),
        db_password=os.environ.get('DB_PASSWORD', ''),
        db_host=os.environ.get('DB_HOST', 'localhost'),
        db_port=os.environ.get('DB_PORT', '5432'),
        db_name=os.environ.get('DB_NAME', 'postgres')))

engine = create_engine(DB_URL, echo=True)

session_factory = sessionmaker()

session_factory.configure(bind=engine)

Session = scoped_session(session_factory)

logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': True,
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'api': {
            'handlers': ['console'],
            'level': 'AUDIT',
        },
        'app': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
})

# Install this as a built-in for the entire application
gettext.install('status_page')


def create_app():
    # api = falcon.API(middleware=[auth_middleware])
    api = falcon.API(middleware=[SQLAlchemySessionManager(Session)])
    api.add_route('/', RootRoute())
    api.add_route('/status', StatusRoute())
    api.add_route('/services', ServicesRoute())
    api.add_route('/services/{service_slug}', ServiceRoute())
    api.add_route('/services/{service_slug}/status', ServiceStatusRoute())
    api.add_route('/services/{service_slug}/events', EventsRoute())
    api.add_route('/services/{service_slug}/events/{event_id}', EventRoute())
    api.add_route('/services/{service_slug}/permissions', PermissionsRoute())
    api.add_route('/services/{service_slug}/permissions/{permission_id}', PermissionRoute())
    api.add_route('/users/{username}/permissions', UserPermissionsRoute())
    api.add_route('/api-keys', APIKeyRoute())
    return api


def get_app():
    return create_app()


if __name__ == '__main__':
    Base = declarative_base()

    db_dne_rgx = re.compile(r'''\((?P<error>[\w.]+)\) FATAL:\s+database "(?P<dbname>\w+)" does not exist\n*''')
    ext_dne_rgx = re.compile(r'''\((?P<error>[\w.]+)\) FATAL:\s+function (?P<func_name>\w+)(?P<func_args>\([^)]*\))? does not exist''')

    EXTENSION_MAP = {
        'uuid_generate_v4': 'uuid-ossp',
    }

    try:
        Base.metadata.create_all(engine)
    except Exception as e:
        db_does_not_exist_match = db_dne_rgx.match(e.args[0])
        ext_does_not_exist_match = ext_dne_rgx.match(e.args[0])

        if db_does_not_exist_match:
            # psycopg2.OperationalError
            print(
                "You need to create the database\n"
                "\n"
                f"    CREATE DATABASE {db_does_not_exist_match.group('dbname')} \n"
                "        WITH \n"
                "        OWNER = postgres \n"
                "        ENCODING = 'UTF8' \n"
                "        CONNECTION LIMIT = -1;\n")
        elif ext_does_not_exist_match and ext_does_not_exist_match.group('func_name') == 'uuid_generate_v4':
            # psycopg2.ProgrammingError
            print(
                """You need to run\n"""
                """\n"""
                """    CREATE EXTENSION IF NOT EXISTS """
                f"""'{EXTENSION_MAP[ext_does_not_exist_match.group('func_name')]}';\n""")
        else:
            raise e

application = get_app()
