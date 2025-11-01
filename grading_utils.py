import json
import re

def calculate_edit_distance(seq1, seq2):
    """
    计算两个序列之间的编辑距离（Levenshtein Distance）
    使用动态规划算法
    
    参数:
        seq1: 序列1（标准答案的键值对列表）
        seq2: 序列2（学生答案的键值对列表）
    
    返回:
        编辑距离（最少需要多少次插入、删除、替换操作）
    """
    m, n = len(seq1), len(seq2)
    
    # 创建DP表
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    # 初始化边界条件
    for i in range(m + 1):
        dp[i][0] = i  # 删除操作
    for j in range(n + 1):
        dp[0][j] = j  # 插入操作
    
    # 填充DP表
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq1[i-1] == seq2[j-1]:
                # 如果元素相同，不需要操作
                dp[i][j] = dp[i-1][j-1]
            else:
                # 取三种操作的最小值
                dp[i][j] = 1 + min(
                    dp[i-1][j],      # 删除
                    dp[i][j-1],      # 插入
                    dp[i-1][j-1]     # 替换
                )
    
    return dp[m][n]

def extract_json_from_response(response_text):
    """从响应文本中提取JSON"""
    try:
        # 尝试提取```json ... ```代码块中的内容
        json_pattern = r'```json\s*(\{[^`]+\})\s*```'
        match = re.search(json_pattern, response_text, re.DOTALL)
        
        if match:
            json_str = match.group(1)
            return json.loads(json_str)
        
        # 如果没有代码块，尝试直接查找JSON对象
        json_pattern2 = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern2, response_text, re.DOTALL)
        
        for match_str in matches:
            try:
                data = json.loads(match_str)
                # 检查是否包含数字键
                if any(key.isdigit() for key in data.keys()):
                    return data
            except:
                continue
        
        return None
    except Exception as e:
        print(f"提取JSON失败: {e}")
        return None

def grade_answers(student_answers, standard_answers):
    """
    基于编辑距离的评分函数（Edit Distance Scoring）
    
    该算法会：
    1. 将标准答案和学生答案都转换为有序的键值对序列
    2. 计算两个序列之间的编辑距离
    3. 编辑距离越小，相似度越高
    4. 准确率 = (1 - 编辑距离 / 最大序列长度) * 100%
    
    优势：
    - 惩罚多余的键（幻觉，如多加了个7）
    - 惩罚缺失的键（漏答）
    - 惩罚错误的值
    - 惩罚顺序错误
    
    例如：
    标准答案：1:1234, 2:5678, 3:9012, 4:3456, 5:7890, 6:1111
    学生答案：1:1234, 2:5678, 7:9999, 3:9012, 4:3456, 5:7890, 6:1111
    编辑距离：1（需要删除7:9999）
    准确率：(1 - 1/7) * 100% = 85.71%
    """
    if not standard_answers:
        return {
            'correct_count': 0,
            'answered_count': 0,
            'total': 0,
            'accuracy': 0.0,
            'edit_distance': 0,
            'missing_count': 0,
            'extra_count': 0,
            'wrong_count': 0
        }
    
    if not student_answers:
        return {
            'correct_count': 0,
            'answered_count': 0,
            'total': len(standard_answers),
            'accuracy': 0.0,
            'edit_distance': len(standard_answers),
            'missing_count': len(standard_answers),
            'extra_count': 0,
            'wrong_count': 0
        }
    
    # 构建标准答案序列（按键排序）
    try:
        standard_keys = sorted([int(k) for k in standard_answers.keys()])
        standard_sequence = [(k, standard_answers[str(k)]) for k in standard_keys]
    except (ValueError, TypeError):
        return {
            'correct_count': 0,
            'answered_count': len(student_answers),
            'total': len(standard_answers),
            'accuracy': 0.0,
            'edit_distance': len(standard_answers) + len(student_answers),
            'missing_count': len(standard_answers),
            'extra_count': len(student_answers),
            'wrong_count': 0
        }
    
    # 构建学生答案序列（按键排序）
    try:
        student_keys = sorted([int(k) for k in student_answers.keys()])
        student_sequence = [(k, student_answers[str(k)]) for k in student_keys]
    except (ValueError, TypeError):
        return {
            'correct_count': 0,
            'answered_count': len(student_answers),
            'total': len(standard_answers),
            'accuracy': 0.0,
            'edit_distance': len(standard_answers) + len(student_answers),
            'missing_count': len(standard_answers),
            'extra_count': len(student_answers),
            'wrong_count': 0
        }
    
    # 计算编辑距离
    edit_distance = calculate_edit_distance(standard_sequence, student_sequence)
    
    # 计算统计信息
    total = len(standard_answers)
    answered_count = len(student_answers)
    
    # 统计完全正确的数量
    correct_count = 0
    for key in standard_keys:
        key_str = str(key)
        if key_str in student_answers and student_answers[key_str] == standard_answers[key_str]:
            correct_count += 1
    
    # 统计缺失、多余、错误的数量
    standard_key_set = set(str(k) for k in standard_keys)
    student_key_set = set(str(k) for k in student_keys)
    
    missing_count = len(standard_key_set - student_key_set)  # 标准答案有但学生没答的
    extra_count = len(student_key_set - standard_key_set)    # 学生答了但标准答案没有的（幻觉）
    wrong_count = answered_count - correct_count - extra_count  # 答了但值错误的
    
    # 计算准确率（基于编辑距离）
    max_length = max(len(standard_sequence), len(student_sequence))
    if max_length > 0:
        # 相似度 = 1 - (编辑距离 / 最大序列长度)
        similarity = 1.0 - (edit_distance / max_length)
        accuracy = similarity * 100
    else:
        accuracy = 0.0
    
    return {
        'correct_count': correct_count,
        'answered_count': answered_count,
        'total': total,
        'accuracy': accuracy,
        'edit_distance': edit_distance,
        'missing_count': missing_count,
        'extra_count': extra_count,
        'wrong_count': wrong_count
    }

def load_json_file(filepath):
    """加载JSON文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"错误: 文件 '{filepath}' 不存在")
        return None
    except json.JSONDecodeError:
        print(f"错误: 文件 '{filepath}' 不是有效的JSON格式")
        return None