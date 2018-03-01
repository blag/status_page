import os
import uuid
from collections import OrderedDict
from datetime import (datetime, timedelta)

import falcon
from falcon.media.validators import jsonschema
import jwt
import pytz

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (aliased, contains_eager)
from sqlalchemy.orm.exc import NoResultFound

from .models import *
from .utils import *


SITE_ADMINS = os.environ.get('STATUS_PAGE_SITE_ADMINS').split(',')

LANDING_PAGE_PUBLIC_KEY = os.environ.get('LANDING_PAGE_JWT_PUBLIC_KEY').encode('utf-8')

STATUS_PAGE_PRIVATE_KEY = os.environ.get('STATUS_PAGE_JWT_PRIVATE_KEY').encode('utf-8')
STATUS_PAGE_PUBLIC_KEY = os.environ.get('STATUS_PAGE_JWT_PUBLIC_KEY').encode('utf-8')

HTTP_HEADER_PREFIX = os.environ.get('HTTP_HEADER_PREFIX', 'JWT')


def get_user_dict(data):
    user_dict = data['user_dict']

    user_dict['username'] = user_dict['username'].replace('@corpmz.com', '')
    user_dict['authentication_method'] = 'Landing page JWT'

    return user_dict


def verify_is_not_bot(payload):
    try:
        if payload['bot']:
            err = _("You cannot use a bot key")
        else:
            err = None
    except KeyError:
        err = _("The 'bot' key is missing from the JWT payload")

    return err


def verify_is_bot(payload):
    try:
        if not payload['bot']:
            err = _("You must use a bot key")
        else:
            err = None
    except KeyError:
        err = _("The 'bot' key is missing from the JWT payload")

    return err


def add_authentication_method(data):
    data['authentication_method'] = "Self JWT"
    return data


landing_page_auth = JWTAuth(
    public_key=LANDING_PAGE_PUBLIC_KEY, algorithm='RS512',
    http_header_prefix=HTTP_HEADER_PREFIX, options={'verify_exp': True},
    userdata_function=get_user_dict)

status_page_human_auth = JWTAPIKeyAuth(
    private_key=STATUS_PAGE_PRIVATE_KEY, public_key=STATUS_PAGE_PUBLIC_KEY, algorithm='RS512',
    http_header_prefix=HTTP_HEADER_PREFIX, options={'verify_exp': True},
    verify_function=verify_is_not_bot, userdata_function=add_authentication_method)

status_page_bot_auth = JWTAPIKeyAuth(
    private_key=STATUS_PAGE_PRIVATE_KEY, public_key=STATUS_PAGE_PUBLIC_KEY, algorithm='RS512',
    http_header_prefix=HTTP_HEADER_PREFIX, options={'verify_exp': False},
    verify_function=verify_is_bot, userdata_function=add_authentication_method)


logger = logging.getLogger(__name__)


class RootRoute(object):
    def on_get(self, req, resp):
        resp.media = {
            "name": "Status Server",
            "description": "Welcome to the REST server for the internal services status page. "
                           "Unlike most things that call themselves RESTful, this server actually "
                           "supports HTTP verbs to the fullest extent possible, so try an OPTIONS "
                           "request at different endpoints to see the various supported query "
                           "parameters. In fact, this documentation is probably the least RESTful "
                           "part of this API!",
            "features": [
                "Collects up/down events from system checks (eg: Sensu, Datadog, Mirad, OpsGenie)",
                "Single source for service status",
                "User-based permissions scheme",
                "JWT authentication",
                "Integration with the internal landing page ( https://mz/ )",
            ],
            "todo": [
                "Individual user preferences",
                "Ephemeral (one time) subscriptions for updates",
            ],
            "routes": {
                "Status List": {
                    "url": "/status",
                    "description": "List the status of all registered services",
                },
                "Service List": {
                    "url": "/services",
                    "description": "List of registered services",
                },
                "Service Details": {
                    "url": "/services/{{ slug }}",
                    "description": "View the details of a registered service",
                },
                "Service Status": {
                    "url": "/services/{{ slug }}/status",
                    "description": "View the current status for a specific service",
                },
                "Events List": {
                    "url": "/services/{{ slug }}/events",
                    "description": "View events for a specific service",
                },
                "Event Detail": {
                    "url": "/services/{{ slug }}/events/{{ event_uuid }}",
                    "description": "View the details for a specific event",
                },
                "Service Permissions List": {
                    "url": "/services/{{ slug }}/permissions",
                    "description": "List all of the users who have permissons for a specific service",
                },
                "Service Permission Detail": {
                    "url": "/services/{{ slug }}/permissions/{{ permissions_uuid }}",
                    "description": "View the details for a specific service permission",
                },
                "User Permissions List": {
                    "url": "/user/{{ username }}/permissions",
                    "description": "List the permissions for a specific user",
                },
                "API Keys": {
                    "url": "/api-keys",
                    "description": "Get an API key for a user or an updater bot",
                },
            },
        }


