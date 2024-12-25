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
from websocket import WebSocketConnectionClosedException

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
        self.SESSION_HEADER = {
            "User-Agent": r"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.139 Safari/537.36"}
        self.SESSION_COOKIE = {}
        #
        # --start
        # self.connect()
        # this auto function delay too long

    # --------------------------------------------------------------------------

    def get_server_timestamp(self):
        return self.api.timesync.server_timestamp

    def re_subscribe_stream(self):
        """
        Reassina automaticamente os streams previamente configurados.
    
        Este método é usado após uma reconexão para garantir que todos os streams 
        (candle, mood e outros) sejam reassinados. Ele tenta cada categoria de assinatura
        e ignora falhas individuais, continuando com as demais.
    
        Streams Reassinados:
            - subscribe_candle: Stream de candles individuais.
            - subscribe_candle_all_size: Stream de candles em todos os tamanhos.
            - subscribe_mood: Stream de sentimento dos traders.
    
        Returns:
            None
        """
        # Reassinar candles individuais
        for ac in self.subscribe_candle:
            try:
                asset, size = ac.split(",")
                self.start_candles_one_stream(asset, size)
            except Exception as e:
                print(f"Erro ao reassinar candle de {ac}: {e}")
    
        # Reassinar candles de todos os tamanhos
        for ac in self.subscribe_candle_all_size:
            try:
                self.start_candles_all_size_stream(ac)
            except Exception as e:
                print(f"Erro ao reassinar candle de todos os tamanhos para {ac}: {e}")
    
        # Reassinar stream de sentimento dos traders
        for ac in self.subscribe_mood:
            try:
                self.start_mood_stream(ac)
            except Exception as e:
                print(f"Erro ao reassinar stream de sentimento para {ac}: {e}")

    def set_session(self, header, cookie):
        self.SESSION_HEADER = header
        self.SESSION_COOKIE = cookie
            
    def connect(self, sms_code=None):
        """
        Estabelece ou reestabelece a conexão com a API da IQ Option.
        Retorna (status, reason) onde:
          - status: True/False indicando sucesso ou falha
          - reason: Mensagem explicativa
        """
        try:
            # Fecha conexões anteriores, se existirem
            if hasattr(self, 'api') and self.api:
                self.api.close()
            self.api = IQOptionAPI("iqoption.com", self.email, self.password)
            
            # Autenticação 2FA (se necessário)
            if sms_code:
                self.api.setTokenSMS(self.resp_sms)
                status, reason = self.api.connect2fa(sms_code)
                return status, reason
            
            # Conexão padrão
            status, reason = self.api.connect()
            if status:
                print("[SUCESSO] Conexão estabelecida.")
                self._initialize_subscriptions()
                return True, "Conexão estabelecida com sucesso."
            else:
                print(f"[FALHA] Não foi possível conectar: {reason}")
                return False, reason
        except Exception as e:
            print(f"[ERRO] Falha ao conectar: {e}")
            return False, str(e)
            
    def disconnect(self):
        """
        Encerra a conexão com a API de forma segura.
        """
        try:
            if hasattr(self, 'api') and self.api:
                self.api.close()
            print("[INFO] Conexão encerrada com sucesso.")
        except Exception as e:
            print(f"[ERRO] Falha ao encerrar conexão: {e}")       
 
    def keep_connection_alive(self):
        """
        Garante que a conexão com a API seja persistente e resiliente a desconexões.
        """
        try:
            while True:  # Loop infinito para persistência
                if not global_value.check_websocket_if_connect:
                    print("[AVISO] Conexão perdida. Tentando reconectar...")
                    self.connect()
                    if global_value.check_websocket_if_connect:
                        print("[SUCESSO] Reconexão bem-sucedida.")
                    else:
                        print("[FALHA] Reconexão falhou. Tentando novamente em 5 segundos...")
                        time.sleep(5)  # Pausa antes de tentar reconectar novamente
                else:
                    print("[INFO] Conexão ativa. Monitorando...")
                    time.sleep(10)  # Monitoramento periódico (10 segundos)
        except KeyboardInterrupt:
            print("\n[INFO] Encerramento solicitado pelo operador.")
            self.disconnect()
        except Exception as e:
            print(f"[ERRO] Ocorreu um erro inesperado: {e}")

    def ensure_connection(self):
        """
        Garante que a conexão com a API está ativa.
        Reconecta automaticamente caso seja necessário.
        """
        try:
            if not global_value.check_websocket_if_connect:
                print("[AVISO] Conexão perdida. Tentando reconectar...")
                self.connect()
        except WebSocketConnectionClosedException:
            print("[ERRO] Conexão WebSocket fechada. Reconectando...")
            self.connect()
        except Exception as e:
            print(f"[ERRO] Falha ao garantir a conexão: {e}")
                                          
    def _initialize_subscriptions(self):
        """
        Inicializa as assinaturas após a conexão bem-sucedida.
    
        Este método é chamado internamente após a conexão com a API ser estabelecida.
        Ele garante que streams, atualizações de posições e ordens sejam configuradas.
    
        Executa os seguintes passos:
            - Reassina streams previamente configurados.
            - Aguarda a sincronização do balance_id global.
            - Configura atualizações automáticas para posições e ordens.
    
        Returns:
            None
        """
        self.re_subscribe_stream()
        while global_value.balance_id is None:
            time.sleep(0.1)  # Reduzir ocupação da CPU enquanto aguarda o balance_id
        self.position_change_all("subscribeMessage", global_value.balance_id)
        self.order_changed_all("subscribeMessage")
        self.api.setOptions(1, True)
    
    def connect_2fa(self, sms_code):
        return self.connect(sms_code=sms_code)

    def check_connect(self):
        """
        Verifica se a conexão com a API está ativa.
    
        Este método verifica o estado atual da conexão com a API.
    
        Retorna:
            bool: True se a conexão estiver ativa, False caso contrário.
        """
        if not global_value.check_websocket_if_connect:
            return False
        return True

    # _________________________UPDATE ACTIVES OPCODE_____________________
    def get_all_ACTIVES_OPCODE(self):
        return OP_code.ACTIVES

    def update_ACTIVES_OPCODE(self):
        """
        Atualiza a lista de códigos de operação disponíveis.
    
        Este método consulta a API para atualizar os códigos de operação (opções binárias, criptomoedas, etc.)
        e reorganiza os ativos para uma estrutura ordenada.
    
        Retorna:
            None
        """
        self.get_ALL_Binary_ACTIVES_OPCODE()
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

    def get_instruments(self, type):
        # type="crypto"/"forex"/"cfd"
        time.sleep(self.suspend)
        self.api.instruments = None
        while self.api.instruments == None:
            try:
                self.api.get_instruments(type)
                start = time.time()
                while self.api.instruments == None and time.time() - start < 10:
                    pass
            except:
                logging.error('**error** api.get_instruments need reconnect')
                self.connect()
        return self.api.instruments

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

    def get_all_init(self):
        """
        Obtém informações iniciais da API.
    
        Este método coleta todas as informações iniciais necessárias da API 
        para configurar os ativos disponíveis e outras funcionalidades.
    
        Retorna:
            dict: Dados retornados pela API com as informações iniciais.
        """
        while True:
            self.api.api_option_init_all_result = None
            try:
                self.api.get_api_option_init_all()
            except Exception as e:
                print(f"[ERRO] Falha ao obter informações iniciais: {e}. Tentando reconectar...")
                self.connect()
                time.sleep(5)
                continue
    
            # Espera até obter os resultados ou atingir o timeout
            start = time.time()
            while self.api.api_option_init_all_result is None:
                if time.time() - start > 30:
                    print("[AVISO] Demora ao obter informações iniciais (30 segundos).")
                    break
                time.sleep(0.1)
    
            try:
                if self.api.api_option_init_all_result["isSuccessful"]:
                    return self.api.api_option_init_all_result
            except KeyError:
                pass

    def get_all_init_v2(self):
        self.api.api_option_init_all_result_v2 = None

        if self.check_connect() == False:
            self.connect()

        self.api.get_api_option_init_all_v2()
        start_t = time.time()
        while self.api.api_option_init_all_result_v2 == None:
            if time.time() - start_t >= 30:
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
        """
        Verifica os ativos digitais disponíveis.
        """
        try:
            # Substitua aqui por um método correto, como `get_assets_open`
            digital_assets = self.api.get_assets_open("digital")
            for asset, details in digital_assets.items():
                if details["open"]:
                    self.OPEN_TIME["digital"][asset] = details
        except Exception as e:
            print(f"[ERRO] Falha ao verificar ativos digitais: {e}")

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
        """
        Verifica a abertura de todos os mercados (binary, digital e outros).
        Lida com reconexões em caso de falhas no WebSocket.
        """
        self.OPEN_TIME = nested_dict(3, dict)
        
        try:
            self.__get_binary_open()  # Verifica ativos binários
            self.__get_digital_open()  # Verifica ativos digitais
            self.__get_other_open()  # Verifica outros mercados
        except WebSocketConnectionClosedException as e:
            print(f"[AVISO] Conexão WebSocket fechada: {e}. Tentando reconectar...")
            self.connect()  # Reconectar
            self.get_all_open_time()  # Reexecutar após reconexão
        except Exception as e:
            print(f"[ERRO] Falha ao verificar ativos abertos: {e}")
        
        return self.OPEN_TIME

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

    def get_profile_ansyc(self):
        """
        Obtém informações do perfil do usuário de forma assíncrona.
    
        Este método solicita o perfil do usuário à API e aguarda a resposta. 
        Em caso de falha, reconecta automaticamente e tenta novamente.
    
        Retorna:
            dict: Informações do perfil do usuário.
            None: Retorna None se a operação falhar após múltiplas tentativas.
    
        Exceções:
            TimeoutError: Lançada se o tempo limite de espera for excedido.
        """
        timeout = 10
        max_attempts = 3
    
        for attempt in range(max_attempts):
            try:
                start_time = time.time()
                while self.api.profile.msg is None:
                    if time.time() - start_time > timeout:
                        raise TimeoutError("Tempo excedido ao obter perfil do usuário.")
                    time.sleep(0.1)
    
                #print("[SUCESSO] Perfil do usuário obtido com sucesso.")
                return self.api.profile.msg
    
            except Exception as e:
                print(f"[AVISO] Tentativa {attempt + 1} falhou ao obter perfil: {e}. Reconectando...")
                self.connect()
                time.sleep(2 ** attempt)
    
        print("[FALHA] Não foi possível obter o perfil após múltiplas tentativas.")
        return None

    def get_currency(self):
        balances_raw = self.get_balances()
        for balance in balances_raw["msg"]:
            if balance["id"] == global_value.balance_id:
                return balance["currency"]

    def get_balance_id(self):
        return global_value.balance_id

    def get_balance(self):
        """
        Obtém o saldo da conta atual.
    
        Este método coleta o saldo da conta (real ou prática) vinculada ao `balance_id` global.
    
        Retorna:
            float: O saldo disponível.
            None: Retorna None se não for possível obter o saldo.
        """
        balances_raw = self.get_balances()
        for balance in balances_raw["msg"]:
            if balance["id"] == global_value.balance_id:
                return balance["amount"]
        return None

    def get_balances(self):
        self.api.balances_raw = None
        self.api.get_balances()
        while self.api.balances_raw == None:
            pass
        return self.api.balances_raw

    def get_balance_mode(self):
        # self.api.profile.balance_type=None
        profile = self.get_profile_ansyc()
        for balance in profile.get("balances"):
            if balance["id"] == global_value.balance_id:
                if balance["type"] == 1:
                    return "REAL"
                elif balance["type"] == 4:
                    return "PRACTICE"

                elif balance["type"] == 2:
                    return "TOURNAMENT"

    def reset_practice_balance(self):
        self.api.training_balance_reset_request = None
        self.api.reset_training_balance()
        while self.api.training_balance_reset_request == None:
            pass
        return self.api.training_balance_reset_request

    def position_change_all(self, Main_Name, user_balance_id):
        instrument_type = ["cfd", "forex", "crypto",
                           "digital-option", "turbo-option", "binary-option"]
        for ins in instrument_type:
            self.api.portfolio(Main_Name=Main_Name, name="portfolio.position-changed",
                               instrument_type=ins, user_balance_id=user_balance_id)

    def order_changed_all(self, Main_Name):
        instrument_type = ["cfd", "forex", "crypto",
                           "digital-option", "turbo-option", "binary-option"]
        for ins in instrument_type:
            self.api.portfolio(
                Main_Name=Main_Name, name="portfolio.order-changed", instrument_type=ins)

    def change_balance(self, Balance_MODE):
        def set_id(b_id):
            if global_value.balance_id != None:
                self.position_change_all(
                    "unsubscribeMessage", global_value.balance_id)

            global_value.balance_id = b_id

            self.position_change_all("subscribeMessage", b_id)

        real_id = None
        practice_id = None
        tournament_id = None

        for balance in self.get_profile_ansyc()["balances"]:
            if balance["type"] == 1:
                real_id = balance["id"]
            if balance["type"] == 4:
                practice_id = balance["id"]

            if balance["type"] == 2:
                tournament_id = balance["id"]

        if Balance_MODE == "REAL":
            set_id(real_id)

        elif Balance_MODE == "PRACTICE":
            set_id(practice_id)

        elif Balance_MODE == "TOURNAMENT":
            set_id(tournament_id)

        else:
            logging.error("ERROR doesn't have this mode")
            exit(1)

    # ________________________________________________________________________
    # _______________________        CANDLE      _____________________________
    # ________________________self.api.getcandles() wss________________________

    def get_candles(self, ACTIVES, interval, count, endtime):
        """
        Obtém dados históricos de candles para um ativo.
    
        Este método recupera informações de candles (gráficos de velas) 
        de um ativo específico para um intervalo de tempo definido.
    
        Parâmetros:
            ACTIVES (str): Nome do ativo, por exemplo, "EURUSD".
            interval (int): Intervalo de tempo dos candles, em segundos (ex.: 60 para 1 minuto).
            count (int): Número de candles a serem obtidos.
            endtime (int): Timestamp Unix indicando o final do período de candles.
    
        Retorna:
            list: Lista com os dados dos candles obtidos.
            None: Retorna None se a operação falhar.
    
        Exceções:
            TimeoutError: Lançada se o tempo limite de espera for excedido.
        """
        self.api.candles.candles_data = None
    
        if ACTIVES not in OP_code.ACTIVES:
            print(f"[ERRO] Ativo '{ACTIVES}' não encontrado nos códigos de operação.")
            return None
    
        timeout = 10  # Limite por tentativa
        max_attempts = 3  # Máximo de 3 tentativas
    
        for attempt in range(max_attempts):
            try:
                self.api.getcandles(OP_code.ACTIVES[ACTIVES], interval, count, endtime)
    
                # Espera até que os dados sejam recebidos ou timeout
                start_time = time.time()
                while self.api.candles.candles_data is None:
                    if time.time() - start_time > timeout:
                        raise TimeoutError(f"Tempo excedido ao buscar candles para {ACTIVES}.")
                    time.sleep(0.1)
    
                # Dados recebidos com sucesso
                #print(f"[SUCESSO] Dados de candles para {ACTIVES} obtidos com sucesso.")
                return self.api.candles.candles_data
    
            except Exception as e:
                print(f"[AVISO] Tentativa {attempt + 1} falhou ao buscar candles: {e}. Reconectando...")
                self.connect()
                time.sleep(2 ** attempt)
    
        print(f"[FALHA] Não foi possível obter candles para {ACTIVES} após {max_attempts} tentativas.")
        return None

    def start_candles_stream(self, ACTIVE, size, maxdict):

        if size == "all":
            for s in self.size:
                self.full_realtime_get_candle(ACTIVE, s, maxdict)
                self.api.real_time_candles_maxdict_table[ACTIVE][s] = maxdict
            self.start_candles_all_size_stream(ACTIVE)
        elif size in self.size:
            self.api.real_time_candles_maxdict_table[ACTIVE][size] = maxdict
            self.full_realtime_get_candle(ACTIVE, size, maxdict)
            self.start_candles_one_stream(ACTIVE, size)

        else:
            logging.error(
                '**error** start_candles_stream please input right size')

    def stop_candles_stream(self, ACTIVE, size):
        if size == "all":
            self.stop_candles_all_size_stream(ACTIVE)
        elif size in self.size:
            self.stop_candles_one_stream(ACTIVE, size)
        else:
            logging.error(
                '**error** start_candles_stream please input right size')

    def get_realtime_candles(self, ACTIVE, size):
        if size == "all":
            try:
                return self.api.real_time_candles[ACTIVE]
            except:
                logging.error(
                    '**error** get_realtime_candles() size="all" can not get candle')
                return False
        elif size in self.size:
            try:
                return self.api.real_time_candles[ACTIVE][size]
            except:
                logging.error(
                    '**error** get_realtime_candles() size=' + str(size) + ' can not get candle')
                return False
        else:
            logging.error(
                '**error** get_realtime_candles() please input right "size"')

    def get_all_realtime_candles(self):
        return self.api.real_time_candles

    ################################################
    # ---------REAL TIME CANDLE Subset Function---------
    ################################################
    # ---------------------full dict get_candle-----------------------

    def full_realtime_get_candle(self, ACTIVE, size, maxdict):
        candles = self.get_candles(
            ACTIVE, size, maxdict, self.api.timesync.server_timestamp)
        for can in candles:
            self.api.real_time_candles[str(
                ACTIVE)][int(size)][can["from"]] = can

    # ------------------------Subscribe ONE SIZE-----------------------
    def start_candles_one_stream(self, ACTIVE, size):
        """
        Inicia um stream de candles para um ativo específico e tamanho.
    
        Este método assina um stream de candles para um ativo (`ACTIVE`) em um tamanho 
        de intervalo específico (`size`). Ele verifica continuamente até que o stream 
        seja configurado ou até que o tempo limite de 20 segundos seja alcançado.
    
        Args:
            ACTIVE (str): Nome do ativo (por exemplo, "EURUSD").
            size (int): Tamanho do intervalo em segundos (exemplo: 60 para 1 minuto).
    
        Returns:
            bool: 
                - True: Stream iniciado com sucesso.
                - False: Falha ao iniciar o stream no tempo limite.
        """
        # Adiciona a assinatura do candle ao controle local, se ainda não existir
        candle_key = f"{ACTIVE},{size}"
        if candle_key not in self.subscribe_candle:
            self.subscribe_candle.append(candle_key)
    
        # Inicia o temporizador para o tempo limite
        start_time = time.time()
        self.api.candle_generated_check.setdefault(str(ACTIVE), {})[int(size)] = {}
    
        # Loop para verificar a inicialização do stream
        while time.time() - start_time <= 20:
            try:
                # Verifica se o stream foi configurado
                if self.api.candle_generated_check[str(ACTIVE)][int(size)] == True:
                    return True
            except KeyError:
                pass  # Ignorar erros de chave inexistente
    
            # Tentar assinar o stream
            try:
                self.api.subscribe(OP_code.ACTIVES[ACTIVE], size)
            except Exception as e:
                print(f"Erro ao assinar stream de {ACTIVE} com tamanho {size}: {e}")
                self.connect()  # Reestabelecer conexão se necessário
            time.sleep(1)
    
        print(f"Tempo limite ao iniciar stream de {ACTIVE} com tamanho {size}.")
        return False

    def stop_candles_one_stream(self, ACTIVE, size):
        """
        Interrompe o stream de candles para um ativo e tamanho específicos.
    
        Este método cancela a assinatura de um stream de candles para o ativo (`ACTIVE`) 
        e intervalo (`size`) especificados. Verifica continuamente até que a assinatura 
        seja encerrada ou atinja o tempo limite.
    
        Args:
            ACTIVE (str): Nome do ativo (por exemplo, "EURUSD").
            size (int): Tamanho do intervalo em segundos (exemplo: 60 para 1 minuto).
    
        Returns:
            bool: 
                - True: Stream interrompido com sucesso.
                - False: Falha ao interromper o stream no tempo limite.
        """
        # Remove o stream da lista local de assinaturas
        candle_key = f"{ACTIVE},{size}"
        if candle_key in self.subscribe_candle:
            self.subscribe_candle.remove(candle_key)
    
        # Inicia o temporizador para o tempo limite
        start_time = time.time()
    
        # Loop para interromper o stream
        while time.time() - start_time <= 20:  # Tempo limite de 20 segundos
            try:
                # Verifica se o stream foi interrompido
                if self.api.candle_generated_check.get(str(ACTIVE), {}).get(int(size)) == {}:
                    return True
            except KeyError:
                pass  # Ignorar erros de chave inexistente
    
            # Tentar cancelar a assinatura
            try:
                self.api.candle_generated_check[str(ACTIVE)][int(size)] = {}
                self.api.unsubscribe(OP_code.ACTIVES[ACTIVE], size)
            except Exception as e:
                print(f"Erro ao cancelar stream de {ACTIVE} com tamanho {size}: {e}")
            time.sleep(self.suspend)  # Pausa configurável entre tentativas
    
        print(f"Tempo limite ao cancelar stream de {ACTIVE} com tamanho {size}.")
        return False

    # ------------------------Subscribe ALL SIZE-----------------------

    def start_candles_all_size_stream(self, ACTIVE):
        self.api.candle_generated_all_size_check[str(ACTIVE)] = {}
        if (str(ACTIVE) in self.subscribe_candle_all_size) == False:
            self.subscribe_candle_all_size.append(str(ACTIVE))
        start = time.time()
        while True:
            if time.time() - start > 20:
                logging.error('**error** fail ' + ACTIVE +
                              ' start_candles_all_size_stream late for 10 sec')
                return False
            try:
                if self.api.candle_generated_all_size_check[str(ACTIVE)] == True:
                    return True
            except:
                pass
            try:
                self.api.subscribe_all_size(OP_code.ACTIVES[ACTIVE])
            except:
                logging.error(
                    '**error** start_candles_all_size_stream reconnect')
                self.connect()
            time.sleep(1)

    def stop_candles_all_size_stream(self, ACTIVE):
        if (str(ACTIVE) in self.subscribe_candle_all_size) == True:
            self.subscribe_candle_all_size.remove(str(ACTIVE))
        while True:
            try:
                if self.api.candle_generated_all_size_check[str(ACTIVE)] == {}:
                    break
            except:
                pass
            self.api.candle_generated_all_size_check[str(ACTIVE)] = {}
            self.api.unsubscribe_all_size(OP_code.ACTIVES[ACTIVE])
            time.sleep(self.suspend * 10)

    # ------------------------top_assets_updated---------------------------------------------

    def subscribe_top_assets_updated(self, instrument_type):
        self.api.Subscribe_Top_Assets_Updated(instrument_type)

    def unsubscribe_top_assets_updated(self, instrument_type):
        self.api.Unsubscribe_Top_Assets_Updated(instrument_type)

    def get_top_assets_updated(self, instrument_type):
        if instrument_type in self.api.top_assets_updated_data:
            return self.api.top_assets_updated_data[instrument_type]
        else:
            return None

    # ------------------------commission_________
    # instrument_type: "binary-option"/"turbo-option"/"digital-option"/"crypto"/"forex"/"cfd"
    def subscribe_commission_changed(self, instrument_type):

        self.api.Subscribe_Commission_Changed(instrument_type)

    def unsubscribe_commission_changed(self, instrument_type):
        self.api.Unsubscribe_Commission_Changed(instrument_type)

    def get_commission_change(self, instrument_type):
        return self.api.subscribe_commission_changed_data[instrument_type]

    # -----------------------------------------------

    # -----------------traders_mood----------------------

    def start_mood_stream(self, ACTIVES, instrument="turbo-option"):
        if ACTIVES in self.subscribe_mood == False:
            self.subscribe_mood.append(ACTIVES)

        while True:
            self.api.subscribe_Traders_mood(
                OP_code.ACTIVES[ACTIVES], instrument)
            try:
                self.api.traders_mood[OP_code.ACTIVES[ACTIVES]]
                break
            except:
                time.sleep(5)

    def stop_mood_stream(self, ACTIVES, instrument="turbo-option"):
        if ACTIVES in self.subscribe_mood == True:
            del self.subscribe_mood[ACTIVES]
        self.api.unsubscribe_Traders_mood(OP_code.ACTIVES[ACTIVES], instrument)

    def get_traders_mood(self, ACTIVES):
        # return highter %
        return self.api.traders_mood[OP_code.ACTIVES[ACTIVES]]

    def get_all_traders_mood(self):
        # return highter %
        return self.api.traders_mood

