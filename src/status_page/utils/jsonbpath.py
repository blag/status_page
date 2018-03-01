# Vendored in from https://github.com/mz-techops/jsonbpath
import jsonpath_rw


def _generate_jsonb_query(expr, query_tuple=tuple()):
    if isinstance(expr, jsonpath_rw.Child):
        if isinstance(expr.right, jsonpath_rw.Fields):
            query_tuple = _generate_jsonb_query(expr.left, (expr.right.fields[0],) + query_tuple)
        elif isinstance(expr.right, jsonpath_rw.Slice):
            raise NotImplementedError("Filtering using slices is not supported.")
        else:
            raise NotImplementedError(
                "Unrecognized child expression ("
                f"left: {expr.left} [{expr.left.__class__.__name__}], "
                f"right: {expr.right} [{expr.right.__class__.__name__}])")
    elif isinstance(expr, jsonpath_rw.Fields):
        query_tuple = (expr.fields[0],) + query_tuple
    else:
        raise NotImplementedError(f"Unrecognized expression: {expr}")

    return query_tuple


def _generate_jsonb_query_dict(index_tuple, value):
    if len(index_tuple) < 2:
        return {index_tuple[0]: value}
    else:
        return {index_tuple[0]: _generate_jsonb_query_dict(index_tuple[1:], value)}


def generate_jsonb_query(query, column, jsonpath, value=None):
    """
    Generate a SQLAlchemy query for a JSONB column from a jsonpath_rw.JSONPath
    string or object.

    Only selecting via dictionary key is supported. Selecting or filtering using
    slices is not supported.

    Example
    -------
    Filtering using 'contains'.

    generate_jsonb_query(query, MyTable.data, 'extra.eventId', 17)

    is equivalent to:

    query.filter(MyTable.data.contains({'extra': {'eventId': 17}}))

    Filtering using 'has_key'.

    generate_jsonb_query(query, MyTable.data, 'extra.expires')

    is equivalent to:

    query.filter(MyTable.data.has_key(('extra', 'expires')))

    Parameters
    ----------
    query
        A SQLAlchemy query object
    column : sqlalchemy.sql.schema.Column object
        The table column to filter on
    jsonpath : str or jsonpath_rw.JSONPath object
        The jsonpath_rw.JSONPath string to query with
    value : int or str, optional
        The value to match against using 'contains'. If not specified, the query
        is filtered using 'has_key'.

    Returns
    -------
    query
        A SQLAlchemy query object that applies the given jsonpath_rw.JSONPath
        filter to the column
    """
    # TODO: SQLAlchemy's JSONB implementation is relatively new, so its
    #       querying mechanisms will likely improve drastically
    if value is None:
        q = query.filter(column.has_key(jsonpath))  # noqa: W601
    else:
        if isinstance(jsonpath, jsonpath_rw.JSONPath):
            expr = jsonpath
        else:
            expr = jsonpath_rw.parse(jsonpath)

        path_tuple = _generate_jsonb_query(expr)

        path_value_dict = _generate_jsonb_query_dict(path_tuple, value)
        q = query.filter(column.contains(path_value_dict))

    return q
