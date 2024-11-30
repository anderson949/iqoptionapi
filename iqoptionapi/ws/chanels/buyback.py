from iqoptionapi.ws.chanels.base import Base


class Buyback(Base):

    name = "buyback"

    def __call__(self):
        """Method to send message to buyback websocket chanel."""
        pass
