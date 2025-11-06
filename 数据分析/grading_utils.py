import json
import re

def calculate_edit_distance(seq1, seq2, allow_transposition=True):
    """
    计算两个序列之间的Damerau–Levenshtein距离（支持相邻换位）
    仅比较序列中的元素值（调用方应当只传值序列）

    参数:
        seq1: 序列1（仅值的列表）
        seq2: 序列2（仅值的列表）
        allow_transposition: 是否允许相邻换位操作（默认为 True）

    返回:
        编辑距离
    """
    m, n = len(seq1), len(seq2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if seq1[i - 1] == seq2[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,      # 删除
                dp[i][j - 1] + 1,      # 插入
                dp[i - 1][j - 1] + cost  # 替换/不变
            )

            # 相邻换位（Damerau）: ...ab vs ...ba
            '''if allow_transposition and i > 1 and j > 1:
                if seq1[i - 1] == seq2[j - 2] and seq1[i - 2] == seq2[j - 1]:
                    dp[i][j] = min(dp[i][j], dp[i - 2][j - 2] + 1)'''

    return dp[m][n]

def extract_json_from_response(response_text):
    """从响应文本中提取JSON"""
    try:
        json_pattern = r'```json\s*(\{[^`]+\})\s*```'
        match = re.search(json_pattern, response_text, re.DOTALL)
        if match:
            json_str = match.group(1)
            return json.loads(json_str)

        json_pattern2 = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern2, response_text, re.DOTALL)
        for match_str in matches:
            try:
                data = json.loads(match_str)
                if any(key.isdigit() for key in data.keys()):
                    return data
            except:
                continue
        return None
    except Exception as e:
        print(f"提取JSON失败: {e}")
        return None

def grade_answers(student_answers, standard_answers, allow_transposition=True, order_by_key=True):
    """
    基于编辑距离的评分函数（Edit Distance Scoring, 支持相邻换位）

    变更点：
    - 比较时不再把题号/序列号当成元素的一部分，仅比较值序列
    - 编辑距离加入相邻换位（Damerau–Levenshtein）

    参数:
        student_answers: 学生答案（dict: 题号 -> 值）
        standard_answers: 标准答案（dict: 题号 -> 值）
        allow_transposition: 是否允许相邻换位，默认 True
        order_by_key: 值序列的生成是否按题号排序（True）；
                      如果想按输入顺序比较，设为 False（依赖JSON加载的插入顺序）

    返回:
        统计字典
    """
    if not standard_answers:
        return {
            'correct_count': 0,
            'answered_count': len(student_answers) if student_answers else 0,
            'total': 0,
            'accuracy': 0.0,
            'edit_distance': len(student_answers) if student_answers else 0,
            'missing_count': 0,
            'extra_count': len(student_answers) if student_answers else 0,
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

    # 构建用于"编辑距离"的值序列（不比较题号）
    # 默认依旧按题号排序以维持与原逻辑接近；若需按输入顺序比较，order_by_key=False
    def values_sequence_from_dict(d):
        if order_by_key:
            # 尝试按数值题号排序，失败则按字符串排序
            try:
                sorted_keys = sorted([int(k) for k in d.keys()])
                return [d[str(k)] for k in sorted_keys]
            except (ValueError, TypeError):
                sorted_keys = sorted(d.keys())
                return [d[k] for k in sorted_keys]
        else:
            # 按插入顺序（Python 3.7+字典保序）
            return list(d.values())

    standard_sequence = values_sequence_from_dict(standard_answers)
    student_sequence = values_sequence_from_dict(student_answers)

    # 计算编辑距离（允许相邻换位）
    edit_distance = calculate_edit_distance(
        standard_sequence, student_sequence, allow_transposition=allow_transposition
    )

    # 统计信息（以下仍按"题号"来统计对错/缺失/多余，保持兼容原有口径）
    total = len(standard_answers)
    answered_count = len(student_answers)

    # 统计完全正确（题号存在且值相等）
    try:
        standard_keys = sorted([int(k) for k in standard_answers.keys()])
        student_keys = sorted([int(k) for k in student_answers.keys()])
        standard_key_set = set(str(k) for k in standard_keys)
        student_key_set = set(str(k) for k in student_keys)
    except (ValueError, TypeError):
        # 如题号不是纯数字，退化为字符串集合
        standard_key_set = set(standard_answers.keys())
        student_key_set = set(student_answers.keys())

        def get_val(d, k): return d[k]

        correct_count = sum(
            1 for k in (standard_key_set & student_key_set)
            if student_answers[k] == standard_answers[k]
        )
        missing_count = len(standard_key_set - student_key_set)
        extra_count = len(student_key_set - standard_key_set)
        wrong_count = answered_count - correct_count - extra_count
    else:
        correct_count = 0
        for key in standard_keys:
            key_str = str(key)
            if key_str in student_answers and student_answers[key_str] == standard_answers[key_str]:
                correct_count += 1

        missing_count = len(standard_key_set - student_key_set)
        extra_count = len(student_key_set - standard_key_set)
        wrong_count = answered_count - correct_count - extra_count

    # 准确率（基于编辑距离）
    max_length = max(len(standard_sequence), len(student_sequence))
    accuracy = (1.0 - (edit_distance / max_length)) * 100 if max_length > 0 else 0.0

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