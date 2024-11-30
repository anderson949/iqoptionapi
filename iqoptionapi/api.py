import time
import random
import json
import logging
import threading
import requests
import ssl
import atexit
from collections import defaultdict
from iqoptionapi.http.login import Login
from iqoptionapi.http.loginv2 import Loginv2
from iqoptionapi.http.logout import Logout
from iqoptionapi.http.login2fa import Login2FA
from iqoptionapi.http.send_sms import SMS_Sender
from iqoptionapi.http.verify import Verify
from iqoptionapi.http.getprofile import Getprofile
from iqoptionapi.http.auth import Auth
from iqoptionapi.http.token import Token
from iqoptionapi.http.appinit import Appinit
from iqoptionapi.http.billing import Billing
from iqoptionapi.http.buyback import Buyback
from iqoptionapi.http.events import Events
from iqoptionapi.ws.client import WebsocketClient
from iqoptionapi.ws.chanels.ssid import Ssid
from iqoptionapi.ws.chanels.setactives import SetActives
from iqoptionapi.ws.chanels.buy_place_order_temp import Buy_place_order_temp
from iqoptionapi.ws.chanels.heartbeat import Heartbeat
from iqoptionapi.ws.objects.timesync import TimeSync
from iqoptionapi.ws.objects.profile import Profile
from iqoptionapi.ws.objects.candles import Candles
from iqoptionapi.ws.objects.listinfodata import ListInfoData
from iqoptionapi.ws.objects.betinfo import Game_betinfo_data
import iqoptionapi.global_value as global_value

# Desabilitar warnings do urllib3
requests.packages.urllib3.disable_warnings()  # pylint: disable=no-member

# Função auxiliar para criar dicionários aninhados
def nested_dict(n, type):
    if n == 1:
        return defaultdict(type)
    else:
        return defaultdict(lambda: nested_dict(n - 1, type))


class API(object):
    # Atributos de classe
    socket_option_opened = {}
    socket_option_closed = {}
    timesync = TimeSync()
    profile = Profile()
    candles = {}
    listinfodata = ListInfoData()
    instrument_quites_generated_data = nested_dict(2, dict)
    instrument_quites_generated_timestamp = nested_dict(2, dict)
    order_async = nested_dict(2, dict)
    traders_mood = {}
    subscribe_commission_changed_data = nested_dict(2, dict)
    real_time_candles = nested_dict(3, dict)
    real_time_candles_maxdict_table = nested_dict(2, dict)
    candle_generated_check = nested_dict(2, dict)

    def __init__(self, username, password, proxies=None):
        self.logger = logging.getLogger(__name__)
        self.host = "iqoption.com"
        self.url_auth2 = f"https://auth.{self.host}/api/v2/verify/2fa"
        self.https_url = f"https://{self.host}/api"
        self.wss_url = f"wss://{self.host}/echo/websocket"
        self.url_events = f"https://event.{self.host}/api/v1/events"
        self.url_login = f"https://auth.{self.host}/api/v2/login"
        self.url_logout = f"https://auth.{self.host}/api/v1.0/logout"

        self.websocket_client = None
        self.session = requests.Session()
        self.session.verify = False
        self.session.trust_env = False
        self.username = username
        self.password = password
        self.token_login2fa = None
        self.token_sms = None
        self.proxies = proxies

        self.__active_account_type = None
        self.mutex = threading.Lock()
        self.request_id = 0

    def prepare_http_url(self, resource):
        return "/".join((self.https_url, resource.url))

    @property
    def websocket(self):
        if not self.websocket_client:
            raise RuntimeError("WebSocket client not initialized. Call start_websocket first.")
        if not hasattr(self.websocket_client, "wss"):
            raise AttributeError("WebSocket client does not have attribute 'wss'.")
        return self.websocket_client.wss

    def start_websocket(self):
        global_value.check_websocket_if_connect = None
        global_value.check_websocket_if_error = False
        global_value.websocket_error_reason = None

        try:
            self.websocket_client = WebsocketClient(self)
            self.websocket_thread = threading.Thread(
                target=self.websocket.run_forever,
                kwargs={'sslopt': {"check_hostname": False, "cert_reqs": ssl.CERT_NONE, "ca_certs": "cacert.pem"}}
            )
            self.websocket_thread.daemon = True
            self.websocket_thread.start()

            while True:
                if global_value.check_websocket_if_error:
                    self.logger.error("WebSocket connection error: %s", global_value.websocket_error_reason)
                    return False, global_value.websocket_error_reason

                if global_value.check_websocket_if_connect == 0:
                    self.logger.error("WebSocket connection closed.")
                    return False, "WebSocket connection closed."

                if global_value.check_websocket_if_connect == 1:
                    self.logger.info("WebSocket connected successfully.")
                    return True, None
        except Exception as e:
            self.logger.exception("Failed to start WebSocket client: %s", e)
            return False, str(e)

    def send_websocket_request(self, name, msg, request_id="", no_force_send=True):
        if not self.websocket_client:
            raise RuntimeError("WebSocket client not initialized. Call start_websocket first.")
        
        self.mutex.acquire()
        self.request_id += 1
        request = self.request_id if request_id == "" else request_id
        self.mutex.release()

        data = json.dumps(dict(name=name, request_id=str(request), msg=msg))

        while (global_value.ssl_Mutual_exclusion or global_value.ssl_Mutual_exclusion_write) and no_force_send:
            pass

        global_value.ssl_Mutual_exclusion_write = True
        try:
            self.websocket.send(data)
            self.logger.debug("WebSocket request sent: %s", data)
        except Exception as e:
            self.logger.exception("Failed to send WebSocket request: %s", e)
        finally:
            global_value.ssl_Mutual_exclusion_write = False

        return str(request)

    def close(self):
        if self.websocket_client:
            try:
                self.websocket.close()
                self.websocket_thread.join()
                self.logger.info("WebSocket closed successfully.")
            except Exception as e:
                self.logger.exception("Failed to close WebSocket: %s", e)
