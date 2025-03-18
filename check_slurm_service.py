#!/usr/bin/env python3
import subprocess
import requests
import flask
import os
import json
from flask import Flask, jsonify, request
from flask_restx import Api, Resource, fields

# 模型服务地址配置
MODEL_SERVICE_URL = "http://10.21.22.204:29500/v1"  # 实际的API地址

# API密钥配置
API_KEY = "sk-no-key-required"  # 已更新为提供的API密钥

app = Flask(__name__)
api = Api(app, version='1.0', title='AI群聊机器人服务',
    description='检查模型服务状态并处理群聊消息',
    doc='/api/docs'
)

ns = api.namespace('api', description='群聊机器人操作')

# 定义输入消息模型
message_model = api.model('ChatMessage', {
    'user_id': fields.String(description='用户ID或名称', required=True),
    'message': fields.String(description='用户发送的消息', required=True),
    'group_id': fields.String(description='群组ID', required=True),
    'is_at_bot': fields.Boolean(description='是否@机器人', default=True)
})

@ns.route('/check-service')
class CheckService(Resource):
    @api.doc(
        responses={
            200: "成功执行检查",
        },
        description="检查SLURM队列中是否存在名为QwQ-serv的任务"
    )
    def get(self):
        """检查QwQ-serv是否正在运行"""
        is_running = check_qwq_service()
        return jsonify({"running": is_running})

@ns.route('/chat')
class ChatBot(Resource):
    @api.expect(message_model)
    @api.doc(
        responses={
            200: "成功处理群聊消息",
            400: "无效的请求数据",
            503: "模型服务不可用"
        },
        description="处理群聊消息并返回AI回复"
    )
    def post(self):
        """处理群聊消息并返回AI回复"""
        # 首先检查模型服务是否在运行
        if not check_qwq_service():
            return jsonify({"error": "模型服务当前不可用"}), 503
            
        # 获取请求数据
        input_data = request.get_json()
        if not input_data:
            return jsonify({"error": "未提供输入数据"}), 400
            
        # 验证消息内容不为空
        if not input_data.get('message', '').strip():
            return jsonify({"error": "消息内容不能为空", "success": False}), 400
            
        try:
            # 准备发送给模型的数据
            chat_data = prepare_chat_data(input_data)
            
            # 转发请求到模型服务
            response = forward_to_model(chat_data)
            
            # 提取回复内容 - 添加更多安全检查
            if 'choices' in response and len(response['choices']) > 0:
                try:
                    message = response['choices'][0].get('message', {})
                    if not message:
                        raise ValueError("响应中缺少message字段")
                        
                    message_content = message.get('content', '')
                    if not message_content:
                        raise ValueError("响应中缺少content字段")
                        
                    # 移除<think>标签内容（如果存在）
                    if '<think>' in message_content and '</think>' in message_content:
                        parts = message_content.split('</think>')
                        if len(parts) > 1:
                            message_content = parts[1].strip()
                    
                    return jsonify({
                        "response": message_content,
                        "success": True
                    })
                except Exception as e:
                    print(f"解析模型响应时出错: {str(e)}")
                    print(f"原始响应: {json.dumps(response, ensure_ascii=False)}")
                    return jsonify({
                        "error": "解析模型响应时出错",
                        "success": False
                    }), 500
            else:
                return jsonify({
                    "error": "模型未返回有效回复",
                    "success": False
                }), 500
                
        except Exception as e:
            return jsonify({
                "error": f"处理消息时出错: {str(e)}",
                "success": False
            }), 500

@ns.route('/chat/chat/completions')
class ChatCompletions(Resource):
    @api.expect(message_model)
    @api.doc(
        responses={
            200: "成功处理请求",
            400: "无效的请求数据",
            503: "模型服务不可用"
        },
        description="处理聊天完成请求 - 兼容旧路径"
    )
    def post(self):
        """与/chat端点相同功能（兼容旧路径）"""
        # 复用ChatBot的post方法逻辑
        return ChatBot().post()

def check_qwq_service():
    """
    检查SLURM队列中是否有名为QwQ-serv的任务
    """
    try:
        # 使用grep直接过滤结果
        result = subprocess.run(
            "squeue | grep 'QwQ-serv'", 
            shell=True,
            capture_output=True, 
            text=True
        )
        
        # 如果grep找到内容，返回码为0
        is_running = result.returncode == 0
        
        # 打印状态，方便调试
        print(f"QwQ-serv服务状态: {'运行中' if is_running else '未运行'}")
        
        return is_running
    except Exception as e:
        print(f"检查服务状态时出错: {str(e)}")
        return False

def prepare_chat_data(input_data):
    """
    将群聊消息转换为适合OpenAI API的格式
    
    参数:
        input_data: 包含用户消息的原始数据
        
    返回:
        适合OpenAI API的请求数据
    """
    user_id = input_data.get('user_id', '用户')
    message = input_data.get('message', '')
    group_id = input_data.get('group_id', 'default_group')
    
    # 构建聊天请求
    chat_data = {
        "model": "qwen",  # 使用模型名称，根据实际情况调整
        "messages": [
            {"role": "system", "content": "你是一个友好的群聊助手，请简洁清晰地回答问题。"},
            {"role": "user", "content": f"{user_id}说: {message}"}
        ],
        "temperature": 0.7,
        "max_tokens": 800
    }
    
    return chat_data

def forward_to_model(input_data):
    """
    将输入数据转发到模型服务进行推理
    
    参数:
        input_data: 要发送给模型的输入数据
        
    返回:
        模型服务的响应数据
    """
    try:
        # 确定API端点
        endpoint = '/chat/completions'
        
        # 准备headers，添加Authorization
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        
        # 打印发送的请求数据用于调试
        print(f"发送请求到模型: {json.dumps(input_data, ensure_ascii=False)}")
        
        # 发送请求到模型服务
        response = requests.post(
            f"{MODEL_SERVICE_URL}{endpoint}",
            headers=headers,
            json=input_data,
            timeout=60
        )
        
        # 检查响应状态
        response.raise_for_status()
        
        # 返回模型响应
        result = response.json()
        print(f"模型响应: {json.dumps(result, ensure_ascii=False)}")
        return result
        
    except requests.RequestException as e:
        print(f"转发到模型服务时出错: {str(e)}")
        raise Exception(f"模型服务通信错误: {str(e)}")

if __name__ == '__main__':
    # 显示已配置信息
    print(f"API服务已配置：")
    print(f"- 模型服务地址: {MODEL_SERVICE_URL}")
    print(f"- API密钥: {API_KEY}")
    print(f"- 监听端口: 25000")
    
    # 启动Flask应用
    app.run(host='0.0.0.0', port=25000) 