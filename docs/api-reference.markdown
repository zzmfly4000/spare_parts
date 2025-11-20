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
