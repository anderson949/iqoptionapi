
from iqoptionapi.ws.objects.base import Base


class Candle(object):

    def __init__(self, candle_data):

        self.__candle_data = candle_data

    @property
    def candle_time(self):

        return self.__candle_data[0]

    @property
    def candle_open(self):

        return self.__candle_data[1]

    @property
    def candle_close(self):

        return self.__candle_data[2]

    @property
    def candle_high(self):

        return self.__candle_data[3]

    @property
    def candle_low(self):

        return self.__candle_data[4]

    @property
    def candle_type(self):  # pylint: disable=inconsistent-return-statements

        if self.candle_open < self.candle_close:
            return "green"
        elif self.candle_open > self.candle_close:
            return "red"


class Candles(Base):

    def __init__(self, candles_data=None):
        super(Candles, self).__init__()
        self.__name = "candles"
        self.__candles_data = candles_data

    @property
    def candles_data(self):

        return self.__candles_data

    @candles_data.setter
    def candles_data(self, candles_data):

        self.__candles_data = candles_data

    @property
    def first_candle(self):

        return Candle(self.candles_data[0])

    @property
    def second_candle(self):

        return Candle(self.candles_data[1])

    @property
    def current_candle(self):

        return Candle(self.candles_data[-1])
