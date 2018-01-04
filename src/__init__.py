import gettext
import simplejson as json
import uuid

from datetime import datetime
from functools import singledispatch, update_wrapper


# Install this as a built-in for the entire application
gettext.install('status_page')
print(f'__file__={__file__:<35} | __name__={__name__:<20} | __package__={__package__:<20}')


def methdispatch(func):
    print(f"Registering {func.__name__}")
    dispatcher = singledispatch(func)
    def wrapper(*args, **kw):
        return dispatcher.dispatch(args[1].__class__)(*args, **kw)
    wrapper.register = dispatcher.register
    update_wrapper(wrapper, func)
    return wrapper


@methdispatch
def default(self, obj):
    print("Default default function")
    pass


print("Registering datetime with JSONEncoder")
@default.register(datetime)
def _(self, obj):
    print("Datetime encoder function")
    return obj.isoformat()


print("Registering datetime with JSONEncoder")
@default.register(uuid.UUID)
def _(self, obj):
    print("UUID encoder function")
    return str(obj)

json.JSONEncoder.default = default
print("json.JSONEncoder.default:", default)
