'''
Convert objects to dictionaries
'''


def obj_to_dict(item, exclude_attrs=None):
    exclude_attrs = exclude_attrs if exclude_attrs else []
    return {k: v for k, v in vars(item).items() if not k.startswith('_') and k not in exclude_attrs}


def event_to_dict(event, exclude_attrs=None):
    exclude_attrs = exclude_attrs or ['id', 'service', 'service_id']

    return dict(
        **{"url": f"/services/{event.service.slug}/events/{event.id}"},
        **obj_to_dict(event, exclude_attrs=exclude_attrs),
    )


def service_to_dict(service, exclude_attrs=None):
    exclude_attrs = exclude_attrs or ['id']

    return dict(
        **{"url": f"/services/{service.slug}"},
        **obj_to_dict(service, exclude_attrs),
    )


def permission_to_dict(permission, exclude_attrs=None):
    exclude_attrs = exclude_attrs or ['service_id', 'service']

    return dict(
        **{
            "url": f"/services/{permission.service.slug}/permissions/{permission.id}",
            "service": f"/services/{permission.service.slug}",
        },
        **obj_to_dict(permission, exclude_attrs),
    )
