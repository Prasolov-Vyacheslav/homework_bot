class HTTPRequestError(Exception):
    def __init__(self, response):
        message = (
            f'Эндпоинт {response.url} недоступен. '
            f'Код ответа API: {response.status_code}]'
        )
        super().__init__(message)


class EmptyResponseFromAPI(Exception):
    """Исключение, вызываемое при пустом ответе от API"""
    pass
