
from iqoptionapi.http.login import Login


class Loginv2(Login):

    url = "/".join((Login.url, "v2"))

    def __init__(self, api):
        super(Loginv2, self).__init__(api)
