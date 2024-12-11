from shared.models.base import ServiceInfo
from datetime import datetime

async def test_register_api_service():
    """测试手动注册API服务"""
    service_info = ServiceInfo(
        name="api",
        url="http://localhost:8001",
        description="API服务",
        version="1.0.0",
        status="healthy",
        started_at=datetime.now()
    )
    
    success = await service_registry.register_service(service_info)
    assert success, "Failed to register API service" 