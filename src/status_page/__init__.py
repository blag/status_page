import gettext
import json
import uuid

from datetime import datetime
from functools import singledispatch


# Install this as a built-in for the entire application
gettext.install('status_page')


# See https://github.com/python/cpython/pull/4987
# From https://gist.github.com/ianhoffman/e25899e8fca3c1ef8772f331b14031d0
class singledispatchmethod(object):
    def __init__(self, method):
        self.method = singledispatch(method)

    def register(self, klass, method=None):
        return self.method.register(klass, func=method)

    def __get__(self, instance=None, owner=None):
        if instance or owner:
            def _method(*args, **kwargs):
                method = self.method.dispatch(args[0].__class__)
                return method.__get__(instance, owner)(*args, **kwargs)

            _method.__isabstractmethod__ = self.__isabstractmethod__
            _method.register = self.register
            return _method
        else:
            return self

    @property
    def __isabstractmethod__(self):
        return getattr(self.method, '__isabstractmethod__', False)


@singledispatchmethod
def default(encoder, obj):
    pass


@default.register(datetime)
def json_datetime(encoder, obj):
    return obj.isoformat()


@default.register(uuid.UUID)
def json_uuid(encoder, obj):
    return str(obj)


json.JSONEncoder.default = default
