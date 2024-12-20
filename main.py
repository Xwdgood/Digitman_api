import signal
import sys
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 导入子路由
from Routers.chan import router as chan_router

# 应用实例
app = FastAPI(
    title="DigitHuman-XWD",
    description="Establish new API in server platform",
    version="0.0.2",
    openapi_tags=[
        {
            "name": "chan",
            "description": "API group for Chan module, including seed generation.",
        }
    ],
)

# 配置 CORS 中间件
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加子路由，这里chan_router包含了call-gradio-api的路由
app.include_router(chan_router, prefix="/api", tags=["chan"])

# 静态文件
app.mount("/public", StaticFiles(directory="public"), name="public")

@app.get("/")
async def root():
    """
    根路径，用于测试
    """
    return {"message": "Hello pi"}

def signal_handler(sig, frame):
    """
    信号处理器：捕获 Ctrl+C 等信号，优雅退出程序
    """
    print("\nReceived Ctrl+C, exiting...")
    sys.exit(0)

if __name__ == "__main__":
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 启动 Uvicorn 服务
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # 开发模式可设置为 True
        workers=4,
        use_colors=True,
        timeout_keep_alive=0,
        timeout_graceful_shutdown=3,
        log_level="info",
    )
