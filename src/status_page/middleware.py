# http://docs.sqlalchemy.org/en/rel_1_1/orm/contextual.html#using-thread-local-scope-with-web-applications
# http://docs.sqlalchemy.org/en/latest/orm/session_basics.html#session-faq-whentocreate
# https://eshlox.net/2017/07/28/integrate-sqlalchemy-with-falcon-framework/


class SQLAlchemySessionManager(object):
    """
    Create a scoped session for every request and close it when the request ends.
    """

    def __init__(self, session_cls):
        self.DBSession = session_cls

    def process_resource(self, req, resp, resource, params):
        resource.db = self.DBSession()

    def process_response(self, req, resp, resource, req_succeeded):
        if hasattr(resource, 'db'):
            if not req_succeeded:
                resource.db.rollback()
            self.DBSession.remove()
