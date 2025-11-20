# API接口文档

## 路由映射表
- 备件管理相关路由
- 库位管理相关路由
- 操作记录相关路由
- 系统设置相关路由

## 请求/响应格式
RESTful API的输入输出规范...

## 错误码定义
系统可能返回的错误状态码及含义...

## 数据访问接口

### 备件管理接口
- `get_spare_part_by_id(part_id)`: 根据ID获取备件信息
- `get_spare_part_by_part_no(part_no)`: 根据备件编号获取备件信息
- `create_spare_part(part_data)`: 创建新备件
- `update_spare_part(part_id, part_data)`: 更新备件信息
- `delete_spare_part(part_id)`: 删除备件
- `get_all_spare_parts()`: 获取所有备件列表

### 操作记录接口
- `create_operation_record(operation_data)`: 创建操作记录

### 库存管理接口
- `calculate_stock_from_operations(part_no)`: 根据操作记录计算备件库存
- `update_stock_for_part(part_id, new_stock)`: 更新单个备件的库存数量
- `recalculate_all_stock()`: 重新计算所有备件的库存
- `calculate_stock_status(current_stock, min_stock)`: 计算备件库存状态
- `is_low_stock(part_id)`: 判断备件是否处于低库存状态
- `get_low_stock_parts()`: 获取所有低库存备件列表

### 备件管理路由接口
- `GET /parts`: 备件列表页面，支持搜索和筛选
- `GET /add_part`: 添加备件页面
- `POST /add_part`: 处理添加备件表单
- `GET /edit_part/<int:part_id>`: 编辑备件页面
- `POST /edit_part/<int:part_id>`: 处理编辑备件表单
- `GET /part/<int:part_id>`: 备件详情页面
- `GET /delete_part/<int:part_id>`: 删除备件

### 库位管理路由接口
- `GET /location_management`: 库位列表页面，支持搜索和筛选
- `GET /add_location`: 添加库位页面
- `POST /add_location`: 处理添加库位表单
- `GET /edit_location/<string:location_code>`: 编辑库位页面
- `POST /edit_location/<string:location_code>`: 处理编辑库位表单
- `GET /location_detail/<string:location_code>`: 库位详情页面
- `GET /delete_location/<string:location_code>`: 删除库位

### 操作记录路由接口
- `GET /operation_records`: 操作记录列表页面，支持搜索和筛选
- `GET /smart_inbound`: 智能入库页面
- `POST /smart_inbound`: 处理智能入库表单
- `GET /outbound_part/<int:part_id>`: 备件出库页面

### 系统设置路由接口
- `GET /settings`: 系统设置页面，显示当前配置
- `POST /settings`: 保存系统设置，接收系统基本信息配置
- `POST /update_email_settings`: 更新邮件配置，接收邮件服务器相关设置
- `POST /update_inventory_settings`: 更新库存设置，接收库存阈值相关配置

### 数据导入导出路由接口
- `GET /import_parts`: 备件信息导入页面，提供文件上传表单
- `POST /import_parts`: 处理备件信息导入，接收Excel文件并解析导入数据
- `GET /import_operations`: 操作记录导入页面，提供文件上传表单
- `POST /import_operations`: 处理操作记录导入，接收Excel文件并解析导入数据
- `GET /export_data`: 数据导出功能，返回Excel格式的备件数据

### 库存报警接口
- `StockAlertService.check_low_stock_and_alert()`: 检查低库存并发送报警邮件
- `StockAlertService.get_low_stock_statistics()`: 获取低库存统计信息

### 数据统计分析接口
- `DataAnalyticsService.get_part_usage_statistics(days)`: 获取备件使用频率统计
- `DataAnalyticsService.get_inventory_trend(part_no, days)`: 获取备件库存变化趋势
- `DataAnalyticsService.get_location_usage_statistics()`: 获取库位使用率统计

### 系统监控接口
- `SystemMonitor.check_database_status()`: 检查数据库状态
- `SystemMonitor.get_system_info()`: 获取系统信息
- `SystemMonitor.get_resource_usage()`: 获取系统资源使用情况
- `SystemMonitor.get_health_status()`: 获取系统健康状态

