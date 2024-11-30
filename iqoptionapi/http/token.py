from iqoptionapi.http.resource import Resource
from iqoptionapi.http.auth import Auth


class Token(Resource):

    # pylint: disable=too-few-public-methods

    url = "/".join((Auth.url, "token"))

    def __init__(self, api):
        super(Token, self).__init__(api)

    def _get(self):

        return self.send_http_request("GET")

    def __call__(self):

        return self._get()
