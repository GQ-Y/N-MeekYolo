from fastapi import FastAPI, Request
import uvicorn
import json

app = FastAPI()

@app.post("/")
async def callback(request: Request):
    """处理回调请求"""
    try:
        data = await request.json()
        print("\n收到回调:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return {"status": "success"}
    except Exception as e:
        print(f"处理回调失败: {str(e)}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    print("\n回调测试服务器启动中...")
    print("监听地址: http://localhost:8081")
    print("等待接收回调...\n")
    uvicorn.run(app, host="0.0.0.0", port=8081) 