class StatusRoute(object):
    def on_get(self, req, resp):
        last_up = self.db.query(Event.service_id, func.max(Event.when).label('when'))\
            .filter(Event.status == 'up')\
            .group_by(Event.service_id)

        last_up_subquery = last_up.subquery('last_up_subquery')

        # Not sure if this is strictly required, since SQLAlchemy doesn't seem to be running any
        # additional queries when it loads event.service.slug in the loop below, but this is
        # working
        service_alias = aliased(Service)

        relevant_events = self.db.query(Event)\
            .join(service_alias, service_alias.id == Event.service_id)\
            .join(last_up_subquery, (last_up_subquery.c.when <= Event.when) &
                                    (last_up_subquery.c.service_id == Event.service_id))\
            .order_by(service_alias.name.asc(), Event.when.desc())\
            .options(contains_eager(Event.service, alias=service_alias))

        events_result = {}
        last_service_id = None
        for event in relevant_events:
            if event.service_id != last_service_id:
                events_result[event.service.name] = {
                    "url": f"/services/{event.service.slug}",
                    "status": event.status,
                    "events": [event_to_dict(event)],
                }

                last_service_id = event.service_id
            else:
                events_result[event.service.name]['events'].append(event_to_dict(event))

        resp.media = {
            "url": "/status",
            "results": events_result,
        }


class ServicesRoute(object):
    def on_options(self, req, resp):
        resp.media = {
            "q": {
                "type": "string",
                "description": _("Search by service name"),
            },
        }

    def on_get(self, req, resp):
        page_number = req.get_param_as_int('page')

        search_query = req.get_param('q')

        q = self.db.query(Service)

        if search_query is not None:
            q = q.filter(Service.name.ilike(f'%{search_query}%'))

        page = paginate(q.order_by(Service.name.asc()), page_number, 20,
                        path=req.path,
                        params=req.params,
                        convert_items_callback=service_to_dict)

        resp.media = obj_to_dict(page)

    @jsonschema.validate({
        "$schema": "http://json-schema.org/draft-06/schema#",
        "title": "Service",
        "description": "Register a new service",
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "minLength": 4,
            },
            "description": {
                "type": "string",
                # Try to force users to create reasonable descriptions
                "minLength": 20,
            },
        },
        "required": ["name", "description"],
    })
    @authenticate(landing_page_auth | status_page_human_auth)
    def on_post(self, req, resp):
        # If the user is not a site admin
        if req.user['username'] not in SITE_ADMINS:
            logger.audit(f"Unauthorized: user {req.user['username']} attempted to create a "
                         "service but is not a site admin")
            title = _(f"You cannot register a new service.")
            description = _(f"Only site administrators are allowed to register new services.")
            raise falcon.HTTPUnauthorized(title, description)

        service = Service(name=req.media.get('name'), description=req.media.get('description'))
        self.db.add(service)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()

            logger.audit(f"User {req.user['username']} attempted to replace the existing "
                         f"'{service.name}' service")

            title = _(f"A service with the slug '{service.slug}' already exists.")
            description = _("You can create a new service with a different slug/name, or update "
                            "that service (if are a superuser or the service owner) with an HTTP "
                            "PUT.")
            raise falcon.HTTPBadRequest(title, description)
        else:
            logger.audit(f"User {req.user['username']} created the '{service.name}' service")

        resp.media = service_to_dict(service)
        resp.status = falcon.HTTP_CREATED
        resp.location = f"/services/{service.slug}"


