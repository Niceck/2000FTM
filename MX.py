import logging
import requests
import hashlib
import hmac
import time
import numpy as np
import talib
import json


# 全局变量定义
api_key = "mx0vglJrU5yVdWi4i3"
api_secret = "f4b12641f8364b4a952e21aed19ab40c"
api_base_url = "https://www.mexc.com/open/api/v2"
symbol = "MX_USDT"
amount_in_usdt = 100   # 设置买入的USDT金额
kline_interval = "1m"


# 创建MEXC签名函数
def create_mexc_signature(api_secret, timestamp, params, method, endpoint):
    if method == "GET" or method == "DELETE":
        sorted_params = "&".join([f"{key}={params[key]}" for key in sorted(params)]) if params else ""
    else:
        sorted_params = json.dumps(params) if params else ""

    message = api_key + timestamp + sorted_params
    signature = hmac.new(api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return signature


# 发送请求
def send_request(method, endpoint, params=None):
    response = None  # 在try-except块之外初始化response变量
    timestamp = str(int(time.time() * 1000))
    headers = {
        'Content-Type': 'application/json',
        'ApiKey': api_key,
        'Request-Time': timestamp,
        'Signature': create_mexc_signature(api_secret, timestamp, params, method, endpoint)
    }

    full_url = api_base_url + endpoint
    try:
        if method == "GET":
            response = requests.get(full_url, headers=headers, params=params)
        elif method == "POST":
            response = requests.post(full_url, headers=headers, json=params)
        elif method == "DELETE":
            response = requests.delete(full_url, headers=headers, params=params)
        else:
            raise ValueError("Unsupported HTTP method")

        response.raise_for_status()
        return response.json()
    except Exception as e:
        error_message = f"Error in send_request: {e}"
        logging.error(error_message)
        if response is not None:
            response_message = f"Response: {response.text}"
            logging.error(response_message)
            print(error_message)
            print(response_message)
        else:
            print(error_message)
        return None
# 简化的 get_request 函数
def get_request(endpoint, params=None):
    return send_request("GET", endpoint, params)

# 简化的 post_request 函数
def post_request(endpoint, params):
    return send_request("POST", endpoint, params)

# 获取账户余额信息
def get_account_balance_info():
    balance = 0  # TAO余额初始化
    endpoint = "/account/info"
    response = get_request(endpoint)
    if response and response.get('code') == 200:
        data = response['data']
        for currency, balance_info in data.items():
            available = balance_info['available']
            frozen = balance_info['frozen']
            print(f"{currency}: $$$$$$= {available}, $$$$$ = {frozen}")
            if currency == 'MX':
                balance = float(available)
    else:
        print(f"获取账户余额失败：{response}")
    return balance  # 返回TAO余额


def get_previous_kline_and_ma(symbol, interval, ma_periods):
    endpoint = f"{api_base_url}/market/kline"
    max_period = max(ma_periods)
    params = {'symbol': symbol, 'interval': interval, 'limit': max_period + 1}
    try:
        response = requests.get(endpoint, params=params).json()
        if response['code'] == 200 and len(response['data']) >= max_period + 1:
            kline_data = response['data']
            # 获取收盘价
            close_prices = np.array([float(kline[2]) for kline in kline_data])  # 使用索引2获取收盘价
            # 计算倒数第二根K线的MA
            ma_values = {period: talib.SMA(close_prices, timeperiod=period)[-2] for period in ma_periods}
            previous_close_price = close_prices[-2]
            return previous_close_price, ma_values
        return None, None
    except Exception as e:
        print(f"获取K线数据失败，错误信息为：{str(e)}")
        return None, None

def get_latest_market_price(symbol):
    endpoint = f"{api_base_url}/market/ticker"
    params = {'symbol': symbol}
    try:
        response = requests.get(endpoint, params=params).json()
        return float(response['data'][0]['last']) if response['code'] == 200 else None
    except Exception as e:
        print(f"获取市价失败，错误信息为：{str(e)}")
        return None

def place_order(symbol, price, quantity, trade_type):
    params = {
        'symbol': symbol,
        'price': price,
        'quantity': quantity,
        'trade_type': trade_type,
        'order_type': "IMMEDIATE_OR_CANCEL"  # 设置为立即执行或取消
    }
    return send_request("POST", "/order/place", params)

def calculate_adx(symbol, interval, adx_period):
    endpoint = f"{api_base_url}/market/kline"
    params = {'symbol': symbol, 'interval': interval, 'limit': adx_period * 2}  # 增加获取的数据点数量
    try:
        response = requests.get(endpoint, params=params).json()
        if response['code'] == 200 and len(response['data']) >= adx_period:
            kline_data = response['data']
            high_prices = np.array([float(kline[3]) for kline in kline_data])
            low_prices = np.array([float(kline[4]) for kline in kline_data])
            close_prices = np.array([float(kline[2]) for kline in kline_data])
            adx = talib.ADX(high_prices, low_prices, close_prices, timeperiod=adx_period)
            plus_di = talib.PLUS_DI(high_prices, low_prices, close_prices, timeperiod=adx_period)
            minus_di = talib.MINUS_DI(high_prices, low_prices, close_prices, timeperiod=adx_period)
            return adx[-1] if not np.isnan(adx[-1]) else None, plus_di[-1], minus_di[-1]
        return None, None, None
    except Exception as e:
        print(f"计算ADX失败，错误信息为：{str(e)}")
        return None, None, None

def calculate_return_over_period(close_prices, period):
    return (close_prices[-1] - close_prices[-1-period]) / close_prices[-1-period]

def get_price_change(symbol, interval, periods):
    endpoint = f"{api_base_url}/market/kline"
    params = {'symbol': symbol, 'interval': interval, 'limit': max(periods) + 1}
    try:
        response = requests.get(endpoint, params=params).json()
        if response['code'] == 200:
            kline_data = response['data']
            close_prices = np.array([float(kline[2]) for kline in kline_data])
            return {period: calculate_return_over_period(close_prices, period) for period in periods}
        return None
    except Exception as e:
        print(f"获取价格变化失败，错误信息为：{str(e)}")
        return None

def get_historical_close_prices(symbol, interval, limit):
    endpoint = f"{api_base_url}/market/kline"
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    try:
        response = requests.get(endpoint, params=params).json()
        if response['code'] == 200:
            kline_data = response['data']
            return [float(kline[2]) for kline in kline_data]
        else:
            return []
    except Exception as e:
        print(f"获取历史价格失败，错误信息为：{str(e)}")
        return []

def calculate_macd(close_prices, fastperiod=12, slowperiod=26, signalperiod=9):
    # 将输入的收盘价转换为浮点数
    close_prices = np.array(close_prices, dtype=float)
    macd, macdsignal, macdhist = talib.MACD(close_prices, fastperiod, slowperiod, signalperiod)
    return macd, macdsignal, macdhist

# 计算ATR
def calculate_atr(symbol, interval, atr_period):
    endpoint = f"{api_base_url}/market/kline"
    params = {'symbol': symbol, 'interval': interval, 'limit': atr_period + 1}
    try:
        response = requests.get(endpoint, params=params).json()
        if response['code'] == 200:
            kline_data = response['data']
            high_prices = np.array([float(kline[3]) for kline in kline_data])
            low_prices = np.array([float(kline[4]) for kline in kline_data])
            close_prices = np.array([float(kline[2]) for kline in kline_data])
            atr = talib.ATR(high_prices, low_prices, close_prices, timeperiod=atr_period)
            return atr[-1]
        return None
    except Exception as e:
        print(f"计算ATR失败，错误信息为：{str(e)}")
        return None

# 判断价格是否显著偏离均线
def is_price_deviation_from_ma(price, ma, threshold=0.01):
    return abs(price - ma) / ma > threshold

if __name__ == "__main__":
    while True:
        try:
            tao_balance = get_account_balance_info()
            latest_price = get_latest_market_price(symbol)
            previous_close, ma_values = get_previous_kline_and_ma(symbol, kline_interval, [5, 10])
            adx_value, plus_di, minus_di = calculate_adx(symbol, kline_interval, 7)  # 假设使用14个周期的ADX
            price_changes = get_price_change(symbol, kline_interval, [20, 60])
            # 计算ATR
            atr_value = calculate_atr(symbol, kline_interval, 7)
            # 获取历史收盘价数据
            historical_close_prices = get_historical_close_prices(symbol, kline_interval, 100)  # 例如最近100根K线的收盘价
            if not historical_close_prices:
                continue
            _, _, macdhist = calculate_macd(np.array(historical_close_prices))
            current_macd = macdhist[-1]

            if price_changes is None:
                continue
            print(f"MX ---- {price_changes} ------")
            print(f"==={adx_value:.3f}===, ++++++ {plus_di:.3f}++++++, ------: {minus_di:.3f}----MA")
            print(f"ATR --- {atr_value:.4f}--- ---")
            # 判断是否卖出或买入
            if tao_balance > 0 and latest_price < min(ma_values.values()) and plus_di < minus_di:
                quantity = str(tao_balance)  # 卖出所有TAO余额
                trade_type = "ASK"
                print(f"MX--------MX---------MX {quantity}")
                print()
                order_response = place_order(symbol, str(latest_price), quantity, trade_type)

            elif tao_balance < float(round(5 / latest_price, 3)) and \
                 previous_close > max(ma_values.values()) and \
                 ma_values[5] > ma_values[10] and \
                 price_changes[20] > 0 and price_changes[60] > 0 and \
                 adx_value > 20 and plus_di > minus_di and atr_value > 0.001
                 print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
                # 执行买入操作
                quantity = str(round(amount_in_usdt / latest_price - tao_balance,3))  # 计算买入数量
                trade_type = "BID"
                print()     
                print(f"MX+++++++++MX+++++++++MX {quantity}")
                print()
                order_response = place_order(symbol, str(latest_price), quantity, trade_type)
            else:
                print()
                print("MX=========MX==========MX")
                print()
                order_response = None

            # 设置循环延时，例如每5分钟检查一次
            time.sleep(15)

        except Exception as e:
            import traceback
            print(f"发生错误: {e}")
            traceback.print_exc()  # 输出完整的堆栈跟踪
            time.sleep(60)
        except KeyboardInterrupt:
            print("程序已手动中断")
