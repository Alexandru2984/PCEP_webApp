"""Gunicorn access-log policy for the production container."""

from gunicorn.glogging import Logger


def is_successful_internal_healthcheck(response, environ):
    status = str(getattr(response, 'status', '')).split(None, 1)[0]
    return (
        status == '200'
        and environ.get('REQUEST_METHOD') == 'GET'
        and environ.get('PATH_INFO') == '/api/health/'
        and environ.get('HTTP_X_PCEP_INTERNAL_HEALTHCHECK') == '1'
        and environ.get('REMOTE_ADDR') in {'127.0.0.1', '::1'}
    )


class ProductionLogger(Logger):
    """Keep successful container probes from hiding useful request logs."""

    def access(self, response, request, environ, request_time):
        if is_successful_internal_healthcheck(response, environ):
            return
        super().access(response, request, environ, request_time)