class ServiceRoute(object):
    def on_get(self, req, resp, service_slug):
        try:
            service = self.db.query(Service).filter(Service.slug == service_slug).one()
        except NoResultFound:
            self.db.rollback()
            raise falcon.HTTPNotFound()

        resp.media = service_to_dict(service)

    @jsonschema.validate({
        "$schema": "http://json-schema.org/draft-06/schema#",
        "title": "Service",
        "description": "Update a registered service",
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "minLength": 4,
            },
            # Consider allowing descriptions with <20 characters, because services may be very
            # obvious to the most casual observer, so an enforced description isn't necessarily
            # helpful.
            "description": {
                "type": "string",
                "minLength": 20,
            }
        },
        "required": ["name", "description"],
    })
    @authenticate(landing_page_auth | status_page_human_auth)
    def on_put(self, req, resp, service_slug):
        try:
            service = self.db.query(Service).filter(Service.slug == service_slug).one()
        except NoResultFound:
            self.db.rollback()
            resp.status = HTTP_BAD_REQUEST
            resp.media = {
                "title": _(f"No service with slug '{service_slug}' exists."),
                "description": _("You can see all services at /services"),
            }

        # If the user is not a site admin
        if req.user['username'] not in SITE_ADMINS:
            # Only let site admins and service admins modify services
            try:
                self.db.query(Permission)\
                    .join(Service, Service.id == Permission.service_id)\
                    .filter(Service.slug == service_slug,
                            Permission.type == 'service-admin',
                            Permission.username == req.user['username'])\
                    .one()
            except NoResultFound:
                logger.audit(f"Unauthorized: user {req.user['username']} attempted to update the "
                             f"'{service.name}' service but is not a site admin or a service "
                             "admin for it")

                title = _(f"You cannot modify the metadata of this service.")
                description = _(f"Only site administrators and service administrators are allowed "
                                "to modify service metadata.")
                raise falcon.HTTPUnauthorized(title, description)

        service.name = req.media.get('name')
        service.description = req.media.get('description')

        self.db.add(service)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise
        else:
            resp.media = service_to_dict(service)

    @jsonschema.validate({
        "$schema": "http://json-schema.org/draft-06/schema#",
        "title": "Service",
        "description": "Update an attribute of a registered service",
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "minLength": 4,
            },
            # Consider allowing descriptions with <20 characters, because services may be very
            # obvious to the most casual observer, so an enforced description isn't necessarily
            # helpful.
            "description": {
                "type": "string",
                "minLength": 20,
            }
        },
    })
    @authenticate(landing_page_auth | status_page_human_auth)
    def on_patch(self, req, resp, service_slug):
        try:
            service = self.db.query(Service).filter(Service.slug == service_slug).one()
        except NoResultFound:
            self.db.rollback()
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.media = {
                "title": _(f"No service with slug '{service_slug}' exists."),
                "description": _("You can see all services at /services"),
            }
            return

        # If the user is not a site admin
        if req.user['username'] not in SITE_ADMINS:
            # Only let site admins and service admins modify services
            try:
                self.db.query(Permission)\
                    .join(Service, Service.id == Permission.service_id)\
                    .filter(Service.slug == service_slug,
                            Permission.type == 'service-admin',
                            Permission.username == req.user['username'])\
                    .one()
            except NoResultFound:
                logger.audit(f"Unauthorized: user {req.user['username']} attempted to update the "
                             f"'{service.name}' service but is not a site admin or a service "
                             "admin for it")

                title = _(f"You cannot modify the metadata of this service.")
                description = _(f"Only site administrators and service administrators are allowed "
                                "to modify service metadata.")
                raise falcon.HTTPUnauthorized(title, description)

        if req.media.get('name') is not None:
            service.name = req.media.get('name')

        if req.media.get('description') is not None:
            service.description = req.media.get('description')

        self.db.add(service)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise
        else:
            resp.media = service_to_dict(service)

    @authenticate(landing_page_auth | status_page_human_auth)
    def on_delete(self, req, resp, service_slug):
        # If the user is not a site admin
        if req.user['username'] not in SITE_ADMINS:
            logger.audit(f"Unauthorized: user {req.user['username']} attempted to delete the "
                         f"'{service_slug}' service but is not a site admin")

            title = _(f"Only site admins can remove services.")
            description = _(f"Only site administrators can remove services.")
            raise falcon.HTTPUnauthorized(title, description)

        try:
            service = self.db.query(Service).filter(Service.slug == service_slug).one()
        except NoResultFound:
            # If the user asked to delete a service that doesn't actually exist, just move on
            self.db.rollback()

            logger.audit(f"User {req.user['username']} attempted to delete a non-existent "
                         f"'{service_slug}' service")

            resp.location = "/services"
        else:
            self.db.delete(service)
            service_name = service.name

            self.db.commit()
            logger.audit(f"User {req.user['username']} deleted the '{service_name}' service")

            resp.location = "/services"


