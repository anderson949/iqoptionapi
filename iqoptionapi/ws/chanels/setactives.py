
from iqoptionapi.ws.chanels.base import Base


class SetActives(Base):

    name = "setActives"

    def __call__(self, actives):

        data = {"actives": actives}
        self.send_websocket_request(self.name, data)
