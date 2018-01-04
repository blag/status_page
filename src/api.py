import os
import re
import uuid
import simplejson as json
from datetime import datetime

import arrow
import falcon

from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy.orm import (aliased, contains_eager, sessionmaker)
from sqlalchemy.orm.exc import NoResultFound

from models import *
from utils import *


# Configure some things via environment variables
DB_URL = os.environ.get('DB_URL')
# EXTERNAL_JWT_PUBLIC_KEYS = os.environ.get('EXTERNAL_JWTS').split(':')
# INTERNAL_JWT_PUBLIC_KEY = os.environ.get('INTERNAL_JWT')

engine = create_engine(DB_URL, echo=True)

Session = sessionmaker()

Session.configure(bind=engine)

session = Session()

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
        print("You need to create the database\n"
              "\n"
              f"    CREATE DATABASE {db_does_not_exist_match.group('dbname')} \n"
              "        WITH \n"
              "        OWNER = postgres \n"
              "        ENCODING = 'UTF8' \n"
              "        CONNECTION LIMIT = -1;\n")
    elif ext_does_not_exist_match and ext_does_not_exist_match.group('func_name') == 'uuid_generate_v4':
        # psycopg2.ProgrammingError
        print("""You need to run\n"""
              """\n"""
              """    CREATE EXTENSION IF NOT EXISTS """
              f"""'{EXTENSION_MAP[ext_does_not_exist_match.group('func_name')]}';\n""")
    else:
        raise e


# def get_user(key_header_string):
#     username, key = key_header_string.split(':')
#     api_key = session.query(APIKey).filter(key=)
#     return {
#         'username': api_key.username,
#         'bot': api_key.bot,
#     }


# jwt_auth = JWTAuth()

# api_key_auth = JWTKeyAuth(query_function=lambda key: session.query(APIKey).filter())


class StatusRoute(object):
    pass

class ServicesRoute(object):
    def on_get(self, req, resp):
        page = req.params.get('page', 1)

        search_query = req.params.get('q')

        q = session.query(Service)

        if search_query is not None:
            q = q.filter(Service.name.like(f'%{search_query}%') or Service.slug.like(f'%{search_query}%'))

        def service_to_dict(item):
            return {
                "name": item.name,
                "description": item.description,
                "slug": item.slug,
                "groups": [
                    {
                        "url": "a"
                    }
                    for item in item.groups
                ],
            }

class EventsRoute(object):
    def on_get(self, req, resp, service_slug):
        page = req.params.get('page', 1)

        status = req.params.get('status')
        informational = req.params.get('informational')
        before = req.params.get('before')
        after = req.params.get('after')

        q = session.query(Event).join(Service).filter(Service.slug == service_slug)

        if status is not None:
            q = q.filter(Event.status == status)

        if informational is not None:
            q = q.filter(Event.informational == informational)

        if before is not None:
            try:
                before = arrow.get(before).datetime
            except arrow.parser.ParserError as e:
                msg = _("Couldn't parse ISO8601 datetime from 'before' parameter")
                raise falcon.HTTPBadRequest('Bad request', msg)
            else:
                q = q.filter(Event.when < before)

        if after is not None:
            try:
                after = arrow.get(after).datetime
            except arrow.parser.ParserError as e:
                msg = _("Couldn't parse ISO8601 datetime from 'after' parameter")
                raise falcon.HTTPBadRequest('Bad request', msg)
            else:
                q = q.filter(Event.when > after)

        page = paginate(q.order_by(Event.when.desc()), page, 20,
            path=req.path,
            params=req.params,
            # Combine two dictionaries: https://stackoverflow.com/a/26853961
            convert_items_callback=lambda obj: {
            **obj_to_dict(obj), **{
                "url": f"/services/{service_slug}/events/{obj.id}",
                "service": f"{obj.service.name}",
            }
        })

        resp.body = json.dumps(obj_to_dict(page))
        resp.content_type = falcon.MEDIA_JSON
        resp.status = falcon.HTTP_200


class EventRoute(object):
    def on_get(self, req, resp, service_slug, event_id):
        try:
            service = session.query(Service).filter(Service.slug == service_slug).one()
        except NoResultFound as e:
            msg = _(f"There is no service for '{service_slug}'")
            raise falcon.HTTPBadRequest('Bad request', msg)

        try:
            event_id = uuid.UUID(event_id)
        except ValueError as e:
            msg = _("Couldn't parse UUID")
            raise falcon.HTTPBadRequest('Bad request', msg)

        try:
            event = session.query(Event).join(Service).filter(Service.slug == service_slug, Event.id == event_id).one()
        except NoResultFound:
            resp.body = json.dumps({})
            resp.status = falcon.HTTP_400
        else:
            resp.body = json.dumps(event_to_dict(event))
            resp.status = falcon.HTTP_200
        finally:
            resp.content_type = falcon.MEDIA_JSON


class ServiceStatusRoute(object):
    def on_get(self, req, resp, service_slug):
        try:
            service = session.query(Service).filter(Service.slug == service_slug).one()
        except NoResultFound as e:
            msg = _(f"There is no service for '{service_slug}'")
            raise falcon.HTTPBadRequest('Bad request', msg)

        last_up_query = session.query(Event).join(Service).filter(Service.slug == service_slug, Event.status == 'up').order_by(Event.when.desc()).limit(1)

        relevant_events = session.query(Event)\
            .join(Service)\
            .filter(Service.slug == service_slug,
                    last_up_query.subquery('last_up_query').c.when <= Event.when)\
            .order_by(Event.when.desc())

        try:
            event_status = relevant_events[0].status
        except IndexError:
            event_status = None

        resp.body = json.dumps(dict(
            **{
                "url": f"/services/{service_slug}/status",
            },
            **{
                "status": event_status,
                "events": [event_to_dict(event) for event in relevant_events],
            },
        ))


# class Preferences(object):
#     @falcon.before(validate_jwt)
#     def on_get(self, req, resp):





