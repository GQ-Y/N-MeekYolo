"""
认证服务层
处理用户注册、登录、令牌管理等业务逻辑
"""
import logging # 导入 logging
import secrets # 用于生成安全令牌
import datetime
import hashlib # 用于哈希重置令牌
from datetime import timedelta # 用于设置过期时间
from sqlalchemy.orm import Session
from core.database import get_db # 虽然服务层通常不直接依赖 get_db，但暂时保留
from core.auth import Auth # 依赖核心认证工具
from core.models.user import User # 修改导入路径
from core.exceptions import UserExistsException, InvalidCredentialsException, GatewayException, NotFoundException, InvalidTokenException # 添加 NotFoundException, InvalidTokenException
from core.schemas import TokenResponse # 用于 authenticate_user 返回类型
from typing import Optional

logger = logging.getLogger(__name__) # 获取 logger

class AuthService:
    def __init__(self, db: Session):
        self.db = db
        logger.debug("AuthService initialized") # 添加初始化日志

    def register_user(self, username: str, password: str, email: Optional[str] = None, nickname: Optional[str] = None) -> User:
        """
        处理用户注册逻辑
        :param username: 用户名
        :param password: 密码
        :param email: 邮箱 (可选)
        :param nickname: 昵称 (可选)
        :return: 创建成功的 User 对象
        :raises UserExistsException: 如果用户已存在
        :raises GatewayException: 如果发生其他错误
        """
        logger.info(f"尝试注册用户: {username}")
        # 检查用户是否已存在 (这部分逻辑在 core.auth.Auth.register_user 内部处理)
        # existing_user = self.db.query(User).filter(User.username == username).first()
        # if existing_user:
        #     raise UserExistsException(f"用户名 '{username}' 已被注册")
            
        try:
            # 调用核心 Auth 类处理实际的密码哈希和数据库插入
            new_user = Auth.register_user(
                db=self.db, 
                username=username, 
                password=password,
                email=email, # 传递 email
                nickname=nickname # 传递 nickname
            )
            logger.info(f"用户 {username} (ID: {new_user.id}) 注册成功")
            return new_user
        except UserExistsException as e: # 从 core.auth 透传异常
             logger.warning(f"注册失败，用户已存在: {username}")
             raise e
        except Exception as e:
            # 在服务层记录具体错误日志会更好
            logger.error(f"注册用户 {username} 时发生意外错误: {e}", exc_info=True) # 替换注释
            raise GatewayException(message=f"注册过程中发生错误: {e}", code=500)

    def authenticate_user(self, username: str, password: str) -> dict:
        """
        处理用户认证逻辑并生成令牌
        :param username: 用户名
        :param password: 密码
        :return: 包含 token 和 user_info 的字典
        :raises InvalidCredentialsException: 如果认证失败
        :raises GatewayException: 如果发生其他错误
        """
        logger.info(f"尝试认证用户: {username}")
        try:
            # 调用核心 Auth 类处理密码验证和令牌生成
            auth_result = Auth.authenticate_user(
                db=self.db,
                username=username,
                password=password
            )
            # auth_result 应该是一个包含 token_response 和 user_info 的字典
            # 例如: 
            # {
            #    "token": TokenResponse(...).dict(), 
            #    "user": {"id": user.id, "username": user.username, ...}
            # }
            logger.info(f"用户 {username} (ID: {auth_result['user_info']['id']}) 认证成功")
            return auth_result # 直接返回 Auth.authenticate_user 的结果
        except InvalidCredentialsException as e: # 从 core.auth 透传异常
            logger.warning(f"认证失败，凭证无效: {username}")
            raise e
        except Exception as e:
            logger.error(f"认证用户 {username} 时发生意外错误: {e}", exc_info=True) # 替换注释
            raise GatewayException(message=f"认证过程中发生错误: {e}", code=500)

    def request_password_reset(self, email: str) -> bool:
        """
        用户请求密码重置。
        生成重置令牌，更新用户信息，并模拟发送邮件。
        
        :param email: 用户邮箱
        :return: bool 指示操作是否（看起来）成功。即使找不到用户也返回 True 以防止邮箱探测。
        :raises GatewayException: 如果发生内部错误
        """
        logger.info(f"收到邮箱 {email} 的密码重置请求")
        user = self.db.query(User).filter(User.email == email).first()

        if not user:
            logger.warning(f"密码重置请求失败：未找到邮箱 {email} 对应的用户。为防止探测，仍返回成功。")
            # 出于安全考虑，不告知请求者邮箱是否存在
            return True
            
        # 检查用户状态，例如非活动或暂停用户可能不允许重置
        if user.status != 0: # 0: active
            logger.warning(f"密码重置请求失败：用户 {user.id} (邮箱: {email}) 状态非活动 ({user.status})。")
            return True # 同样返回 True

        try:
            # 生成安全的随机令牌 (URL 安全)
            reset_token = secrets.token_urlsafe(32)
            # 存储令牌的哈希值到数据库，而不是原始令牌
            token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
            # 设置令牌过期时间 (例如，1小时后)
            expiry_time = datetime.datetime.utcnow() + timedelta(hours=1)

            user.reset_password_token = token_hash
            user.reset_password_token_expiry = expiry_time
            
            self.db.commit()
            logger.info(f"已为用户 {user.id} (邮箱: {email}) 生成密码重置令牌哈希并设置过期时间")

            # --- 模拟发送邮件 --- 
            # 在实际应用中，这里应该调用邮件服务发送包含 reset_token 的链接
            reset_url = f"https://your-frontend-app.com/reset-password?token={reset_token}" # 前端重置页面的 URL
            logger.info(f"(模拟邮件发送) 请访问以下链接重置密码 (令牌: {reset_token}): {reset_url}")
            # mail_service.send_password_reset_email(user.email, reset_url)
            # -------------------

            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"为邮箱 {email} 处理密码重置请求时出错: {e}", exc_info=True)
            # 不能向上层泄露具体错误，但需要记录
            # 这里不抛出 GatewayException，因为可能不想让用户知道后台出错了
            # 返回 True 看起来像是成功了，但后台记录了错误
            return True # 或者根据策略决定是否抛出 GatewayException

    def reset_password(self, token: str, new_password: str) -> bool:
        """
        根据有效的重置令牌设置新密码。
        
        :param token: 用户收到的原始重置令牌
        :param new_password: 用户设置的新密码
        :return: bool 指示密码是否成功重置
        :raises InvalidTokenException: 如果令牌无效或已过期
        :raises GatewayException: 如果发生内部错误
        """
        logger.info(f"尝试使用令牌重置密码") # 不记录令牌本身
        if not token or not new_password:
            logger.warning("重置密码失败：令牌或新密码为空")
            raise InvalidTokenException("无效的请求") # 或 InvalidInputException

        # 计算传入令牌的哈希值以匹配数据库
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        try:
            # --- 查找并验证令牌 --- 
            user = self.db.query(User).filter(User.reset_password_token == token_hash).first()
            
            if not user:
                logger.warning("重置密码失败：令牌无效或已被使用")
                raise InvalidTokenException("密码重置令牌无效或已过期")
            
            # 检查令牌是否过期
            if not user.reset_password_token_expiry or user.reset_password_token_expiry < datetime.datetime.utcnow():
                logger.warning(f"重置密码失败：用户 {user.id} 的令牌已过期 ({user.reset_password_token_expiry})" )
                # 清除过期的令牌信息
                user.reset_password_token = None
                user.reset_password_token_expiry = None
                self.db.commit()
                raise InvalidTokenException("密码重置令牌无效或已过期")
                
            # --- 重置密码并清除令牌 --- 
            user.password = Auth.hash_password(new_password)
            user.reset_password_token = None
            user.reset_password_token_expiry = None
            # updated_at 会自动更新
            
            self.db.commit()
            logger.info(f"用户 {user.id} 密码已成功重置")
            
            # TODO: (可选) 发送密码已重置的确认邮件
            # mail_service.send_password_reset_confirmation(user.email)

            return True

        except InvalidTokenException as e:
            # 令牌无效或过期，直接抛出
            # logger 已在上面记录
            self.db.rollback() # 确保回滚 (如果过期时清除了令牌)
            raise e
        except Exception as e:
            # 修正缩进
            self.db.rollback()
        logger.error(f"使用令牌重置密码时发生意外错误 (用户 ID 可能未知): {e}", exc_info=True)
        raise GatewayException(message="重置密码时发生内部错误", code=500)

# --- 服务依赖注入 ---
# 这种方式允许 FastAPI 自动为每个请求创建 AuthService 实例
# 但通常我们会在路由层使用 Depends(get_db) 然后手动创建服务实例
# 或者使用更高级的依赖注入框架 (如 fastapi-injector)
# def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
#     return AuthService(db=db)
# 在路由中: auth_service: AuthService = Depends(get_auth_service)

# 更常见的做法 (暂时): 在路由中获取 db，然后实例化 Service
# from services.auth_service import AuthService
# @router.post(...)
# async def login(..., db: Session = Depends(get_db)):
#     auth_service = AuthService(db)
#     try:
#         result = auth_service.authenticate_user(...)
#         ...
#     except ...:
#         ... 