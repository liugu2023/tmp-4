from nekro_agent.api import core, message, timer
from nekro_agent.api.schemas import AgentCtx
import requests
import time

__meta__ = core.ExtMetaData(
    name="model_monitor",
    description="深度学习模型服务监控扩展",
    version="1.0.0",
    author="DeepSeek",
    url="https://github.com/yourusername/model-monitor-extension"
)

# 存储模型状态历史
model_status = {"last_check": 0, "current_status": None, "available": True, "retry_count": 0}

# 定义常量
MONITOR_API = "http://10.21.22.100:30000"  # 状态检查地址
MODEL_API = "http://10.21.22.204:29500"    # 模型推理地址

@core.agent_collector.mount_method(core.MethodType.TOOL)
async def check_model_status(api_url: str, _ctx: AgentCtx) -> dict:
    """检查指定模型API的状态
    Args:
        api_url (str): 需要监控的API地址（HTTP协议）
        
    Returns:
        dict: 包含以下键值的字典：
            - status_code: HTTP状态码
            - latency_ms: 接口延迟(毫秒)
            - is_healthy: 服务健康状态
            - timestamp: 检查时间戳
    """
    global model_status
    
    try:
        start_time = time.time()
        response = requests.get(api_url, timeout=10)
        latency = round((time.time() - start_time) * 1000, 2)  # 毫秒
        is_healthy = response.status_code == 200 and model_status["available"]
        
        # 记录状态变化
        status_changed = model_status["current_status"] != is_healthy
        model_status.update({
            "last_check": int(time.time()),
            "current_status": is_healthy,
            "last_latency": latency,
            "available": is_healthy  # 同步更新可用状态
        })
        
        # 设置下次检查（每5分钟）
        await timer.set_temp_timer(
            _ctx.chat_key,
            int(time.time()) + 300,
            "定时模型状态检查"
        )
        
        # 如果状态变化发送通知
        if status_changed:
            status_msg = "✅ 模型服务恢复" if is_healthy else "❌ 模型服务异常"
            await message.send_text(
                _ctx.chat_key,
                f"{status_msg}\n最新延迟: {latency}ms",
                _ctx
            )
            
        return {
            "status_code": response.status_code,
            "latency_ms": latency,
            "is_healthy": is_healthy,
            "timestamp": model_status["last_check"]
        }
        
    except Exception as e:
        core.logger.error(f"模型状态检查失败: {str(e)}")
        return {
            "error": str(e),
            "is_healthy": False,
            "timestamp": int(time.time())
        }

@core.agent_collector.mount_method(core.MethodType.BEHAVIOR)
async def start_model_monitoring(_ctx: AgentCtx) -> str:
    """启动模型状态监控
    Returns:
        str: 启动结果描述
    """
    # 首次立即检查
    await check_model_status(MONITOR_API, _ctx)
    return f"监控已启动\n• 状态检查: {MONITOR_API}\n• 模型服务: {MODEL_API}"

@core.agent_collector.mount_method(core.MethodType.TOOL)
async def forward_to_model(input_data: str, _ctx: AgentCtx) -> dict:
    """将输入数据转发到模型API
    Args:
        input_data (str): 需要处理的输入数据
        
    Returns:
        dict: 模型响应或错误信息
    """
    global model_status
    
    if not model_status["available"]:
        return {"error": "service_unavailable", "message": "模型服务不可用"}

    try:
        start_time = time.time()
        response = requests.post(
            MODEL_API,
            json={"input": input_data},
            timeout=15
        )
        latency = round((time.time() - start_time) * 1000, 2)
        
        if response.status_code == 200:
            model_status["retry_count"] = 0
            return {
                "status": "success",
                "result": response.json(),
                "latency_ms": latency
            }
        else:
            raise Exception(f"API返回错误状态码: {response.status_code}")
            
    except Exception as e:
        core.logger.error(f"模型请求失败: {str(e)}")
        model_status["retry_count"] += 1
        
        # 连续3次失败标记为不可用
        if model_status["retry_count"] >= 3:
            model_status["available"] = False
            await message.send_text(
                _ctx.chat_key,
                "⚠️ 模型服务已标记为不可用，将停止转发请求",
                _ctx
            )
            
        return {
            "status": "error",
            "message": str(e),
            "retry_count": model_status["retry_count"]
        }

@core.agent_collector.mount_method(core.MethodType.AGENT)
async def handle_model_request(input_data: str, _ctx: AgentCtx) -> str:
    """处理模型请求入口
    Args:
        input_data (str): 用户输入内容
            示例值: "帮我生成一段文本"
        
    Returns:
        str: 当服务不可用时返回提示信息，否则返回空字符串继续后续处理
    """
    if not model_status["available"]:
        return "[系统拦截] 模型服务暂不可用，请稍后再试"
    
    return ""

def clean_up():
    """清理监控状态"""
    global model_status
    model_status = {"last_check": 0, "current_status": None, "available": True, "retry_count": 0} 