from iqoptionapi.http.resource import Resource
import json


class SMS_Sender(Resource):
    # pylint: disable=too-few-public-methods

    url = ""

    def _post(self, data=None, headers=None):

        return self.api.send_http_request_v2(method="POST", url=f'https://auth.{self.api.host}/api/v2/verify/2fa',data=json.dumps(data), headers=headers)

    def __call__(self, token_reason):

        data = {"method": "sms",
                "token": token_reason}

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Referer': f'https://{self.api.host}/en/login',
            'Sec-Fetch-Mode': 'cors',
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36'
            }

        return self._post(data=data, headers=headers)
