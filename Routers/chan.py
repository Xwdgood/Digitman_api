from fastapi import APIRouter, File, UploadFile, Query
from gradio_client import Client, handle_file
import os
import shutil
import paramiko
from typing import Dict
import logging
import requests
from fastapi.responses import JSONResponse
from datetime import datetime
from sse_starlette import EventSourceResponse  # 使用 sse_starlette 库
import asyncio
import pynvml
import time
from fastapi.responses import JSONResponse




# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# 生成随机种子接口
@router.get("/generate-seed")
async def generate_seed():
    try:
        client = Client("http://10.204.10.11:50000/")
        result = client.predict(api_name="/generate_seed")
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

# 在内存中或数据库中保存当前上传的音频文件路径
last_uploaded_audio = "/home/ubuntu/tmpwav/recorded_audio.wav"  # 变量用于保存上次上传的音频文件路径

# 生成语音接口
@router.get("/generate-audio")
async def generate_audio(tts_text: str):

    print("++++++++++++++++++++++++++++++++++++++")
    print("tts_text:", tts_text)

    global last_uploaded_audio  # 确保使用全局变量
    try:
        if not tts_text:
            return JSONResponse(content={"success": False, "error": "没有提供文本"})

        # 检查是否存在最新上传的音频文件
        if not last_uploaded_audio:
            return JSONResponse(content={"success": False, "error": "没有上传音频文件"})

        # 调用 Gradio API 生成音频
        client = Client("http://10.204.10.11:50000/")
        print("调用服务器API")

        print("last_uploaded_audio:", last_uploaded_audio)

        result = client.predict(
            tts_text=tts_text,  # 动态传入文本
            mode_checkbox_group="3s极速复刻",
            sft_dropdown="中文女",
            prompt_text="我正在记录声音模版",
            prompt_wav_upload=handle_file(last_uploaded_audio),  # 使用最新上传的音频文件
            prompt_wav_record=handle_file(last_uploaded_audio),  # 使用最新上传的音频文件
            instruct_text="",
            seed=0,
            stream="false",
            speed=1,
            api_name="/generate_audio"
        )

        if result is None:
            return JSONResponse(content={"success": False, "error": "生成音频失败"})

        return {"success": True, "result": result}

    except Exception as e:
        return JSONResponse(content={"success": False, "error": str(e)})


def upload_file_to_server(local_file_path: str, remote_file_path: str):
    """
    使用 SSH 将文件从本地上传到远程服务器
    """
    try:
        # 设置远程服务器的连接信息
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect('119.255.238.247', username='ubuntu', key_filename='/Users/mac/Desktop/ssh/8card_rsa')

        # 创建 SFTP 会话
        sftp = ssh_client.open_sftp()

        # 检查远程目录是否存在，如果不存在则创建
        remote_dir = os.path.dirname(remote_file_path)
        try:
            sftp.stat(remote_dir)  # 检查远程目录是否存在
            logger.info(f"Directory {remote_dir} exists on the remote server.")
        except FileNotFoundError:
            logger.info(f"Directory {remote_dir} does not exist. Creating it.")
            sftp.mkdir(remote_dir)  # 创建远程目录

        # 上传文件
        logger.info(f"Uploading file {local_file_path} to {remote_file_path}")
        sftp.put(local_file_path, remote_file_path)  # 上传文件

        # 上传后检查文件大小
        remote_size = sftp.stat(remote_file_path).st_size
        logger.info(f"Uploaded file size (remote): {remote_size} bytes")

        sftp.close()
        ssh_client.close()
        logger.info(f"File uploaded to {remote_file_path}")
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise e


