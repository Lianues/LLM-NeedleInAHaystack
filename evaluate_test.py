import json
import sys
import os

# 添加数据分析目录到路径，以便导入grading_utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '数据分析'))
from grading_utils import grade_answers

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

def main():
    """主函数：评估test.json相对于答案.json的准确率"""
    
    # 加载测试答案和标准答案
    print("=" * 70)
    print("测试结果准确率评分")
    print("=" * 70)
    print()
    
    test_file = "test.json"
    answer_file = "答案.json"
    
    print(f"正在加载测试文件: {test_file}")
    test_data = load_json_file(test_file)
    if test_data is None:
        return
    
    print(f"正在加载标准答案: {answer_file}")
    standard_data = load_json_file(answer_file)
    if standard_data is None:
        return
    
    print()
    print("-" * 70)
    print("开始评分...")
    print("-" * 70)
    print()
    
    # 使用grading_utils中的评分函数
    result = grade_answers(test_data, standard_data)
    
    # 显示评分结果
    print("评分结果:")
    print("=" * 70)
    print(f"准确率: {result['accuracy']:.2f}%")
    print()
    print("详细统计:")
    print(f"  标准答案总数: {result['total']}")
    print(f"  测试答案总数: {result['answered_count']}")
    print(f"  完全正确数量: {result['correct_count']}")
    print(f"  缺失数量 (漏答): {result['missing_count']}")
    print(f"  多余数量 (幻觉): {result['extra_count']}")
    print(f"  错误数量 (答错): {result['wrong_count']}")
    print(f"  编辑距离: {result['edit_distance']}")
    print()
    
    # 显示详细对比（如果有差异）
    if result['accuracy'] < 100.0:
        print("-" * 70)
        print("差异详情:")
        print("-" * 70)
        
        # 找出所有差异
        standard_keys = set(standard_data.keys())
        test_keys = set(test_data.keys())
        
        # 缺失的键
        missing_keys = standard_keys - test_keys
        if missing_keys:
            print(f"\n缺失的键 ({len(missing_keys)}个):")
            for key in sorted(missing_keys, key=lambda x: int(x)):
                print(f"  键 {key}: 标准值={standard_data[key]}, 测试值=未回答")
        
        # 多余的键（幻觉）
        extra_keys = test_keys - standard_keys
        if extra_keys:
            print(f"\n多余的键/幻觉 ({len(extra_keys)}个):")
            for key in sorted(extra_keys, key=lambda x: int(x)):
                print(f"  键 {key}: 测试值={test_data[key]}, 标准答案中不存在")
        
        # 值错误的键
        wrong_keys = []
        for key in standard_keys & test_keys:
            if standard_data[key] != test_data[key]:
                wrong_keys.append(key)
        
        if wrong_keys:
            print(f"\n值错误的键 ({len(wrong_keys)}个):")
            for key in sorted(wrong_keys, key=lambda x: int(x)):
                print(f"  键 {key}: 标准值={standard_data[key]}, 测试值={test_data[key]}")
    else:
        print("✓ 完美匹配! 测试结果与标准答案完全一致。")
    
    print()
    print("=" * 70)

if __name__ == "__main__":
    main()