class ServiceStatusRoute(object):
    def on_get(self, req, resp, service_slug):
        try:
            self.db.query(Service).filter(Service.slug == service_slug).one()
        except NoResultFound as e:
            title = _(f"Service '{service_slug}' does not exist")
            description = _("You must specify a slug for a service that exists. Go to /services "
                            "for a list of services and their slugs.")
            raise falcon.HTTPBadRequest(title, description)

        last_up_query = self.db.query(Event)\
            .join(Service)\
            .filter(Service.slug == service_slug,
                    Event.status == 'up')\
            .order_by(Event.when.desc())\
            .limit(1)

        relevant_events = self.db.query(Event)\
            .join(Service)\
            .filter(Service.slug == service_slug,
                    last_up_query.subquery('last_up_query').c.when <= Event.when)\
            .order_by(Event.when.desc())

        try:
            event_status = relevant_events[0].status
        except IndexError:
            event_status = None

        resp.media = dict(
            **{
                "url": f"/services/{service_slug}/status",
            },
            **{
                "status": event_status,
                "events": [event_to_dict(event) for event in relevant_events],
            },
        )


class EventsRoute(object):
    ALLOWED_ORDERING_COLUMNS = ('service_id', 'when', 'status', 'informational')

    def on_options(self, req, resp, service_slug):
        resp.media = {
            "q": {
                "type": "string",
                "description": _("Search event descriptions"),
            },
            "status": {
                "type": "string",
                "enum": ["up", "down"],  # Also "limited", but we don't expose that yet
                "description": _("Search by status"),
            },
            "informational": {
                "type": "boolean",
                "description": _("Search by informational status"),
            },
            "after": {
                "type": "string",
                "format": "date-time",
                "description": _("Search for events after this datetime"),
            },
            "before": {
                "type": "string",
                "format": "date-time",
                "description": _("Search for events before this datetime"),
            },
            "order_by": {
                "type": "string",
                "enum": EventsRoute.ALLOWED_ORDERING_COLUMNS,
                "description": _("Order results by different columns. Prepend with '-' "
                                 "to order by descending."),
            },
        }

    def on_get(self, req, resp, service_slug):
        page_number = req.get_param_as_int('page', min=1)

        # search_query = req.get_param('q')

        status = req.get_param('status')
        informational = req.get_param_as_bool('informational')
        after = req.get_param_as_datetime('after')
        before = req.get_param_as_datetime('before')

        order_bys = req.get_param_as_list('order_by')

        # self.events.search(slug=service_slug, status=status, informational=informational, after=after, before=before, order_bys=order_bys)
        q = self.db.query(Event).join(Service).filter(Service.slug == service_slug)

        # TODO: Implement full-text search
        # if search_query is not None:
        #     q = q.filter(Event.description.)

        if status is not None:
            q = q.filter(Event.status == status)

        if informational is not None:
            q = q.filter(Event.informational == informational)

        if after is not None:
            q = q.filter(Event.when > after)

        if before is not None:
            q = q.filter(Event.when < before)

        # Special processing for extra because we want to allow JSONPath-ish strings
        for param, extra_value in req.params.items():
            if param.startswith('extra.'):
                extra = param[6:] if param.startswith('extra.') else param

                if extra.endswith(':exists'):
                    # Do a has_key instead
                    extra = extra[:-7]
                    extra_value = None

                q = generate_jsonb_query(query=q, column=Event.extra, jsonpath=extra, value=extra_value)

        if order_bys is not None:
            # Use an ordered dictionary so specifying the same key twice doesn't confuse things
            order_bys_dict = OrderedDict()
            for order_by_string in order_bys:
                if order_by_string.startswith('-'):
                    column_name = order_by_string[1:]
                    descending = True
                else:
                    column_name = order_by_string
                    descending = False

                if column_name not in EventsRoute.ALLOWED_ORDERING_COLUMNS:
                    title = _(f"Unknown ordering column name '{column_name}'")
                    description = _("You can only order events by these columns "
                                    f"{', '.join(EventsRoute.ALLOWED_ORDERING_COLUMNS)}. To use "
                                    "descending order, prepend a dash in front of the column name.")
                    raise falcon.HTTPBadRequest(title, description)

                column = getattr(Event, column_name)

                order_bys_dict[column_name] = column.desc() if descending else column.asc()
        else:
            order_bys_dict = OrderedDict(when=Event.when.desc())

        page = paginate(
            q.order_by(*order_bys_dict.values()), page_number, 20,
            path=req.path,
            params=req.params,
            # Combine two dictionaries: https://stackoverflow.com/a/26853961
            convert_items_callback=lambda obj: {
                **obj_to_dict(obj, exclude_attrs=['service_id']),
                **{
                    "url": f"/services/{service_slug}/events/{obj.id}",
                    "service": f"/services/{service_slug}",
                }
            })

        resp.media = obj_to_dict(page)

    @jsonschema.validate({
        "$schema": "http:/json-schema.org/draft-06/schema#",
        "title": "Event",
        "description": "Report an event for a registered service.",
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["up", "down"],
            },
            "description": {
                "type": "string",
            },
            "informational": {
                "type": "boolean",
            },
            "extra": {
                "type": "object",
            },
        },
        "required": ["status", "description", "informational"],
    })
    @authenticate(landing_page_auth | status_page_human_auth | status_page_bot_auth)
    def on_post(self, req, resp, service_slug):
        try:
            service = self.db.query(Service).filter(Service.slug == service_slug).one()
        except NoResultFound as e:
            title = _(f"Service '{service_slug}' does not exist")
            description = _("You must specify a slug for service that exists. Go to /services "
                            "for a list of services and their slugs.")
            raise falcon.HTTPBadRequest(title, description)

        # If the user is not a site admin
        if req.user['username'] not in SITE_ADMINS:
            # Only let site admins, service admins, and/or updaters report events
            try:
                self.db.query(Permission)\
                    .join(Service, Service.id == Permission.service_id)\
                    .filter(Service.slug == service_slug,
                            Permission.type.in_(['service-admin', 'updater']),
                            Permission.username == req.user['username'])\
                    .one()
            except NoResultFound:
                logger.audit(f"Unauthorized: user {req.user['username']} attempted to log an "
                             f"event for the '{service.name}' service but is not a site admin or "
                             "a service admin or an updater for it")

                title = _(f"You cannot create events for this service.")
                description = _(f"Only site administrators, service administrators, and updaters "
                                "are allowed to report events for this service.")
                raise falcon.HTTPUnauthorized(title, description)

        event = Event(
            service_id=service.id,
            when=datetime.now(tz=pytz.UTC),
            status=req.media.get('status'),
            description=req.media.get('description'),
            informational=req.media.get('informational'),
            extra=req.media.get('extra', {}))

        self.db.add(event)
        self.db.commit()

        logger.audit(f"User {req.user['username']} logged an '{event.status}' event for the "
                     f"'{service.name}' service")

        resp.media = dict(
            **event_to_dict(event),
            **{
                "id": event.id,
                "service": f"/services/{service_slug}",
            })