##############################################################################################

    # -----------------technical_indicators----------------------

    def get_technical_indicators(self, ACTIVES):
        request_id = self.api.get_Technical_indicators(
            OP_code.ACTIVES[ACTIVES])
        while self.api.technical_indicators.get(request_id) == None:
            pass
        return self.api.technical_indicators[request_id]

##############################################################################################


##############################################################################################

    def check_binary_order(self, order_id):
        while order_id not in self.api.order_binary:
            pass
        your_order = self.api.order_binary[order_id]
        del self.api.order_binary[order_id]
        return your_order

    def check_win_v4(self, id_number):
        """
        Verifica o resultado de uma operação com base no ID da ordem.
        Atualiza métricas diretamente no retorno.
        """
        timeout = 60  # Tempo máximo de espera
        start_time = time.time()
        
        while time.time() - start_time <= timeout:
            try:
                # Garante que a conexão está ativa
                if not global_value.check_websocket_if_connect:
                    print("[AVISO] Reconectando...")
                    self.connect()
                
                # Busca o resultado da ordem
                result = self.api.socket_option_closed.get(id_number)
                if result and "msg" in result:
                    msg = result["msg"]
                    win_status = msg.get("win", "undefined")
                    
                    if win_status == "equal":
                        print("[EMPATE] Lucro: $ 0.00")
                        return "equal", 0.0
                    elif win_status == "loose":
                        loss = -float(msg.get("sum", 0.0))
                        print(f"[DERROTA] Perda: ${loss:.2f}")
                        return "loose", loss
                    elif win_status == "win":
                        profit = float(msg.get("win_amount", 0.0)) - float(msg.get("sum", 0.0))
                        print(f"[VITÓRIA] Lucro: ${profit:.2f}")
                        return "win", profit
            except Exception as e:
                print(f"[ERRO] Falha ao verificar resultado: {e}")
            time.sleep(1)  # Aguarda antes de tentar novamente
        
        print(f"[FALHA] Tempo limite excedido para a ordem {id_number}.")
        return "timeout", 0.0
    
    def check_result_forex(self, order_id):
        """
        Verifica o resultado de uma operação em Forex, Criptomoedas ou Ações.
    
        Parâmetros:
            order_id (int): ID da ordem enviada.
    
        Retorna:
            dict: Resultado contendo status, lucro/prejuízo e detalhes da operação.
        """
        timeout = 120  # Tempo limite para aguardar o fechamento da operação
        start_time = time.time()
    
        while time.time() - start_time <= timeout:
            try:
                result = self.api.get_order_result(order_id)
                if result and result.get("status") == "closed":
                    profit = result.get("profit_amount", 0.0)
                    print(f"[RESULTADO] Ordem {order_id} encerrada. Lucro/Prejuízo: {profit}")
                    return {
                        "status": "closed",
                        "profit": profit,
                        "details": result
                    }
            except Exception as e:
                print(f"[ERRO] Falha ao verificar resultado da ordem {order_id}: {e}")
                time.sleep(1)
    
        print(f"[FALHA] Tempo limite excedido ao aguardar resultado da ordem {order_id}.")
        return {"status": "timeout", "profit": 0.0, "details": None}
        
    def close_forex(self, order_id):
        """
        Fecha uma posição aberta em Forex, Criptomoedas ou Ações.
    
        Parâmetros:
            order_id (int): ID da ordem que será fechada.
    
        Retorna:
            dict: Resultado do encerramento, contendo status e detalhes.
        """
        max_attempts = 3  # Número máximo de tentativas
        for attempt in range(max_attempts):
            try:
                # Solicita o fechamento da ordem
                result = self.api.close_order(order_id)
                if result and result.get("status") == "closed":
                    print(f"[SUCESSO] Posição {order_id} fechada com sucesso. Detalhes: {result}")
                    return {"status": "success", "details": result}
    
                # Caso a API retorne um erro, tratamos aqui
                if result and result.get("status") != "closed":
                    print(f"[FALHA] Não foi possível fechar a posição {order_id}. Status retornado: {result.get('status')}")
                    return {"status": "error", "message": "A posição não foi fechada.", "details": result}
    
            except Exception as e:
                print(f"[AVISO] Tentativa {attempt + 1} falhou ao fechar posição {order_id}: {e}. Reconectando...")
                self.connect()
                time.sleep(2 ** attempt)  # Atraso exponencial entre tentativas
    
        print(f"[FALHA] Não foi possível fechar a posição {order_id} após {max_attempts} tentativas.")
        return {"status": "error", "message": "Falha após múltiplas tentativas"}
    
    def get_betinfo(self, id_number):
        # INPUT:int
        while True:
            self.api.game_betinfo.isSuccessful = None
            start = time.time()
            try:
                self.api.get_betinfo(id_number)
            except:
                logging.error(
                    '**error** def get_betinfo  self.api.get_betinfo reconnect')
                self.connect()
            while self.api.game_betinfo.isSuccessful == None:
                if time.time() - start > 10:
                    logging.error(
                        '**error** get_betinfo time out need reconnect')
                    self.connect()
                    self.api.get_betinfo(id_number)
                    time.sleep(self.suspend * 10)
            if self.api.game_betinfo.isSuccessful == True:
                return self.api.game_betinfo.isSuccessful, self.api.game_betinfo.dict
            else:
                return self.api.game_betinfo.isSuccessful, None
            time.sleep(self.suspend * 10)

    def get_optioninfo(self, limit):
        self.api.api_game_getoptions_result = None
        self.api.get_options(limit)
        while self.api.api_game_getoptions_result == None:
            pass

        return self.api.api_game_getoptions_result

    def get_optioninfo_v2(self, limit):
        self.api.get_options_v2_data = None
        self.api.get_options_v2(limit, "binary,turbo")
        while self.api.get_options_v2_data == None:
            pass

        return self.api.get_options_v2_data

    # __________________________BUY__________________________

    # __________________FOR OPTION____________________________

    def buy_multi(self, price, ACTIVES, ACTION, expirations):
        self.api.buy_multi_option = {}
        if len(price) == len(ACTIVES) == len(ACTION) == len(expirations):
            buy_len = len(price)
            for idx in range(buy_len):
                self.api.buyv3(
                    price[idx], OP_code.ACTIVES[ACTIVES[idx]], ACTION[idx], expirations[idx], idx)
            while len(self.api.buy_multi_option) < buy_len:
                pass
            buy_id = []
            for key in sorted(self.api.buy_multi_option.keys()):
                try:
                    value = self.api.buy_multi_option[str(key)]
                    buy_id.append(value["id"])
                except:
                    buy_id.append(None)

            return buy_id
        else:
            logging.error('buy_multi error please input all same len')

    def get_remaning(self, duration):
        for remaning in get_remaning_time(self.api.timesync.server_timestamp):
            if remaning[0] == duration:
                return remaning[1]
        logging.error('get_remaning(self,duration) ERROR duration')
        return "ERROR duration"

    def buy_by_raw_expirations(self, price, active, direction, option, expired):

        self.api.buy_multi_option = {}
        self.api.buy_successful = None
        req_id = "buyraw"
        try:
            self.api.buy_multi_option[req_id]["id"] = None
        except:
            pass
        self.api.buyv3_by_raw_expired(
            price, OP_code.ACTIVES[active], direction, option, expired, request_id=req_id)
        start_t = time.time()
        id = None
        self.api.result = None
        while self.api.result == None or id == None:
            try:
                if "message" in self.api.buy_multi_option[req_id].keys():
                    logging.error(
                        '**warning** buy' + str(self.api.buy_multi_option[req_id]["message"]))
                    return False, self.api.buy_multi_option[req_id]["message"]
            except:
                pass
            try:
                id = self.api.buy_multi_option[req_id]["id"]
            except:
                pass
            if time.time() - start_t >= 5:
                logging.error('**warning** buy late 5 sec')
                return False, None

        return self.api.result, self.api.buy_multi_option[req_id]["id"]

