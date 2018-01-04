'''
Convert objects to dictionaries
'''

def obj_to_dict(item, exclude_attrs=None):
    exclude_attrs = exclude_attrs if exclude_attrs else []
    return {k: v for k, v in vars(item).items() if not k.startswith('_') and k not in exclude_attrs}


def event_to_dict(event):
    return dict(
        **{'url': f"/services/{event.service.slug}/events/{event.id}"},
        **obj_to_dict(event, exclude_attrs=['service', 'service_id']),
    )
