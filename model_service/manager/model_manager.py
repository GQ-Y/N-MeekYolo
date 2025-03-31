"""
模型管理器
"""
import os
import shutil
import yaml
import zipfile
from typing import List, Dict, Any
from fastapi import UploadFile, HTTPException
from model_service.models.models import ModelInfo, ModelList
from shared.utils.logger import setup_logger

logger = setup_logger(__name__)

class ModelManager:
    """模型管理器"""
    
    def __init__(self):
        # 使用 model_service 目录下的 store 目录
        self.base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "store")
        self.temp_dir = os.path.join(self.base_dir, "temp")
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        logger.info(f"Model base directory: {self.base_dir}")
    
    def _read_model_info(self, model_dir: str, model_code: str) -> ModelInfo:
        """读取模型信息"""
        try:
            data_file = os.path.join(model_dir, "data.yaml")
            if os.path.exists(data_file):
                with open(data_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    # 从 data.yaml 中提取信息
                    return ModelInfo(
                        name=data.get("name", model_code),  # 直接使用 name 字段
                        code=model_code,
                        version=data.get("version", "1.0.0"),
                        author=data.get("author", ""),
                        description=data.get("description", "")
                    )
            
            # 如果没有 data.yaml 或读取失败，返回基本信息
            return ModelInfo(
                name=model_code,
                code=model_code,
                version="1.0.0"
            )
        except Exception as e:
            logger.warning(f"Failed to read model info from data.yaml: {str(e)}")
            return ModelInfo(
                name=model_code,
                code=model_code,
                version="1.0.0"
            )
    
    def _find_yaml_config(self, files: List[UploadFile]) -> Dict:
        """查找YAML配置文件"""
        for file in files:
            if file.filename.endswith(".yaml") or file.filename.endswith(".yml"):
                try:
                    content = file.file.read().decode("utf-8")
                    data = yaml.safe_load(content)
                    if isinstance(data, dict) and "code" in data:
                        file.file.seek(0)  # 重置文件指针
                        return data
                    file.file.seek(0)  # 重置文件指针
                except Exception as e:
                    logger.warning(f"Failed to parse YAML file {file.filename}: {str(e)}")
                    file.file.seek(0)  # 重置文件指针
        return {}
    
    def _extract_zip(self, zip_file: UploadFile, extract_dir: str) -> List[str]:
        """
        解压ZIP文件
        返回解压后的文件列表
        """
        try:
            # 保存上传的ZIP文件到临时目录
            temp_zip = os.path.join(self.temp_dir, "temp.zip")
            with open(temp_zip, "wb") as f:
                shutil.copyfileobj(zip_file.file, f)
            
            # 解压文件
            with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                # 获取文件列表
                file_list = zip_ref.namelist()
                logger.info(f"Files in zip: {file_list}")
                
                # 解压文件
                zip_ref.extractall(extract_dir)
            
            # 清理临时文件
            os.remove(temp_zip)
            return file_list
            
        except Exception as e:
            if os.path.exists(temp_zip):
                os.remove(temp_zip)
            logger.error(f"Failed to extract zip file: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Failed to extract zip file: {str(e)}")
    
    def _process_extracted_files(self, model_dir: str) -> tuple[bool, bool, Dict]:
        """
        处理解压后的文件
        返回: (has_model_file, has_yaml_file, config_data)
        """
        has_model_file = False
        has_yaml_file = False
        config_data = {}
        pt_file = None
        yaml_file = None
        
        # 遍历目录中的所有文件
        for root, _, files in os.walk(model_dir):
            for file in files:
                file_path = os.path.join(root, file)
                
                if file.endswith(".pt"):
                    pt_file = file_path
                    has_model_file = True
                elif file.endswith((".yaml", ".yml")):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = yaml.safe_load(f)
                            if isinstance(data, dict) and "code" in data:
                                yaml_file = file_path
                                config_data = data
                                has_yaml_file = True
                    except Exception as e:
                        logger.warning(f"Failed to parse YAML file {file}: {str(e)}")
        
        # 清理目录，只保留必要文件
        if has_model_file and has_yaml_file:
            # 创建临时目录
            temp_dir = os.path.join(self.temp_dir, "temp_model")
            os.makedirs(temp_dir, exist_ok=True)
            
            try:
                # 移动必要文件到临时目录
                shutil.copy2(pt_file, os.path.join(temp_dir, "best.pt"))
                shutil.copy2(yaml_file, os.path.join(temp_dir, "data.yaml"))
                
                # 清空原目录
                shutil.rmtree(model_dir)
                os.makedirs(model_dir)
                
                # 移动文件回原目录
                shutil.move(os.path.join(temp_dir, "best.pt"), os.path.join(model_dir, "best.pt"))
                shutil.move(os.path.join(temp_dir, "data.yaml"), os.path.join(model_dir, "data.yaml"))
            finally:
                # 清理临时目录
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
        
        return has_model_file, has_yaml_file, config_data
    
    async def upload_model(self, files: List[UploadFile], model_info: ModelInfo) -> Dict[str, Any]:
        """上传模型文件"""
        model_dir = None
        try:
            # 创建模型目录
            model_dir = os.path.join(self.base_dir, model_info.code)
            if os.path.exists(model_dir):
                shutil.rmtree(model_dir)
            os.makedirs(model_dir)
            
            has_model_file = False
            has_yaml_file = False
            config_data = {}
            
            # 处理文件
            for file in files:
                if file.filename.endswith(".zip"):
                    # 解压ZIP文件
                    self._extract_zip(file, model_dir)
                    # 处理解压后的文件
                    has_model_file, has_yaml_file, config_data = self._process_extracted_files(model_dir)
                else:
                    # 处理单个文件
                    if file.filename.endswith(".pt"):
                        file_path = os.path.join(model_dir, "best.pt")
                        has_model_file = True
                    elif file.filename.endswith((".yaml", ".yml")):
                        file_path = os.path.join(model_dir, "data.yaml")
                        has_yaml_file = True
                        # 读取配置
                        content = file.file.read()
                        data = yaml.safe_load(content.decode("utf-8"))
                        if isinstance(data, dict) and "code" in data:
                            config_data = data
                        file.file.seek(0)
                    else:
                        file_path = os.path.join(model_dir, file.filename)
                    
                    with open(file_path, "wb") as f:
                        shutil.copyfileobj(file.file, f)
            
            # 更新模型信息
            if config_data:
                model_info = ModelInfo(
                    name=config_data.get("names", ["Unknown"])[0],
                    code=model_info.code,  # 保持原有的code
                    version=config_data.get("version", "1.0.0"),
                    author=config_data.get("author", ""),
                    description=config_data.get("description", "")
                )
            
            # 验证必要的文件
            if not has_model_file:
                raise HTTPException(status_code=400, detail="Missing model file (.pt)")
            if not has_yaml_file:
                raise HTTPException(status_code=400, detail="Missing YAML configuration file")
            
            logger.info(f"Model uploaded to {model_dir}")
            return {
                "code": model_info.code,
                "path": model_dir
            }
            
        except HTTPException:
            if model_dir and os.path.exists(model_dir):
                shutil.rmtree(model_dir)
            raise
        except Exception as e:
            if model_dir and os.path.exists(model_dir):
                shutil.rmtree(model_dir)
            logger.error(f"Failed to upload model: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def list_models(self, skip: int = 0, limit: int = 10) -> ModelList:
        """获取模型列表"""
        try:
            models = []
            # 遍历 store 目录
            if os.path.exists(self.base_dir):
                for model_code in os.listdir(self.base_dir):
                    # 跳过临时目录和非目录文件
                    if model_code == "temp" or not os.path.isdir(os.path.join(self.base_dir, model_code)):
                        continue
                    
                    # 检查必要的文件
                    model_dir = os.path.join(self.base_dir, model_code)
                    model_file = os.path.join(model_dir, "best.pt")
                    data_file = os.path.join(model_dir, "data.yaml")
                    
                    if os.path.exists(model_file) and os.path.exists(data_file):
                        # 读取模型信息
                        model_info = self._read_model_info(model_dir, model_code)
                        models.append(model_info)
            
            # 排序和分页
            models.sort(key=lambda x: x.code)
            total = len(models)
            models = models[skip:skip + limit]
            
            logger.info(f"Found {total} models in {self.base_dir}")
            return ModelList(
                total=total,
                items=models,
                page=(skip // limit) + 1,
                size=limit
            )
            
        except Exception as e:
            logger.error(f"Failed to list models: {str(e)}")
            raise
    
    async def get_model_info(self, model_code: str) -> ModelInfo:
        """获取模型信息"""
        try:
            model_dir = os.path.join(self.base_dir, model_code)
            if not os.path.exists(model_dir) or not os.path.isdir(model_dir):
                return None
            
            # 检查必要的文件
            model_file = os.path.join(model_dir, "best.pt")
            data_file = os.path.join(model_dir, "data.yaml")
            
            if not os.path.exists(model_file) or not os.path.exists(data_file):
                return None
            
            # 读取模型信息
            return self._read_model_info(model_dir, model_code)
                
        except Exception as e:
            logger.error(f"Failed to get model info: {str(e)}")
            raise
    
    async def delete_model(self, model_code: str) -> bool:
        """删除模型"""
        try:
            model_dir = os.path.join(self.base_dir, model_code)
            if not os.path.exists(model_dir):
                return False
                
            shutil.rmtree(model_dir)
            logger.info(f"Model {model_code} deleted")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete model: {str(e)}")
            raise
    
    async def load_model(self, model_code: str) -> bool:
        """
        加载模型
        
        参数：
        - model_code: 模型代码
        
        返回：
        - bool: 是否成功加载
        
        异常：
        - HTTPException(404): 模型不存在
        - HTTPException(400): 模型文件不完整
        """
        try:
            model_dir = os.path.join(self.base_dir, model_code)
            if not os.path.exists(model_dir):
                logger.error(f"Model directory not found: {model_dir}")
                raise HTTPException(status_code=404, detail="模型不存在")
            
            # 检查必要的文件
            model_file = os.path.join(model_dir, "best.pt")
            data_file = os.path.join(model_dir, "data.yaml")
            
            if not os.path.exists(model_file) or not os.path.exists(data_file):
                logger.error(f"Missing required files in model directory: {model_dir}")
                raise HTTPException(status_code=400, detail="模型文件不完整")
            
            logger.info(f"Model {model_code} loaded successfully")
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            raise HTTPException(status_code=500, detail=f"加载模型失败: {str(e)}")