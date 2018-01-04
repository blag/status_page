from functools import wraps

from falcon import HTTPUnauthorized


__all__ = ['authenticate', 'APIKeyAuth', 'JWTAuth']


def authenticate(auth_expr, unauthenticated_exception=HTTPUnauthorized):
    """
    `auth_expr` is an expression of authentication directives
    """
    def auth_required_decorator(f):
        @wraps(f)
        def authed_function(req, *args, **kwargs):
            if auth_expr.authenticate(req, *args, **kwargs):
                raise unauthenticated_exception()
            return f(req, *args, **kwargs)
        return authed_function
    return auth_required_decorator


class AuthNode(object):
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

    def authenticate(self, *args, **kwargs):
        if self.operation == self.or_:
            return self.left.authenticate(*args, **kwargs) or self.right.authenticate(*args, **kwargs)
        elif self.operation == self.and_:
            return self.left.authenticate(*args, **kwargs) and self.right.authenticate(*args, **kwargs)


class APIKeyAuth(AuthNode):
    class BadAuthenticationError(Exception):
        pass

    def __init__(self, *args, query_function=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.query = query_function

    def authenticate(self, req):
        try:
            api_key = req.get_header('api-key')
        except HTTPMissingHeader:
            return False
        else:
            try:
                req.user = getattr(self, 'query')(api_key)
            except BadAuthenticationError:
                return False
            else:
                return True


class JWTAuth(AuthNode):
    SUPPORTED_ALGORITHMS = [
        'HS256', 'HS384', 'HS512',
        'ES256', 'ES384', 'ES512',
        'RS256', 'RS384', 'RS512',
        'PS256', 'PS384', 'PS512',
    ]

    def __init__(self, *args, secret=None, algorithm=None, issuer=None, audience=None, leeway=None, **kwargs):
        super().__init__(*args, **kwargs)

        if algorithm not in SUPPORTED_ALGORITHMS:
            raise RuntimeError(_("Unsupported algorithm type '{algorithm}'"))

        self.secret = secret
        self.algorithm = algorithm
        self.issue = issuer
        self.audience = audience
        self.leeway = leeway

    def authenticate(self, req):
        try:
            req.user = jwt.decode(token, algorithms=[self.algorithm], key=self.secret, issuer=self.issuer, audience=self.audience, leeway=self.leeway)
        except jwt.InvalidTokenError as err:
            return False
        else:
            return True
