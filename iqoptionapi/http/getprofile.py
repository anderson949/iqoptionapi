from iqoptionapi.http.resource import Resource


class Getprofile(Resource):

    url = "getprofile"

    def _get(self):

        return self.send_http_request("GET")

    def __call__(self):

        return self._get()