class EventRoute(object):
    def on_get(self, req, resp, service_slug, event_id):
        try:
            self.db.query(Service).filter(Service.slug == service_slug).one()
        except NoResultFound:
            title = _(f"Service '{service_slug}' does not exist")
            description = _("You must specify a slug for a service that exists. Go to /services "
                            "for a list of services and their slugs.")
            raise falcon.HTTPBadRequest(title, description)

        try:
            event_id = uuid.UUID(event_id)
        except ValueError:
            title = _(f"Couldn't parse UUID from '{event_id}'")
            description = _("Event UUIDs must be in aaaabbbb-cccc-dddd-eeee-ffffgggghhh format")
            raise falcon.HTTPBadRequest(title, description)

        try:
            event = self.db.query(Event).join(Service).filter(Service.slug == service_slug, Event.id == event_id).one()
        except NoResultFound:
            title = _(f"Event with ID '{event_id}' does not exist for '{service_slug}' service")
            description = _("You must specify an event ID that exists. Go to "
                            f"/services/{service_slug}/events for a list of events for that "
                            "service.")
            raise falcon.HTTPNotFound(title, description)
        else:
            resp.media = event_to_dict(event)


class PermissionsRoute(object):
    def on_options(self, req, resp, service_slug):
        resp.media = {
            "page": {
                "type": "number",
                "description": _("Page to return"),
            },
            "user": {
                "type": "string",
                "description": _("Search by username"),
            },
        }

    @authenticate(landing_page_auth | status_page_human_auth)
    def on_get(self, req, resp, service_slug):
        try:
            self.db.query(Service).filter(Service.slug == service_slug).one()
        except NoResultFound as e:
            title = _(f"Service '{service_slug}' does not exist")
            description = _("You must specify a slug for a service that exists. Go to /services "
                            "for a list of services and their slugs.")
            raise falcon.HTTPBadRequest(title, description)

        permissions = self.db.query(Permission)\
            .join(Service, Service.id == Permission.service_id)\
            .filter(Service.slug == service_slug)

        # If the user is not a site admin
        if req.user['username'] not in SITE_ADMINS:
            # Check that they are a service admin
            try:
                self.db.query(Permission)\
                    .join(Service, Service.id == Permission.service_id)\
                    .filter(Service.slug == service_slug,
                            Permission.type == 'service-admin',
                            Permission.username == req.user['username'])\
                    .one()
            except NoResultFound:
                # If they aren't a service admin, they are only allowed to view their own permissions
                # title = _(f"You cannot view the permissions of other users.")
                # description = _(f"Only site administrators and service administrators are allowed "
                #                 "to list the permissions of other users.")
                # raise falcon.HTTPUnauthorized(title, description)
                permissions = permissions.filter(Permission.username == req.user['username'])

        page_number = req.get_param_as_int('page')

        page = paginate(
            permissions.order_by(Service.name, Permission.username), page_number, 20,
            path=req.path,
            params=req.params,
            convert_items_callback=permission_to_dict)

        resp.media = obj_to_dict(page)

    @jsonschema.validate({
        "$schema": "http://json-schema.org/draft-06/schema#",
        "title": "Create a permission",
        "description": "Grant a user a specific permission level for a service",
        "type": "object",
        "properties": {
            "username": {
                "type": "string",
            },
            "type": {
                "type": "string",
                "enum": ["service-admin", "updater"],
            },
        },
        "required": ["username", "type"],
    })
    @authenticate(landing_page_auth | status_page_human_auth)
    def on_post(self, req, resp, service_slug):
        try:
            service = self.db.query(Service).filter(Service.slug == service_slug).one()
        except NoResultFound as e:
            title = _(f"Service '{service_slug}' does not exist")
            description = _("You must specify a slug for a service that exists. Go to /services "
                            "for a list of services and their slugs.")
            raise falcon.HTTPBadRequest(title, description)

        # If the user is not a site admin
        if req.user['username'] not in SITE_ADMINS:
            # Only let the user view their own permissions
            try:
                self.db.query(Permission)\
                    .join(Service, Service.id == Permission.service_id)\
                    .filter(Service.slug == service_slug,
                            Permission.type == 'service-admin',
                            Permission.username == req.user['username'])\
                    .one()
            except NoResultFound:
                logger.audit(f"Unauthorized: user {req.user['username']} attempted to grant a "
                             f"'{req.media.get('type')}' permission for the '{service.name}' "
                             f"service to {req.media.get('username')} but is not a site "
                             "admin or a service admin for it")

                title = _(f"You cannot add the permissions of another user.")
                description = _(f"Only site administrators and service administrators are allowed "
                                "to grant permissions to other users.")
                raise falcon.HTTPUnauthorized(title, description)

        permission = Permission(
            username=req.media.get('username'),
            service=service,
            type=req.media.get('type'))

        self.db.add(permission)
        self.db.commit()

        logger.audit(f"User {req.user['username']} granted '{permission.type}' permission for the "
                     f"'{service.name}' service to '{req.media.get('username')}' ")

        resp.media = permission_to_dict(permission)


