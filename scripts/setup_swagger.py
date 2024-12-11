"""
设置Swagger UI
下载并配置Swagger UI文件
"""
import os
import requests
from pathlib import Path

def setup_swagger_ui():
    """下载并设置Swagger UI文件"""
    # Swagger UI文件列表
    files = {
        "swagger-ui-bundle.js": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui-bundle.js",
        "swagger-ui.css": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui.css",
        "swagger-ui-standalone-preset.js": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui-standalone-preset.js",
        "favicon.png": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/favicon-32x32.png"
    }
    
    # 为每个服务创建static目录
    services = ["gateway", "api_service", "analysis_service", "model_service"]
    
    for service in services:
        static_dir = Path(service) / "static"
        static_dir.mkdir(parents=True, exist_ok=True)
        
        # 下载文件
        for filename, url in files.items():
            file_path = static_dir / filename
            if not file_path.exists():
                print(f"Downloading {filename} for {service}...")
                response = requests.get(url)
                with open(file_path, "wb") as f:
                    f.write(response.content)
                print(f"Downloaded {filename}")

if __name__ == "__main__":
    setup_swagger_ui() 