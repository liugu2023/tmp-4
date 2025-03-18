#!/usr/bin/env python3
import time
import logging
import requests
from datetime import datetime

# 配置参数
CHECK_INTERVAL = 300  # 检查间隔(秒)，5分钟
API_URL = "http://10.21.22.204:30000/api/check-service"  # 状态检查API地址
QQ_BOT_URL = "http://127.0.0.1:5700"  # go-cqhttp的API地址
GROUP_ID = "783316363"  # 需要通知的QQ群号
ACCESS_TOKEN = "lgy060802"  # 机器人访问令牌

# 初始化日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('model_monitor.log'),
        logging.StreamHandler()
    ]
)

last_status = None
error_count = 0

def send_qq_message(message):
    """通过QQ机器人API发送群消息"""
    url = f"{QQ_BOT_URL}/send_group_msg"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "group_id": GROUP_ID,
        "message": message
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            logging.info("消息发送成功")
            return True
        else:
            logging.error(f"消息发送失败: {response.text}")
            return False
    except Exception as e:
        logging.error(f"发送消息时出错: {str(e)}")
        return False

def check_model_status():
    """检查模型服务状态"""
    global error_count
    try:
        response = requests.get(API_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            error_count = 0  # 重置错误计数器
            return data.get('running', False)
        else:
            logging.error(f"API返回异常状态码: {response.status_code}")
            error_count += 1
            return None
    except Exception as e:
        logging.error(f"检查服务状态失败: {str(e)}")
        error_count += 1
        return None

def main():
    global last_status
    
    logging.info("模型状态监控服务启动")
    
    while True:
        current_status = check_model_status()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 处理连续错误
        if error_count >= 3:
            alert_msg = f"连续检查失败{error_count}次，请检查监控系统！"
            logging.critical(alert_msg)
            send_qq_message(alert_msg)
            error_count = 0
            
        # 状态变化处理
        if current_status is not None:
            if last_status is None:  # 首次运行
                last_status = current_status
                logging.info(f"初始服务状态: {'运行中' if current_status else '已停止'}")
            else:
                if current_status != last_status:
                    status_text = '已恢复运行' if current_status else '已停止运行'
                    message = f"{now}\n模型服务状态变化：{status_text}"
                    if send_qq_message(message):
                        last_status = current_status
                        
                # 服务持续停止状态
                if not current_status and last_status == current_status:
                    message = f"{now}\n模型服务仍处于停止状态，请及时处理！"
                    send_qq_message(message)
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("监控服务已手动停止")
    except Exception as e:
        logging.error(f"未处理的异常: {str(e)}") 