class PermissionRoute(object):
    # def __init__(self, services):
    #     self.services = services

    @authenticate(landing_page_auth | status_page_human_auth)
    def on_get(self, req, resp, service_slug, permission_id):
        try:
            # service = self.services.get_by_slug(service_slug)
            self.db.query(Service).filter(Service.slug == service_slug).one()
        except NoResultFound as e:
            title = _(f"Service '{service_slug}' does not exist")
            description = _("You must specify a slug for a service that exists. Go to /services "
                            "for a list of services and their slugs.")
            raise falcon.HTTPBadRequest(title, description)

        try:
            permission_id = uuid.UUID(permission_id)
        except ValueError as e:
            title = _(f"Couldn't parse UUID from '{permission_id}'")
            description = _("Permission UUIDs must be in aaaabbbb-cccc-dddd-eeee-ffffgggghhh format")
            raise falcon.HTTPBadRequest(title, description)

        # If the user is not a site admin
        if req.user['username'] not in SITE_ADMINS:
            # Only let the user view their own permissions
            try:
                self.db.query(Permission)\
                    .join(Service, Service.id == Permission.service_id)\
                    .filter(Service.slug == service_slug,
                            Permission.type == 'service-admin',
                            Permission.username == req.user['username'])\
                    .one()
            except NoResultFound:
                logger.audit(f"Unauthorized: user {req.user['username']} attempted to view a "
                             "permission for another user but is not a site admin")

                title = _(f"You cannot view the permissions of another user.")
                description = _(f"Only site administrators and service administrators are allowed "
                                "to view the permissions of other users.")
                raise falcon.HTTPUnauthorized(title, description)

        service_alias = aliased(Service)

        try:
            permission = self.db.query(Permission)\
                .join(service_alias, service_alias.id == Permission.service_id)\
                .filter(service_alias.slug == service_slug, Permission.id == permission_id)\
                .one()
        except NoResultFound:
            title = _(f"Permission with ID '{permission_id}' does not exist for '{service_slug}' "
                      "service")
            description = _("You must specify a permision ID that exists. Go to "
                            f"/services/{service_slug}/permissions for a list of permissions for "
                            "that service.")
            raise falcon.HTTPNotFound(title, description)
        else:
            resp.media = permission_to_dict(permission)

    @authenticate(landing_page_auth | status_page_human_auth)
    def on_delete(self, req, resp, service_slug, permission_id):
        try:
            self.db.query(Service).filter(Service.slug == service_slug).one()
        except NoResultFound as e:
            title = _(f"Service '{service_slug}' does not exist")
            description = _("You must specify a slug for a service that exists. Go to /services "
                            "for a list of services and their slugs.")
            raise falcon.HTTPBadRequest(title, description)

        try:
            permission_id = uuid.UUID(permission_id)
        except ValueError as e:
            title = _(f"Couldn't parse UUID from '{permission_id}'")
            description = _("Permission UUIDs must be in aaaabbbb-cccc-dddd-eeee-ffffgggghhh format")
            raise falcon.HTTPBadRequest(title, description)

        # If the user is not a site admin
        if req.user['username'] not in SITE_ADMINS:
            # Only let the user remove their own permissions
            try:
                self.db.query(Permission)\
                    .join(Service, Service.id == Permission.service_id)\
                    .filter(Service.slug == service_slug,
                            Permission.type == 'service-admin',
                            Permission.username == req.user['username'])\
                    .one()
            except NoResultFound:
                logger.audit(f"Unauthorized: user {req.user['username']} attempted to revoke the "
                             f"'{req.media.get('type')}' permission for the '{service.name}' "
                             f"service from {req.media.get('username')} but "
                             f"{req.user['username']} is not a site admin or a service admin for "
                             "it")

                title = _(f"You cannot revoke the permissions of another user.")
                description = _(f"Only site administrators and service administrators are allowed "
                                "to revoke the permissions of other users.")
                raise falcon.HTTPUnauthorized(title, description)

        service_alias = aliased(Service)

        try:
            permission = self.db.query(Permission)\
                .join(service_alias, service_alias.id == Permission.service_id)\
                .filter(service_alias.slug == service_slug, Permission.id == permission_id)\
                .one()
        except NoResultFound:
            title = _(f"Permission with ID '{permission_id}' does not exist for '{service_slug}' "
                      "service")
            description = _("You must specify a permision ID that exists. Go to "
                            f"/services/{service_slug}/permissions for a list of permissions for "
                            "that service.")
            raise falcon.HTTPNotFound(title, description)
        else:
            self.db.delete(permission)
            self.db.commit()

            logger.audit(f"User {req.user['username']} revoked the '{permission.type}' permission "
                         f"for the '{service.name}' service from '{req.media.get('username')}'")

            resp.location = f"/services/{service_slug}/permissions"


