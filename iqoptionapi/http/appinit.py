
from iqoptionapi.http.resource import Resource


class Appinit(Resource):

    url = "appinit"

    def _get(self, data=None, headers=None):

        return self.send_http_request("GET", data=data, headers=headers)

    def __call__(self):

        return self._get()
