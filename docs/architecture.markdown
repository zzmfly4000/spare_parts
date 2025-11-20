# 系统架构设计文档

## 模块划分说明
- `models`: 数据模型层，负责数据库操作和数据结构定义
- `routes`: 路由控制层，处理HTTP请求和业务逻辑
- `utils`: 工具服务层，提供通用功能和服务
- `templates`: 视图模板层，前端页面展示
- `static`: 静态资源文件

## 核心组件关系
- `DatabaseManager`: 负责数据库连接和操作
- `EmailSender`: 处理邮件报警功能
- `TaskScheduler`: 管理定时任务
- `StockAlertService`: 实现库存预警机制

## 数据流设计
描述系统中数据的流转过程和各模块间的数据交互方式

## 路由控制层
- `routes/parts_routes.py`: 备件管理路由模块，处理备件增删改查相关HTTP请求
- `routes/location_routes.py`: 库位管理路由模块
- `routes/operation_routes.py`: 操作记录路由模块

### 备件管理路由接口
- `GET /parts`: 备件列表页面
- `GET /add_part`: 添加备件页面
- `POST /add_part`: 处理添加备件表单
- `GET /edit_part/<int:part_id>`: 编辑备件页面
- `POST /edit_part/<int:part_id>`: 处理编辑备件表单
- `GET /part/<int:part_id>`: 备件详情页面
- `GET /delete_part/<int:part_id>`: 删除备件

### 库位管理路由接口
- `GET /location_management`: 库位列表页面
- `GET /add_location`: 添加库位页面
- `POST /add_location`: 处理添加库位表单
- `GET /edit_location/<string:location_code>`: 编辑库位页面
- `POST /edit_location/<string:location_code>`: 处理编辑库位表单
- `GET /location_detail/<string:location_code>`: 库位详情页面
- `GET /delete_location/<string:location_code>`: 删除库位

### 操作记录路由接口
- `GET /operation_records`: 操作记录列表页面
- `GET /smart_inbound`: 智能入库页面
- `POST /smart_inbound`: 处理智能入库表单
- `GET /outbound_part/<int:part_id>`: 备件出库页面

### 系统设置路由接口
- `GET /settings`: 系统设置页面
- `POST /settings`: 保存系统设置
- `POST /update_email_settings`: 更新邮件配置
- `POST /update_inventory_settings`: 更新库存设置

### 数据导入导出路由接口
- `GET /import_parts`: 备件信息导入页面
- `POST /import_parts`: 处理备件信息导入
- `GET /import_operations`: 操作记录导入页面
- `POST /import_operations`: 处理操作记录导入
- `GET /export_data`: 数据导出功能

### 低库存报警服务
- `utils/stock_alert.py`: 库存报警服务模块，提供低库存检查和邮件报警功能
- `StockAlertService` 类负责定时检查低库存备件并发送报警邮件

### 数据统计分析服务
- `utils/data_analytics.py`: 数据统计分析模块，提供数据统计和分析功能
- `DataAnalyticsService` 类负责备件使用频率统计、库存变化趋势分析等功能

### 系统监控服务
- `utils/system_monitor.py`: 系统监控模块，提供系统监控和健康检查功能
- `SystemMonitor` 类负责数据库状态检查、系统资源监控等功能

### 用户权限管理服务
- `utils/user_manager.py`: 用户权限管理模块，提供用户认证和权限管理功能
- `UserManager` 类负责用户登录、注销、身份验证和权限控制等功能

### 系统备份服务
- `utils/backup_manager.py`: 系统备份管理模块，提供系统备份和恢复功能
- `BackupManager` 类负责数据库备份、备份文件管理和恢复功能

### API文档服务
- `utils/api_documentation.py`: API文档管理模块，提供API文档生成和管理功能
- `APIDocumentation` 类负责API端点信息注册和文档生成
- `routes/api_test_routes.py`: API测试路由模块，提供交互式API测试界面

### 系统日志服务
- `utils/log_manager.py`: 系统日志管理模块，提供日志记录和管理功能
- `LogManager` 类负责操作日志记录、系统事件日志记录和日志文件管理


### 性能优化服务
- `utils/performance_optimizer.py`: 性能优化模块，提供系统性能监控和优化功能
- `PerformanceOptimizer` 类负责查询性能分析、数据库统计和索引优化建议

### 系统配置管理服务
- `utils/config_manager.py`: 系统配置管理模块，提供配置加载、保存和管理功能
- `ConfigManager` 类负责系统参数配置管理、配置文件读写和配置热更新

### 系统监控告警服务
- `utils/alert_manager.py`: 系统监控告警模块，提供系统监控告警功能
- `AlertManager` 类负责告警规则配置、系统性能阈值监控和告警通知发送

### 数据可视化服务
- `utils/data_visualization.py`: 数据可视化模块，提供数据可视化展示功能
- `DataVisualization` 类负责图表生成和展示、数据报表生成

### 移动端适配服务
- `utils/mobile_adapter.py`: 移动端适配模块，提供移动端适配功能
- `MobileAdapter` 类负责响应式布局适配、设备检测和触摸操作优化

### 多语言支持服务
- `utils/language_manager.py`: 多语言支持模块，提供多语言支持功能
- `LanguageManager` 类负责语言包加载和管理、语言切换和文本国际化


### 帮助文档服务
- `utils/help_documentation.py`: 帮助文档模块，提供系统帮助文档功能
- `HelpDocumentation` 类负责帮助内容管理、在线帮助浏览和搜索功能


### 系统升级服务
- `utils/system_updater.py`: 系统升级模块，提供系统升级和维护功能
- `SystemUpdater` 类负责版本检查和更新、数据库迁移和系统维护

### 系统安全服务
- `utils/security_manager.py`: 系统安全模块，提供系统安全加固功能
- `SecurityManager` 类负责用户身份验证、密码加密存储和安全防护


### 性能监控服务
- `utils/performance_dashboard.py`: 性能监控模块，提供系统性能监控仪表板功能
- `PerformanceDashboard` 类负责实时性能数据收集、可视化图表展示和系统资源监控

### 数据导出服务
- `utils/data_exporter.py`: 数据导出模块，提供数据导出和报表生成功能
- `DataExporter` 类负责多种格式数据导出、自定义报表模板和报表生成

### 系统集成服务
- `utils/system_integration_api.py`: 系统集成模块，提供系统集成API功能
- `SystemIntegrationAPI` 类负责RESTful API接口、第三方系统对接和数据同步

### 用户行为分析服务
- `utils/user_behavior_analyzer.py`: 用户行为分析模块，提供用户行为分析功能
- `UserBehaviorAnalyzer` 类负责用户操作轨迹记录、用户偏好分析和行为统计

### 自动化运维服务
- `utils/auto_ops_manager.py`: 自动化运维模块，提供系统自动化运维功能
- `AutoOpsManager` 类负责定时任务调度、自动化监控和告警、系统自动备份


### 高可用部署服务
- `utils/high_availability_manager.py`: 高可用部署模块，提供系统高可用部署功能
- `HighAvailabilityManager` 类负责负载均衡配置、故障自动切换和多实例部署配置

### 容灾备份服务
- `utils/disaster_recovery_manager.py`: 容灾备份模块，提供系统容灾备份功能
- `DisasterRecoveryManager` 类负责异地备份存储、灾难恢复计划、数据备份加密和压缩