@router.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    """
    接收上传的音频文件并将其保存到本地路径 /home/ubuntu/tmpwav
    """
    global last_uploaded_audio  # 确保使用全局变量

    try:
        # 临时保存文件到本地
        local_file_path = f"/tmp/{file.filename}"
        with open(local_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 确认文件大小是否一致
        local_size = os.path.getsize(local_file_path)
        logger.info(f"Uploaded file size (local): {local_size} bytes")

        # 保存文件到目标路径
        target_file_path = f"/home/ubuntu/tmpwav/{file.filename}"
        shutil.move(local_file_path, target_file_path)  # 将文件从临时目录移动到目标目录

        # 更新 last_uploaded_audio 为当前上传的文件路径
        last_uploaded_audio = f"/home/ubuntu/tmpwav/{file.filename}"  # 更新路径
        logger.info(f"Last uploaded audio file path updated: {last_uploaded_audio}")

        # 输出更新后的路径，确保更新成功
        print(f"Updated last_uploaded_audio: {last_uploaded_audio}")

        return {"success": True, "message": f"File uploaded successfully: {file.filename}"}
    except Exception as e:
        logger.error(f"Error during file upload process: {e}")
        return {"success": False, "error": str(e)}
    

@router.post("/call-gradio-api")
async def call_gradio_api(
    audio_name: str = Query(..., description="Audio file name (e.g., generated_audio_20241207_0858.wav)"),
    image_name: str = Query(..., description="Image file name (e.g., generated_audio_20241207_0858.jpg)")
):
    try:
        # 打印接收到的音频和图片文件名
        print(f"Received audio_name: {audio_name}")
        print(f"Received image_name: {image_name}")

        audio_path = f"/tmp/gradio/xwd/{audio_name}"
        image_path = f"/tmp/gradio/xwd/{image_name}"

        # 打印生成的文件路径
        print(f"Audio file path: {audio_path}")
        print(f"Image file path: {image_path}")

        # 第一阶段：发起POST请求，获取event_id
        url = "http://10.204.10.11:7860/gradio_api/call/generate"  # 修改为实际的 Gradio API 地址
        data = {
            "data": [
                {"path": image_path, "meta": {"_type": "gradio.FileData"}},
                {"path": audio_path, "meta": {"_type": "gradio.FileData"}},
                "assets/halfbody_demo/pose/01",  # 填入实际的资源路径
                768,  # 填入宽度
                768,  # 填入高度
                240,  # 填入其他参数
                20,   # 填入其他参数
                16000,  # 填入采样率
                2.5,  # 填入速度或其他设置
                24,   # 填入其他参数
                12,   # 填入其他参数
                3,    # 填入其他参数
                False,  # 是否需要其他布尔参数
                -1    # 填入其他参数，或根据需要传入特定值
            ]
        }

        headers = {"Content-Type": "application/json"}
        print("Sending POST request to Gradio API...")
        response = requests.post(url, json=data, headers=headers)

        # 打印请求的响应状态码和响应内容
        print(f"Gradio API response status code: {response.status_code}")
        print(f"Gradio API response content: {response.text}")

        # 解析返回结果，获取EVENT_ID
        if response.status_code == 200:
            response_data = response.json()
            event_id = response_data.get("event_id")  # 确保Gradio返回正确的event_id
            print(f"Received event_id: {event_id}")

            if event_id:
                # 第二阶段：通过event_id进行查询
                event_url = f"http://10.204.10.11:7860/gradio_api/call/generate/{event_id}"
                print(f"Sending GET request to fetch event results for event_id: {event_id}")
                event_response = requests.get(event_url)

                # 打印事件响应的状态码和内容
                print(f"Event API response status code: {event_response.status_code}")
                print(f"Event API response content: {event_response.text}")

                if event_response.status_code == 200:
                    # 直接返回 Gradio 的结果，不再涉及 GPU 数据
                    return JSONResponse(content={"gradio_data": event_response.json()})
                else:
                    return JSONResponse(content={"success": False, "error": "Failed to retrieve event results"})
            else:
                return JSONResponse(content={"success": False, "error": "Event ID not found"})
        else:
            return JSONResponse(content={"success": False, "error": "Failed to call Gradio API"})

    except Exception as e:
        # 打印异常信息
        print(f"Error occurred: {e}")
        return JSONResponse(content={"success": False, "error": str(e)})




# 文件上传接口
@router.post("/upload-audio-and-image")
async def upload_audio_and_image(image_file: UploadFile = File(...)):
    """
    接收上传的图片文件并保存到指定路径
    """
    try:
        # 设置目标路径
        target_path = "/tmp/gradio/xwd/"
        if not os.path.exists(target_path):
            os.makedirs(target_path)  # 如果目标目录不存在则创建

        # 保存图片文件到指定路径
        image_local_path = os.path.join(target_path, image_file.filename)
        with open(image_local_path, "wb") as image_buffer:
            shutil.copyfileobj(image_file.file, image_buffer)

        return {"success": True, "message": f"图片文件上传成功！文件路径: {image_local_path}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

# 初始化 NVIDIA GPU 管理工具
def init_nvidia_ml():
    try:
        pynvml.nvmlInit()
        return True
    except pynvml.NVMLError as error:
        return False

# 获取 GPU 数据接口
@router.get("/gpu-stats")
async def get_gpu_stats():
    if not init_nvidia_ml():
        return JSONResponse(content={"error": "Failed to initialize NVIDIA ML"}, status_code=500)

    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)  # 获取第一个GPU
        
        # 获取 GPU 信息
        memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
        utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
        temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        power_usage = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0  # 单位转化为千瓦（kW）
        power_limit = pynvml.nvmlDeviceGetEnforcedPowerLimit(handle) / 1000.0  # 单位转化为千瓦（kW）
        
        try:
            fan_speed = pynvml.nvmlDeviceGetFanSpeed(handle)
        except pynvml.NVMLError:
            fan_speed = 0  # 如果无法获取风扇转速，则默认设为0

        # 返回 GPU 状态信息
        return JSONResponse({
            'timestamp': int(time.time() * 1000),  # 时间戳
            'utilization': utilization.gpu,  # GPU 使用率
            'memory_used': memory.used / 1024**2,  # 已使用内存 (MB)
            'memory_total': memory.total / 1024**2,  # 总内存 (MB)
            'temperature': temperature,  # GPU 温度 (C)
            'power_usage': power_usage,  # 功耗 (kW)
            'power_limit': power_limit,  # 功率限制 (kW)
            'fan_speed': fan_speed  # 风扇转速 (rpm)
        })

    except pynvml.NVMLError as error:
        return JSONResponse(content={"error": str(error)}, status_code=500)