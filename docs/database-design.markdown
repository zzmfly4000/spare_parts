# 数据库设计文档

## 核心表结构

### `spare_parts` 表
存储设备备件的基本信息和库存状态

字段说明：
- `id`: 主键，自增ID
- `part_no`: 备件编号，不能为空
- `name`: 备件名称，不能为空
- `type`: 备件类型
- `current_stock`: 当前库存数量，默认0
- `min_stock`: 最低库存阈值，默认0
- `max_stock`: 最高库存阈值，默认0
- `key_part`: 关键备件标识，默认False
- `lt_weeks`: 交货期(周)，默认0
- `unit_price`: 单价，默认0.0
- `unit`: 单位
- `location`: 库位代码
- `supplier`: 供应商
- `description`: 描述信息
- `created_date`: 创建时间，默认当前时间
- `updated_date`: 更新时间，默认当前时间
- 约束：`part_no` 和 `name` 组合唯一

### `operation_records` 表
记录所有备件操作历史

字段说明：
- `id`: 主键，自增ID
- `operation_type`: 操作类型（如Stock in、Stock out等）
- `operation_date`: 操作时间，默认当前时间
- `supplier_recipient`: 供应商或接收方
- `location`: 库位代码
- `part_no`: 备件编号
- `description`: 备件描述
- `part_type`: 备件类型
- `quantity`: 操作数量
- `work_center`: 工作中心
- `created_date`: 记录创建时间，默认当前时间

### `locations` 表
管理库位信息和状态

字段说明：
- `location_code`: 库位代码，主键
- `description`: 库位描述
- `status`: 库位状态（free、in_use、low_stock等），默认free
- `part_count`: 备件数量，默认0
- `capacity`: 库位容量，默认0
- `last_updated`: 最后更新时间，默认当前时间



### `inbound_records` 和 `outbound_records` 表
字段说明...

## 索引策略

为了提高数据库查询性能，为以下字段创建了索引：

### spare_parts 表索引
- `idx_spare_parts_location`: 库位查询优化
- `idx_spare_parts_type`: 备件类型查询优化
- `idx_spare_parts_stock`: 库存状态查询优化
- `idx_spare_parts_part_no`: 备件编号查询优化

### operation_records 表索引
- `idx_operation_records_date`: 操作时间范围查询优化
- `idx_operation_records_part_no`: 备件操作历史查询优化

### locations 表索引
- `idx_locations_status`: 库位状态查询优化

## 外键约束
保证数据一致性的外键关系...

## 性能优化配置
SQLite的PRAGMA设置参数...

### locations 表操作接口
- `create_location(location_data)`: 创建新库位
- `get_location_by_code(location_code)`: 根据库位代码获取库位信息
- `update_location(location_code, location_data)`: 更新库位信息
- `delete_location(location_code)`: 删除库位
- `get_all_locations()`: 获取所有库位列表
- `update_location_status(location_code, status)`: 更新库位状态

### 库存管理相关接口
- `calculate_stock_from_operations(part_no)`: 根据操作记录计算备件库存
- `update_stock_for_part(part_id, new_stock)`: 更新单个备件的库存数量
- `recalculate_all_stock()`: 重新计算所有备件的库存
- `calculate_stock_status(current_stock, min_stock)`: 计算备件库存状态
- `is_low_stock(part_id)`: 判断备件是否处于低库存状态
- `get_low_stock_parts()`: 获取所有低库存备件列表


