import logging


AUDIT = 27


class _AuditLogger(logging.getLoggerClass()):
    def __init__(self, name, level=logging.NOTSET):
        super().__init__(name, level)

        logging.addLevelName(AUDIT, 'AUDIT')

    def audit(self, msg, *args, **kwargs):
        if self.isEnabledFor(AUDIT):
            self._log(AUDIT, msg, args, **kwargs)


logging.setLoggerClass(_AuditLogger)
