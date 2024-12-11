from typing import Dict
import httpx

async def fetch_service_docs(service_url: str) -> Dict:
    """获取服务的API文档"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{service_url}/openapi.json")
        return response.json()

async def merge_api_docs() -> Dict:
    """合并所有服务的API文档"""
    docs = {}
    services = {
        "api": "http://localhost:8001",
        "model": "http://localhost:8002",
        "analysis": "http://localhost:8003",
        "cloud": "http://localhost:8004"
    }
    
    for service_name, url in services.items():
        try:
            service_docs = await fetch_service_docs(url)
            docs[service_name] = service_docs
        except Exception as e:
            logger.error(f"Failed to fetch docs from {service_name}: {str(e)}")
            
    return docs 