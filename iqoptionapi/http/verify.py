
from iqoptionapi.http.resource import Resource
import json


class Verify(Resource):
    # pylint: disable=too-few-public-methods

    url = ""

    def _post(self, data=None, headers=None):

        return self.api.send_http_request_v2(method="POST", url=self.api.url_auth2,data=json.dumps(data), headers=headers)

    def __call__(self, sms_received, token_sms):

        data = {"code": str(sms_received),
                "token": token_sms}

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            f'Referer': 'https://{self.api.host}/en/login',
            'Sec-Fetch-Mode': 'cors',
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36'
            }

        return self._post(data=data, headers=headers)
