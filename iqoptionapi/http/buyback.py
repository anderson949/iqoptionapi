
from iqoptionapi.http.resource import Resource
from iqoptionapi.http.billing import Billing


class Buyback(Resource):

    url = "/".join((Billing.url, "buyback"))

    def _post(self, data=None, headers=None):

        return self.send_http_request("POST", data=data, headers=headers)

    def __call__(self, option_id):

        data = {"option_id": [option_id]}
        return self._post(data=data)
