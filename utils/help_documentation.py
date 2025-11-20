import os
import json
from typing import Dict, List

class HelpDocumentation:
    """帮助文档服务，负责系统帮助文档功能"""
    
    def __init__(self, help_dir='help'):
        self.help_dir = help_dir
        self._ensure_help_directory()
        self.help_contents = {}
        self._load_help_contents()
    
    def _ensure_help_directory(self):
        """确保帮助文档目录存在"""
        if not os.path.exists(self.help_dir):
            os.makedirs(self.help_dir)
            # 创建默认帮助文档
            self._create_default_help_docs()
    
    def _create_default_help_docs(self):
        """创建默认帮助文档"""
        # 创建用户操作指南
        user_guide = {
            "title": "用户操作指南",
            "sections": [
                {
                    "id": "introduction",
                    "title": "系统介绍",
                    "content": "设备备件管理系统是一个用于管理工厂设备备件的系统，包括备件信息管理、库存跟踪、出入库操作等功能。"
                },
                {
                    "id": "parts_management",
                    "title": "备件管理",
                    "content": "备件管理模块用于添加、编辑、删除和查询备件信息。"
                }
            ]
        }
        
        with open(os.path.join(self.help_dir, 'user_guide_zh.json'), 'w', encoding='utf-8') as f:
            json.dump(user_guide, f, ensure_ascii=False, indent=2)
        
        # 创建FAQ文档
        faq_content = {
            "title": "常见问题解答",
            "questions": [
                {
                    "question": "如何添加新备件？",
                    "answer": "在备件管理页面点击'添加备件'按钮，填写备件信息后保存即可。"
                },
                {
                    "question": "如何进行入库操作？",
                    "answer": "在操作记录页面选择'智能入库'功能，填写相关信息后提交。"
                }
            ]
        }
        
        with open(os.path.join(self.help_dir, 'faq_zh.json'), 'w', encoding='utf-8') as f:
            json.dump(faq_content, f, ensure_ascii=False, indent=2)
    
    def _load_help_contents(self):
        """加载帮助文档内容"""
        for filename in os.listdir(self.help_dir):
            if filename.endswith('.json'):
                with open(os.path.join(self.help_dir, filename), 'r', encoding='utf-8') as f:
                    doc_name = filename[:-5]  # 移除.json后缀
                    self.help_contents[doc_name] = json.load(f)
    
    def get_help_document(self, doc_name: str) -> Dict:
        """获取帮助文档内容"""
        return self.help_contents.get(doc_name, {})
    
    def search_help_content(self, keyword: str) -> List[Dict]:
        """搜索帮助内容"""
        results = []
        for doc_name, content in self.help_contents.items():
            # 在标题中搜索
            if 'title' in content and keyword.lower() in content['title'].lower():
                results.append({
                    'document': doc_name,
                    'title': content['title'],
                    'type': 'title'
                })
            
            # 在章节内容中搜索
            if 'sections' in content:
                for section in content['sections']:
                    if keyword.lower() in section.get('title', '').lower() or \
                       keyword.lower() in section.get('content', '').lower():
                        results.append({
                            'document': doc_name,
                            'section': section.get('id', ''),
                            'title': section.get('title', ''),
                            'type': 'section'
                        })
        
        return results
