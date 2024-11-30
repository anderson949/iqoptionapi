"""Module for IQ option websocket."""

import json
import logging, time
import websocket
import iqoptionapi.constants as OP_code
import iqoptionapi.global_value as global_value
from threading import Thread


class WebsocketClient(object):
    def __init__(self, api):

        self.api = api
        self.wss = websocket.WebSocketApp(
            self.api.wss_url, on_message=self.on_message,
            on_error=self.on_error, on_close=self.on_close,
            on_open=self.on_open)

    def dict_queue_add(self, dict, maxdict, key1, key2, key3, value):
        if key3 in dict[key1][key2]:
            dict[key1][key2][key3] = value
        else:
            while True:
                try:
                    dic_size = len(dict[key1][key2])
                except:
                    dic_size = 0
                if dic_size < maxdict:
                    dict[key1][key2][key3] = value
                    break
                else:
                    # del mini key
                    del dict[key1][key2][sorted(
                        dict[key1][key2].keys(), reverse=False)[0]]

    def api_dict_clean(self, obj):
        if len(obj) > 5000:
            for k in obj.keys():
                del obj[k]
                break

    def on_message(self, wss, message):  # pylint: disable=unused-argument
        """Method to process websocket messages."""
        global_value.ssl_Mutual_exclusion = True
        logger = logging.getLogger(__name__)
        logger.debug(message)

        message = json.loads(str(message))

        if message["name"] == "position-changed":


            if message["msg"]["source"] == "digital-options" or message["msg"]["source"] == "trading":
                #print(message)
                raw_event =  message["msg"]["raw_event"]["digital_options_position_changed1"]
                id = raw_event["order_ids"][0]
   
            else:        
                id = message["msg"]["external_id"]

            #print(f'recebido id: {id}')
            if message["msg"]["status"] == "closed":
                self.api.order_async[int(id)]['closed'] = True
                self.api.order_async[int(id)]['msg'] = message['msg']
            else:
                self.api.order_async[int(id)]['closed'] = False


        elif message['name'] == 'top-assets':
            if message['msg']['instrument_type'] == 'digital-option':
                self.api.assets_digital = message['msg']['data']
                
        elif message['name'] == 'option-opened':
            self.api.orders_history.append(message['msg'])
            self.api.order_async[int(message["msg"]["option_id"])][message["name"]] = message

        elif message['name'] == 'order-changed':
            self.api.orders_history.append(message['msg'])
        
        elif message['name'] == 'digital-option-placed':
            request_id = message['request_id']
            self.api.orders[request_id] = message['msg']

        elif message['name'] == 'option':
            request_id = message['request_id']
            self.api.orders[request_id] = message['msg']
      
        elif message["name"] == "candle-generated":
            try:
                active_name = list(OP_code.ACTIVES.keys())[list(OP_code.ACTIVES.values()).index(message["msg"]["active_id"])]
                self.api.all_realtime_candles[active_name] = message["msg"]
            except:
                pass

        elif message["name"] == "alert":
            try:
                self.api.alerta = message['msg']
            except:
                pass
                
        elif message["name"] == "alert-triggered":
            try:
                self.api.alertas_tocados.append(message["msg"])
            except:
                pass
            
        elif message["name"] == "alerts":
            try:
                self.api.alertas = message['msg']['records']
            except:
                pass

        elif message["name"] == "stop-order-placed":
            try:
                self.api.buy_forex_id = message
            except:
                pass

        elif message["name"] == "pending-order-canceled":
            try:
                self.api.cancel_order_forex = message
            except:
                pass

        elif message["name"] == "positions":
            try:
                self.api.positions_forex= message
                self.api.positions = message
            except:
                pass

        elif message["name"] == "history-positions":
            try:
                self.api.fechadas_forex = message
                self.api.position_history_v2 = message
            except:
                pass

        elif message["name"] == "orders":
            try:
                self.api.pendentes_forex = message
            except:
                pass

        elif message["name"] == "underlying-list":
            try:
                self.api.leverage_forex = message
                self.api.underliyng_list = message["msg"]
            except:
                pass

        elif message['name'] == "initialization-data":
            self.api.payout_binarias = message["msg"]

        elif message['name'] == 'client-price-generated':
            ask_price = [d for d in message["msg"]["prices"] if d['strike'] == 'SPT'][0]['call']['ask']
            pay = int(((100-ask_price)*100)/ask_price)
            self.api.payout_digitais[message["msg"]["asset_id"]] = {}
            self.api.payout_digitais[message["msg"]["asset_id"]]['hora']= time.time()
            self.api.payout_digitais[message["msg"]["asset_id"]]['pay']= pay
        
        elif message['name'] == 'candles':
            try:
                self.api.addcandles(message["request_id"], message["msg"]["candles"])
            except:
                pass
        
        elif message["name"] == "socket-option-closed":
            id = message["msg"]["id"]
            self.api.socket_option_closed[id] = message

        elif message["name"] == "position-closed":
            self.api.close_position_data = message

        elif message["name"] == "listInfoData":
            for get_m in message["msg"]:
                self.api.listinfodata.set(get_m["win"], get_m["game_state"], get_m["id"])

        elif message["name"] == "leaderboard-userinfo-deals-client":
            self.api.leaderboard_userinfo_deals_client = message["msg"]

        elif message["name"] == "leaderboard-deals-client":
            self.api.leaderboard_deals_client = message["msg"]

        elif message["name"] == "instruments":
                self.api.instruments = message["msg"]

        elif message["name"] == "heartbeat":
            try:
                self.api.heartbeat(message["msg"])
            except:
                pass
        
        elif message["name"] == "financial-information":
                self.api.financial_information = message

        elif message["name"] == "deferred-orders":
            self.api.deferred_orders = message

        elif message["name"] == "commission-changed":
            instrument_type = message["msg"]["instrument_type"]
            active_id = message["msg"]["active_id"]
            Active_name = list(OP_code.ACTIVES.keys())[list(OP_code.ACTIVES.values()).index(active_id)]
            commission = message["msg"]["commission"]["value"]
            self.api.subscribe_commission_changed_data[instrument_type][Active_name][self.api.timesync.server_timestamp] = int(commission)

        elif message["name"] == "balances":
            self.api.balances_raw = message

        elif message['name'] == 'balance-changed':
            balance = message['msg']['current_balance']
            try:
                self.api.profile.balance = balance["amount"]
            except:
                pass
            try:
                self.api.profile.balance_id = balance["id"]
            except:
                pass
            try:
                self.api.profile.balance_type = balance["type"]
            except:
                pass

        elif message["name"] == "auto-margin-call-changed":
            self.api.auto_margin_call_changed_respond = message

        elif message["name"] == "available-leverages":
            self.api.available_leverages = message

        elif message["name"] == "option-closed":
            self.api.order_async[int(message["msg"]["option_id"])][message["name"]] = message
            if message["microserviceName"] == "binary-options":
                self.api.order_binary[message["msg"]["option_id"]] = message['msg']

        elif message["name"] == "options":
            self.api.get_options_v2_data = message

        elif message["name"] == "order":
            self.api.order_data = message

        elif message["name"] == "order-placed-temp":
            self.api.buy_order_id = message["msg"]["id"]

        elif message["name"] == "position":
            self.api.position = message

        elif message["name"] == "position-history":
            self.api.position_history = message

        elif message["name"] == "profile":
            self.api.profile.msg = message["msg"]
            if self.api.profile.msg != False:
                # ---------------------------
                try:
                    self.api.profile.balance = message["msg"]["balance"]
                except:
                    pass
                # Set Default account
                if global_value.balance_id == None:
                    for balance in message["msg"]["balances"]:
                        if balance["type"] == 4:
                            global_value.balance_id = balance["id"]
                            break
                try:
                    self.api.profile.balance_id = message["msg"]["balance_id"]
                except:
                    pass

                try:
                    self.api.profile.balance_type = message["msg"]["balance_type"]
                except:
                    pass

                try:
                    self.api.profile.balances = message["msg"]["balances"]
                except:
                    pass

        elif message["name"] == "result":
            self.api.result = message["msg"]["success"]

        elif message["name"] == "socket-option-opened":
            id = message["msg"]["id"]
            self.api.socket_option_opened[id] = message

        elif message["name"] == "sold-options":
            self.api.sold_options_respond = message

        elif message["name"] == "timeSync":
            self.api.timesync.server_timestamp = message["msg"]

        elif message["name"] == "top-assets-updated":
            self.api.top_assets_updated_data[str(message["msg"]["instrument_type"])] = message["msg"]["data"]

        elif message["name"] == "tpsl-changed":
            self.api.tpsl_changed_respond = message

        elif message["name"] == "traders-mood-changed":
            self.api.traders_mood[message["msg"]["asset_id"]] = message["msg"]["value"]

        elif message["name"] == "training-balance-reset":
            self.api.training_balance_reset_request = message["msg"]["isSuccessful"]

        elif message["name"] == "user-profile-client":
            self.api.user_profile_client = message["msg"]

        elif message["name"] == "users-availability":
           self. api.users_availability = message["msg"]





        global_value.ssl_Mutual_exclusion = False

    def on_error(self, wss, error):  # pylint: disable=unused-argument
        """Method to process websocket errors."""
        logger = logging.getLogger(__name__)
        logger.error(error)
        global_value.websocket_error_reason = str(error)
        global_value.check_websocket_if_error = True

    def on_open(self, wss):  # pylint: disable=unused-argument
        """Method to process websocket open."""
        logger = logging.getLogger(__name__)
        logger.debug("Websocket client connected.")
        global_value.check_websocket_if_connect = 1

    def on_close(self, wss, close_status_code, close_msg):  # pylint: disable=unused-argument
        """Method to process websocket close."""
        logger = logging.getLogger(__name__)
        logger.debug("Websocket connection closed.")
        global_value.check_websocket_if_connect = 0
