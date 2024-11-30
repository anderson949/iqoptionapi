from iqoptionapi.http.resource import Resource


class Logout(Resource):

    url = ""

    def _post(self, data=None, headers=None):

        return self.api.send_http_request_v2(method="POST", url=f"https://auth.{self.api.host}/api/v1.0/logout",data=data, headers=headers)

    def __call__(self):
       
        return self._post()

