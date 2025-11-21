class TrainingCoordinator:
    """培训协调器，负责用户培训和知识转移功能"""
    
    def __init__(self):
        self.training_courses = {}
        self.user_progress = {}
    
    def design_training_course(self, course_name: str, modules: list):
        """设计培训课程"""
        self.training_courses[course_name] = {
            'modules': modules,
            'duration': len(modules) * 2,  # 每个模块2小时
            'target_audience': []
        }
        return self.training_courses[course_name]
    
    def track_user_progress(self, user_id: str, course_name: str):
        """跟踪用户学习进度"""
        if user_id not in self.user_progress:
            self.user_progress[user_id] = {}
        self.user_progress[user_id][course_name] = {
            'completed_modules': [],
            'progress_percentage': 0
        }
        return self.user_progress[user_id][course_name]
