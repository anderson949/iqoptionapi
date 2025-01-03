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
from typing import Tuple, Union  # Importação necessária
from typing import Optional

def nested_dict(n, type):
    if n == 1:
        return defaultdict(type)
    else:
        return defaultdict(lambda: nested_dict(n - 1, type))

class IQ_Option:
    __version__ = api_version

    def __init__(self, email, password, active_account_type="PRACTICE"):
        """
        Inicializa o cliente IQ_Option com as credenciais do usuário e configurações.
        """
        self.api = None  # Initialize api attribute
        self.size = [1, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 
                     14400, 28800, 43200, 86400, 604800, 2592000]
        self.email = email
        self.password = password
        self.suspend = 0.5
        self.thread = None
        self.subscribe_candle = []
        self.subscribe_candle_all_size = []
        self.subscribe_mood = []
        self.subscribe_indicators = []
        self.get_digital_spot_profit_after_sale_data = defaultdict(lambda: defaultdict(int))
        self.get_realtime_strike_list_temp_data = {}
        self.get_realtime_strike_list_temp_expiration = 0
        self.SESSION_HEADER = {
            "User-Agent": r"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.139 Safari/537.36"
        }
        self.SESSION_COOKIE = {}
 
        self.OPEN_TIME = nested_dict(3, dict)

    def connect(self, sms_code=None):
            """
            Estabelece uma conexão com a API da IQ Option.
            """
            try:
                # Check if self.api exists and is not None before calling close()
                if self.api is not None:
                    self.api.close()  # Fecha a conexão anterior
            except Exception as e:
                logging.warning(f"Falha ao fechar a conexão anterior: {e}")
        
            # Inicializa a API com as credenciais do usuário
            self.api = IQOptionAPI("iqoption.com", self.email, self.password)
    
            # Verifica se a autenticação de dois fatores (2FA) é necessária
            if sms_code is not None:
                self.api.setTokenSMS(self.resp_sms)
                status, reason = self.api.connect2fa(sms_code)
                if not status:
                    return status, reason
        
            # Configura os cabeçalhos e cookies da sessão
            self.api.set_session(headers=self.SESSION_HEADER, cookies=self.SESSION_COOKIE)
        
            # Tenta estabelecer a conexão
            check, reason = self.api.connect()
        
            if check:
                # Reconecta aos streams de dados previamente inscritos
                self.re_subscribe_stream()
        
                # Aguarda até que o balance_id esteja disponível
                while global_value.balance_id is None:
                    time.sleep(0.1)  # Evita o uso excessivo da CPU
        
                # Inscreve-se para receber atualizações de posições e ordens
                self.position_change_all("subscribeMessage", global_value.balance_id)
                self.order_changed_all("subscribeMessage")
                self.api.setOptions(1, True)
        
                return True, None
            else:
                # Verifica se a falha foi devido à necessidade de autenticação de dois fatores (2FA)
                if json.loads(reason)['code'] == 'verify':
                    response = self.api.send_sms_code(json.loads(reason)['token'])
                    if response.json()['code'] != 'success':
                        return False, response.json()['message']
        
                    # Armazena a resposta do SMS para uso futuro
                    self.resp_sms = response
                    return False, "2FA"
                return False, reason
    
    def get_server_timestamp(self):
        """
        Obtém o timestamp atual do servidor da IQ Option.
    
        Este método retorna o timestamp do servidor, que é útil para sincronizar operações
        e garantir que as requisições estejam alinhadas com o horário do servidor.
    
        :return: Timestamp do servidor (em segundos desde a época Unix).
        :rtype: int
        """
        return self.api.timesync.server_timestamp
    
    def re_subscribe_stream(self):
        """
        Reconecta-se aos streams de dados previamente inscritos.
    
        Este método tenta reconectar-se aos streams de candles, candles de todos os tamanhos
        e mood (humor dos traders) que foram inscritos anteriormente. Se ocorrer algum erro
        durante a reconexão, ele é silenciosamente ignorado para evitar interrupções.
    
        Fluxo:
        1. Reconecta-se aos streams de candles individuais.
        2. Reconecta-se aos streams de candles de todos os tamanhos.
        3. Reconecta-se aos streams de mood (humor dos traders).
        """
        try:
            for ac in self.subscribe_candle:
                sp = ac.split(",")
                if len(sp) == 2:  # Verifica se a string foi corretamente dividida
                    self.start_candles_one_stream(sp[0], sp[1])
        except Exception as e:
            logging.warning(f"Erro ao reconectar ao stream de candles individuais: {e}")
    
        try:
            for ac in self.subscribe_candle_all_size:
                self.start_candles_all_size_stream(ac)
        except Exception as e:
            logging.warning(f"Erro ao reconectar ao stream de candles de todos os tamanhos: {e}")
    
        try:
            for ac in self.subscribe_mood:
                self.start_mood_stream(ac)
        except Exception as e:
            logging.warning(f"Erro ao reconectar ao stream de mood: {e}")
            
    def set_session(self, header, cookie):
        """
        Define os cabeçalhos (headers) e cookies da sessão para as requisições HTTP.
    
        Este método permite configurar os cabeçalhos e cookies que serão utilizados
        nas requisições feitas à API da IQ Option. Isso é útil para personalizar
        a sessão ou adicionar autenticação personalizada.
    
        Parâmetros:
        header (dict): Dicionário contendo os cabeçalhos HTTP a serem utilizados.
        cookie (dict): Dicionário contendo os cookies a serem utilizados.
    
        Exemplo de uso:
        >>> headers = {"User-Agent": "Meu User Agent"}
        >>> cookies = {"session_id": "123456"}
        >>> iq_option.set_session(headers, cookies)
        """
        self.SESSION_HEADER = header
        self.SESSION_COOKIE = cookie      
        
    def connect(self, sms_code=None):
        """
        Estabelece uma conexão com a API da IQ Option.
    
        Este método realiza a conexão com a API, configurando a sessão e reconectando-se
        aos streams de dados previamente inscritos. Também suporta autenticação de dois fatores (2FA).
    
        Parâmetros:
        sms_code (str, opcional): Código de autenticação de dois fatores (2FA), se necessário.
    
        Retorno:
        tuple: Uma tupla contendo:
            - bool: True se a conexão for bem-sucedida, False caso contrário.
            - str: Motivo da falha (se houver), ou None em caso de sucesso.
    
        Exceções:
        logging.warning: Registra avisos em caso de falhas durante o processo de conexão.
        """
        try:
            self.api.close()
        except Exception as e:
            pass
    
        # Inicializa a API com as credenciais do usuário
        self.api = IQOptionAPI("iqoption.com", self.email, self.password)
    
        # Verifica se a autenticação de dois fatores (2FA) é necessária
        if sms_code is not None:
            self.api.setTokenSMS(self.resp_sms)
            status, reason = self.api.connect2fa(sms_code)
            if not status:
                return status, reason
    
        # Configura os cabeçalhos e cookies da sessão
        self.api.set_session(headers=self.SESSION_HEADER, cookies=self.SESSION_COOKIE)
    
        # Tenta estabelecer a conexão
        check, reason = self.api.connect()
    
        if check:
            # Reconecta aos streams de dados previamente inscritos
            self.re_subscribe_stream()
    
            # Aguarda até que o balance_id esteja disponível
            while global_value.balance_id is None:
                time.sleep(0.1)  # Evita o uso excessivo da CPU
    
            # Inscreve-se para receber atualizações de posições e ordens
            self.position_change_all("subscribeMessage", global_value.balance_id)
            self.order_changed_all("subscribeMessage")
            self.api.setOptions(1, True)
    
            return True, None
        else:
            # Verifica se a falha foi devido à necessidade de autenticação de dois fatores (2FA)
            if json.loads(reason)['code'] == 'verify':
                response = self.api.send_sms_code(json.loads(reason)['token'])
                if response.json()['code'] != 'success':
                    return False, response.json()['message']
    
                # Armazena a resposta do SMS para uso futuro
                self.resp_sms = response
                return False, "2FA"
            return False, reason        
            
    def connect_2fa(self, sms_code):
        """
        Realiza a conexão com a API da IQ Option utilizando autenticação de dois fatores (2FA).
    
        Este método é um wrapper para o método `connect`, permitindo a passagem do código de autenticação
        de dois fatores (2FA) de forma simplificada.
    
        Parâmetros:
        sms_code (str): Código de autenticação de dois fatores (2FA) recebido pelo usuário.
    
        Retorno:
        tuple: Uma tupla contendo:
            - bool: True se a conexão for bem-sucedida, False caso contrário.
            - str: Motivo da falha (se houver), ou None em caso de sucesso.
        """
        return self.connect(sms_code=sms_code)     
        
    def check_connect(self):
        """
        Verifica se a conexão com o websocket da IQ Option está ativa.
    
        Este método verifica o status da conexão com o websocket, retornando True se estiver conectado
        e False caso contrário. Ele lida com casos em que o status pode ser None ou '0'.
    
        Retorno:
        bool: True se a conexão estiver ativa, False caso contrário.
        """
        return bool(global_value.check_websocket_if_connect)
        
    def get_all_ACTIVES_OPCODE(self):
        """
        Retorna um dicionário com todos os códigos de ativos (ACTIVES) disponíveis.
    
        Este método fornece acesso ao dicionário global `OP_code.ACTIVES`, que mapeia os nomes
        dos ativos para seus respectivos códigos.
    
        Retorno:
        dict: Dicionário contendo os códigos de ativos.
        """
        return OP_code.ACTIVES
        
    def update_ACTIVES_OPCODE(self):
        """
        Atualiza o dicionário de códigos de ativos (ACTIVES) com dados das opções binárias e outros instrumentos.
    
        Este método realiza duas operações principais:
        1. Atualiza os códigos de ativos das opções binárias.
        2. Atualiza os códigos de ativos de outros instrumentos (criptomoedas, forex, CFD).
    
        Após a atualização, o dicionário `OP_code.ACTIVES` é ordenado pelos valores dos códigos.
        """
        # Atualiza os códigos de ativos das opções binárias
        self.get_ALL_Binary_ACTIVES_OPCODE()
    
        # Atualiza os códigos de ativos de outros instrumentos (criptomoedas, forex, CFD)
        self.instruments_input_all_in_ACTIVES()
    
        # Ordena o dicionário de códigos de ativos pelos valores
        sorted_actives = sorted(OP_code.ACTIVES.items(), key=operator.itemgetter(1))
        OP_code.ACTIVES = dict(sorted_actives)
        
    def get_name_by_activeId(self, activeId):
        """
        Obtém o nome de um ativo com base no seu ID.
    
        Este método consulta as informações financeiras do ativo e retorna o nome correspondente
        ao ID fornecido. Se o ID não for encontrado ou ocorrer um erro, retorna None.
    
        Parâmetros:
        activeId (int): ID do ativo a ser consultado.
    
        Retorno:
        str: Nome do ativo, ou None se o ID não for encontrado ou ocorrer um erro.
        """
        info = self.get_financial_information(activeId)
        try:
            return info["msg"]["data"]["active"]["name"]
        except (KeyError, TypeError):
            logging.warning(f"Não foi possível obter o nome do ativo com ID {activeId}.")
            return None        
            
    def get_financial_information(self, activeId):
        """
        Obtém informações financeiras sobre um ativo específico com base no seu ID.
    
        Este método consulta a API para obter detalhes financeiros do ativo, como nome, preço,
        e outras informações relevantes. Ele aguarda até que a resposta da API esteja disponível.
    
        Parâmetros:
        activeId (int): ID do ativo a ser consultado.
    
        Retorno:
        dict: Dicionário contendo as informações financeiras do ativo.
        """
        self.api.financial_information = None
        self.api.get_financial_information(activeId)
    
        # Aguarda até que as informações financeiras estejam disponíveis
        while self.api.financial_information is None:
            time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        return self.api.financial_information        
        
    def get_leader_board(self, country, from_position, to_position, near_traders_count, user_country_id=0,
                         near_traders_country_count=0, top_country_count=0, top_count=0, top_type=2):
        """
        Obtém o ranking de líderes (leaderboard) para um país específico.
    
        Este método consulta a API para obter o ranking de líderes com base em vários parâmetros,
        como posição inicial, posição final, número de traders próximos, etc.
    
        Parâmetros:
        country (str): Nome do país para o qual obter o ranking.
        from_position (int): Posição inicial no ranking.
        to_position (int): Posição final no ranking.
        near_traders_count (int): Número de traders próximos a serem incluídos.
        user_country_id (int, opcional): ID do país do usuário. Padrão é 0.
        near_traders_country_count (int, opcional): Número de traders próximos do mesmo país. Padrão é 0.
        top_country_count (int, opcional): Número de países no topo do ranking. Padrão é 0.
        top_count (int, opcional): Número de traders no topo do ranking. Padrão é 0.
        top_type (int, opcional): Tipo de ranking. Padrão é 2.
    
        Retorno:
        dict: Dicionário contendo os dados do ranking de líderes.
        """
        self.api.leaderboard_deals_client = None
    
        # Obtém o ID do país com base no nome
        country_id = Country.ID.get(country)
        if country_id is None:
            logging.warning(f"País '{country}' não encontrado.")
            return None
    
        # Consulta o ranking de líderes na API
        self.api.Get_Leader_Board(country_id, user_country_id, from_position, to_position,
                                  near_traders_country_count, near_traders_count, top_country_count, top_count, top_type)
    
        # Aguarda até que os dados do ranking estejam disponíveis
        while self.api.leaderboard_deals_client is None:
            time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        return self.api.leaderboard_deals_client    
        
    def get_instruments(self, type):
        """
        Obtém a lista de instrumentos disponíveis para um tipo específico (crypto, forex, cfd).
    
        Este método consulta a API para obter os instrumentos disponíveis e aguarda até que a resposta
        esteja disponível. Se ocorrer um erro, ele tenta reconectar à API.
    
        Parâmetros:
        type (str): Tipo de instrumento a ser consultado ("crypto", "forex" ou "cfd").
    
        Retorno:
        dict: Dicionário contendo os instrumentos disponíveis.
        """
        time.sleep(self.suspend)  # Aguarda um tempo para evitar sobrecarga
        self.api.instruments = None
    
        while self.api.instruments is None:
            try:
                self.api.get_instruments(type)
                start = time.time()
                while self.api.instruments is None and time.time() - start < 10:
                    time.sleep(0.1)  # Evita o uso excessivo da CPU
            except Exception as e:
                logging.error(f"Erro ao obter instrumentos: {e}. Tentando reconectar...")
                self.connect()
    
        return self.api.instruments    
        
    def instruments_input_to_ACTIVES(self, type):
        """
        Atualiza o dicionário de códigos de ativos (ACTIVES) com os instrumentos de um tipo específico.
    
        Este método obtém os instrumentos disponíveis para o tipo especificado e os mapeia no
        dicionário global `OP_code.ACTIVES`.
    
        Parâmetros:
        type (str): Tipo de instrumento a ser mapeado ("crypto", "forex" ou "cfd").
        """
        instruments = self.get_instruments(type)
        for ins in instruments.get("instruments", []):
            OP_code.ACTIVES[ins["id"]] = ins["active_id"]
            
    def instruments_input_all_in_ACTIVES(self):
        """
        Atualiza o dicionário de códigos de ativos (ACTIVES) com todos os tipos de instrumentos.
    
        Este método mapeia os instrumentos de criptomoedas, forex e CFD no dicionário global
        `OP_code.ACTIVES`.
        """
        self.instruments_input_to_ACTIVES("crypto")
        self.instruments_input_to_ACTIVES("forex")
        self.instruments_input_to_ACTIVES("cfd")
        
    def get_ALL_Binary_ACTIVES_OPCODE(self):
        """
        Atualiza o dicionário de códigos de ativos (ACTIVES) com os ativos das opções binárias e turbo.
    
        Este método obtém os ativos disponíveis para as opções binárias e turbo e os mapeia no
        dicionário global `OP_code.ACTIVES`.
        """
        init_info = self.get_all_init()
        for dirr in ["binary", "turbo"]:
            for i in init_info["result"][dirr]["actives"]:
                active_name = init_info["result"][dirr]["actives"][i]["name"].split(".")[1]
                OP_code.ACTIVES[active_name] = int(i)        
                
    def get_all_init(self):
        """
        Obtém todas as informações de inicialização da API, incluindo ativos e configurações.
    
        Este método consulta a API para obter os dados de inicialização e aguarda até que a resposta
        esteja disponível. Se ocorrer um erro, ele tenta reconectar à API. O método também possui
        um timeout de 120 segundos para evitar loops infinitos.
    
        Retorno:
        dict: Dicionário contendo as informações de inicialização da API.
        """
        while True:
            self.api.api_option_init_all_result = None
    
            # Tenta obter os dados de inicialização
            while True:
                try:
                    self.api.get_api_option_init_all()
                    break
                except Exception as e:
                    logging.error(f"Erro ao obter dados de inicialização: {e}. Tentando reconectar...")
                    self.connect()
                    time.sleep(5)  # Aguarda antes de tentar novamente
    
            # Aguarda até que os dados estejam disponíveis ou o timeout seja atingido
            start = time.time()
            while True:
                if time.time() - start > 120:
                    logging.warning("Timeout ao aguardar dados de inicialização.")
                    break
                try:
                    if self.api.api_option_init_all_result is not None:
                        if self.api.api_option_init_all_result.get("isSuccessful") == True:
                            return self.api.api_option_init_all_result
                except Exception as e:
                    logging.warning(f"Erro ao verificar dados de inicialização: {e}")
                time.sleep(0.1)  # Evita o uso excessivo da CPU     
                
    def get_all_init_v2(self):
        """
        Obtém todas as informações de inicialização da API (versão 2).
    
        Este método consulta a API para obter os dados de inicialização na versão 2 e aguarda até que
        a resposta esteja disponível. Se a conexão não estiver ativa, ele tenta reconectar. O método
        também possui um timeout de 120 segundos para evitar loops infinitos.
    
        Retorno:
        dict: Dicionário contendo as informações de inicialização da API, ou None em caso de timeout.
        """
        self.api.api_option_init_all_result_v2 = None
    
        # Verifica se a conexão está ativa
        if not self.check_connect():
            self.connect()
    
        # Tenta obter os dados de inicialização
        self.api.get_api_option_init_all_v2()
    
        # Aguarda até que os dados estejam disponíveis ou o timeout seja atingido
        start_t = time.time()
        while self.api.api_option_init_all_result_v2 is None:
            if time.time() - start_t >= 120:
                logging.warning("Timeout ao aguardar dados de inicialização (v2).")
                return None
            time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        return self.api.api_option_init_all_result_v2     
        
    def __get_binary_open(self):
        """
        Atualiza o status de abertura dos pares binários e turbo.
    
        Este método verifica se os pares binários e turbo estão abertos para negociação com base
        nos dados de inicialização da API. O status de abertura é armazenado no dicionário
        `self.OPEN_TIME`.
    
        Nota:
        Este método é privado e deve ser chamado apenas internamente.
        """
        binary_data = self.get_all_init_v2()
        binary_list = ["binary", "turbo"]
    
        if binary_data:
            for option in binary_list:
                if option in binary_data:
                    for actives_id in binary_data[option]["actives"]:
                        active = binary_data[option]["actives"][actives_id]
                        name = str(active["name"]).split(".")[1]
    
                        if active["enabled"]:
                            self.OPEN_TIME[option][name]["open"] = not active["is_suspended"]
                        else:
                            self.OPEN_TIME[option][name]["open"] = active["enabled"]
                            
    def __get_digital_open(self):
        """
        Atualiza o status de abertura das opções digitais.
    
        Este método verifica se as opções digitais estão abertas para negociação com base
        nos horários de abertura e fechamento. O status de abertura é armazenado no dicionário
        `self.OPEN_TIME`.
    
        Nota:
        Este método é privado e deve ser chamado apenas internamente.
        """
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
        """
        Atualiza o status de abertura de outros instrumentos (criptomoedas, forex, CFD).
    
        Este método verifica se os instrumentos de criptomoedas, forex e CFD estão abertos para
        negociação com base nos horários de abertura e fechamento. O status de abertura é
        armazenado no dicionário `self.OPEN_TIME`.
    
        Nota:
        Este método é privado e deve ser chamado apenas internamente.
        """
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
        Obtém o status de abertura de todos os pares e instrumentos disponíveis.
    
        Este método utiliza threads para verificar o status de abertura de pares binários, opções
        digitais e outros instrumentos (criptomoedas, forex, CFD) de forma concorrente. O resultado
        é armazenado no dicionário `self.OPEN_TIME`.
    
        Retorno:
        dict: Dicionário contendo o status de abertura de todos os pares e instrumentos.
        """
        self.OPEN_TIME = nested_dict(3, dict)
    
        # Cria threads para verificar o status de abertura de cada tipo de instrumento
        binary_thread = threading.Thread(target=self.__get_binary_open)
        digital_thread = threading.Thread(target=self.__get_digital_open)
        other_thread = threading.Thread(target=self.__get_other_open)
    
        # Inicia as threads
        binary_thread.start()
        digital_thread.start()
        other_thread.start()
    
        # Aguarda a conclusão das threads
        binary_thread.join()
        digital_thread.join()
        other_thread.join()
    
        return self.OPEN_TIME     
        
    def get_binary_option_detail(self):
        """
        Obtém detalhes sobre as opções binárias e turbo disponíveis.
    
        Este método consulta as informações de inicialização da API e retorna um dicionário
        contendo detalhes sobre os ativos disponíveis para as opções binárias e turbo.
    
        Retorno:
        dict: Dicionário contendo detalhes dos ativos para opções binárias e turbo.
        """
        detail = nested_dict(2, dict)
        init_info = self.get_all_init()
    
        # Processa os ativos turbo
        for actives in init_info["result"]["turbo"]["actives"]:
            active_data = init_info["result"]["turbo"]["actives"][actives]
            name = active_data["name"].split(".")[1]  # Extrai o nome do ativo
            detail[name]["turbo"] = active_data
    
        # Processa os ativos binários
        for actives in init_info["result"]["binary"]["actives"]:
            active_data = init_info["result"]["binary"]["actives"][actives]
            name = active_data["name"].split(".")[1]  # Extrai o nome do ativo
            detail[name]["binary"] = active_data
    
        return detail                     
        
    def get_all_profit(self):
        """
        Calcula o lucro líquido para todos os ativos de opções binárias e turbo.
    
        Este método consulta as informações de inicialização da API e calcula o lucro líquido
        (após a dedução da comissão) para cada ativo disponível nas opções binárias e turbo.
    
        Retorno:
        dict: Dicionário contendo o lucro líquido para cada ativo.
        """
        all_profit = nested_dict(2, dict)
        init_info = self.get_all_init()
    
        # Processa os ativos turbo
        for actives in init_info["result"]["turbo"]["actives"]:
            active_data = init_info["result"]["turbo"]["actives"][actives]
            name = active_data["name"].split(".")[1]  # Extrai o nome do ativo
            commission = active_data["option"]["profit"]["commission"]
            all_profit[name]["turbo"] = (100.0 - commission) / 100.0
    
        # Processa os ativos binários
        for actives in init_info["result"]["binary"]["actives"]:
            active_data = init_info["result"]["binary"]["actives"][actives]
            name = active_data["name"].split(".")[1]  # Extrai o nome do ativo
            commission = active_data["option"]["profit"]["commission"]
            all_profit[name]["binary"] = (100.0 - commission) / 100.0
    
        return all_profit               
        
    def get_profile_ansyc(self):
        """
        Obtém o perfil do usuário de forma assíncrona.
    
        Este método aguarda até que as informações do perfil do usuário estejam disponíveis
        e as retorna.
    
        Retorno:
        dict: Dicionário contendo as informações do perfil do usuário.
        """
        while self.api.profile.msg is None:
            time.sleep(0.1)  # Evita o uso excessivo da CPU
        return self.api.profile.msg
        
    def get_currency(self):
        """
        Obtém a moeda associada ao saldo ativo do usuário.
    
        Este método consulta as informações de saldo do usuário e retorna a moeda associada
        ao saldo ativo.
    
        Retorno:
        str: Código da moeda (ex: "USD", "EUR").
        """
        balances_raw = self.get_balances()
        for balance in balances_raw["msg"]:
            if balance["id"] == global_value.balance_id:
                return balance["currency"]
        return None                                    
        
    def get_balance_id(self):
        """
        Obtém o ID do saldo ativo do usuário.
    
        Este método retorna o ID do saldo ativo armazenado na variável global `global_value.balance_id`.
    
        Retorno:
        int: ID do saldo ativo.
        """
        return global_value.balance_id            
        
    def get_balance(self):
        """
        Obtém o valor do saldo ativo do usuário.
    
        Este método consulta as informações de saldo do usuário e retorna o valor do saldo ativo.
    
        Retorno:
        float: Valor do saldo ativo.
        """
        balances_raw = self.get_balances()
        for balance in balances_raw["msg"]:
            if balance["id"] == global_value.balance_id:
                return balance["amount"]
        return None
        
    def get_balances(self):
        """
        Obtém todos os saldos disponíveis do usuário.
    
        Este método consulta a API para obter os saldos do usuário e aguarda até que a resposta
        esteja disponível.
    
        Retorno:
        dict: Dicionário contendo os saldos do usuário.
        """
        self.api.balances_raw = None
        self.api.get_balances()
    
        while self.api.balances_raw is None:
            time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        return self.api.balances_raw    
        
    def get_balance_mode(self):
        """
        Obtém o modo do saldo ativo do usuário (REAL, PRACTICE ou TOURNAMENT).
    
        Este método consulta o perfil do usuário e retorna o modo do saldo ativo.
    
        Retorno:
        str: Modo do saldo ativo ("REAL", "PRACTICE" ou "TOURNAMENT").
        """
        profile = self.get_profile_ansyc()
        for balance in profile.get("balances", []):
            if balance["id"] == global_value.balance_id:
                if balance["type"] == 1:
                    return "REAL"
                elif balance["type"] == 4:
                    return "PRACTICE"
                elif balance["type"] == 2:
                    return "TOURNAMENT"
        return None    
        
    def reset_practice_balance(self):
        """
        Reseta o saldo da conta de prática do usuário.
    
        Este método solicita o reset do saldo da conta de prática e aguarda até que a resposta
        esteja disponível.
    
        Retorno:
        dict: Resposta da API contendo o resultado do reset.
        """
        self.api.training_balance_reset_request = None
        self.api.reset_training_balance()
    
        while self.api.training_balance_reset_request is None:
            time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        return self.api.training_balance_reset_request    
        
    def position_change_all(self, Main_Name, user_balance_id):
        """
        Inscreve ou cancela a inscrição para atualizações de mudanças de posição para todos os tipos de instrumentos.
    
        Este método percorre todos os tipos de instrumentos (CFD, forex, criptomoedas, opções digitais, turbo e binárias)
        e inscreve ou cancela a inscrição para receber atualizações de mudanças de posição.
    
        Parâmetros:
        Main_Name (str): Nome da ação principal ("subscribeMessage" para inscrever, "unsubscribeMessage" para cancelar).
        user_balance_id (int): ID do saldo do usuário.
        """
        instrument_type = ["cfd", "forex", "crypto", "digital-option", "turbo-option", "binary-option"]
        
        for ins in instrument_type:
            self.api.portfolio(
                Main_Name=Main_Name,
                name="portfolio.position-changed",
                instrument_type=ins,
                user_balance_id=user_balance_id
            )
            
    def order_changed_all(self, Main_Name):
        """
        Inscreve ou cancela a inscrição para atualizações de mudanças de ordens para todos os tipos de instrumentos.
    
        Este método percorre todos os tipos de instrumentos (CFD, forex, criptomoedas, opções digitais, turbo e binárias)
        e inscreve ou cancela a inscrição para receber atualizações de mudanças de ordens.
    
        Parâmetros:
        Main_Name (str): Nome da ação principal ("subscribeMessage" para inscrever, "unsubscribeMessage" para cancelar).
        """
        instrument_type = ["cfd", "forex", "crypto", "digital-option", "turbo-option", "binary-option"]
        
        for ins in instrument_type:
            self.api.portfolio(
                Main_Name=Main_Name,
                name="portfolio.order-changed",
                instrument_type=ins
            )
            
    def change_balance(self, Balance_MODE):
        """
        Altera o saldo ativo do usuário para REAL, PRACTICE ou TOURNAMENT.
    
        Este método identifica o ID do saldo correspondente ao modo especificado e atualiza o saldo ativo.
        Ele também gerencia a inscrição para atualizações de mudanças de posição.
    
        Parâmetros:
        Balance_MODE (str): Modo do saldo desejado ("REAL", "PRACTICE" ou "TOURNAMENT").
    
        Exceções:
        logging.error: Registra um erro e encerra o programa se o modo especificado for inválido.
        """
        def set_id(b_id):
            """
            Define o saldo ativo e gerencia a inscrição para atualizações de mudanças de posição.
    
            Parâmetros:
            b_id (int): ID do saldo a ser definido como ativo.
            """
            if global_value.balance_id is not None:
                self.position_change_all("unsubscribeMessage", global_value.balance_id)
            
            global_value.balance_id = b_id
            self.position_change_all("subscribeMessage", b_id)
    
        # Identifica os IDs dos saldos REAL, PRACTICE e TOURNAMENT
        real_id = None
        practice_id = None
        tournament_id = None
    
        for balance in self.get_profile_ansyc().get("balances", []):
            if balance["type"] == 1:
                real_id = balance["id"]
            elif balance["type"] == 4:
                practice_id = balance["id"]
            elif balance["type"] == 2:
                tournament_id = balance["id"]
    
        # Define o saldo ativo com base no modo especificado
        if Balance_MODE == "REAL":
            set_id(real_id)
        elif Balance_MODE == "PRACTICE":
            set_id(practice_id)
        elif Balance_MODE == "TOURNAMENT":
            set_id(tournament_id)
        else:
            logging.error("Erro: Modo de saldo inválido.")
            exit(1)
            
    def get_candles(self, ACTIVES, interval, count, endtime):
        """
        Obtém os candles históricos para um ativo específico.
    
        Este método consulta a API para obter os candles históricos com base no ativo, intervalo,
        quantidade e tempo de fim especificados. Se o ativo não for encontrado ou ocorrer um erro,
        ele tenta reconectar à API.
    
        Parâmetros:
        ACTIVES (str): Nome do ativo (ex: "EURUSD").
        interval (int): Intervalo dos candles em segundos.
        count (int): Número de candles a serem obtidos.
        endtime (int): Timestamp de fim dos candles.
    
        Retorno:
        list: Lista de candles históricos.
        """
        self.api.candles.candles_data = None
    
        while True:
            try:
                if ACTIVES not in OP_code.ACTIVES:
                    logging.warning(f"Ativo '{ACTIVES}' não encontrado nos consts.")
                    break
    
                self.api.getcandles(OP_code.ACTIVES[ACTIVES], interval, count, endtime)
    
                while self.check_connect() and self.api.candles.candles_data is None:
                    time.sleep(0.1)  # Evita o uso excessivo da CPU
    
                if self.api.candles.candles_data is not None:
                    break
            except Exception as e:
                logging.error(f"Erro ao obter candles: {e}. Tentando reconectar...")
                self.connect()
    
        return self.api.candles.candles_data        
        
    def start_candles_stream(self, ACTIVE, size, maxdict):
        """
        Inicia o streaming de candles em tempo real para um ativo e tamanho específicos.
    
        Este método configura o streaming de candles em tempo real para o ativo e tamanho especificados.
        Se o tamanho for "all", ele inicia o streaming para todos os tamanhos disponíveis.
    
        Parâmetros:
        ACTIVE (str): Nome do ativo (ex: "EURUSD").
        size (int ou str): Tamanho do candle em segundos ou "all" para todos os tamanhos.
        maxdict (int): Tamanho máximo do dicionário de candles em tempo real.
        """
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
            logging.error(f"Tamanho inválido: {size}. Use 'all' ou um tamanho válido.")
            
    def stop_candles_stream(self, ACTIVE, size):
        """
        Para o streaming de candles em tempo real para um ativo e tamanho específicos.
    
        Este método interrompe o streaming de candles em tempo real para o ativo e tamanho especificados.
        Se o tamanho for "all", ele interrompe o streaming para todos os tamanhos disponíveis.
    
        Parâmetros:
        ACTIVE (str): Nome do ativo (ex: "EURUSD").
        size (int ou str): Tamanho do candle em segundos ou "all" para todos os tamanhos.
        """
        if size == "all":
            self.stop_candles_all_size_stream(ACTIVE)
        elif size in self.size:
            self.stop_candles_one_stream(ACTIVE, size)
        else:
            logging.error(f"Tamanho inválido: {size}. Use 'all' ou um tamanho válido.")      
            
    def get_realtime_candles(self, ACTIVE, size):
        """
        Obtém os candles em tempo real para um ativo e tamanho específicos.
    
        Este método retorna os candles em tempo real armazenados no dicionário `real_time_candles`.
    
        Parâmetros:
        ACTIVE (str): Nome do ativo (ex: "EURUSD").
        size (int ou str): Tamanho do candle em segundos ou "all" para todos os tamanhos.
    
        Retorno:
        dict: Dicionário contendo os candles em tempo real, ou False em caso de erro.
        """
        if size == "all":
            try:
                return self.api.real_time_candles[ACTIVE]
            except Exception as e:
                logging.error(f"Erro ao obter candles em tempo real (todos os tamanhos): {e}")
                return False
        elif size in self.size:
            try:
                return self.api.real_time_candles[ACTIVE][size]
            except Exception as e:
                logging.error(f"Erro ao obter candles em tempo real (tamanho {size}): {e}")
                return False
        else:
            logging.error(f"Tamanho inválido: {size}. Use 'all' ou um tamanho válido.")
            return False
            
    def get_all_realtime_candles(self):
        """
        Obtém todos os candles em tempo real armazenados.
    
        Este método retorna todos os candles em tempo real armazenados no dicionário `real_time_candles`.
    
        Retorno:
        dict: Dicionário contendo todos os candles em tempo real.
        """
        return self.api.real_time_candles              
        
    def full_realtime_get_candle(self, ACTIVE, size, maxdict):
        """
        Preenche o dicionário de candles em tempo real com dados históricos.
    
        Este método obtém candles históricos para um ativo e tamanho específicos e os armazena
        no dicionário `real_time_candles` para uso em tempo real.
    
        Parâmetros:
        ACTIVE (str): Nome do ativo (ex: "EURUSD").
        size (int): Tamanho do candle em segundos.
        maxdict (int): Número máximo de candles a serem armazenados.
        """
        candles = self.get_candles(ACTIVE, size, maxdict, self.api.timesync.server_timestamp)
        for can in candles:
            self.api.real_time_candles[str(ACTIVE)][int(size)][can["from"]] = can            
            
    def start_candles_one_stream(self, ACTIVE, size):
        """
        Inicia o streaming de candles em tempo real para um ativo e tamanho específicos.
    
        Este método inscreve o usuário para receber candles em tempo real para o ativo e tamanho
        especificados. Ele aguarda até que o streaming seja confirmado ou um timeout ocorra.
    
        Parâmetros:
        ACTIVE (str): Nome do ativo (ex: "EURUSD").
        size (int): Tamanho do candle em segundos.
    
        Retorno:
        bool: True se o streaming for iniciado com sucesso, False em caso de timeout.
        """
        if f"{ACTIVE},{size}" not in self.subscribe_candle:
            self.subscribe_candle.append(f"{ACTIVE},{size}")
    
        start = time.time()
        self.api.candle_generated_check[str(ACTIVE)][int(size)] = {}
    
        while True:
            if time.time() - start > 20:
                logging.error("Timeout ao iniciar o streaming de candles.")
                return False
    
            try:
                if self.api.candle_generated_check[str(ACTIVE)][int(size)] == True:
                    return True
            except KeyError:
                pass
    
            try:
                self.api.subscribe(OP_code.ACTIVES[ACTIVE], size)
            except Exception as e:
                logging.error(f"Erro ao iniciar o streaming de candles: {e}. Tentando reconectar...")
                self.connect()
    
            time.sleep(1)  # Evita o uso excessivo da CPU     
            
    def stop_candles_one_stream(self, ACTIVE, size):
        """
        Para o streaming de candles em tempo real para um ativo e tamanho específicos.
    
        Este método cancela a inscrição para receber candles em tempo real para o ativo e tamanho
        especificados. Ele aguarda até que o streaming seja interrompido.
    
        Parâmetros:
        ACTIVE (str): Nome do ativo (ex: "EURUSD").
        size (int): Tamanho do candle em segundos.
    
        Retorno:
        bool: True se o streaming for interrompido com sucesso.
        """
        if f"{ACTIVE},{size}" in self.subscribe_candle:
            self.subscribe_candle.remove(f"{ACTIVE},{size}")
    
        while True:
            try:
                if self.api.candle_generated_check[str(ACTIVE)][int(size)] == {}:
                    return True
            except KeyError:
                pass
    
            self.api.candle_generated_check[str(ACTIVE)][int(size)] = {}
            self.api.unsubscribe(OP_code.ACTIVES[ACTIVE], size)
            time.sleep(self.suspend * 10)  # Aguarda antes de tentar novamente
            
    def start_candles_all_size_stream(self, ACTIVE):
        """
        Inicia o streaming de candles em tempo real para todos os tamanhos de um ativo específico.
    
        Este método inscreve o usuário para receber candles em tempo real para todos os tamanhos
        disponíveis do ativo especificado. Ele aguarda até que o streaming seja confirmado ou um
        timeout ocorra.
    
        Parâmetros:
        ACTIVE (str): Nome do ativo (ex: "EURUSD").
    
        Retorno:
        bool: True se o streaming for iniciado com sucesso, False em caso de timeout.
        """
        self.api.candle_generated_all_size_check[str(ACTIVE)] = {}
    
        if str(ACTIVE) not in self.subscribe_candle_all_size:
            self.subscribe_candle_all_size.append(str(ACTIVE))
    
        start = time.time()
        while True:
            if time.time() - start > 20:
                logging.error(f"Timeout ao iniciar o streaming de candles para {ACTIVE}.")
                return False
    
            try:
                if self.api.candle_generated_all_size_check[str(ACTIVE)] == True:
                    return True
            except KeyError:
                pass
    
            try:
                self.api.subscribe_all_size(OP_code.ACTIVES[ACTIVE])
            except Exception as e:
                logging.error(f"Erro ao iniciar o streaming de candles: {e}. Tentando reconectar...")
                self.connect()
    
            time.sleep(1)  # Evita o uso excessivo da CPU
            
    def stop_candles_all_size_stream(self, ACTIVE):
        """
        Para o streaming de candles em tempo real para todos os tamanhos de um ativo específico.
    
        Este método cancela a inscrição para receber candles em tempo real para todos os tamanhos
        do ativo especificado. Ele aguarda até que o streaming seja interrompido.
    
        Parâmetros:
        ACTIVE (str): Nome do ativo (ex: "EURUSD").
        """
        if str(ACTIVE) in self.subscribe_candle_all_size:
            self.subscribe_candle_all_size.remove(str(ACTIVE))
    
        while True:
            try:
                if self.api.candle_generated_all_size_check[str(ACTIVE)] == {}:
                    break
            except KeyError:
                pass
    
            self.api.candle_generated_all_size_check[str(ACTIVE)] = {}
            self.api.unsubscribe_all_size(OP_code.ACTIVES[ACTIVE])
            time.sleep(self.suspend * 10)  # Aguarda antes de tentar novamente
            
    def subscribe_top_assets_updated(self, instrument_type):
        """
        Inscreve-se para receber atualizações sobre os ativos mais negociados de um tipo específico.
    
        Este método inscreve o usuário para receber atualizações em tempo real sobre os ativos
        mais negociados de um tipo de instrumento específico (ex: "forex", "crypto").
    
        Parâmetros:
        instrument_type (str): Tipo de instrumento (ex: "forex", "crypto").
        """
        self.api.Subscribe_Top_Assets_Updated(instrument_type)
        
    def unsubscribe_top_assets_updated(self, instrument_type):
        """
        Cancela a inscrição para receber atualizações sobre os ativos mais negociados de um tipo específico.
    
        Este método cancela a inscrição para receber atualizações em tempo real sobre os ativos
        mais negociados de um tipo de instrumento específico (ex: "forex", "crypto").
    
        Parâmetros:
        instrument_type (str): Tipo de instrumento (ex: "forex", "crypto").
        """
        self.api.Unsubscribe_Top_Assets_Updated(instrument_type)
        
    def get_top_assets_updated(self, instrument_type):
        """
        Obtém os dados atualizados sobre os ativos mais negociados de um tipo específico.
    
        Este método retorna os dados mais recentes sobre os ativos mais negociados de um tipo
        de instrumento específico (ex: "forex", "crypto").
    
        Parâmetros:
        instrument_type (str): Tipo de instrumento (ex: "forex", "crypto").
    
        Retorno:
        dict: Dicionário contendo os dados dos ativos mais negociados, ou None se não houver dados.
        """
        return self.api.top_assets_updated_data.get(instrument_type)
        
    def subscribe_commission_changed(self, instrument_type):
        """
        Inscreve-se para receber atualizações sobre mudanças na comissão de um tipo de instrumento.
    
        Este método inscreve o usuário para receber atualizações em tempo real sobre mudanças
        na comissão de um tipo de instrumento específico (ex: "forex", "crypto").
    
        Parâmetros:
        instrument_type (str): Tipo de instrumento (ex: "forex", "crypto").
        """
        self.api.Subscribe_Commission_Changed(instrument_type)
        
    def unsubscribe_commission_changed(self, instrument_type):
        """
        Cancela a inscrição para receber atualizações sobre mudanças na comissão de um tipo de instrumento.
    
        Este método cancela a inscrição para receber atualizações em tempo real sobre mudanças
        na comissão de um tipo de instrumento específico (ex: "forex", "crypto").
    
        Parâmetros:
        instrument_type (str): Tipo de instrumento (ex: "forex", "crypto").
        """
        self.api.Unsubscribe_Commission_Changed(instrument_type)
        
    def get_commission_change(self, instrument_type):
        """
        Obtém os dados atualizados sobre mudanças na comissão de um tipo de instrumento.
    
        Este método retorna os dados mais recentes sobre mudanças na comissão de um tipo
        de instrumento específico (ex: "forex", "crypto").
    
        Parâmetros:
        instrument_type (str): Tipo de instrumento (ex: "forex", "crypto").
    
        Retorno:
        dict: Dicionário contendo os dados sobre mudanças na comissão.
        """
        return self.api.subscribe_commission_changed_data.get(instrument_type)
        
    def start_mood_stream(self, ACTIVES, instrument="turbo-option"):
        """
        Inicia o streaming do humor dos traders para um ativo específico.
    
        Este método inscreve o usuário para receber atualizações em tempo real sobre o humor
        dos traders (sentimento de compra/venda) para um ativo específico.
    
        Parâmetros:
        ACTIVES (str): Nome do ativo (ex: "EURUSD").
        instrument (str, opcional): Tipo de instrumento (padrão: "turbo-option").
        """
        if ACTIVES not in self.subscribe_mood:
            self.subscribe_mood.append(ACTIVES)
    
        while True:
            try:
                self.api.subscribe_Traders_mood(OP_code.ACTIVES[ACTIVES], instrument)
                if OP_code.ACTIVES[ACTIVES] in self.api.traders_mood:
                    break
            except Exception as e:
                logging.error(f"Erro ao iniciar o streaming do humor dos traders: {e}. Tentando novamente...")
                time.sleep(5)  # Aguarda antes de tentar novamente
                
    def stop_mood_stream(self, ACTIVES, instrument="turbo-option"):
        """
        Para o streaming do humor dos traders para um ativo específico.
    
        Este método cancela a inscrição para receber atualizações em tempo real sobre o humor
        dos traders para um ativo específico.
    
        Parâmetros:
        ACTIVES (str): Nome do ativo (ex: "EURUSD").
        instrument (str, opcional): Tipo de instrumento (padrão: "turbo-option").
        """
        if ACTIVES in self.subscribe_mood:
            self.subscribe_mood.remove(ACTIVES)
    
        self.api.unsubscribe_Traders_mood(OP_code.ACTIVES[ACTIVES], instrument)
        
    def get_traders_mood(self, ACTIVES):
        """
        Obtém o humor dos traders (sentimento de compra/venda) para um ativo específico.
    
        Este método retorna o humor dos traders (percentual de compra/venda) para o ativo especificado.
    
        Parâmetros:
        ACTIVES (str): Nome do ativo (ex: "EURUSD").
    
        Retorno:
        dict: Dicionário contendo o humor dos traders.
        """
        return self.api.traders_mood.get(OP_code.ACTIVES[ACTIVES])
        
    def get_all_traders_mood(self):
        """
        Obtém o humor dos traders (sentimento de compra/venda) para todos os ativos.
    
        Este método retorna o humor dos traders (percentual de compra/venda) para todos os ativos
        disponíveis.
    
        Retorno:
        dict: Dicionário contendo o humor dos traders para todos os ativos.
        """
        return self.api.traders_mood
        
    def get_technical_indicators(self, ACTIVES):
        """
        Obtém os indicadores técnicos para um ativo específico.
    
        Este método consulta a API para obter os indicadores técnicos (ex: médias móveis, RSI)
        para o ativo especificado e aguarda até que a resposta esteja disponível.
    
        Parâmetros:
        ACTIVES (str): Nome do ativo (ex: "EURUSD").
    
        Retorno:
        dict: Dicionário contendo os indicadores técnicos.
        """
        request_id = self.api.get_Technical_indicators(OP_code.ACTIVES[ACTIVES])
    
        while self.api.technical_indicators.get(request_id) is None:
            time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        return self.api.technical_indicators[request_id]    
        
    def check_binary_order(self, order_id):
        """
        Verifica o status de uma ordem binária específica.
    
        Este método aguarda até que a ordem binária especificada esteja disponível e retorna
        os detalhes da ordem.
    
        Parâmetros:
        order_id (int): ID da ordem binária.
    
        Retorno:
        dict: Dicionário contendo os detalhes da ordem binária.
        """
        while order_id not in self.api.order_binary:
            time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        your_order = self.api.order_binary[order_id]
        del self.api.order_binary[order_id]  # Remove a ordem após a consulta
        return your_order
        
    def check_win(self, id_number):
        """
        Verifica o resultado de uma operação binária.
    
        Este método aguarda até que o resultado da operação binária especificada esteja disponível
        e retorna o resultado ("win", "equal" ou "loose").
    
        Parâmetros:
        id_number (int): ID da operação binária.
    
        Retorno:
        str: Resultado da operação ("win", "equal" ou "loose").
        """
        while True:
            try:
                listinfodata_dict = self.api.listinfodata.get(id_number)
                if listinfodata_dict["game_state"] == 1:
                    break
            except KeyError:
                time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        self.api.listinfodata.delete(id_number)  # Remove a operação após a consulta
        return listinfodata_dict["win"]         
        
    def check_win_v2(self, id_number, polling_time):
        """
        Verifica o resultado de uma operação binária com polling.
    
        Este método verifica periodicamente o resultado da operação binária especificada até que
        o resultado esteja disponível. Retorna o lucro líquido da operação.
    
        Parâmetros:
        id_number (int): ID da operação binária.
        polling_time (int): Intervalo de tempo entre as verificações (em segundos).
    
        Retorno:
        float: Lucro líquido da operação.
        """
        while True:
            check, data = self.get_betinfo(id_number)
            win = data["result"]["data"][str(id_number)]["win"]
    
            if check and win != "":
                try:
                    return data["result"]["data"][str(id_number)]["profit"] - data["result"]["data"][str(id_number)]["deposit"]
                except KeyError:
                    pass
    
            time.sleep(polling_time)  # Aguarda antes de tentar novamente
            
    def check_win_v3(self, id_number):
        """
        Verifica o resultado de uma operação binária usando a versão 3 da API.
    
        Este método aguarda até que o resultado da operação binária especificada esteja disponível
        e retorna o resultado e o lucro líquido.
    
        Parâmetros:
        id_number (int): ID da operação binária.
    
        Retorno:
        tuple: Uma tupla contendo o resultado ("win", "equal" ou "loose") e o lucro líquido.
        """
        while True:
            result = self.get_optioninfo_v2(10)
            if result['msg']['closed_options'][0]['id'][0] == id_number and result['msg']['closed_options'][0]['id'][0] is not None:
                win = result['msg']['closed_options'][0]['win']
                profit = result['msg']['closed_options'][0]['win_amount'] - result['msg']['closed_options'][0]['amount']
                return win, (profit if win != 'equal' else 0)
            time.sleep(1)  # Aguarda antes de tentar novamente
            
    def check_win_v4(self, id_number):
        """
        Verifica o resultado de uma operação binária usando a versão 4 da API.
    
        Este método aguarda até que o resultado da operação binária especificada esteja disponível
        e retorna o resultado e o lucro líquido.
    
        Parâmetros:
        id_number (int): ID da operação binária.
    
        Retorno:
        tuple: Uma tupla contendo o resultado ("win", "equal" ou "loose") e o lucro líquido.
        """
        while True:
            try:
                if self.api.socket_option_closed[id_number] is not None:
                    break
            except KeyError:
                time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        x = self.api.socket_option_closed[id_number]
        win = x['msg']['win']
        profit = (
            0 if win == 'equal'
            else float(x['msg']['sum']) * -1 if win == 'loose'
            else float(x['msg']['win_amount']) - float(x['msg']['sum'])
        )
        return win, profit                  
        
    def get_betinfo(self, id_number):
        """
        Obtém informações detalhadas sobre uma aposta específica.
    
        Este método consulta a API para obter informações sobre uma aposta com base no ID fornecido.
        Ele aguarda até que a resposta esteja disponível ou um timeout ocorra.
    
        Parâmetros:
        id_number (int): ID da aposta.
    
        Retorno:
        tuple: Uma tupla contendo:
            - bool: True se a consulta for bem-sucedida, False caso contrário.
            - dict: Dicionário com os detalhes da aposta, ou None em caso de falha.
        """
        while True:
            self.api.game_betinfo.isSuccessful = None
            start = time.time()
    
            try:
                self.api.get_betinfo(id_number)
            except Exception as e:
                logging.error(f"Erro ao obter informações da aposta: {e}. Tentando reconectar...")
                self.connect()
    
            while self.api.game_betinfo.isSuccessful is None:
                if time.time() - start > 10:
                    logging.error("Timeout ao obter informações da aposta. Tentando novamente...")
                    self.connect()
                    self.api.get_betinfo(id_number)
                    time.sleep(self.suspend * 10)
    
            if self.api.game_betinfo.isSuccessful:
                return True, self.api.game_betinfo.dict
            else:
                return False, None                   
                
    def get_optioninfo(self, limit):
        """
        Obtém informações sobre as últimas opções negociadas.
    
        Este método consulta a API para obter informações sobre as últimas opções negociadas,
        limitadas pelo número especificado.
    
        Parâmetros:
        limit (int): Número máximo de opções a serem retornadas.
    
        Retorno:
        dict: Dicionário contendo as informações das opções negociadas.
        """
        self.api.api_game_getoptions_result = None
        self.api.get_options(limit)
    
        while self.api.api_game_getoptions_result is None:
            time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        return self.api.api_game_getoptions_result        
        
    def get_optioninfo_v2(self, limit):
        """
        Obtém informações sobre as últimas opções negociadas (versão 2 da API).
    
        Este método consulta a API para obter informações sobre as últimas opções negociadas,
        limitadas pelo número especificado, usando a versão 2 da API.
    
        Parâmetros:
        limit (int): Número máximo de opções a serem retornadas.
    
        Retorno:
        dict: Dicionário contendo as informações das opções negociadas.
        """
        self.api.get_options_v2_data = None
        self.api.get_options_v2(limit, "binary,turbo")
    
        while self.api.get_options_v2_data is None:
            time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        return self.api.get_options_v2_data
        
    def buy_multi(self, price, ACTIVES, ACTION, expirations):
        """
        Executa múltiplas ordens de compra.
    
        Parâmetros:
        price (list): Lista de preços.
        ACTIVES (list): Lista de ativos.
        ACTION (list): Lista de ações.
        expirations (list): Lista de expirações.
    
        Retorna:
        list: Lista de IDs das ordens executadas.
        """
        if len(price) != len(ACTIVES) != len(ACTION) != len(expirations):
            logging.error('buy_multi error: please input all same len')
            return None
    
        self.api.buy_multi_option = {}
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
        
    def get_remaning(self, duration):
        """
        Obtém o tempo restante até a expiração para uma duração específica.
    
        Este método retorna o tempo restante até a expiração com base na duração especificada.
    
        Parâmetros:
        duration (int): Duração em segundos.
    
        Retorno:
        int: Tempo restante até a expiração, ou "ERROR duration" se a duração não for encontrada.
        """
        for remaning in get_remaning_time(self.api.timesync.server_timestamp):
            if remaning[0] == duration:
                return remaning[1]
    
        logging.error(f"Erro: Duração '{duration}' não encontrada.")
        return "ERROR duration"                      
        
    def buy_by_raw_expirations(self, price, active, direction, option, expired):
        """
        Realiza uma compra de opção binária com base em uma expiração bruta.
    
        Este método permite comprar uma opção binária com base em uma expiração bruta (timestamp).
    
        Parâmetros:
        price (float): Preço da opção.
        active (str): Nome do ativo (ex: "EURUSD").
        direction (str): Direção da opção ("call" ou "put").
        option (str): Tipo de opção (ex: "binary").
        expired (int): Timestamp de expiração.
    
        Retorno:
        tuple: Uma tupla contendo:
            - bool: True se a compra for bem-sucedida, False caso contrário.
            - int: ID da ordem criada, ou None em caso de falha.
        """
        self.api.buy_multi_option = {}
        self.api.buy_successful = None
        req_id = "buyraw"
    
        try:
            self.api.buy_multi_option[req_id]["id"] = None
        except KeyError:
            pass
    
        self.api.buyv3_by_raw_expired(price, OP_code.ACTIVES[active], direction, option, expired, request_id=req_id)
    
        start_t = time.time()
        id = None
        self.api.result = None
    
        while self.api.result is None or id is None:
            try:
                if "message" in self.api.buy_multi_option[req_id]:
                    logging.error(f"Erro na compra: {self.api.buy_multi_option[req_id]['message']}")
                    return False, self.api.buy_multi_option[req_id]["message"]
            except KeyError:
                pass
    
            try:
                id = self.api.buy_multi_option[req_id]["id"]
            except KeyError:
                pass
    
            if time.time() - start_t >= 5:
                logging.error("Timeout na compra.")
                return False, None
    
        return self.api.result, self.api.buy_multi_option[req_id]["id"]

    def buy(self, price, ACTIVES, ACTION, expirations):
        """
        Realiza uma compra de opção binária.

        Parâmetros:
        price (float): Valor da compra.
        ACTIVES (str): Ativo (e.g., "EURUSD").
        ACTION (str): Ação da opção ('put' ou 'call').
        expirations (int): Tempo de expiração em minutos.

        Retorna:
        tuple: (bool, int) - True e o ID da ordem se bem-sucedido, False e None caso contrário.
        """
        if not hasattr(self, 'api') or self.api is None:
            logging.error("Conexão não estabelecida. Não é possível realizar a compra.")
            return False, None

        try:
            self.api.buy_multi_option = {}
            req_id = str(int(time.time()))  # ID único para a requisição

            self.api.buyv3(float(price), OP_code.ACTIVES[ACTIVES], str(ACTION), int(expirations), req_id)

            start_time = time.time()
            timeout = 10  # Tempo limite de 10 segundos

            while self.api.buy_multi_option.get(req_id) is None:
                if time.time() - start_time > timeout:
                    logging.error("Timeout na compra.")
                    return False, None
                time.sleep(0.1)  # Aguarda por intervalos curtos

            order_id = self.api.buy_multi_option[req_id]["id"]
            if isinstance(order_id, int):
                logging.info(f"Compra realizada com sucesso! ID da ordem: {order_id}")
                return True, order_id
            else:
                logging.error("Falha ao obter ID da ordem.")
                return False, None

        except Exception as e:
            logging.error(f"Erro ao realizar a compra: {e}")
            return False, None
                                        
    def sell_option(self, options_ids):
        """
        Vende uma opção binária com base no ID da ordem.
    
        Este método permite vender uma opção binária antes da expiração.
    
        Parâmetros:
        options_ids (int): ID da ordem a ser vendida.
    
        Retorno:
        dict: Resposta da API contendo o resultado da venda.
        """
        self.api.sell_option(options_ids)
        self.api.sold_options_respond = None
    
        while self.api.sold_options_respond is None:
            time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        return self.api.sold_options_respond              
        
    def sell_digital_option(self, options_ids):
        """
        Vende uma opção digital com base no ID da ordem.
    
        Este método permite vender uma opção digital antes da expiração.
    
        Parâmetros:
        options_ids (int): ID da ordem a ser vendida.
    
        Retorno:
        dict: Resposta da API contendo o resultado da venda.
        """
        self.api.sell_digital_option(options_ids)
        self.api.sold_digital_options_respond = None
    
        while self.api.sold_digital_options_respond is None:
            time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        return self.api.sold_digital_options_respond        
        
    def get_digital_underlying_list_data(self):
        """
        Obtém a lista de ativos subjacentes disponíveis para opções digitais.
    
        Este método consulta a API para obter a lista de ativos subjacentes e aguarda até que a resposta
        esteja disponível. Se o tempo de espera exceder 120 segundos, retorna None.
    
        Retorno:
        dict: Dicionário contendo a lista de ativos subjacentes, ou None em caso de timeout.
        """
        self.api.underlying_list_data = None
        self.api.get_digital_underlying()
    
        start_t = time.time()
        while self.api.underlying_list_data is None:
            if time.time() - start_t >= 120:
                logging.warning("Timeout ao obter a lista de ativos subjacentes.")
                return None
            time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        return self.api.underlying_list_data
        
    def get_strike_list(self, ACTIVES, duration):
        """
        Obtém a lista de strikes (preços de exercício) para um ativo e duração específicos.
    
        Este método consulta a API para obter a lista de strikes e os IDs das opções call e put
        associados a cada strike.
    
        Parâmetros:
        ACTIVES (str): Nome do ativo (ex: "EURUSD").
        duration (int): Duração da opção em minutos.
    
        Retorno:
        tuple: Uma tupla contendo:
            - dict: Dados brutos da lista de strikes.
            - dict: Dicionário formatado com strikes e IDs das opções call e put.
        """
        self.api.strike_list = None
        self.api.get_strike_list(ACTIVES, duration)
    
        while self.api.strike_list is None:
            time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        ans = {}
        try:
            for data in self.api.strike_list["msg"]["strike"]:
                temp = {"call": data["call"]["id"], "put": data["put"]["id"]}
                ans[f"{float(data['value']) * 10e-7:.6f}"] = temp
        except KeyError as e:
            logging.error(f"Erro ao processar a lista de strikes: {e}")
            return self.api.strike_list, None
    
        return self.api.strike_list, ans          
        
    def subscribe_strike_list(self, ACTIVE, expiration_period):
        """
        Inscreve-se para receber atualizações sobre a lista de strikes de um ativo.
    
        Este método inscreve o usuário para receber atualizações em tempo real sobre a lista de strikes
        para um ativo e período de expiração específicos.
    
        Parâmetros:
        ACTIVE (str): Nome do ativo (ex: "EURUSD").
        expiration_period (int): Período de expiração em minutos.
        """
        self.api.subscribe_instrument_quites_generated(ACTIVE, expiration_period)
        
    def unsubscribe_strike_list(self, ACTIVE, expiration_period):
        """
        Cancela a inscrição para receber atualizações sobre a lista de strikes de um ativo.
    
        Este método cancela a inscrição para receber atualizações em tempo real sobre a lista de strikes
        para um ativo e período de expiração específicos.
    
        Parâmetros:
        ACTIVE (str): Nome do ativo (ex: "EURUSD").
        expiration_period (int): Período de expiração em minutos.
        """
        if ACTIVE in self.api.instrument_quites_generated_data:
            del self.api.instrument_quites_generated_data[ACTIVE]
        self.api.unsubscribe_instrument_quites_generated(ACTIVE, expiration_period)
        
    def get_instrument_quites_generated_data(self, ACTIVE, duration):
        """
        Obtém os dados gerados de cotações para um ativo e duração específicos.
    
        Este método aguarda até que os dados de cotações estejam disponíveis e os retorna.
    
        Parâmetros:
        ACTIVE (str): Nome do ativo (ex: "EURUSD").
        duration (int): Duração da opção em minutos.
    
        Retorno:
        dict: Dicionário contendo os dados de cotações.
        """
        while self.api.instrument_quotes_generated_raw_data[ACTIVE][duration * 60] == {}:
            time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        return self.api.instrument_quotes_generated_raw_data[ACTIVE][duration * 60]        
        
    def get_realtime_strike_list(self, ACTIVE, duration):
        """
        Obtém a lista de strikes em tempo real para um ativo e duração específicos.
    
        Este método aguarda até que os dados de strikes em tempo real estejam disponíveis e os retorna
        em um formato estruturado.
    
        Parâmetros:
        ACTIVE (str): Nome do ativo (ex: "EURUSD").
        duration (int): Duração da opção em minutos.
    
        Retorno:
        dict: Dicionário contendo a lista de strikes em tempo real.
        """
        while not self.api.instrument_quites_generated_data[ACTIVE][duration * 60]:
            time.sleep(0.1)  # Evita o uso excessivo da CPU
    
        ans = {}
        now_timestamp = self.api.instrument_quites_generated_timestamp[ACTIVE][duration * 60]
    
        while not ans:
            if not self.get_realtime_strike_list_temp_data or now_timestamp != self.get_realtime_strike_list_temp_expiration:
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
                        detail_data = {
                            "profit": profit[strike_list[price_key][side_key]],
                            "id": strike_list[price_key][side_key]
                        }
                        side_data[side_key] = detail_data
                    ans[price_key] = side_data
                except KeyError:
                    pass
    
        return ans
        
    def get_digital_current_profit(self, ACTIVE, duration):
        """
        Obtém o lucro em tempo real para opções digitais com base em ACTIVE e duração.
    
        Parâmetros:
        ACTIVE (str): Ativo para o qual obter o lucro.
        duration (int): Duração em minutos da opção.
    
        Retorna:
        float: O lucro atual se encontrado, caso contrário, False.
        """
        try:
            profit = self.api.instrument_quites_generated_data[ACTIVE][duration * 60]
            # Encontra a primeira chave que contém "SPT" usando generator expression
            key = next(k for k in profit if "SPT" in k)
            return profit[key]
        except (KeyError, StopIteration):
            # Retorna False se ACTIVE, duration ou a chave não forem encontrados
            return False                      

    def buy_digital_spot(self, active: str, amount: float, action: str, duration: int) -> Tuple[bool, Union[int, str]]:
        """
        Compra uma opção digital spot com base no ativo, montante, ação e duração.

        Parâmetros:
        active (str): Ativo (e.g., "EURUSD").
        amount (float): Montante a ser investido.
        action (str): Ação da opção ('put' ou 'call').
        duration (int): Duração da opção em minutos.

        Retorna:
        tuple: (bool, Union[int, str]) - True e o ID da ordem se bem-sucedido, False e mensagem de erro caso contrário.
        """
        action = action.lower()
        if action == 'put':
            action_type = 'P'
        elif action == 'call':
            action_type = 'C'
        else:
            logging.error('buy_digital_spot active error')
            return False, "Ação inválida"

        timestamp = int(self.api.timesync.server_timestamp)
        if duration == 1:
            exp, _ = get_expiration_time(timestamp, duration)
        else:
            now_date = datetime.fromtimestamp(timestamp) + timedelta(minutes=1, seconds=30)
            while now_date.minute % duration != 0 or time.mktime(now_date.timetuple()) - timestamp <= 30:
                now_date += timedelta(minutes=1)
            exp = time.mktime(now_date.timetuple())

        date_formatted = datetime.utcfromtimestamp(exp).strftime("%Y%m%d%H%M")
        instrument_id = f"do{active}{date_formatted}PT{duration}M{action_type}SPT"

        request_id = self.api.place_digital_option(instrument_id, amount)

        start_time = time.time()
        timeout = 120  # Tempo limite em segundos

        while self.api.digital_option_placed_id.get(request_id) is None:
            if time.time() - start_time > timeout:
                logging.error('buy_digital_spot tempo esgotado esperando ID da ordem')
                return False, "Tempo esgotado"
            time.sleep(0.1)  # Aguarda por intervalos curtos

        digital_order_id = self.api.digital_option_placed_id.get(request_id)
        if isinstance(digital_order_id, int):
            return True, digital_order_id
        else:
            return False, digital_order_id
                                                          
    def get_digital_spot_profit_after_sale(self, position_id):
        """
        Calcula o lucro após a venda de uma opção digital com base no ID da posição.
    
        Parâmetros:
        position_id (int): ID da posição da opção digital.
    
        Retorna:
        float: O lucro após a venda, ou None caso não seja possível calcular.
        """
        def get_instrument_id_to_bid(data, instrument_id):
            try:
                return next(row["price"]["bid"] for row in data["msg"]["quotes"] if row["symbols"][0] == instrument_id)
            except StopIteration:
                return None
    
        import time
    
        # Aguarda até que os dados da posição estejam disponíveis com um timeout
        start_time = time.time()
        TIMEOUT = 10  # segundos
        while time.time() - start_time < TIMEOUT:
            position_data = self.get_async_order(position_id).get("position-changed", {})
            if position_data != {}:
                break
            time.sleep(0.1)
        else:
            logging.error("Timeout esperando pelos dados da posição")
            return None
    
        position = position_data.get("msg", {})
        if not position:
            logging.error("Dados da posição não encontrados")
            return None
    
        # Determina se é 'call' ou 'put' com base no instrument_id
        if "MPSPT" in position.get("instrument_id", ""):
            z = False
        elif "MCSPT" in position.get("instrument_id", ""):
            z = True
        else:
            logging.error(f'Position ID {position.get("instrument_id", "")} não contém "MPSPT" ou "MCSPT"')
            return None
    
        # Extrai dados relevantes da posição
        ACTIVES = position.get('raw_event', {}).get('instrument_underlying', "")
        amount = max(position.get('raw_event', {}).get("buy_amount", 0),
                     position.get('raw_event', {}).get("sell_amount", 0))
        duration_str = position.get("instrument_id", "")
        start_duration = duration_str.find("PT") + 2
        end_duration = start_duration + duration_str[start_duration:].find("M")
        duration = int(duration_str[start_duration:end_duration])
        z2 = False
    
        getAbsCount = position.get('raw_event', {}).get("count", 0)
        instrumentStrikeValue = position.get('raw_event', {}).get("instrument_strike_value", 0) / 1000000.0
        spotLowerInstrumentStrike = position.get('raw_event', {}).get("extra_data", {}).get("lower_instrument_strike", 0) / 1000000.0
        spotUpperInstrumentStrike = position.get('raw_event', {}).get("extra_data", {}).get("upper_instrument_strike", 0) / 1000000.0
    
        aVar = position.get('raw_event', {}).get("extra_data", {}).get("lower_instrument_id", "")
        aVar2 = position.get('raw_event', {}).get("extra_data", {}).get("upper_instrument_id", "")
        getRate = position.get('raw_event', {}).get("currency_rate", 1)
    
        # Obtém os dados de geração de instrumentos
        instrument_quites_generated_data = self.get_instrument_quites_generated_data(ACTIVES, duration)
    
        # Obtém os preços de oferta (bid) para os instrumentos
        f_tmp = get_instrument_id_to_bid(instrument_quites_generated_data, aVar)
        if f_tmp is not None:
            self.get_digital_spot_profit_after_sale_data[position_id]["f"] = f_tmp
            f = f_tmp
        else:
            f = self.get_digital_spot_profit_after_sale_data[position_id].get("f", None)
    
        f2_tmp = get_instrument_id_to_bid(instrument_quites_generated_data, aVar2)
        if f2_tmp is not None:
            self.get_digital_spot_profit_after_sale_data[position_id]["f2"] = f2_tmp
            f2 = f2_tmp
        else:
            f2 = self.get_digital_spot_profit_after_sale_data[position_id].get("f2", None)
    
        # Calcula o preço com base nas condições
        if (spotLowerInstrumentStrike != instrumentStrikeValue) and f is not None and f2 is not None:
            if (spotLowerInstrumentStrike > instrumentStrikeValue or instrumentStrikeValue > spotUpperInstrumentStrike):
                if z:
                    instrumentStrikeValue = (spotUpperInstrumentStrike - instrumentStrikeValue) / abs(spotUpperInstrumentStrike - spotLowerInstrumentStrike)
                    f = abs(f2 - f)
                else:
                    instrumentStrikeValue = (instrumentStrikeValue - spotUpperInstrumentStrike) / abs(spotUpperInstrumentStrike - spotLowerInstrumentStrike)
                    f = abs(f2 - f)
            elif z:
                f += ((instrumentStrikeValue - spotLowerInstrumentStrike) / (spotUpperInstrumentStrike - spotLowerInstrumentStrike)) * (f2 - f)
            else:
                instrumentStrikeValue = (spotUpperInstrumentStrike - instrumentStrikeValue) / (spotUpperInstrumentStrike - spotLowerInstrumentStrike)
                f -= f2
            f = f2 + (instrumentStrikeValue * f)
    
        if z2:
            pass  # Placeholder para futuras condições
    
        if f is not None:
            price = f / getRate
            return price * getAbsCount - amount
        else:
            return None                             
            
    def buy_digital(self, amount: float, instrument_id: str) -> Tuple[bool, Union[int, None]]:
        """
        Compra uma opção digital com o montante especificado e o ID do instrumento.
    
        Parâmetros:
        amount (float): O montante a ser investido.
        instrument_id (str): O ID do instrumento da opção digital.
    
        Retorna:
        tuple: (bool, int) - True e o ID da ordem se bem-sucedido, False e None caso contrário.
        """
        self.api.digital_option_placed_id = None
        self.api.place_digital_option(instrument_id, amount)
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.digital_option_placed_id is None:
            if time.time() - start_time > timeout:
                logging.error('buy_digital perdeu digital_option_placed_id')
                return False, None
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        return True, self.api.digital_option_placed_id
    
    def close_digital_option(self, position_id: int) -> bool:
        """
        Fecha a posição de opção digital com o ID especificado.
    
        Parâmetros:
        position_id (int): O ID da posição a ser fechada.
    
        Retorna:
        bool: True se o fechamento for bem-sucedido, False caso contrário.
        """
        self.api.result = None
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.get_async_order(position_id).get("position-changed", {}) == {}:
            if time.time() - start_time > timeout:
                logging.error('close_digital_option tempo esgotado esperando position-changed')
                return False
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        position_changed = self.get_async_order(position_id)["position-changed"]["msg"]
        external_id = position_changed.get("external_id")
        if external_id is None:
            logging.error('close_digital_option external_id não encontrado')
            return False
    
        self.api.close_digital_option(external_id)
        while self.api.result is None:
            if time.time() - start_time > timeout:
                logging.error('close_digital_option tempo esgotado esperando resultado')
                return False
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        return True
    
    def check_win_digital(self, buy_order_id: int, polling_time: float) -> Optional[float]:
        """
        Verifica se a posição de opção digital foi fechada e retorna o lucro realizado.
    
        Parâmetros:
        buy_order_id (int): O ID da ordem de compra.
        polling_time (float): O intervalo de tempo entre cada verificação.
    
        Retorna:
        float: O lucro realizado se a posição estiver fechada, None caso contrário.
        """
        start_time = time.time()
        timeout = 300  # Tempo limite em segundos
    
        while True:
            if time.time() - start_time > timeout:
                logging.error('check_win_digital tempo esgotado esperando posição fechada')
                return None
            data = self.get_digital_position(buy_order_id)
            if data.get("msg", {}).get("position", {}).get("status") == "closed":
                close_reason = data["msg"]["position"]["close_reason"]
                if close_reason == "default":
                    return data["msg"]["position"]["pnl_realized"]
                elif close_reason == "expired":
                    return data["msg"]["position"]["pnl_realized"] - data["msg"]["position"]["buy_amount"]
            time.sleep(polling_time)
    
    def check_win_digital_v2(self, buy_order_id: int) -> Tuple[bool, Optional[float]]:
        """
        Verifica o status da ordem de opção digital e retorna o lucro se estiver fechada.
    
        Parâmetros:
        buy_order_id (int): O ID da ordem de compra.
    
        Retorna:
        tuple: (bool, float) - True e o lucro se fechada, False e None caso contrário.
        """
        start_time = time.time()
        timeout = 300  # Tempo limite em segundos
    
        while self.get_async_order(buy_order_id).get("position-changed", {}) == {}:
            if time.time() - start_time > timeout:
                logging.error('check_win_digital_v2 tempo esgotado esperando position-changed')
                return False, None
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        order_data = self.get_async_order(buy_order_id)["position-changed"]["msg"]
        if order_data is not None:
            if order_data.get("status") == "closed":
                close_reason = order_data.get("close_reason")
                if close_reason == "expired":
                    return True, order_data.get("close_profit") - order_data.get("invest")
                elif close_reason == "default":
                    return True, order_data.get("pnl_realized")
            else:
                return False, None
        else:
            return False, None        
            
    def buy_order(self,
                  instrument_type: str, instrument_id: str,
                  side: str, amount: float, leverage: int,
                  type: str, limit_price: Optional[float] = None, stop_price: Optional[float] = None,
                  stop_lose_kind: Optional[str] = None, stop_lose_value: Optional[float] = None,
                  take_profit_kind: Optional[str] = None, take_profit_value: Optional[float] = None,
                  use_trail_stop: bool = False, auto_margin_call: bool = False,
                  use_token_for_commission: bool = False) -> Tuple[bool, Union[int, str]]:
        """
        Executa uma ordem de compra com os parâmetros especificados.
    
        Parâmetros:
        instrument_type (str): Tipo do instrumento (e.g., 'forex', 'crypto').
        instrument_id (str): ID do instrumento.
        side (str): Lado da ordem ('buy' ou 'sell').
        amount (float): Quantidade a ser investida.
        leverage (int): Alavancagem.
        type (str): Tipo de ordem (e.g., 'market', 'limit').
        limit_price (float, opcional): Preço limite para ordens limitadas.
        stop_price (float, opcional): Preço de stop para ordens stop.
        stop_lose_kind (str, opcional): Tipo de stop loss (e.g., 'percent', 'price').
        stop_lose_value (float, opcional): Valor do stop loss.
        take_profit_kind (str, opcional): Tipo de take profit (e.g., 'percent', 'price').
        take_profit_value (float, opcional): Valor do take profit.
        use_trail_stop (bool, opcional): Usar trailing stop.
        auto_margin_call (bool, opcional): Ativar chamada de margem automática.
        use_token_for_commission (bool, opcional): Usar tokens para comissão.
    
        Retorna:
        tuple: (bool, Union[int, str]) - True e o ID da ordem se bem-sucedido, False e mensagem de erro caso contrário.
        """
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
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.buy_order_id is None:
            if time.time() - start_time > timeout:
                logging.error('buy_order tempo esgotado esperando buy_order_id')
                return False, "Tempo esgotado esperando buy_order_id"
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        check, data = self.get_order(self.api.buy_order_id)
        while data.get("status") == "pending_new":
            if time.time() - start_time > timeout:
                logging.error('buy_order tempo esgotado esperando status diferente de pending_new')
                return False, "Tempo esgotado esperando status da ordem"
            check, data = self.get_order(self.api.buy_order_id)
            time.sleep(1)
    
        if check:
            if data.get("status") != "rejected":
                return True, self.api.buy_order_id
            else:
                return False, data.get("reject_status", "Status de rejeição desconhecido")
        else:
            return False, "Falha ao obter dados da ordem"      
            
    def change_auto_margin_call(self, ID_Name: str, ID: int, auto_margin_call: bool) -> Tuple[bool, dict]:
        """
        Altera a configuração de chamada de margem automática para uma ordem ou posição.
    
        Parâmetros:
        ID_Name (str): Tipo de ID ('position_id' ou 'order_id').
        ID (int): ID da ordem ou posição.
        auto_margin_call (bool): True para ativar, False para desativar.
    
        Retorna:
        tuple: (bool, dict) - True e a resposta da API se bem-sucedido, False e a resposta da API caso contrário.
        """
        self.api.auto_margin_call_changed_respond = None
        self.api.change_auto_margin_call(ID_Name, ID, auto_margin_call)
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.auto_margin_call_changed_respond is None:
            if time.time() - start_time > timeout:
                logging.error('change_auto_margin_call tempo esgotado esperando resposta')
                return False, {"error": "Tempo esgotado esperando resposta"}
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        if self.api.auto_margin_call_changed_respond.get("status") == 2000:
            return True, self.api.auto_margin_call_changed_respond
        else:
            return False, self.api.auto_margin_call_changed_respond
    
    def change_order(self, ID_Name: str, order_id: int,
                     stop_lose_kind: Optional[str], stop_lose_value: Optional[float],
                     take_profit_kind: Optional[str], take_profit_value: Optional[float],
                     use_trail_stop: bool, auto_margin_call: bool) -> Tuple[bool, Union[dict, str]]:
        """
        Altera os parâmetros de uma ordem ou posição, incluindo stop loss, take profit e chamada de margem automática.
    
        Parâmetros:
        ID_Name (str): Tipo de ID ('position_id' ou 'order_id').
        order_id (int): ID da ordem ou posição.
        stop_lose_kind (str, opcional): Tipo de stop loss (e.g., 'percent', 'price').
        stop_lose_value (float, opcional): Valor do stop loss.
        take_profit_kind (str, opcional): Tipo de take profit (e.g., 'percent', 'price').
        take_profit_value (float, opcional): Valor do take profit.
        use_trail_stop (bool): Usar trailing stop.
        auto_margin_call (bool): Ativar chamada de margem automática.
    
        Retorna:
        tuple: (bool, Union[dict, str]) - True e a resposta da API se bem-sucedido, False e mensagem de erro caso contrário.
        """
        check = True
        if ID_Name == "position_id":
            check, order_data = self.get_order(order_id)
            if check:
                position_id = order_data.get("position_id")
                if position_id is None:
                    logging.error('change_order falha ao obter position_id')
                    return False, "Falha ao obter position_id"
                ID = position_id
            else:
                logging.error('change_order falha ao obter dados da ordem')
                return False, "Falha ao obter dados da ordem"
        elif ID_Name == "order_id":
            ID = order_id
        else:
            logging.error('change_order erro de entrada: ID_Name inválido')
            return False, "ID_Name inválido"
    
        if check:
            self.api.tpsl_changed_respond = None
            self.api.change_order(
                ID_Name=ID_Name, ID=ID,
                stop_lose_kind=stop_lose_kind, stop_lose_value=stop_lose_value,
                take_profit_kind=take_profit_kind, take_profit_value=take_profit_value,
                use_trail_stop=use_trail_stop)
    
            self.change_auto_margin_call(ID_Name=ID_Name, ID=ID, auto_margin_call=auto_margin_call)
    
            start_time = time.time()
            timeout = 120  # Tempo limite em segundos
    
            while self.api.tpsl_changed_respond is None:
                if time.time() - start_time > timeout:
                    logging.error('change_order tempo esgotado esperando resposta')
                    return False, {"error": "Tempo esgotado esperando resposta"}
                time.sleep(0.1)  # Aguarda por intervalos curtos
    
            if self.api.tpsl_changed_respond.get("status") == 2000:
                return True, self.api.tpsl_changed_respond.get("msg", {})
            else:
                return False, self.api.tpsl_changed_respond
        else:
            logging.error('change_order falha ao obter position_id')
            return False, "Falha ao obter position_id"
    
    def get_async_order(self, buy_order_id: int) -> dict:
        """
        Obtém os dados assíncronos de uma ordem com base no ID.
    
        Parâmetros:
        buy_order_id (int): ID da ordem.
    
        Retorna:
        dict: Dados da ordem assíncrona.
        """
        return self.api.order_async.get(buy_order_id, {})      
        
    def get_order(self, buy_order_id: int) -> Tuple[bool, Optional[dict]]:
        """
        Obtém os detalhes de uma ordem com base no ID.
    
        Parâmetros:
        buy_order_id (int): ID da ordem.
    
        Retorna:
        tuple: (bool, dict) - True e os dados da ordem se bem-sucedido, False e None caso contrário.
        """
        self.api.order_data = None
        self.api.get_order(buy_order_id)
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.order_data is None:
            if time.time() - start_time > timeout:
                logging.error('get_order tempo esgotado esperando dados da ordem')
                return False, None
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        if self.api.order_data.get("status") == 2000:
            return True, self.api.order_data.get("msg", {})
        else:
            return False, None
    
    def get_pending(self, instrument_type: str) -> Tuple[bool, Optional[dict]]:
        """
        Obtém as ordens pendentes para um tipo de instrumento específico.
    
        Parâmetros:
        instrument_type (str): Tipo de instrumento (e.g., 'forex', 'crypto').
    
        Retorna:
        tuple: (bool, dict) - True e as ordens pendentes se bem-sucedido, False e None caso contrário.
        """
        self.api.deferred_orders = None
        self.api.get_pending(instrument_type)
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.deferred_orders is None:
            if time.time() - start_time > timeout:
                logging.error('get_pending tempo esgotado esperando ordens pendentes')
                return False, None
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        if self.api.deferred_orders.get("status") == 2000:
            return True, self.api.deferred_orders.get("msg", {})
        else:
            return False, None
    
    def get_positions(self, instrument_type: str) -> Tuple[bool, Optional[dict]]:
        """
        Obtém as posições abertas para um tipo de instrumento específico.
    
        Parâmetros:
        instrument_type (str): Tipo de instrumento (e.g., 'forex', 'crypto').
    
        Retorna:
        tuple: (bool, dict) - True e as posições abertas se bem-sucedido, False e None caso contrário.
        """
        self.api.positions = None
        self.api.get_positions(instrument_type)
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.positions is None:
            if time.time() - start_time > timeout:
                logging.error('get_positions tempo esgotado esperando posições')
                return False, None
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        if self.api.positions.get("status") == 2000:
            return True, self.api.positions.get("msg", {})
        else:
            return False, None
    
    def get_position(self, buy_order_id: int) -> Tuple[bool, Optional[dict]]:
        """
        Obtém os detalhes de uma posição com base no ID da ordem.
    
        Parâmetros:
        buy_order_id (int): ID da ordem.
    
        Retorna:
        tuple: (bool, dict) - True e os dados da posição se bem-sucedido, False e None caso contrário.
        """
        check, order_data = self.get_order(buy_order_id)
        if not check:
            logging.error('get_position falha ao obter dados da ordem')
            return False, None
    
        position_id = order_data.get("position_id")
        if position_id is None:
            logging.error('get_position position_id não encontrado')
            return False, None
    
        self.api.position = None
        self.api.get_position(position_id)
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.position is None:
            if time.time() - start_time > timeout:
                logging.error('get_position tempo esgotado esperando dados da posição')
                return False, None
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        if self.api.position.get("status") == 2000:
            return True, self.api.position.get("msg", {})
        else:
            return False, None
    
    def get_digital_position_by_position_id(self, position_id: int) -> dict:
        """
        Obtém os detalhes de uma posição digital com base no ID da posição.
    
        Parâmetros:
        position_id (int): ID da posição.
    
        Retorna:
        dict: Dados da posição digital.
        """
        self.api.position = None
        self.api.get_digital_position(position_id)
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.position is None:
            if time.time() - start_time > timeout:
                logging.error('get_digital_position_by_position_id tempo esgotado esperando dados da posição')
                return {}
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        return self.api.position
    
    def get_digital_position(self, order_id: int) -> dict:
        """
        Obtém os detalhes de uma posição digital com base no ID da ordem.
    
        Parâmetros:
        order_id (int): ID da ordem.
    
        Retorna:
        dict: Dados da posição digital.
        """
        self.api.position = None
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.get_async_order(order_id).get("position-changed", {}) == {}:
            if time.time() - start_time > timeout:
                logging.error('get_digital_position tempo esgotado esperando position-changed')
                return {}
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        position_id = self.get_async_order(order_id)["position-changed"]["msg"].get("external_id")
        if position_id is None:
            logging.error('get_digital_position external_id não encontrado')
            return {}
    
        self.api.get_digital_position(position_id)
    
        while self.api.position is None:
            if time.time() - start_time > timeout:
                logging.error('get_digital_position tempo esgotado esperando dados da posição')
                return {}
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        return self.api.position                 
        
    def get_position_history(self, instrument_type: str) -> Tuple[bool, Optional[dict]]:
        """
        Obtém o histórico de posições para um tipo de instrumento específico.
    
        Parâmetros:
        instrument_type (str): Tipo de instrumento (e.g., 'forex', 'crypto').
    
        Retorna:
        tuple: (bool, dict) - True e o histórico de posições se bem-sucedido, False e None caso contrário.
        """
        self.api.position_history = None
        self.api.get_position_history(instrument_type)
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.position_history is None:
            if time.time() - start_time > timeout:
                logging.error('get_position_history tempo esgotado esperando histórico de posições')
                return False, None
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        if self.api.position_history.get("status") == 2000:
            return True, self.api.position_history.get("msg", {})
        else:
            return False, None
    
    def get_position_history_v2(self, instrument_type: str, limit: int, offset: int, start: int, end: int) -> Tuple[bool, Optional[dict]]:
        """
        Obtém o histórico de posições com filtros adicionais.
    
        Parâmetros:
        instrument_type (str): Tipo de instrumento (e.g., 'forex', 'crypto').
        limit (int): Limite de registros retornados.
        offset (int): Deslocamento para paginação.
        start (int): Timestamp de início do intervalo.
        end (int): Timestamp de fim do intervalo.
    
        Retorna:
        tuple: (bool, dict) - True e o histórico de posições se bem-sucedido, False e None caso contrário.
        """
        self.api.position_history_v2 = None
        self.api.get_position_history_v2(instrument_type, limit, offset, start, end)
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.position_history_v2 is None:
            if time.time() - start_time > timeout:
                logging.error('get_position_history_v2 tempo esgotado esperando histórico de posições')
                return False, None
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        if self.api.position_history_v2.get("status") == 2000:
            return True, self.api.position_history_v2.get("msg", {})
        else:
            return False, None
    
    def get_available_leverages(self, instrument_type: str, actives: str = "") -> Tuple[bool, Optional[dict]]:
        """
        Obtém as alavancagens disponíveis para um tipo de instrumento e ativo específico.
    
        Parâmetros:
        instrument_type (str): Tipo de instrumento (e.g., 'forex', 'crypto').
        actives (str, opcional): Ativo específico (e.g., 'EURUSD').
    
        Retorna:
        tuple: (bool, dict) - True e as alavancagens disponíveis se bem-sucedido, False e None caso contrário.
        """
        self.api.available_leverages = None
        if actives == "":
            self.api.get_available_leverages(instrument_type, "")
        else:
            self.api.get_available_leverages(instrument_type, OP_code.ACTIVES[actives])
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.available_leverages is None:
            if time.time() - start_time > timeout:
                logging.error('get_available_leverages tempo esgotado esperando alavancagens disponíveis')
                return False, None
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        if self.api.available_leverages.get("status") == 2000:
            return True, self.api.available_leverages.get("msg", {})
        else:
            return False, None
    
    def cancel_order(self, buy_order_id: int) -> bool:
        """
        Cancela uma ordem com base no ID.
    
        Parâmetros:
        buy_order_id (int): ID da ordem.
    
        Retorna:
        bool: True se o cancelamento for bem-sucedido, False caso contrário.
        """
        self.api.order_canceled = None
        self.api.cancel_order(buy_order_id)
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.order_canceled is None:
            if time.time() - start_time > timeout:
                logging.error('cancel_order tempo esgotado esperando confirmação de cancelamento')
                return False
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        return self.api.order_canceled.get("status") == 2000
    
    def close_position(self, position_id: int) -> bool:
        """
        Fecha uma posição com base no ID.
    
        Parâmetros:
        position_id (int): ID da posição.
    
        Retorna:
        bool: True se o fechamento for bem-sucedido, False caso contrário.
        """
        check, data = self.get_order(position_id)
        if not check or data.get("position_id") is None:
            logging.error('close_position falha ao obter dados da ordem ou position_id não encontrado')
            return False
    
        self.api.close_position_data = None
        self.api.close_position(data["position_id"])
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.close_position_data is None:
            if time.time() - start_time > timeout:
                logging.error('close_position tempo esgotado esperando confirmação de fechamento')
                return False
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        return self.api.close_position_data.get("status") == 2000
    
    def close_position_v2(self, position_id: int) -> bool:
        """
        Fecha uma posição com base no ID usando a versão 2.
    
        Parâmetros:
        position_id (int): ID da posição.
    
        Retorna:
        bool: True se o fechamento for bem-sucedido, False caso contrário.
        """
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.get_async_order(position_id) is None:
            if time.time() - start_time > timeout:
                logging.error('close_position_v2 tempo esgotado esperando dados da posição')
                return False
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        position_changed = self.get_async_order(position_id)
        self.api.close_position(position_changed["id"])
    
        while self.api.close_position_data is None:
            if time.time() - start_time > timeout:
                logging.error('close_position_v2 tempo esgotado esperando confirmação de fechamento')
                return False
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        return self.api.close_position_data.get("status") == 2000
    
    def get_overnight_fee(self, instrument_type: str, active: str) -> Tuple[bool, Optional[dict]]:
        """
        Obtém a taxa de overnight para um tipo de instrumento e ativo específico.
    
        Parâmetros:
        instrument_type (str): Tipo de instrumento (e.g., 'forex', 'crypto').
        active (str): Ativo específico (e.g., 'EURUSD').
    
        Retorna:
        tuple: (bool, dict) - True e a taxa de overnight se bem-sucedido, False e None caso contrário.
        """
        self.api.overnight_fee = None
        self.api.get_overnight_fee(instrument_type, OP_code.ACTIVES[active])
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.overnight_fee is None:
            if time.time() - start_time > timeout:
                logging.error('get_overnight_fee tempo esgotado esperando taxa de overnight')
                return False, None
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        if self.api.overnight_fee.get("status") == 2000:
            return True, self.api.overnight_fee.get("msg", {})
        else:
            return False, None       
            
    def get_option_open_by_other_pc(self) -> dict:
        """
        Retorna as opções abertas por outros dispositivos.
    
        Retorna:
        dict: Dicionário contendo as opções abertas por outros dispositivos.
        """
        return self.api.socket_option_opened
    
    def del_option_open_by_other_pc(self, id: int) -> None:
        """
        Remove uma opção aberta por outro dispositivo com base no ID.
    
        Parâmetros:
        id (int): ID da opção a ser removida.
        """
        if id in self.api.socket_option_opened:
            del self.api.socket_option_opened[id]
        else:
            logging.warning(f'Opção com ID {id} não encontrada para remoção.')
    
    def opcode_to_name(self, opcode: int) -> str:
        """
        Converte um código de operação (opcode) para o nome do ativo correspondente.
    
        Parâmetros:
        opcode (int): Código de operação.
    
        Retorna:
        str: Nome do ativo correspondente ao opcode.
        """
        try:
            return list(OP_code.ACTIVES.keys())[list(OP_code.ACTIVES.values()).index(opcode)]
        except ValueError:
            logging.error(f'Opcode {opcode} não encontrado.')
            return None
    
    def subscribe_live_deal(self, name: str, active: str, _type: str, buffersize: int) -> None:
        """
        Inscreve-se para receber atualizações em tempo real de negócios ao vivo.
    
        Parâmetros:
        name (str): Nome do evento (e.g., "live-deal-binary-option-placed").
        active (str): Ativo para o qual se inscrever (e.g., "EURUSD").
        _type (str): Tipo de negócio (e.g., "binary", "digital").
        buffersize (int): Tamanho do buffer para armazenar os dados.
        """
        active_id = OP_code.ACTIVES.get(active)
        if active_id is None:
            logging.error(f'Ativo {active} não encontrado.')
            return
    
        self.api.Subscribe_Live_Deal(name, active_id, _type)
        # Comentado: Código para inicializar o buffer de dados (opcional)
        # self.api.live_deal_data[name][active][_type] = deque(list(), buffersize)
    
    def unscribe_live_deal(self, name: str, active: str, _type: str) -> None:
        """
        Cancela a inscrição para receber atualizações em tempo real de negócios ao vivo.
    
        Parâmetros:
        name (str): Nome do evento (e.g., "live-deal-binary-option-placed").
        active (str): Ativo para o qual cancelar a inscrição (e.g., "EURUSD").
        _type (str): Tipo de negócio (e.g., "binary", "digital").
        """
        active_id = OP_code.ACTIVES.get(active)
        if active_id is None:
            logging.error(f'Ativo {active} não encontrado.')
            return
    
        self.api.Unscribe_Live_Deal(name, active_id, _type)   
        
    def set_digital_live_deal_cb(self, cb: callable) -> None:
        """
        Define uma função de callback para negócios ao vivo de opções digitais.
    
        Parâmetros:
        cb (callable): Função de callback a ser chamada quando um novo negócio digital é recebido.
        """
        self.api.digital_live_deal_cb = cb
    
    def set_binary_live_deal_cb(self, cb: callable) -> None:
        """
        Define uma função de callback para negócios ao vivo de opções binárias.
    
        Parâmetros:
        cb (callable): Função de callback a ser chamada quando um novo negócio binário é recebido.
        """
        self.api.binary_live_deal_cb = cb
    
    def get_live_deal(self, name: str, active: str, _type: str) -> list:
        """
        Obtém os dados de negócios ao vivo para um nome, ativo e tipo específicos.
    
        Parâmetros:
        name (str): Nome do evento (e.g., "live-deal-binary-option-placed").
        active (str): Ativo (e.g., "EURUSD").
        _type (str): Tipo de negócio (e.g., "binary", "digital").
    
        Retorna:
        list: Lista de negócios ao vivo.
        """
        return self.api.live_deal_data.get(name, {}).get(active, {}).get(_type, [])
    
    def pop_live_deal(self, name: str, active: str, _type: str) -> Optional[dict]:
        """
        Remove e retorna o último negócio ao vivo para um nome, ativo e tipo específicos.
    
        Parâmetros:
        name (str): Nome do evento (e.g., "live-deal-binary-option-placed").
        active (str): Ativo (e.g., "EURUSD").
        _type (str): Tipo de negócio (e.g., "binary", "digital").
    
        Retorna:
        dict: Último negócio ao vivo, ou None se a lista estiver vazia.
        """
        try:
            return self.api.live_deal_data[name][active][_type].pop()
        except (KeyError, IndexError):
            logging.warning(f'Nenhum negócio ao vivo encontrado para {name}, {active}, {_type}')
            return None
    
    def clear_live_deal(self, name: str, active: str, _type: str, buffersize: int) -> None:
        """
        Limpa e redefine o buffer de negócios ao vivo para um nome, ativo e tipo específicos.
    
        Parâmetros:
        name (str): Nome do evento (e.g., "live-deal-binary-option-placed").
        active (str): Ativo (e.g., "EURUSD").
        _type (str): Tipo de negócio (e.g., "binary", "digital").
        buffersize (int): Tamanho do buffer.
        """
        self.api.live_deal_data[name][active][_type] = deque(list(), buffersize)
    
    def get_user_profile_client(self, user_id: int) -> dict:
        """
        Obtém o perfil do cliente com base no ID do usuário.
    
        Parâmetros:
        user_id (int): ID do usuário.
    
        Retorna:
        dict: Dados do perfil do cliente.
        """
        self.api.user_profile_client = None
        self.api.Get_User_Profile_Client(user_id)
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.user_profile_client is None:
            if time.time() - start_time > timeout:
                logging.error('get_user_profile_client tempo esgotado esperando dados do perfil')
                return {}
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        return self.api.user_profile_client
    
    def request_leaderboard_userinfo_deals_client(self, user_id: int, country_id: int) -> dict:
        """
        Solicita informações do líder e negócios do cliente com base no ID do usuário e país.
    
        Parâmetros:
        user_id (int): ID do usuário.
        country_id (int): ID do país.
    
        Retorna:
        dict: Dados do líder e negócios do cliente.
        """
        self.api.leaderboard_userinfo_deals_client = None
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while True:
            if time.time() - start_time > timeout:
                logging.error('request_leaderboard_userinfo_deals_client tempo esgotado esperando dados')
                return {}
    
            try:
                if self.api.leaderboard_userinfo_deals_client and self.api.leaderboard_userinfo_deals_client.get("isSuccessful") == True:
                    break
            except Exception as e:
                logging.error(f'Erro ao verificar leaderboard_userinfo_deals_client: {e}')
    
            self.api.Request_Leaderboard_Userinfo_Deals_Client(user_id, country_id)
            time.sleep(0.2)
    
        return self.api.leaderboard_userinfo_deals_client   
        
    def get_users_availability(self, user_id: int) -> dict:
        """
        Obtém a disponibilidade de um usuário com base no ID.
    
        Parâmetros:
        user_id (int): ID do usuário.
    
        Retorna:
        dict: Dados de disponibilidade do usuário.
        """
        self.api.users_availability = None
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.users_availability is None:
            if time.time() - start_time > timeout:
                logging.error('get_users_availability tempo esgotado esperando dados de disponibilidade')
                return {}
            self.api.Get_Users_Availability(user_id)
            time.sleep(0.2)  # Aguarda por intervalos curtos
    
        return self.api.users_availability
    
    def get_digital_payout(self, active: str, seconds: int = 0) -> float:
        """
        Obtém o payout de uma opção digital para um ativo específico.
    
        Parâmetros:
        active (str): Ativo (e.g., "EURUSD").
        seconds (int, opcional): Tempo máximo de espera em segundos.
    
        Retorna:
        float: Payout da opção digital, ou 0 se não for obtido dentro do tempo limite.
        """
        self.api.digital_payout = None
        asset_id = OP_code.ACTIVES.get(active)
        if asset_id is None:
            logging.error(f'Ativo {active} não encontrado.')
            return 0
    
        self.api.subscribe_digital_price_splitter(asset_id)
    
        start_time = time.time()
        while self.api.digital_payout is None:
            if seconds and int(time.time() - start_time) > seconds:
                break
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        self.api.unsubscribe_digital_price_splitter(asset_id)
    
        return self.api.digital_payout if self.api.digital_payout else 0
    
    def logout(self) -> None:
        """
        Realiza o logout do usuário.
        """
        self.api.logout()
    
    def buy_digital_spot_v2(self, active: str, amount: float, action: str, duration: int) -> Tuple[bool, Union[int, None]]:
        """
        Compra uma opção digital spot com base no ativo, montante, ação e duração.
    
        Parâmetros:
        active (str): Ativo (e.g., "EURUSD").
        amount (float): Montante a ser investido.
        action (str): Ação da opção ('put' ou 'call').
        duration (int): Duração da opção em minutos.
    
        Retorna:
        tuple: (bool, int) - True e o ID da ordem se bem-sucedido, False e None caso contrário.
        """
        action = action.lower()
        if action == 'put':
            action_type = 'P'
        elif action == 'call':
            action_type = 'C'
        else:
            logging.error(f'Ação inválida: {action}')
            return False, None
    
        timestamp = int(self.api.timesync.server_timestamp)
    
        if duration == 1:
            exp, _ = get_expiration_time(timestamp, duration)
        else:
            now_date = datetime.fromtimestamp(timestamp) + timedelta(minutes=1, seconds=30)
            while now_date.minute % duration != 0 or time.mktime(now_date.timetuple()) - timestamp <= 120:
                now_date += timedelta(minutes=1)
            exp = time.mktime(now_date.timetuple())
    
        date_formatted = datetime.utcfromtimestamp(exp).strftime("%Y%m%d%H%M")
        active_id = str(OP_code.ACTIVES.get(active))
        if active_id is None:
            logging.error(f'Ativo {active} não encontrado.')
            return False, None
    
        instrument_id = f"do{active_id}A{date_formatted[:8]}D{date_formatted[8:]}00T{duration}M{action_type}SPT"
        logger = logging.getLogger(__name__)
        logger.info(instrument_id)
    
        request_id = self.api.place_digital_option_v2(instrument_id, active_id, amount)
    
        start_time = time.time()
        timeout = 120  # Tempo limite em segundos
    
        while self.api.digital_option_placed_id.get(request_id) is None:
            if time.time() - start_time > timeout:
                logging.error('buy_digital_spot_v2 tempo esgotado esperando ID da ordem')
                return False, None
            time.sleep(0.1)  # Aguarda por intervalos curtos
    
        digital_order_id = self.api.digital_option_placed_id.get(request_id)
        if isinstance(digital_order_id, int):
            return True, digital_order_id
        else:
            return False, digital_order_id