class UserPermissionsRoute(object):
    def on_options(self, req, resp, username):
        resp.media = {
            "type": {
                "type": "string",
                "enum": ["service-admin", "updater"],
            },
        }

    @authenticate(landing_page_auth | status_page_human_auth)
    def on_get(self, req, resp, username):
        # If the user is not a site admin
        if req.user['username'] not in SITE_ADMINS:
            # Only let the user view their own permissions
            if username != req.user['username']:
                logger.audit(f"Unauthorized: user {req.user['username']} attempted to view the "
                             f"permissions for {username} but is not a site admin")

                title = _(f"You cannot view the permissions of another user.")
                description = _(f"Only site administrators are allowed to view the permissions of "
                                "other users.")
                raise falcon.HTTPUnauthorized(title, description)

        permission_type = req.get_param('type')

        service_alias = aliased(Service)

        permissions = self.db.query(Permission)\
            .join(service_alias, service_alias.id == Permission.service_id)\
            .filter(Permission.username == username)\
            .order_by(service_alias.name.asc())\
            .options(contains_eager(Permission.service, alias=service_alias))

        if permission_type is not None:
            if permission_type not in ['service-admin', 'updater']:
                title = _(f"Invalid permission type: '{permission_type}'")
                description = _("Valid permission types are 'service-admin' and 'updater'")
                raise falcon.HTTPBadRequest(title, description)

            permissions = permissions.filter(Permission.type == permission_type)

        resp.media = {
            "url": req.path,
            "results": [
                permission_to_dict(permission)
                for permission in permissions.all()
            ],
        }


