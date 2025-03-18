#!/usr/bin/env python3
import time
import logging
from datetime import datetime
from qqbot import _bot as bot

# 配置参数
CHECK_INTERVAL = 300  # 检查间隔(秒)，5分钟
API_URL = "http://10.21.22.204:25000/api/check-service"  # 状态检查API地址
GROUP_ID = "783316363"  # 需要通知的QQ群号（直接填数字即可）
ADMIN_QQ = "3078919738"  # 管理员QQ号（用于错误通知）
BOT_QQ = "3923494064"    # 机器人QQ号
BOT_PASSWORD = "lgy060802"  # 机器人密码

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

def send_qq_message(to, msg):
    """使用qqbot发送消息"""
    try:
        # 登录QQ（每次发送都重新登录确保连接有效）
        bot.Login(['-q', BOT_QQ, '-p', BOT_PASSWORD])
        # 发送群消息
        bot.SendTo(to, msg)
        logging.info(f"消息发送成功至 {to}")
        return True
    except Exception as e:
        logging.error(f"发送消息失败: {str(e)}")
        return False
    finally:
        bot.Stop()  # 确保释放资源

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

def send_admin_alert(message):
    """给管理员发送私聊提醒"""
    try:
        bot.Login(['-q', BOT_QQ, '-p', BOT_PASSWORD])
        # 发送私聊消息
        bot.SendTo(ADMIN_QQ, f"[模型监控] {message}")
        return True
    except Exception as e:
        logging.error(f"发送管理员通知失败: {str(e)}")
        return False
    finally:
        bot.Stop()

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
            send_admin_alert(alert_msg)
            error_count = 0  # 重置计数器
            
        # 状态变化处理
        if current_status is not None:
            if last_status is None:  # 首次运行
                last_status = current_status
                logging.info(f"初始服务状态: {'运行中' if current_status else '已停止'}")
            else:
                if current_status != last_status:
                    status_text = '已恢复运行' if current_status else '已停止运行'
                    message = f"{now}\n模型服务状态变化：{status_text}"
                    if send_qq_message(GROUP_ID, message):
                        last_status = current_status
                    else:
                        send_admin_alert("消息发送失败，请检查机器人状态")
                        
                # 服务持续停止状态
                if not current_status and last_status == current_status:
                    message = f"{now}\n模型服务仍处于停止状态，请及时处理！"
                    send_qq_message(GROUP_ID, message)
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("监控服务已手动停止")
    except Exception as e:
        logging.error(f"未处理的异常: {str(e)}")
        send_admin_alert(f"监控服务异常终止: {str(e)}") 