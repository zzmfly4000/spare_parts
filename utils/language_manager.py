import json
import os
from typing import Dict, Any

class LanguageManager:
    """多语言管理服务，负责多语言支持功能"""
    
    def __init__(self, default_language='zh'):
        self.default_language = default_language
        self.current_language = default_language
        self.language_packs = {}
        self._load_language_packs()
    
    def _load_language_packs(self):
        """加载语言包"""
        # 定义语言包路径
        lang_dir = 'languages'
        if not os.path.exists(lang_dir):
            os.makedirs(lang_dir)
            # 创建默认中文语言包
            self._create_default_language_pack()
        
        # 加载所有语言包
        for filename in os.listdir(lang_dir):
            if filename.endswith('.json'):
                lang_code = filename[:-5]  # 移除.json后缀
                with open(os.path.join(lang_dir, filename), 'r', encoding='utf-8') as f:
                    self.language_packs[lang_code] = json.load(f)
    
    def _create_default_language_pack(self):
        """创建默认语言包"""
        default_pack = {
            "system": {
                "title": "设备备件管理系统",
                "welcome": "欢迎使用设备备件管理系统"
            },
            "navigation": {
                "home": "首页",
                "parts": "备件管理",
                "locations": "库位管理",
                "operations": "操作记录",
                "reports": "报表分析",
                "settings": "系统设置"
            },
            "common": {
                "save": "保存",
                "cancel": "取消",
                "delete": "删除",
                "edit": "编辑",
                "add": "添加",
                "search": "搜索"
            }
        }
        
        # 保存中文语言包
        with open('languages/zh.json', 'w', encoding='utf-8') as f:
            json.dump(default_pack, f, ensure_ascii=False, indent=2)
        
        # 创建英文语言包模板
        english_pack = {
            "system": {
                "title": "Equipment Spare Parts Management System",
                "welcome": "Welcome to Equipment Spare Parts Management System"
            },
            "navigation": {
                "home": "Home",
                "parts": "Parts Management",
                "locations": "Location Management",
                "operations": "Operation Records",
                "reports": "Reports & Analysis",
                "settings": "System Settings"
            },
            "common": {
                "save": "Save",
                "cancel": "Cancel",
                "delete": "Delete",
                "edit": "Edit",
                "add": "Add",
                "search": "Search"
            }
        }
        
        # 保存英文语言包
        with open('languages/en.json', 'w', encoding='utf-8') as f:
            json.dump(english_pack, f, ensure_ascii=False, indent=2)
    
    def set_language(self, language_code: str):
        """设置当前语言"""
        if language_code in self.language_packs:
            self.current_language = language_code
            return True
        return False
    
    def get_text(self, key_path: str, language_code: str = None) -> str:
        """获取指定语言的文本"""
        if language_code is None:
            language_code = self.current_language
        
        # 如果指定语言不存在，使用默认语言
        if language_code not in self.language_packs:
            language_code = self.default_language
        
        # 解析键路径
        keys = key_path.split('.')
        text_data = self.language_packs.get(language_code, {})
        
        # 逐级获取文本
        try:
            for key in keys:
                text_data = text_data[key]
            return text_data
        except (KeyError, TypeError):
            # 如果找不到对应文本，返回键路径作为默认值
            return key_path