class APIKeyRoute(object):
    @jsonschema.validate({
        "$schema": "http://json-schema.org/draft-06/schema#",
        "title": "Get an API key for this service",
        "description": "Get API key (in the form of a JWT) for this status page server. If a "
                       "bot token is requested, the API key will not expire, but it has fewer "
                       "permissions than an API key issued for a (human) user. API keys issued to "
                       "(human) users expire, but do not have such strict permissions "
                       "restrictions. Note that you cannot use keys issued by this endpoint to "
                       "re-authenticate to this endpoint (read: you cannot use this endpoint to "
                       "refresh API keys).",
        "type": "object",
        "properties": {
            "permission": {
                "type": "string",
                "pattern": "^[0-9a-fA-f]{8}-?[0-9a-fA-f]{4}-?[0-9a-fA-f]{4}-?[0-9a-fA-f]{4}-?[0-9a-fA-F]{12}$",
            },
            "bot": {
                "type": "boolean",
            },
        },
    })
    @authenticate(landing_page_auth)
    def on_post(self, req, resp):
        # JWT API key info = req.user + {
        #     'jti': {permission.id},
        #     'iat': {issued_at},
        #     'bot': {is_bot},
        #     'exp': {expires},
        # }
        try:
            permission = self.db.query(Permission)\
                .filter(Permission.id == req.media.get('permission'),
                        Permission.username == req.user['username'])\
                .one()
        except NoResultFound as e:
            title = _(f"Permission '{req.media.get('permission')}' does not exist")
            description = _("You must specify a permission that exists. Go to "
                            "/services/{{service_slug}}/permissions for a list of permissions for "
                            "a specific service.")
            raise falcon.HTTPBadRequest(title, description)

        is_bot = req.media.get('bot')

        jwt_payload = req.user

        jwt_payload.update({
            # JWT ID - same as permission ID
            'jti': permission.id,
            # # Issuer
            # 'iss': "status_page",
            # # Subject
            # 'sub': "",
            # Issued at
            'iat': datetime.now(tz=pytz.UTC),
        })

        # Bots don't have expiration times, but can only be service status updaters
        if is_bot:
            jwt_payload['bot'] = True
        else:
            jwt_payload['bot'] = False
            jwt_payload['exp'] = datetime.now(tz=pytz.UTC) + timedelta(hours=24)

        jwt_ = jwt.encode(jwt_payload, STATUS_PAGE_PRIVATE_KEY, algorithm='RS512').decode('utf-8')

        logger.audit(f"User {req.user['username']} created a "
                     f"{'bot ' if jwt_payload['bot'] else ' '}JWT/API key for permission "
                     f"{permission.id}")

        resp.media = {
            "payload": jwt_payload,
            "api_key": {
                "description": f"Send this API key in a header as the {HTTP_HEADER_PREFIX} auth "
                               "token or in the 'api-key' URL query parameter.",
                "jwt": jwt_,
            },
        }
