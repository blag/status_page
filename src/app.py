import gettext
import os
import simplejson as json
import uuid

from datetime import datetime
from functools import singledispatch, update_wrapper

import falcon

# from falcon_auth import FalconAuthMiddleware, JWTAuthBackend

# from .images import (Collection, ImageStore, Item)
from api import (StatusRoute, EventRoute, EventsRoute, ServiceStatusRoute,)


# def load_jwt_user(jwt_payload):
#     return jwt_payload.get('username')


# jwt_auth_backend = JWTAuthBackend(
#     user_loader=load_jwt_user,
#     secret_key=os.environ.get('JWT_PUBLIC_KEY'),
#     algorithm='RS512')


# Install this as a built-in for the entire application
gettext.install('status_page')


def methdispatch(func):
    dispatcher = singledispatch(func)
    def wrapper(*args, **kw):
        return dispatcher.dispatch(args[1].__class__)(*args, **kw)
    wrapper.register = dispatcher.register
    update_wrapper(wrapper, func)
    return wrapper


@methdispatch
def default(self, obj):
    pass


@default.register(datetime)
def _(self, obj):
    return obj.isoformat()


@default.register(uuid.UUID)
def _(self, obj):
    return str(obj)

json.JSONEncoder.default = default


def create_app():
    # api = falcon.API(middleware=[auth_middleware])
    api = falcon.API()
    api.add_route('/status', StatusRoute())
    api.add_route('/services/{service_slug}/status', ServiceStatusRoute())
    api.add_route('/services/{service_slug}/events', EventsRoute())
    api.add_route('/services/{service_slug}/events/{event_id}', EventRoute())
    return api


def get_app():
    return create_app()


# def create_app(image_store):
#     api = falcon.API()
#     api.add_route('/images', Collection(image_store))
#     api.add_route('/images/{name}', Item(image_store))
#     return api


# def get_app():
#     storage_path = os.environ.get('STATUS_PAGE_STORAGE_PATH', '.')
#     image_store = ImageStore(storage_path)
#     return create_app(image_store)
