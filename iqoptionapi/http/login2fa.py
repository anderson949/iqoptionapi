
from iqoptionapi.http.resource import Resource


class Login2FA(Resource):

    url = ""

    def _post(self, data=None, headers=None):

        return self.api.send_http_request_v2(method="POST", url=f"https://auth.{self.api.host}/api/v2/login",data=data, headers=headers)

    def __call__(self, username, password, token_login):

        data = {"identifier": username,
                "password": password,
                "token": token_login}

        return self._post(data=data)
