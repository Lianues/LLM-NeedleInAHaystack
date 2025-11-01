import random
import json
import os
import sys

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 配置参数
BASE_PATTERN = "a|"
DIGIT_LENGTH = 4       # 4位数

# 从命令行参数获取配置
# 参数1: 上下文长度（默认20000）
# 参数2: 插入数量（默认40）

if len(sys.argv) > 1:
    try:
        TARGET_LENGTH = int(sys.argv[1])
        if TARGET_LENGTH <= 0:
            print("错误: 上下文数必须大于0")
            sys.exit(1)
    except ValueError:
        print("错误: 上下文数必须是整数")
        print("使用方法: python generate_text.py [上下文数] [插入数量]")
        print("示例:")
        print("  python generate_text.py 20000      # 20000字符，插入40个数")
        print("  python generate_text.py 30000 50   # 30000字符，插入50个数")
        sys.exit(1)
else:
    TARGET_LENGTH = 50000  # 默认长度20k字符

if len(sys.argv) > 2:
    try:
        NUM_INSERTIONS = int(sys.argv[2])
        if NUM_INSERTIONS <= 0:
            print("错误: 插入数量必须大于0")
            sys.exit(1)
    except ValueError:
        print("错误: 插入数量必须是整数")
        sys.exit(1)
else:
    NUM_INSERTIONS = 40  # 默认插入40个数字

# 1. 构造基础字符串
base_string = BASE_PATTERN * (TARGET_LENGTH // len(BASE_PATTERN) + 1)
base_string = base_string[:TARGET_LENGTH]

# 2. 计算插入位置（均匀分配 + 小范围随机）
interval = len(base_string) // (NUM_INSERTIONS + 1)  # 计算基础间隔
random_range = interval // 4  # 随机范围为间隔的1/4

positions = []
for i in range(1, NUM_INSERTIONS + 1):
    base_pos = i * interval
    # 添加小范围随机偏移
    random_offset = random.randint(-random_range, random_range)
    actual_pos = max(0, min(len(base_string), base_pos + random_offset))
    positions.append(actual_pos)

# 排序位置以便从后向前插入（避免位置偏移）
positions.sort(reverse=True)

# 3. 生成随机4位数并插入
# 先生成所有数字并记录（按正序）
numbers_list = []
result_string = list(base_string)

for idx, pos in enumerate(positions):
    # 生成4位随机数
    random_num = random.randint(1000, 9999)
    # 插入到字符串中
    result_string.insert(pos, str(random_num))
    # 记录数字（注意positions是倒序的，所以序号需要反转）
    numbers_list.append((NUM_INSERTIONS - idx, random_num))

# 转换回字符串
final_string = ''.join(result_string)

# 按序号排序并构建字典（确保键按正序）
numbers_list.sort(key=lambda x: x[0])
inserted_numbers = {str(num): val for num, val in numbers_list}

# 4. 输出到md文件（包含提示信息）
prompt_text = """

---
Please give me an answer worth $200, think very carefully, and give me the best possible response.Extract all pure four-digit numbers (i.e., 1000–9999) interspersed within the text above, and output the numbers and their order of appearance in a JSON format following the example below:
{
"1": 123,
"2": 234,
"3": 345
}"""

# 构造输出文件的完整路径（相对于脚本目录）
output_md_path = os.path.join(SCRIPT_DIR, 'output.md')
numbers_json_path = os.path.join(SCRIPT_DIR, 'numbers.json')

with open(output_md_path, 'w', encoding='utf-8') as f:
    f.write(final_string)
    f.write(prompt_text)

# 5. 输出json文件
with open(numbers_json_path, 'w', encoding='utf-8') as f:
    json.dump(inserted_numbers, f, indent=2, ensure_ascii=False)

print(f"生成完成！")
print(f"目标长度: {TARGET_LENGTH} 字符")
print(f"基础字符串长度: {len(base_string)} 字符")
print(f"最终字符串长度: {len(final_string)} 字符")
print(f"字节数: {len(final_string.encode('utf-8'))} bytes")
print(f"插入了 {NUM_INSERTIONS} 个4位数字")
print(f"输出文件: {output_md_path} 和 {numbers_json_path}")