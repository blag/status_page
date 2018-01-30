'''
Pagination utilities
'''
import math
from urllib.parse import (urlencode, urlunparse)


__all__ = ['paginate']


def paginate(query, page, page_size, request=None, path=None, params=None, convert_items_callback=None):
    """
    Split results from a SQLAlchemy query into multiple pages

    `query` - The (lazily evaluated) SQLAlchemy query object
    `page` - The page number of results to return
    `page_size` - The size of each page in the page set
    `request` - The request itself, used to calculate paths and query parameters
    `path` - If the request parameter was not passed, this should be the request path
    `params` - If the request parameter was not passed, this should be the request query parameters
    `convert_items_callback` - A callback function to convert each query object to a dictionary
    """

    if not page:
        page = 1

    if page <= 0:
        raise ValueError("The page parameter must be greater than zero")

    if page_size and page_size <= 0:
        raise ValueError("The page_size parameter must be greater than zero")

    items = query.limit(page_size).offset((page - 1) * page_size).all()
    count = query.order_by(None).count()
    return Page(items, page, page_size, count, path=path, params=params,
                convert_items_callback=convert_items_callback)


# Adapted from:
# https://github.com/wizeline/sqlalchemy-pagination/blob/master/sqlalchemy_pagination/__init__.py
class Page(object):
    def __init__(self, items, page, page_size, count, request=None, path=None, params=None,
                 convert_items_callback=None):
        """
        A single page in a list of pages of results

        `items` - An iterable of items in this page
        `page` - The page number in the page sequence
        `page_size` - The number of items to display on each page
        `count` - The total number of items in the iterable
        `request` (optional) - The request object, passing this will override the path and params
                               parameters
        `path` - The path of the page, used to calculate the next and previous page URLs
        `params` - The params used to create this page, used to calcualte the next and previous
                   page URLs
        `convert_items_callback` (optional) - A callable used to convert each item to a dictionary
                                              for JSON serialization

        Either `request` should be given, or `path` and `params` should be given. If none are
        given, path defaults to `/` and `params` defaults to an empty dictionary.
        """

        # This function got ugly once it tried to calcualte URLs, because the URLs it calculates
        # rely on path and query parameters that aren't really pertinent to the page itself.

        if convert_items_callback is None:
            def convert_items_callback(item):
                return item

        if request is not None:
            path = request.path
            params = request.params

        if path is None:
            path = '/'

        if params is None:
            params = {}

        previous_params = params.copy()
        next_params = params.copy()

        has_previous = page > 1
        previous_items = (page - 1) * page_size
        has_next = previous_items + len(items) < count

        self.results = [convert_items_callback(item) for item in items]

        self.count = count
        self.pages = int(math.ceil(count / page_size))

        self.previous_page = (page - 1) if has_previous else None
        self.next_page = (page + 1) if has_next else None

        previous_params['page'] = self.previous_page
        next_params['page'] = self.next_page

        self.url = urlunparse(('', '', path, '', urlencode(params, doseq=True), ''))

        if has_previous:
            # Construct the URL, taking care to not overwrite any query parameters
            self.previous = urlunparse(('', '', path, '', urlencode(previous_params, doseq=True), ''))
        else:
            self.previous = None

        if has_next:
            self.next = urlunparse(('', '', path, '', urlencode(next_params, doseq=True), ''))
        else:
            self.next = None
