"""
市场服务
"""
import httpx
import os
import zipfile
import shutil
from sqlalchemy.orm import Session
from fastapi import HTTPException
from model_service.core.config import settings
from model_service.services.key import KeyService
from shared.utils.logger import setup_logger
import json
from model_service.manager.model_manager import ModelManager

logger = setup_logger(__name__)

class MarketService:
    """市场服务"""
    
    def __init__(self):
        self.key_service = KeyService()
        self.base_url = settings.CLOUD.url
        self.api_prefix = settings.CLOUD.api_prefix
        self.model_manager = ModelManager()
    
    def _get_api_url(self, path: str) -> str:
        """获取完整的API URL"""
        return f"{self.base_url}{self.api_prefix}{path}"
    
    async def get_models(self, db: Session, skip: int = 0, limit: int = 10):
        """
        获取云市场模型列表
        
        参数：
        - db: 数据库会话
        - skip: 跳过的记录数
        - limit: 返回的记录数
        
        返回：
        - 模型列表
        
        异常：
        - HTTPException(401): 无效的访问凭证
        - HTTPException(403): 没有权限执行此操作
        - HTTPException(503): 云服务暂时不可用
        """
        try:
            # 获取API密钥
            key = await self.key_service.get_key(db)
            if not key:
                raise HTTPException(
                    status_code=401,
                    detail="未找到有效的API密钥"
                )
            if not key.status:
                raise HTTPException(
                    status_code=403,
                    detail="API密钥已失效"
                )
            
            # 调用云市场API
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        self._get_api_url("/models"),
                        params={"skip": skip, "limit": limit},
                        headers={"x-api-key": key.key},
                        timeout=30.0  # 设置超时时间
                    )
                    response.raise_for_status()
                    result = response.json()
                    # 只返回data字段
                    return result.get("data", {})
            except httpx.TimeoutException:
                logger.error("云服务请求超时")
                raise HTTPException(
                    status_code=503,
                    detail="云服务请求超时，请稍后重试"
                )
            except httpx.RequestError as e:
                logger.error(f"云服务请求失败: {str(e)}")
                raise HTTPException(
                    status_code=503,
                    detail="云服务暂时不可用，请稍后重试"
                )
            except httpx.HTTPStatusError as e:
                logger.error(f"云服务返回错误: {str(e)}")
                if e.response.status_code == 401:
                    raise HTTPException(
                        status_code=401,
                        detail="无效的访问凭证"
                    )
                elif e.response.status_code == 403:
                    raise HTTPException(
                        status_code=403,
                        detail="没有权限执行此操作"
                    )
                elif e.response.status_code == 404:
                    raise HTTPException(
                        status_code=404,
                        detail="请求的资源不存在"
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                        detail="云服务内部错误"
                    )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取模型列表失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="获取模型列表失败"
            )
    
    async def sync_models(self, db: Session):
        """
        同步云市场模型
        
        参数：
        - db: 数据库会话
        
        返回：
        - 同步结果
        
        异常：
        - HTTPException(401): 无效的访问凭证
        - HTTPException(403): 没有权限执行此操作
        - HTTPException(503): 云服务暂时不可用
        """
        try:
            # 获取API密钥
            key = await self.key_service.get_key(db)
            if not key:
                raise HTTPException(
                    status_code=401,
                    detail="未找到有效的API密钥"
                )
            if not key.status:
                raise HTTPException(
                    status_code=403,
                    detail="API密钥已失效"
                )
            
            # 调用云市场API
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        self._get_api_url("/models/available"),
                        headers={"x-api-key": key.key},
                        timeout=30.0  # 设置超时时间
                    )
                    response.raise_for_status()
                    result = response.json()
                    logger.info("成功从云市场同步模型")
                    # 只返回data字段
                    return result.get("data", {})
            except httpx.TimeoutException:
                logger.error("云服务请求超时")
                raise HTTPException(
                    status_code=503,
                    detail="云服务请求超时，请稍后重试"
                )
            except httpx.RequestError as e:
                logger.error(f"云服务请求失败: {str(e)}")
                raise HTTPException(
                    status_code=503,
                    detail="云服务暂时不可用，请稍后重试"
                )
            except httpx.HTTPStatusError as e:
                logger.error(f"云服务返回错误: {str(e)}")
                if e.response.status_code == 401:
                    raise HTTPException(
                        status_code=401,
                        detail="无效的访问凭证"
                    )
                elif e.response.status_code == 403:
                    raise HTTPException(
                        status_code=403,
                        detail="没有权限执行此操作"
                    )
                elif e.response.status_code == 404:
                    raise HTTPException(
                        status_code=404,
                        detail="请求的资源不存在"
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                        detail="云服务内部错误"
                    )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"同步模型失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="同步模型失败"
            )
    
    async def sync_model(self, db: Session, code: str):
        """
        同步指定的模型
        
        参数：
        - db: 数据库会话
        - code: 模型代码
        
        返回：
        - 同步结果
        
        异常：
        - HTTPException(401): 无效的访问凭证
        - HTTPException(403): 没有权限执行此操作
        - HTTPException(404): 模型不存在
        - HTTPException(503): 云服务暂时不可用
        """
        zip_path = None
        model_dir = None
        try:
            logger.info("==================== 开始同步模型 ====================")
            logger.info(f"同步模型代码: {code}")
            
            # 获取API密钥
            key = await self.key_service.get_key(db)
            if not key:
                logger.error("未找到有效的API密钥")
                raise HTTPException(
                    status_code=401,
                    detail="未找到有效的API密钥"
                )
            if not key.status:
                logger.error("API密钥已失效")
                raise HTTPException(
                    status_code=403,
                    detail="API密钥已失效"
                )
            
            logger.info("API密钥验证通过")
            
            # 调用云市场API获取下载URL
            try:
                url = self._get_api_url("/models/sync")
                params = {"code": code}
                headers = {
                    "x-api-key": key.key,
                    "accept": "application/json",
                    "Content-Type": "application/json"
                }
                
                logger.info("准备调用云服务同步API:")
                logger.info(f"请求URL: {url}")
                logger.info(f"请求参数: {params}")
                logger.info(f"请求头: {headers}")
                
                async with httpx.AsyncClient() as client:
                    # 1. 调用同步API获取下载URL
                    logger.info("发送同步请求...")
                    response = await client.post(
                        url,
                        params=params,
                        headers=headers,
                        timeout=30.0
                    )
                    
                    # 记录响应状态和内容
                    logger.info(f"云服务同步API响应状态码: {response.status_code}")
                    logger.info(f"云服务同步API响应头: {dict(response.headers)}")
                    
                    try:
                        response_json = response.json()
                        logger.info(f"云服务同步API响应内容: {json.dumps(response_json, ensure_ascii=False, indent=2)}")
                    except Exception as e:
                        logger.error(f"解析响应JSON失败: {str(e)}")
                        logger.info(f"原始响应内容: {response.text}")
                        raise HTTPException(status_code=500, detail="解析云服务响应失败")
                    
                    response.raise_for_status()
                    
                    # 2. 从响应中获取下载URL
                    if not response_json.get("success"):
                        logger.error(f"同步模型失败: 云服务返回失败状态, 响应: {json.dumps(response_json, ensure_ascii=False)}")
                        raise HTTPException(
                            status_code=400,
                            detail=response_json.get("message", "云服务同步失败")
                        )
                    
                    download_url = response_json.get("data", {}).get("download_url")
                    if not download_url:
                        logger.error(f"同步模型失败: 未获取到下载地址, 响应: {json.dumps(response_json, ensure_ascii=False)}")
                        raise HTTPException(
                            status_code=400,
                            detail="未获取到模型下载地址"
                        )
                    
                    logger.info(f"获取到模型下载URL: {download_url}")
                    
                    # 3. 使用下载URL获取模型文件
                    logger.info("开始下载模型文件...")
                    download_response = await client.get(
                        download_url,
                        headers=headers,  # 添加API密钥到下载请求
                        timeout=60.0
                    )
                    
                    logger.info(f"模型文件下载响应状态码: {download_response.status_code}")
                    logger.info(f"模型文件下载响应头: {dict(download_response.headers)}")
                    
                    download_response.raise_for_status()
                    
                    # 4. 保存模型文件
                    zip_path = os.path.join(self.model_manager.base_dir, f"{code}.zip")
                    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
                    
                    with open(zip_path, "wb") as f:
                        f.write(download_response.content)
                    
                    logger.info(f"模型文件已保存到: {zip_path}")
                    
                    # 5. 解压模型文件
                    model_dir = os.path.join(self.model_manager.base_dir, code)
                    if os.path.exists(model_dir):
                        logger.info(f"删除已存在的模型目录: {model_dir}")
                        shutil.rmtree(model_dir)
                    
                    os.makedirs(model_dir)
                    logger.info(f"创建模型目录: {model_dir}")
                    
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(model_dir)
                    logger.info(f"模型文件已解压到: {model_dir}")
                    
                    # 6. 加载模型
                    logger.info("开始加载模型...")
                    await self.model_manager.load_model(code)
                    logger.info(f"模型 {code} 已成功加载")
                    
                    result = {
                        "code": code,
                        "status": "success",
                        "message": "模型同步成功"
                    }
                    logger.info(f"同步完成，结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
                    logger.info("==================== 模型同步完成 ====================")
                    
                    return result
                    
            except httpx.TimeoutException:
                logger.error("云服务请求超时")
                raise HTTPException(
                    status_code=503,
                    detail="云服务请求超时，请稍后重试"
                )
            except httpx.RequestError as e:
                logger.error(f"云服务请求失败: {str(e)}")
                raise HTTPException(
                    status_code=503,
                    detail="云服务暂时不可用，请稍后重试"
                )
            except httpx.HTTPStatusError as e:
                logger.error(f"云服务返回错误: {str(e)}")
                try:
                    error_json = e.response.json()
                    logger.error(f"错误响应内容: {json.dumps(error_json, ensure_ascii=False, indent=2)}")
                except:
                    logger.error(f"原始错误响应: {e.response.text}")
                
                if e.response.status_code == 401:
                    raise HTTPException(
                        status_code=401,
                        detail="无效的访问凭证"
                    )
                elif e.response.status_code == 403:
                    raise HTTPException(
                        status_code=403,
                        detail="没有权限执行此操作"
                    )
                elif e.response.status_code == 404:
                    raise HTTPException(
                        status_code=404,
                        detail="模型不存在"
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                        detail="云服务内部错误"
                    )
                
        except HTTPException:
            # 清理临时文件
            if zip_path and os.path.exists(zip_path):
                os.remove(zip_path)
            if model_dir and os.path.exists(model_dir):
                shutil.rmtree(model_dir)
            logger.info("==================== 模型同步失败 ====================")
            raise
        except Exception as e:
            # 清理临时文件
            if zip_path and os.path.exists(zip_path):
                os.remove(zip_path)
            if model_dir and os.path.exists(model_dir):
                shutil.rmtree(model_dir)
            logger.error(f"同步模型失败: {str(e)}")
            logger.info("==================== 模型同步异常 ====================")
            raise HTTPException(
                status_code=500,
                detail=f"同步模型失败: {str(e)}"
            )
        finally:
            # 清理 ZIP 文件
            if zip_path and os.path.exists(zip_path):
                os.remove(zip_path)
                logger.info(f"清理临时文件: {zip_path}") 