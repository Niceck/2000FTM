import logging
import requests
import hashlib
import hmac
import time
import numpy as np
import talib
import json


# 全局变量定义
api_key = "mx0vgluzuLV5p5SFck"
api_secret = "475cb0de5d41458d86eeb801b54fea2e"
api_base_url = "https://www.mexc.com/open/api/v2"
symbol = "tao_USDT"
amount_in_usdt = 100 # 设置买入的USDT金额
kline_interval = "30m"


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
            print(f"{currency}: 可用余额 = {available}, 冻结余额 = {frozen}")
            if currency == 'TAO':
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




if __name__ == "__main__":
    while True:
        try:
            # 获取TAO余额
            tao_balance = get_account_balance_info()

            # 获取并打印市场数据
            latest_price = get_latest_market_price(symbol)
            previous_close, ma_values = get_previous_kline_and_ma(symbol, kline_interval, [5, 10, 20])
            print(f"最新市价: {latest_price}，前收盘价: {previous_close}")
            print(f"MA5: {ma_values[5]:.2f}, MA10: {ma_values[10]:.2f}, MA20: {ma_values[20]:.2f}")

            # 判断是否卖出或买入
            if tao_balance > 0 and previous_close < min(ma_values.values()):
                # 执行卖出操作
                quantity = str(tao_balance)  # 卖出所有TAO余额
                trade_type = "ASK"
                print(f"------------------ {quantity}")
                order_response = place_order(symbol, str(latest_price), quantity, trade_type)


            elif tao_balance < float(round(amount_in_usdt / latest_price, 2)) and previous_close > max(
                    ma_values.values()) and ma_values[10] > ma_values[20]:
                # 执行买入操作
                quantity = 0.05  # 计算买入数量
                trade_type = "BID"
                print(f"+++++++++++++++++++ {quantity}")
                order_response = place_order(symbol, str(latest_price), quantity, trade_type)
            else:
                print("====================")
                order_response = None
            if order_response:
                print("下单API响应:", order_response)
                logging.info(f"Order Response: {order_response}")
            else:
                logging.error("Failed to place order or no trade executed")

            # 设置循环延时，例如每5分钟检查一次
            time.sleep(5)

        except Exception as e:
            import traceback
            print(f"发生错误: {e}")
            traceback.print_exc()  # 输出完整的堆栈跟踪
            time.sleep(60)
        except KeyboardInterrupt:
            print("程序已手动中断")

