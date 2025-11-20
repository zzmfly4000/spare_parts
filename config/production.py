class ProductionConfig:
    """生产环境配置"""
    DEBUG = False
    TESTING = False
    DATABASE_URL = 'sqlite:///spare_parts_prod.db'
    SECRET_KEY = 'your-production-secret-key'
    LOG_LEVEL = 'INFO'
