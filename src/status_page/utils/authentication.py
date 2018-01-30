from functools import wraps

from falcon import (HTTPMissingHeader, HTTPUnauthorized)

import jwt

from .logging import logging


__all__ = ['authenticate', 'JWTAuth', 'JWTAPIKeyAuth']

logger = logging.getLogger(__name__)


def authenticate(auth_expr, unauthenticated_exception=HTTPUnauthorized):
    """
    `auth_expr` is an expression of authentication directives
    """
    def auth_required_decorator(f):
        @wraps(f)
        def authed_function(route, req, resp, *args, **kwargs):
            if not auth_expr.is_authenticated(req, resp, *args, **kwargs):
                raise unauthenticated_exception(resp.media['error'])
            return f(route, req, resp, *args, **kwargs)
        return authed_function
    return auth_required_decorator


class AuthNode(object):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def __or__(self, other):
        return CombinationNode(self, other, CombinationNode.or_)

    def __and__(self, other):
        return CombinationNode(self, other, CombinationNode.and_)

    def authenticate(self, *args, **kwargs):
        raise NotImplementedError("Subclasses of AuthNode must implement authenticate() themselves")


class CombinationNode(AuthNode):
    or_ = 'OR'
    and_ = 'AND'

    def __init__(self, left, right, operation, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not isinstance(left, AuthNode):
            raise TypeError(left)

        if not isinstance(right, AuthNode):
            raise TypeError(right)

        if operation not in (self.or_, self.and_):
            raise TypeError(operation)

        self.left = left
        self.right = right
        self.operation = operation

    def is_authenticated(self, *args, **kwargs):
        if self.operation == self.or_:
            logger.audit(f"Attempting to authenticate via OR operation")
            return (self.left.is_authenticated(*args, **kwargs) or
                    self.right.is_authenticated(*args, **kwargs))

        elif self.operation == self.and_:
            logger.audit(f"Attempting to authenticate via AND operation")
            return (self.left.is_authenticated(*args, **kwargs) and
                    self.right.is_authenticated(*args, **kwargs))

        else:
            # Make absolutely sure the user is not authenticated - something fishy is going on here
            req = args[0]
            if hasattr(req, 'user'):
                delattr(req, 'user')
            raise NotImplementedError(f"Unexpected authentication operation '{self.operation}' - "
                                      "aborting authentication attempt")


class JWTAuth(AuthNode):
    SUPPORTED_ALGORITHMS = [
        'HS256', 'HS384', 'HS512',
        'ES256', 'ES384', 'ES512',
        'RS256', 'RS384', 'RS512',
        'PS256', 'PS384', 'PS512',
    ]

    def __init__(self, *args, private_key=None, public_key=None, secret_key=None, algorithm=None,
                 http_header_prefix='Bearer', verify_function=None, userdata_function=None,
                 options=None, **kwargs):
        super().__init__(*args, **kwargs)

        if algorithm not in JWTAuth.SUPPORTED_ALGORITHMS:
            raise RuntimeError("Unsupported algorithm type '{algorithm}'")

        self.private_key = private_key
        self.public_key = public_key
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.http_header_prefix = http_header_prefix
        self.options = options

        self.verify_function = verify_function
        self.userdata_function = userdata_function

        self.kwargs = kwargs

    def encode(self, payload, headers=None):
        if self.algorithm.startswith('HS'):
            key = self.secret_key
        else:
            key = self.private_key

        return jwt.encode(payload, key, algorithm=self.algorithm, headers=headers)

    def decode(self, token):
        return jwt.decode(token, self.public_key, algorithms=[self.algorithm],
                          options=self.options, **self.kwargs)

    def get_token(self, req, *args, **kwargs):
        token = req.auth

        if not token:
            raise jwt.InvalidTokenError(f"Missing authorization '{self.http_header_prefix}' header with JWT data")

        # Ignore the header prefix, eg: Authorization: Bearer <token_data>
        if not token.startswith(f'{self.http_header_prefix} '):
            raise jwt.InvalidTokenError(f"Missing authorization header prefix '{self.http_header_prefix}'")
        else:
            # Strip off the prefix
            token = token.replace(f'{self.http_header_prefix} ', '')

        return token

    def authenticate(self, req, *args, **kwargs):
        token = self.get_token(req, *args, **kwargs)

        payload = self.decode(token)

        if self.verify_function:
            problem = self.verify_function(payload)
            if problem is not None:
                raise jwt.InvalidTokenError(f"Problematic JWT token '{problem}'")

        return payload

    def is_authenticated(self, req, resp, *args, **kwargs):
        try:
            user_data = self.authenticate(req, *args, **kwargs)
        except jwt.InvalidTokenError as e:
            logger.audit(f"Unsuccessful authentication attempt via JWT: {str(e)}")
            resp.media = {"error": str(e)}
            return False
        else:
            if self.userdata_function:
                req.user = self.userdata_function(user_data)
            logger.audit(f"Successful authentication via JWT: {str(req.user)}")
            return True


class JWTAPIKeyAuth(JWTAuth):
    def authenticate(self, req, *args, **kwargs):
        try:
            payload = super().authenticate(req, *args, **kwargs)
        except HTTPMissingHeader:
            try:
                token = req.params['api-key']
            except KeyError:
                raise jwt.InvalidTokenError("Missing 'api-key' query parameter")
            payload = self.decode(token)

            if self.verify_function:
                problem = self.verify_function(payload)
                if problem is not None:
                    raise jwt.InvalidTokenError(f"Problematic JWT token '{problem}'")

        return payload
