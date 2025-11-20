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