### 用户权限管理接口
- `UserManager.authenticate_user(username, password)`: 用户身份验证
- `UserManager.logout_user()`: 用户注销
- `UserManager.is_logged_in()`: 检查用户是否已登录
- `UserManager.check_permission(required_role)`: 检查用户权限

### 系统备份接口
- `BackupManager.backup_database()`: 执行数据库备份
- `BackupManager.list_backups()`: 列出所有备份文件

### API文档管理接口
- `APIDocumentation.register_endpoint(endpoint, method, description, parameters, response_example)`: 注册API端点信息
- `APIDocumentation.generate_api_docs()`: 生成API文档
- `APIDocumentation.get_endpoint_info(endpoint)`: 获取特定端点的信息

### API测试接口
- `GET /api/docs`: API文档页面，展示所有API接口说明
- `POST /api/test`: 测试API端点，接收端点信息和参数并返回测试结果

### 系统日志管理接口
- `LogManager.log_operation(user, operation, details)`: 记录操作日志
- `LogManager.log_system_event(event, level, details)`: 记录系统事件日志
- `LogManager.get_log_entries(level, limit)`: 获取日志条目

### 性能优化接口
- `PerformanceOptimizer.analyze_query_performance(query, params)`: 分析查询性能
- `PerformanceOptimizer.get_database_stats()`: 获取数据库统计信息
- `PerformanceOptimizer.suggest_indexes()`: 建议数据库索引优化

### 系统配置管理接口
- `ConfigManager.load_config()`: 加载配置文件
- `ConfigManager.save_config()`: 保存配置文件
- `ConfigManager.get_config(key_path, default)`: 获取配置项值
- `ConfigManager.set_config(key_path, value)`: 设置配置项值

### 系统监控告警接口
- `AlertManager.check_system_alerts()`: 检查系统告警
- `AlertManager._send_alert_notifications(alerts)`: 发送告警通知

### 数据可视化接口
- `DataVisualization.generate_inventory_trend_chart(part_no, days)`: 生成备件库存趋势图表
- `DataVisualization.generate_location_usage_chart()`: 生成库位使用率可视化图表

### 移动端适配接口
- `MobileAdapter.is_mobile_device(user_agent)`: 检测是否为移动设备
- `MobileAdapter.get_device_type(screen_width)`: 根据屏幕宽度判断设备类型
- `MobileAdapter.generate_responsive_css()`: 生成响应式CSS样式

### 多语言支持接口
- `LanguageManager.set_language(language_code)`: 设置当前语言
- `LanguageManager.get_text(key_path, language_code)`: 获取指定语言的文本
- `LanguageManager._load_language_packs()`: 加载语言包

### 帮助文档接口
- `HelpDocumentation.get_help_document(doc_name)`: 获取帮助文档内容
- `HelpDocumentation.search_help_content(keyword)`: 搜索帮助内容
- `HelpDocumentation._load_help_contents()`: 加载帮助文档内容

### 系统升级接口
- `SystemUpdater.check_for_updates()`: 检查系统更新
- `SystemUpdater.perform_backup()`: 执行系统备份
- `SystemUpdater._compare_versions(version1, version2)`: 比较版本号

### 系统安全接口
- `SecurityManager.hash_password(password)`: 密码哈希处理
- `SecurityManager.verify_password(password, hashed_password)`: 验证密码
- `SecurityManager.check_password_strength(password)`: 检查密码强度
- `SecurityManager.generate_secure_token()`: 生成安全令牌


### 性能监控接口
- `PerformanceDashboard.collect_system_metrics()`: 收集系统性能指标
- `PerformanceDashboard.get_database_metrics()`: 获取数据库性能指标

### 数据导出接口
- `DataExporter.export_parts_to_excel()`: 导出备件信息到Excel
- `DataExporter.export_operations_to_csv(start_date, end_date)`: 导出操作记录到CSV
