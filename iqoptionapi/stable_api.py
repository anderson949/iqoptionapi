# python
from iqoptionapi.api import IQOptionAPI
import iqoptionapi.constants as OP_code
import iqoptionapi.country_id as Country
import threading
import time
import json
import logging
import operator
import iqoptionapi.global_value as global_value
from collections import defaultdict
from collections import deque
from iqoptionapi.expiration import get_expiration_time, get_remaning_time
from iqoptionapi.version_control import api_version
from datetime import datetime, timedelta
from random import randint
from circuitbreaker import circuit

def nested_dict(n, type):
    if n == 1:
        return defaultdict(type)
    else:
        return defaultdict(lambda: nested_dict(n - 1, type))


class IQ_Option:
    __version__ = api_version

    def __init__(self, email, password, active_account_type="PRACTICE"):
        self.size = [1, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800,
                     3600, 7200, 14400, 28800, 43200, 86400, 604800, 2592000]
        self.email = email
        self.password = password
        self.suspend = 0.5
        self.thread = None
        self.subscribe_candle = []
        self.subscribe_candle_all_size = []
        self.subscribe_mood = []
        self.subscribe_indicators = []
        # for digit
        self.get_digital_spot_profit_after_sale_data = nested_dict(2, int)
        self.get_realtime_strike_list_temp_data = {}
        self.get_realtime_strike_list_temp_expiration = 0
       
        # In __init__ method
        self.monitor_thread = threading.Thread(target=self.monitor_connection)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
                
        self.SESSION_HEADER = {
            "User-Agent": r"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.139 Safari/537.36"}
        self.SESSION_COOKIE = {}
        self.api = None
        #
        # --start
        #self.connect()
        # this auto function delay too long

    # --------------------------------------------------------------------------

    def get_server_timestamp(self):
        return self.api.timesync.server_timestamp

    def re_subscribe_stream(self):
        try:
            for ac in self.subscribe_candle:
                sp = ac.split(",")
                self.start_candles_one_stream(sp[0], sp[1])
        except:
            pass
        # -----------------
        try:
            for ac in self.subscribe_candle_all_size:
                self.start_candles_all_size_stream(ac)
        except:
            pass
        # -------------reconnect subscribe_mood
        try:
            for ac in self.subscribe_mood:
                self.start_mood_stream(ac)
        except:
            pass

    def set_session(self, header, cookie):
        self.SESSION_HEADER = header
        self.SESSION_COOKIE = cookie
                
    def connect(self, retries=3, delay=5, sms_code=None):
        """
        Estabelece a conexão com o servidor da IQ Option, com suporte a reconexão
        e autenticação 2FA (caso necessário).
        
        :param retries: Número de tentativas de reconexão em caso de falha.
        :param delay: Intervalo (em segundos) entre tentativas.
        :param sms_code: Código de autenticação 2FA, se aplicável.
        :return: Tuple (bool, str | None) indicando sucesso e mensagem de erro (se houver).
        """
        for attempt in range(retries):
            try:
                # Fecha conexão existente, se houver
                if hasattr(self, 'api') and self.api:
                    try:
                        self.api.close()
                    except Exception as e:
                        logging.warning(f"Falha ao fechar conexão anterior: {e}")
    
                # Inicializa a API com credenciais
                self.api = IQOptionAPI("iqoption.com", self.email, self.password)
    
                # Configura sessão
                self.api.set_session(headers=self.SESSION_HEADER, cookies=self.SESSION_COOKIE)
    
                # Autenticação 2FA (se necessário)
                if sms_code is not None:
                    self.api.setTokenSMS(self.resp_sms)
                    status, reason = self.api.connect2fa(sms_code)
                    if not status:
                        return status, reason
    
                # Conecta ao servidor
                check, reason = self.api.connect()
    
                if check:
                    # Reconecta streams e configurações após conexão
                    self.re_subscribe_stream()
    
                    # Espera até que o ID do saldo seja carregado
                    while global_value.balance_id is None:
                        time.sleep(0.1)
    
                    # Subscrição de mensagens e configurações adicionais
                    self.position_change_all("subscribeMessage", global_value.balance_id)
                    self.order_changed_all("subscribeMessage")
                    self.api.setOptions(1, True)
    
                    logging.info("Conexão estabelecida com sucesso.")
                    return True, None  # Retorna True e None para indicar sucesso
                else:
                    # Verifica se o erro exige 2FA
                    if 'code' in json.loads(reason) and json.loads(reason)['code'] == 'verify':
                        response = self.api.send_sms_code(json.loads(reason)['token'])
                        if response.json().get('code') != 'success':
                            return False, response.json().get('message')
                        self.resp_sms = response
                        return False, "2FA necessária"
    
                    logging.error(f"Falha ao conectar: {reason}")
                    return False, reason  # Retorna False e a mensagem de erro
            except Exception as e:
                logging.error(f"Erro durante a tentativa de conexão: {e}")
                if attempt < retries - 1:
                    logging.info(f"Tentativa {attempt + 1} falhou. Retentando em {delay} segundos...")
                    time.sleep(delay)
                else:
                    logging.error("Todas as tentativas de conexão falharam.")
                    return False, str(e)  # Retorna False e a mensagem de erro

    def ensure_connection(self):
        if not hasattr(self, 'api') or self.api is None:
            logging.error("API não foi inicializada. Tentando conectar...")
            self.connect()
        elif not self.check_connect():
            logging.warning("Conexão perdida. Tentando reconectar...")
            self.connect()
            
    def monitor_connection(self):
        while True:
            try:
                if not self.check_connect():
                    logging.warning("Conexão perdida. Tentando reconectar.")
                    self.connect()
                time.sleep(30)  # Intervalo configurável
            except Exception as e:
                logging.error(f"Erro no monitoramento da conexão: {e}")            
            
    def connect_2fa(self, sms_code):
        return self.connect(sms_code=sms_code)

    def check_connect(self, retries=3, delay=5):
        """
        Verifica se a conexão WebSocket está ativa. Tenta reconectar caso esteja desconectada.
    
        :param retries: Número de tentativas de reconexão.
        :param delay: Tempo em segundos entre tentativas.
        :return: True se conectado, False caso contrário.
        """
        if global_value.check_websocket_if_connect:
            return True
    
        logging.warning("Conexão perdida. Tentando reconectar...")
        for attempt in range(retries):
            try:
                if self.connect():
                    logging.info("Reconexão bem-sucedida.")
                    return True
            except Exception as e:
                logging.error(f"Erro ao tentar reconectar: {e}")
            time.sleep(delay)
    
        logging.error("Falha ao reconectar após várias tentativas.")
        return False

    def api_error_handler(func):
        def wrapper(*args, **kwargs):
            self = args[0]
            retries = kwargs.pop('retries', 3)
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.ConnectionError:
                    logging.error(f"Conexão perdida em {func.__name__}. Tentativa {attempt + 1} de {retries}.")
                    self.connect()
                except AttributeError as e:
                    logging.error(f"Erro de atributo em {func.__name__}: {e}")
                    self.connect()
                except Exception as e:
                    logging.error(f"Erro inesperado em {func.__name__}: {e}")
                    if attempt < retries - 1:
                        time.sleep(2 ** attempt)  # Exponential backoff
                    else:
                        raise
            return None
        return wrapper

    def central_error_handler(self, error, method_name):
        logging.error(f"Erro em {method_name}: {error}")
        # Add recovery actions here

    # _________________________UPDATE ACTIVES OPCODE_____________________
    def get_all_ACTIVES_OPCODE(self):
        return OP_code.ACTIVES

    def update_ACTIVES_OPCODE(self):
        # update from binary option
        self.get_ALL_Binary_ACTIVES_OPCODE()
        # crypto /dorex/cfd
        self.instruments_input_all_in_ACTIVES()
        dicc = {}
        for lis in sorted(OP_code.ACTIVES.items(), key=operator.itemgetter(1)):
            dicc[lis[0]] = lis[1]
        OP_code.ACTIVES = dicc

    def get_name_by_activeId(self, activeId):
        info = self.get_financial_information(activeId)
        try:
            return info["msg"]["data"]["active"]["name"]
        except:
            return None

    def get_financial_information(self, activeId):
        self.api.financial_information = None
        self.api.get_financial_information(activeId)
        while self.api.financial_information == None:
            pass
        return self.api.financial_information

    def get_leader_board(self, country, from_position, to_position, near_traders_count, user_country_id=0, near_traders_country_count=0, top_country_count=0, top_count=0, top_type=2):
        self.api.leaderboard_deals_client = None

        country_id = Country.ID[country]
        self.api.Get_Leader_Board(country_id, user_country_id, from_position, to_position,
                                  near_traders_country_count, near_traders_count, top_country_count, top_count, top_type)

        while self.api.leaderboard_deals_client == None:
            pass
        return self.api.leaderboard_deals_client

    @api_error_handler                
    def get_instruments(self, type, retries=3):
        """
        Busca instrumentos financeiros com suporte a reconexão.
    
        :param type: Tipo de instrumento ("crypto", "forex", "cfd").
        :param retries: Número de tentativas em caso de falha.
        :return: Lista de instrumentos ou None em caso de falha.
        """
        for attempt in range(retries):
            try:
                self.ensure_connection()
                self.api.instruments = None
                self.api.get_instruments(type)
    
                start = time.time()
                while self.api.instruments is None:
                    if time.time() - start > 10:  # Timeout de 10 segundos
                        raise TimeoutError("Tempo limite excedido para get_instruments")
    
                return self.api.instruments
            except Exception as e:
                logging.error(f"Tentativa {attempt + 1} falhou: {e}")
                self.connect()
    
        logging.error(f"Falha ao obter instrumentos do tipo {type} após várias tentativas.")
        return None

    def instruments_input_to_ACTIVES(self, type):
        instruments = self.get_instruments(type)
        for ins in instruments["instruments"]:
            OP_code.ACTIVES[ins["id"]] = ins["active_id"]

    def instruments_input_all_in_ACTIVES(self):
        self.instruments_input_to_ACTIVES("crypto")
        self.instruments_input_to_ACTIVES("forex")
        self.instruments_input_to_ACTIVES("cfd")

    def get_ALL_Binary_ACTIVES_OPCODE(self):
        init_info = self.get_all_init()
        for dirr in (["binary", "turbo"]):
            for i in init_info["result"][dirr]["actives"]:
                OP_code.ACTIVES[(init_info["result"][dirr]
                                 ["actives"][i]["name"]).split(".")[1]] = int(i)

    # _________________________self.api.get_api_option_init_all() wss______________________
    def get_all_init(self):
        self.ensure_connection()     

        while True:
            self.api.api_option_init_all_result = None
            while True:
                try:
                    self.api.get_api_option_init_all()
                    break
                except:
                    logging.error('**error** get_all_init need reconnect')
                    self.connect()
                    time.sleep(5)
            start = time.time()
            while True:
                if time.time() - start > 300:
                    logging.error('**warning** get_all_init late 30 sec')
                    break
                try:
                    if self.api.api_option_init_all_result != None:
                        break
                except:
                    pass
            try:
                if self.api.api_option_init_all_result["isSuccessful"] == True:
                    return self.api.api_option_init_all_result
            except:
                pass

    def get_all_init_v2(self):
        self.api.api_option_init_all_result_v2 = None

        if self.check_connect() == False:
            self.connect()

        self.api.get_api_option_init_all_v2()
        start_t = time.time()
        while self.api.api_option_init_all_result_v2 == None:
            if time.time() - start_t >= 300:
                logging.error('**warning** get_all_init_v2 late 30 sec')
                return None
        return self.api.api_option_init_all_result_v2

        # return OP_code.ACTIVES

    # ------- chek if binary/digit/cfd/stock... if open or not

    def __get_binary_open(self):
        # for turbo and binary pairs
        binary_data = self.get_all_init_v2()
        binary_list = ["binary", "turbo"]
        if binary_data:
            for option in binary_list:
                if option in binary_data:
                    for actives_id in binary_data[option]["actives"]:
                        active = binary_data[option]["actives"][actives_id]
                        name = str(active["name"]).split(".")[1]
                        if active["enabled"] == True:
                            if active["is_suspended"] == True:
                                self.OPEN_TIME[option][name]["open"] = False
                            else:
                                self.OPEN_TIME[option][name]["open"] = True
                        else:
                            self.OPEN_TIME[option][name]["open"] = active["enabled"]    

    def __get_digital_open(self):
        # for digital options
        digital_data = self.get_digital_underlying_list_data()["underlying"]
        for digital in digital_data:
            name = digital["underlying"]
            schedule = digital["schedule"]
            self.OPEN_TIME["digital"][name]["open"] = False
            for schedule_time in schedule:
                start = schedule_time["open"]
                end = schedule_time["close"]
                if start < time.time() < end:
                    self.OPEN_TIME["digital"][name]["open"] = True

    def __get_other_open(self):
        # Crypto and etc pairs
        instrument_list = ["cfd", "forex", "crypto"]
        for instruments_type in instrument_list:
            ins_data = self.get_instruments(instruments_type)["instruments"]
            for detail in ins_data:
                name = detail["name"]
                schedule = detail["schedule"]
                self.OPEN_TIME[instruments_type][name]["open"] = False
                for schedule_time in schedule:
                    start = schedule_time["open"]
                    end = schedule_time["close"]
                    if start < time.time() < end:
                        self.OPEN_TIME[instruments_type][name]["open"] = True

    def get_all_open_time(self):
        # all pairs openned
        self.OPEN_TIME = nested_dict(3, dict)
        binary = threading.Thread(target=self.__get_binary_open)
        digital = threading.Thread(target=self.__get_digital_open)
        other = threading.Thread(target=self.__get_other_open)

        binary.start(), digital.start(), other.start()

        binary.join(), digital.join(), other.join()
        return self.OPEN_TIME

    # --------for binary option detail

    def get_binary_option_detail(self):
        detail = nested_dict(2, dict)
        init_info = self.get_all_init()
        for actives in init_info["result"]["turbo"]["actives"]:
            name = init_info["result"]["turbo"]["actives"][actives]["name"]
            name = name[name.index(".") + 1:len(name)]
            detail[name]["turbo"] = init_info["result"]["turbo"]["actives"][actives]

        for actives in init_info["result"]["binary"]["actives"]:
            name = init_info["result"]["binary"]["actives"][actives]["name"]
            name = name[name.index(".") + 1:len(name)]
            detail[name]["binary"] = init_info["result"]["binary"]["actives"][actives]
        return detail

    def get_all_profit(self):
        all_profit = nested_dict(2, dict)
        init_info = self.get_all_init()
        for actives in init_info["result"]["turbo"]["actives"]:
            name = init_info["result"]["turbo"]["actives"][actives]["name"]
            name = name[name.index(".") + 1:len(name)]
            all_profit[name]["turbo"] = (
                100.0 -
                init_info["result"]["turbo"]["actives"][actives]["option"]["profit"][
                    "commission"]) / 100.0

        for actives in init_info["result"]["binary"]["actives"]:
            name = init_info["result"]["binary"]["actives"][actives]["name"]
            name = name[name.index(".") + 1:len(name)]
            all_profit[name]["binary"] = (
                100.0 -
                init_info["result"]["binary"]["actives"][actives]["option"]["profit"][
                    "commission"]) / 100.0
        return all_profit

    # ----------------------------------------

    # ______________________________________self.api.getprofile() https________________________________

    def get_profile_async(self, timeout=30):
        """
        Obtém o perfil do usuário de forma assíncrona com um tempo limite.
        
        :param timeout: Tempo máximo de espera em segundos.
        :return: Dados do perfil ou None em caso de erro.
        """
        start_time = time.time()
        while self.api.profile.msg is None:
            if time.time() - start_time > timeout:
                logging.error("Tempo limite excedido ao obter perfil.")
                return None
            time.sleep(0.1)
        return self.api.profile.msg

    def get_currency(self):
        balances_raw = self.get_balances()
        for balance in balances_raw["msg"]:
            if balance["id"] == global_value.balance_id:
                return balance["currency"]

    def get_balance_id(self):
        return global_value.balance_id

    def get_balance(self, retries=3):
        """
        Obtém o saldo da conta atual, com retry em caso de falha.
        
        :param retries: Número de tentativas.
        :return: Saldo atual ou None em caso de falha.
        """
        for attempt in range(retries):
            try:
                balances_raw = self.get_balances()
                for balance in balances_raw["msg"]:
                    if balanc
