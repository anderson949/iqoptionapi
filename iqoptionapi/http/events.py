from iqoptionapi.http.resource import Resource


class Events(Resource):

    url = ""

    def send_http(self,method, data=None, headers=None):

        return self.api.send_http_request_v2(method=method, url=f"https://event.{self.api.host}/api/v1/events",data=data)

    def __call__(self,method,data,headers=None):

         
        return self.send_http(method=method,data=data,headers=headers)