def buy(self, price, ACTIVES, ACTION, expirations):
    """
    Realiza a compra de uma opção e atualiza métricas após verificar o resultado.
    """
    try:
        # Enviar ordem
        req_id = str(randint(0, 10000))
        self.api.buyv3(float(price), OP_code.ACTIVES[ACTIVES], ACTION, expirations, req_id)
        
        # Aguardar resposta da compra
        start_time = time.time()
        while req_id not in self.api.buy_multi_option:
            if time.time() - start_time > 10:  # Timeout para resposta da compra
                raise TimeoutError(f"[FALHA] Tempo limite excedido ao enviar ordem para {ACTIVES}.")
            time.sleep(0.1)
        
        order = self.api.buy_multi_option.get(req_id)
        if not order or "id" not in order:
            raise ValueError(f"[FALHA] Ordem não foi processada corretamente: {order}")
        
        print(f"[SUCESSO] Compra realizada para o ativo {ACTIVES}. ID da ordem: {order['id']}")
        
        # Verificar o resultado da ordem
        status, payout = self.check_win_v4(order["id"])
        
        # Atualizar métricas após o resultado
        if status == "win":
            self.wins += 1
            self.balance += payout
        elif status == "loose":
            self.losses += 1
            self.balance += payout
        elif status == "equal":
            self.draws += 1
        
        # Calcular assertividade
        total_operations = self.wins + self.losses + self.draws
        self.assertiveness = (self.wins / total_operations) * 100 if total_operations > 0 else 0
        
        # Exibir status atualizado
        print(f"Saldo: ${self.balance:.2f} | Vitórias: {self.wins} | Derrotas: {self.losses} | Empates: {self.draws}")
        print(f"Assertividade: {self.assertiveness:.2f}%")
        return {"status": status, "payout": payout}
    except Exception as e:
        print(f"[ERRO] Falha ao realizar compra: {e}")
        return {"status": "error", "message": str(e)}
        
    def buy_forex(self, active, amount, action, leverage, stop_loss=None, take_profit=None):
        """
        Realiza a compra de uma posição em Forex, Criptomoedas ou Ações.
    
        Parâmetros:
            active (str): Nome do ativo, por exemplo, "EURUSD".
            amount (float): Quantia a ser investida.
            action (str): Direção da operação, "buy" ou "sell".
            leverage (int): Alavancagem a ser utilizada.
            stop_loss (float, opcional): Valor de stop-loss para encerrar a operação automaticamente.
            take_profit (float, opcional): Valor de take-profit para encerrar a operação automaticamente.
    
        Retorna:
            dict: Resultado da operação contendo ID e status.
        """
        action = action.lower()
        if action not in ["buy", "sell"]:
            print(f"[ERRO] Ação inválida '{action}'. Use 'buy' ou 'sell'.")
            return {"status": "error", "message": "Ação inválida"}
    
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Envia a ordem
                order_id = self.api.buy_forex(active, amount, action, leverage, stop_loss, take_profit)
                if order_id:
                    print(f"[SUCESSO] Compra realizada para o ativo {active}. ID da ordem: {order_id}")
                    return {"status": "success", "id": order_id}
    
            except Exception as e:
                print(f"[AVISO] Tentativa {attempt + 1} falhou ao comprar {active}: {e}. Reconectando...")
                self.connect()
                time.sleep(2 ** attempt)
    
        print(f"[FALHA] Não foi possível realizar a compra para {active} após {max_attempts} tentativas.")
        return {"status": "error", "message": "Falha após múltiplas tentativas"}        

    def sell_option(self, options_ids):
        """
        Realiza a venda de uma ou mais opções.
    
        Este método solicita à API a venda de opções identificadas por seus IDs. 
        Ele tenta reconectar automaticamente em caso de falha e possui limite de tentativas.
    
        Parâmetros:
            options_ids (list): Lista com os IDs das opções a serem vendidas.
    
        Retorna:
            dict: Resposta da API com os detalhes da venda.
            None: Retorna None se a operação falhar após múltiplas tentativas.
    
        Exceções:
            TimeoutError: Lançada se o tempo limite de espera for excedido.
        """
        start_time = time.time()
        timeout = 10  # Limite de espera
        max_attempts = 3
    
        for attempt in range(max_attempts):
            try:
                self.api.sell_option(options_ids)
    
                # Espera até que a resposta seja recebida ou timeout
                while self.api.sold_options_respond is None:
                    if time.time() - start_time > timeout:
                        raise TimeoutError(f"Venda de opções {options_ids} excedeu o tempo limite.")
                    time.sleep(0.1)
    
                #print(f"[SUCESSO] Opções {options_ids} vendidas com sucesso.")
                return self.api.sold_options_respond
    
            except Exception as e:
                print(f"[AVISO] Tentativa {attempt + 1} falhou ao vender opções: {e}. Reconectando...")
                self.connect()
                time.sleep(2 ** attempt)
    
        print(f"[FALHA] Não foi possível vender opções {options_ids} após {max_attempts} tentativas.")
        return None

    def sell_digital_option(self, options_ids):
        self.api.sell_digital_option(options_ids)
        self.api.sold_digital_options_respond = None
        while self.api.sold_digital_options_respond == None:
            pass
        return self.api.sold_digital_options_respond
