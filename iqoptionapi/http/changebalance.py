
from iqoptionapi.http.resource import Resource
from iqoptionapi.http.profile import Profile


class Changebalance(Resource):


    url = "/".join((Profile.url, "changebalance"))

    def _post(self, data=None, headers=None):

        return self.send_http_request("POST", data=data, headers=headers)

    def __call__(self,balance_id):

        data = {"balance_id": balance_id}
        return self._post(data)