# __________________for Digital___________________

    def get_digital_underlying_list_data(self):
        """
        Obtém a lista de ativos digitais disponíveis, com reconexão automática.
    
        Retorna:
            dict: Dados dos ativos digitais disponíveis.
        """
        for attempt in range(3):  # Máximo de 3 tentativas
            try:
                self.api.underlying_list_data = None
                self.api.get_digital_underlying()
                start_t = time.time()
    
                while self.api.underlying_list_data is None:
                    if time.time() - start_t >= 30:
                        raise TimeoutError("Tempo excedido ao buscar lista de ativos digitais.")
                    time.sleep(0.1)
    
                return self.api.underlying_list_data
    
            except WebSocketConnectionClosedException as e:
                print(f"[ERRO] Conexão WebSocket encerrada: {e}. Tentando reconectar...")
                self.connect()
                time.sleep(2 ** attempt)  # Atraso exponencial entre tentativas
            except Exception as e:
                print(f"[ERRO] Falha ao obter ativos digitais: {e}")
                time.sleep(2 ** attempt)
    
        print("[FALHA] Não foi possível obter a lista de ativos digitais após várias tentativas.")
        return None
        
    def get_strike_list(self, ACTIVES, duration):
        """
        Obtém a lista de strikes para um ativo específico.
        """
        try:
            self.api.strike_list = None
            self.api.get_strike_list(ACTIVES, duration)
            
            start_time = time.time()
            while self.api.strike_list is None:
                if time.time() - start_time > 10:  # Timeout após 10 segundos
                    raise TimeoutError(f"Tempo excedido ao buscar strikes para {ACTIVES}.")
                time.sleep(0.1)
            
            strike_data = self.api.strike_list.get("msg", {}).get("strike", [])
            strikes = {
                "%.6f" % (float(data["value"]) * 10e-7): {
                    "call": data["call"]["id"],
                    "put": data["put"]["id"]
                } for data in strike_data
            }
            return self.api.strike_list, strikes
        except Exception as e:
            print(f"[ERRO] Falha ao obter strikes: {e}")
            return None, {}

    def subscribe_strike_list(self, ACTIVE, expiration_period):
        self.api.subscribe_instrument_quites_generated(
            ACTIVE, expiration_period)

    def unsubscribe_strike_list(self, ACTIVE, expiration_period):
        del self.api.instrument_quites_generated_data[ACTIVE]
        self.api.unsubscribe_instrument_quites_generated(
            ACTIVE, expiration_period)

    def get_instrument_quites_generated_data(self, ACTIVE, duration):
        while self.api.instrument_quotes_generated_raw_data[ACTIVE][duration * 60] == {}:
            pass
        return self.api.instrument_quotes_generated_raw_data[ACTIVE][duration * 60]

    def get_realtime_strike_list(self, ACTIVE, duration):
        while True:
            if not self.api.instrument_quites_generated_data[ACTIVE][duration * 60]:
                pass
            else:
                break
        """
        strike_list dict: price:{call:id,put:id}
        """
        ans = {}
        now_timestamp = self.api.instrument_quites_generated_timestamp[ACTIVE][duration * 60]

        while ans == {}:
            if self.get_realtime_strike_list_temp_data == {} or now_timestamp != self.get_realtime_strike_list_temp_expiration:
                raw_data, strike_list = self.get_strike_list(ACTIVE, duration)
                self.get_realtime_strike_list_temp_expiration = raw_data["msg"]["expiration"]
                self.get_realtime_strike_list_temp_data = strike_list
            else:
                strike_list = self.get_realtime_strike_list_temp_data

            profit = self.api.instrument_quites_generated_data[ACTIVE][duration * 60]
            for price_key in strike_list:
                try:
                    side_data = {}
                    for side_key in strike_list[price_key]:
                        detail_data = {}
                        profit_d = profit[strike_list[price_key][side_key]]
                        detail_data["profit"] = profit_d
                        detail_data["id"] = strike_list[price_key][side_key]
                        side_data[side_key] = detail_data
                    ans[price_key] = side_data
                except:
                    pass

        return ans

    def get_digital_current_profit(self, ACTIVE, duration):
        profit = self.api.instrument_quites_generated_data[ACTIVE][duration * 60]
        for key in profit:
            if key.find("SPT") != -1:
                return profit[key]
        return False

    # thank thiagottjv
    # https://github.com/Lu-Yi-Hsun/iqoptionapi/issues/65#issuecomment-513998357

    def buy_digital_spot(self, active, amount, action, duration):
        """
        Realiza a compra de uma opção digital.
    
        Este método compra uma opção digital para um ativo específico com os 
        parâmetros fornecidos, incluindo direção (call/put) e duração.
    
        Parâmetros:
            active (str): Nome do ativo, por exemplo, "EURUSD".
            amount (float): Quantia a ser investida.
            action (str): Direção da operação, "call" ou "put".
            duration (int): Duração da operação em minutos.
    
        Retorna:
            tuple:
                - (bool): True em caso de sucesso, False em caso de falha.
                - (int|str): ID da ordem em caso de sucesso, mensagem de erro em caso de falha.
        """
        action = action.lower()
        if action not in ['put', 'call']:
            print(f"[ERRO] Ação inválida '{action}'. Use 'call' ou 'put'.")
            return False, "Ação inválida"
    
        try:
            timestamp = int(self.api.timesync.server_timestamp)
        except AttributeError:
            print("[ERRO] Não foi possível obter o timestamp do servidor.")
            return False, "Erro no timestamp"
    
        # Calcular horário de expiração
        exp, _ = get_expiration_time(timestamp, duration) if duration == 1 else self._calculate_expiration(timestamp, duration)
    
        instrument_id = f"do{active}{exp}PT{duration}M{'P' if action == 'put' else 'C'}SPT"
    
        try:
            request_id = self.api.place_digital_option(instrument_id, amount)
        except Exception as e:
            print(f"[ERRO] Falha ao enviar ordem: {e}")
            return False, "Erro ao enviar ordem"
    
        # Aguardar resposta
        start_time = time.time()
        timeout = 10
        while time.time() - start_time <= timeout:
            if request_id in self.api.digital_option_placed_id:
                order_id = self.api.digital_option_placed_id[request_id]
                if isinstance(order_id, int):
                    return True, order_id
                return False, order_id
            time.sleep(0.1)
    
        print(f"[FALHA] Falha ao realizar compra para {active}: tempo limite excedido.")
        return False, "Tempo limite excedido"

    def get_digital_spot_profit_after_sale(self, position_id):
        def get_instrument_id_to_bid(data, instrument_id):
            for row in data["msg"]["quotes"]:
                if row["symbols"][0] == instrument_id:
                    return row["price"]["bid"]
            return None

        while self.get_async_order(position_id)["position-changed"] == {}:
            pass
        # ___________________/*position*/_________________
        position = self.get_async_order(position_id)["position-changed"]["msg"]
        # doEURUSD201911040628PT1MPSPT
        # z mean check if call or not
        if position["instrument_id"].find("MPSPT"):
            z = False
        elif position["instrument_id"].find("MCSPT"):
            z = True
        else:
            logging.error(
                'get_digital_spot_profit_after_sale position error' + str(position["instrument_id"]))

        ACTIVES = position['raw_event']['instrument_underlying']
        amount = max(position['raw_event']["buy_amount"],
                     position['raw_event']["sell_amount"])
        start_duration = position["instrument_id"].find("PT") + 2
        end_duration = start_duration + \
            position["instrument_id"][start_duration:].find("M")

        duration = int(position["instrument_id"][start_duration:end_duration])
        z2 = False

        getAbsCount = position['raw_event']["count"]
        instrumentStrikeValue = position['raw_event']["instrument_strike_value"] / 1000000.0
        spotLowerInstrumentStrike = position['raw_event']["extra_data"]["lower_instrument_strike"] / 1000000.0
        spotUpperInstrumentStrike = position['raw_event']["extra_data"]["upper_instrument_strike"] / 1000000.0

        aVar = position['raw_event']["extra_data"]["lower_instrument_id"]
        aVar2 = position['raw_event']["extra_data"]["upper_instrument_id"]
        getRate = position['raw_event']["currency_rate"]

        # ___________________/*position*/_________________
        instrument_quites_generated_data = self.get_instrument_quites_generated_data(
            ACTIVES, duration)


        f_tmp = get_instrument_id_to_bid(
            instrument_quites_generated_data, aVar)
        # f is bidprice of lower_instrument_id ,f2 is bidprice of upper_instrument_id
        if f_tmp != None:
            self.get_digital_spot_profit_after_sale_data[position_id]["f"] = f_tmp
            f = f_tmp
        else:
            f = self.get_digital_spot_profit_after_sale_data[position_id]["f"]

        f2_tmp = get_instrument_id_to_bid(
            instrument_quites_generated_data, aVar2)
        if f2_tmp != None:
            self.get_digital_spot_profit_after_sale_data[position_id]["f2"] = f2_tmp
            f2 = f2_tmp
        else:
            f2 = self.get_digital_spot_profit_after_sale_data[position_id]["f2"]

        if (spotLowerInstrumentStrike != instrumentStrikeValue) and f != None and f2 != None:

            if (spotLowerInstrumentStrike > instrumentStrikeValue or instrumentStrikeValue > spotUpperInstrumentStrike):
                if z:
                    instrumentStrikeValue = (spotUpperInstrumentStrike - instrumentStrikeValue) / abs(
                        spotUpperInstrumentStrike - spotLowerInstrumentStrike)
                    f = abs(f2 - f)
                else:
                    instrumentStrikeValue = (instrumentStrikeValue - spotUpperInstrumentStrike) / abs(
                        spotUpperInstrumentStrike - spotLowerInstrumentStrike)
                    f = abs(f2 - f)

            elif z:
                f += ((instrumentStrikeValue - spotLowerInstrumentStrike) /
                      (spotUpperInstrumentStrike - spotLowerInstrumentStrike)) * (f2 - f)
            else:
                instrumentStrikeValue = (spotUpperInstrumentStrike - instrumentStrikeValue) / (
                    spotUpperInstrumentStrike - spotLowerInstrumentStrike)
                f -= f2
            f = f2 + (instrumentStrikeValue * f)

        if z2:
            pass
        if f != None:
            # price=f/getRate
            price = (f / getRate)
            # getAbsCount Reference
            return price * getAbsCount - amount
        else:
            return None

    def buy_digital(self, amount, instrument_id):
        self.api.digital_option_placed_id = None
        self.api.place_digital_option(instrument_id, amount)
        start_t = time.time()
        while self.api.digital_option_placed_id == None:
            if time.time() - start_t > 30:
                logging.error('buy_digital loss digital_option_placed_id')
                return False, None
        return True, self.api.digital_option_placed_id

    def close_digital_option(self, position_id):
        self.api.result = None
        while self.get_async_order(position_id)["position-changed"] == {}:
            pass
        position_changed = self.get_async_order(
            position_id)["position-changed"]["msg"]
        self.api.close_digital_option(position_changed["external_id"])
        while self.api.result == None:
            pass
        return self.api.result

    def check_win_digital_v2(self, buy_order_id):
        """
        Verifica o resultado de uma operação digital com base no ID da ordem.
    
        Parâmetros:
            buy_order_id (int): ID da ordem enviada.
    
        Retorna:
            tuple: 
                - (bool): True se o resultado foi obtido com sucesso, False caso contrário.
                - (float): Lucro ou prejuízo da operação.
        """
        while self.get_async_order(buy_order_id)["position-changed"] == {}:
            pass
    
        order_data = self.get_async_order(buy_order_id)["position-changed"]["msg"]
        if order_data is not None:
            if order_data["status"] == "closed":
                if order_data["close_reason"] == "expired":
                    return True, order_data["close_profit"] - order_data["invest"]
                elif order_data["close_reason"] == "default":
                    return True, order_data["pnl_realized"]
        return False, None

    def buy_order(self,
                  instrument_type, instrument_id,
                  side, amount, leverage,
                  type, limit_price=None, stop_price=None,

                  stop_lose_kind=None, stop_lose_value=None,
                  take_profit_kind=None, take_profit_value=None,

                  use_trail_stop=False, auto_margin_call=False,
                  use_token_for_commission=False):
        self.api.buy_order_id = None
        self.api.buy_order(
            instrument_type=instrument_type, instrument_id=instrument_id,
            side=side, amount=amount, leverage=leverage,
            type=type, limit_price=limit_price, stop_price=stop_price,
            stop_lose_value=stop_lose_value, stop_lose_kind=stop_lose_kind,
            take_profit_value=take_profit_value, take_profit_kind=take_profit_kind,
            use_trail_stop=use_trail_stop, auto_margin_call=auto_margin_call,
            use_token_for_commission=use_token_for_commission
        )

        while self.api.buy_order_id == None:
            pass
        check, data = self.get_order(self.api.buy_order_id)
        while data["status"] == "pending_new":
            check, data = self.get_order(self.api.buy_order_id)
            time.sleep(1)

        if check:
            if data["status"] != "rejected":
                return True, self.api.buy_order_id
            else:
                return False, data["reject_status"]
        else:

            return False, None

    def change_auto_margin_call(self, ID_Name, ID, auto_margin_call):
        self.api.auto_margin_call_changed_respond = None
        self.api.change_auto_margin_call(ID_Name, ID, auto_margin_call)
        while self.api.auto_margin_call_changed_respond == None:
            pass
        if self.api.auto_margin_call_changed_respond["status"] == 2000:
            return True, self.api.auto_margin_call_changed_respond
        else:
            return False, self.api.auto_margin_call_changed_respond

    def change_order(self, ID_Name, order_id,
                     stop_lose_kind, stop_lose_value,
                     take_profit_kind, take_profit_value,
                     use_trail_stop, auto_margin_call):
        check = True
        if ID_Name == "position_id":
            check, order_data = self.get_order(order_id)
            position_id = order_data["position_id"]
            ID = position_id
        elif ID_Name == "order_id":
            ID = order_id
        else:
            logging.error('change_order input error ID_Name')

        if check:
            self.api.tpsl_changed_respond = None
            self.api.change_order(
                ID_Name=ID_Name, ID=ID,
                stop_lose_kind=stop_lose_kind, stop_lose_value=stop_lose_value,
                take_profit_kind=take_profit_kind, take_profit_value=take_profit_value,
                use_trail_stop=use_trail_stop)
            self.change_auto_margin_call(
                ID_Name=ID_Name, ID=ID, auto_margin_call=auto_margin_call)
            while self.api.tpsl_changed_respond == None:
                pass
            if self.api.tpsl_changed_respond["status"] == 2000:
                return True, self.api.tpsl_changed_respond["msg"]
            else:
                return False, self.api.tpsl_changed_respond
        else:
            logging.error('change_order fail to get position_id')
            return False, None

    def get_async_order(self, buy_order_id):
        # name': 'position-changed', 'microserviceName': "portfolio"/"digital-options"
        return self.api.order_async[buy_order_id]

    def get_order(self, buy_order_id):
        # self.api.order_data["status"]
        # reject:you can not get this order
        # pending_new:this order is working now
        # filled:this order is ok now
        # new
        self.api.order_data = None
        self.api.get_order(buy_order_id)
        while self.api.order_data == None:
            pass
        if self.api.order_data["status"] == 2000:
            return True, self.api.order_data["msg"]
        else:
            return False, None

    def get_pending(self, instrument_type):
        self.api.deferred_orders = None
        self.api.get_pending(instrument_type)
        while self.api.deferred_orders == None:
            pass
        if self.api.deferred_orders["status"] == 2000:
            return True, self.api.deferred_orders["msg"]
        else:
            return False, None

    # this function is heavy
    def get_positions(self, instrument_type):
        self.api.positions = None
        self.api.get_positions(instrument_type)
        while self.api.positions == None:
            pass
        if self.api.positions["status"] == 2000:
            return True, self.api.positions["msg"]
        else:
            return False, None

    def get_position(self, buy_order_id):
        self.api.position = None
        check, order_data = self.get_order(buy_order_id)
        position_id = order_data["position_id"]
        self.api.get_position(position_id)
        while self.api.position == None:
            pass
        if self.api.position["status"] == 2000:
            return True, self.api.position["msg"]
        else:
            return False, None

    # this function is heavy

    def get_digital_position_by_position_id(self, position_id):
        self.api.position = None
        self.api.get_digital_position(position_id)
        while self.api.position == None:
            pass
        return self.api.position

    def get_digital_position(self, order_id):
        self.api.position = None
        while self.get_async_order(order_id)["position-changed"] == {}:
            pass
        position_id = self.get_async_order(
            order_id)["position-changed"]["msg"]["external_id"]
        self.api.get_digital_position(position_id)
        while self.api.position == None:
            pass
        return self.api.position

    def get_position_history(self, instrument_type):
        self.api.position_history = None
        self.api.get_position_history(instrument_type)
        while self.api.position_history == None:
            pass

        if self.api.position_history["status"] == 2000:
            return True, self.api.position_history["msg"]
        else:
            return False, None

    def get_position_history_v2(self, instrument_type, limit, offset, start, end):
        # instrument_type=crypto forex fx-option multi-option cfd digital-option turbo-option
        self.api.position_history_v2 = None
        self.api.get_position_history_v2(
            instrument_type, limit, offset, start, end)
        while self.api.position_history_v2 == None:
            pass

        if self.api.position_history_v2["status"] == 2000:
            return True, self.api.position_history_v2["msg"]
        else:
            return False, None

    def get_available_leverages(self, instrument_type, actives=""):
        self.api.available_leverages = None
        if actives == "":
            self.api.get_available_leverages(instrument_type, "")
        else:
            self.api.get_available_leverages(
                instrument_type, OP_code.ACTIVES[actives])
        while self.api.available_leverages == None:
            pass
        if self.api.available_leverages["status"] == 2000:
            return True, self.api.available_leverages["msg"]
        else:
            return False, None

    def cancel_order(self, buy_order_id):
        self.api.order_canceled = None
        self.api.cancel_order(buy_order_id)
        while self.api.order_canceled == None:
            pass
        if self.api.order_canceled["status"] == 2000:
            return True
        else:
            return False

    def close_position(self, position_id):
        check, data = self.get_order(position_id)
        if data["position_id"] != None:
            self.api.close_position_data = None
            self.api.close_position(data["position_id"])
            while self.api.close_position_data == None:
                pass
            if self.api.close_position_data["status"] == 2000:
                return True
            else:
                return False
        else:
            return False

    def close_position_v2(self, position_id):
        while self.get_async_order(position_id) == None:
            pass
        position_changed = self.get_async_order(position_id)
        self.api.close_position(position_changed["id"])
        while self.api.close_position_data == None:
            pass
        if self.api.close_position_data["status"] == 2000:
            return True
        else:
            return False

    def get_overnight_fee(self, instrument_type, active):
        self.api.overnight_fee = None
        self.api.get_overnight_fee(instrument_type, OP_code.ACTIVES[active])
        while self.api.overnight_fee == None:
            pass
        if self.api.overnight_fee["status"] == 2000:
            return True, self.api.overnight_fee["msg"]
        else:
            return False, None

    def get_option_open_by_other_pc(self):
        return self.api.socket_option_opened

    def del_option_open_by_other_pc(self, id):
        del self.api.socket_option_opened[id]

    # -----------------------------------------------------------------

    def opcode_to_name(self, opcode):
        return list(OP_code.ACTIVES.keys())[list(OP_code.ACTIVES.values()).index(opcode)]

    # name:
    # "live-deal-binary-option-placed"
    # "live-deal-digital-option"
    def subscribe_live_deal(self, name, active, _type, buffersize):
        active_id = OP_code.ACTIVES[active]
        self.api.Subscribe_Live_Deal(name, active_id, _type)
        """
        self.api.live_deal_data[name][active][_type]=deque(list(),buffersize)


        while len(self.api.live_deal_data[name][active][_type])==0:
            self.api.Subscribe_Live_Deal(name,active_id,_type)
            time.sleep(1)
        """

    def unscribe_live_deal(self, name, active, _type):
        active_id = OP_code.ACTIVES[active]
        self.api.Unscribe_Live_Deal(name, active_id, _type)
        """

        while len(self.api.live_deal_data[name][active][_type])!=0:
            self.api.Unscribe_Live_Deal(name,active_id,_type)
            del self.api.live_deal_data[name][active][_type]
            time.sleep(1)
        """

    def set_digital_live_deal_cb(self, cb):
        self.api.digital_live_deal_cb = cb

    def set_binary_live_deal_cb(self, cb):
        self.api.binary_live_deal_cb = cb

    def get_live_deal(self, name, active, _type):
        return self.api.live_deal_data[name][active][_type]

    def pop_live_deal(self, name, active, _type):
        return self.api.live_deal_data[name][active][_type].pop()

    def clear_live_deal(self, name, active, _type, buffersize):
        self.api.live_deal_data[name][active][_type] = deque(
            list(), buffersize)

    def get_user_profile_client(self, user_id):
        self.api.user_profile_client = None
        self.api.Get_User_Profile_Client(user_id)
        while self.api.user_profile_client == None:
            pass

        return self.api.user_profile_client

    def request_leaderboard_userinfo_deals_client(self, user_id, country_id):
        self.api.leaderboard_userinfo_deals_client = None

        while True:
            try:
                if self.api.leaderboard_userinfo_deals_client["isSuccessful"] == True:
                    break
            except:
                pass
            self.api.Request_Leaderboard_Userinfo_Deals_Client(
                user_id, country_id)
            time.sleep(0.2)

        return self.api.leaderboard_userinfo_deals_client

    def get_users_availability(self, user_id):
        self.api.users_availability = None

        while self.api.users_availability == None:
            self.api.Get_Users_Availability(user_id)
            time.sleep(0.2)
        return self.api.users_availability

    def get_digital_payout(self, active, seconds=0):
        self.api.digital_payout = None
        asset_id = OP_code.ACTIVES[active]

        self.api.subscribe_digital_price_splitter(asset_id)

        start = time.time()
        while self.api.digital_payout is None:
            if seconds and int(time.time() - start) > seconds:
                break

        self.api.unsubscribe_digital_price_splitter(asset_id)

        return self.api.digital_payout if self.api.digital_payout else 0

    def logout(self):
        self.api.logout()

    def buy_digital_spot_v2(self, active, amount, action, duration):
        """
        Realiza a compra de uma opção digital e aguarda o resultado.
    
        Parâmetros:
            active (str): Nome do ativo, por exemplo, "EURUSD".
            amount (float): Quantia a ser investida.
            action (str): Direção da operação, "call" ou "put".
            duration (int): Duração da operação em minutos.
    
        Retorna:
            dict: Resultado da operação contendo ID, status e lucro/prejuízo.
        """
        action = action.lower()
        if action not in ["put", "call"]:
            print(f"[ERRO] Ação inválida '{action}'. Use 'call' ou 'put'.")
            return {"status": "error", "message": "Ação inválida"}
    
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                timestamp = int(self.api.timesync.server_timestamp)
                if duration == 1:
                    exp, _ = get_expiration_time(timestamp, duration)
                else:
                    now_date = datetime.fromtimestamp(timestamp) + timedelta(minutes=1, seconds=30)
                    while now_date.minute % duration != 0 or time.mktime(now_date.timetuple()) - timestamp <= 30:
                        now_date += timedelta(minutes=1)
                    exp = time.mktime(now_date.timetuple())
    
                date_formatted = datetime.utcfromtimestamp(exp).strftime("%Y%m%d%H%M")
                instrument_id = f"do{active}{date_formatted}PT{duration}M{'P' if action == 'put' else 'C'}SPT"
    
                request_id = self.api.place_digital_option(instrument_id, amount)
    
                # Aguarda resposta da API
                start_time = time.time()
                timeout = 10
                while time.time() - start_time <= timeout:
                    if request_id in self.api.digital_option_placed_id:
                        digital_order_id = self.api.digital_option_placed_id[request_id]
                        if isinstance(digital_order_id, int):
                            print(f"[SUCESSO] Compra realizada para o ativo {active}. Ordem ID: {digital_order_id}")
    
                            # Verifica o resultado usando check_win_digital_v2
                            success, payout = self.check_win_digital_v2(digital_order_id)
                            if success:
                                return {
                                    "id": digital_order_id,
                                    "status": "closed",
                                    "payout": payout
                                }
                            else:
                                return {"status": "error", "message": "Falha ao obter o resultado"}
    
                        return {"status": "error", "message": digital_order_id}
    
                raise TimeoutError(f"Compra de {active} excedeu o tempo limite.")
    
            except Exception as e:
                print(f"[AVISO] Tentativa {attempt + 1} falhou ao comprar {active}: {e}. Reconectando...")
                self.connect()
                time.sleep(2 ** attempt)
    
        print(f"[FALHA] Não foi possível realizar a compra para {active} após {max_attempts} tentativas.")
        return {"status": "error", "message": "Falha após múltiplas tentativas"}
