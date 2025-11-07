import random
import json
import os
import sys

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 配置参数
BASE_PATTERN = "a|"
DIGIT_LENGTH = 4       # 4位数
DEFAULT_NEEDLE_RANGE = "0-0.1:1,0.9-1:39"  # 默认插针返回范围（0-1表示全部，0.5-1表示后半部分，支持多区间：0-0.25,0.75-1，支持指定数量：0-0.1:1,0.9-1:20）

# 从命令行参数获取配置
# 参数1: 上下文长度（默认50000）
# 参数2: 插入数量（默认40）
# 参数3: 插针返回范围（默认0-1）

if len(sys.argv) > 1:
    try:
        TARGET_LENGTH = int(sys.argv[1])
        if TARGET_LENGTH <= 0:
            print("错误: 上下文数必须大于0")
            sys.exit(1)
    except ValueError:
        print("错误: 上下文数必须是整数")
        print("使用方法: python generate_text.py [上下文数] [插入数量] [插针范围]")
        print("示例:")
        print("  python generate_text.py 20000          # 20000字符，插入40个数")
        print("  python generate_text.py 30000 50       # 30000字符，插入50个数")
        print("  python generate_text.py 30000 50 0.5-1             # 30000字符，插入50个数，后半部分")
        print("  python generate_text.py 30000 50 0-0.25,0.75-1     # 30000字符，插入50个数，前后两段（多区间）")
        print("  python generate_text.py 30000 50 0-0.1:1,0.9-1:20  # 30000字符，指定数量：前1个，后20个")
        sys.exit(1)
else:
    TARGET_LENGTH = 100000  # 默认长度20k字符

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

if len(sys.argv) > 3:
    NEEDLE_RANGE = sys.argv[3]
    # 验证格式（支持单区间、多区间、指定数量）
    try:
        for range_str in NEEDLE_RANGE.split(','):
            range_str = range_str.strip()
            
            # 检查是否有指定数量（格式：start-end:count）
            if ':' in range_str:
                range_part, count_part = range_str.split(':')
                try:
                    count = int(count_part)
                    if count < 0:
                        raise ValueError("数量不能为负数")
                except ValueError:
                    raise ValueError(f"数量格式错误: {count_part}")
            else:
                range_part = range_str
            
            range_parts = range_part.split('-')
            if len(range_parts) != 2:
                raise ValueError("区间格式错误")
            range_start = float(range_parts[0])
            range_end = float(range_parts[1])
            if not (0 <= range_start <= range_end <= 1):
                raise ValueError("区间值超出范围")
    except (ValueError, IndexError) as e:
        print(f"错误: 插针范围格式错误")
        print(f"支持格式:")
        print(f"  单区间: 'start-end' (如 '0-1' 或 '0.5-1')")
        print(f"  多区间: 'start1-end1,start2-end2,...' (如 '0-0.25,0.75-1')")
        print(f"  指定数量: 'start-end:count' (如 '0-0.1:1,0.9-1:20')")
        print(f"详细错误: {e}")
        sys.exit(1)
else:
    NEEDLE_RANGE = DEFAULT_NEEDLE_RANGE

# 1. 构造基础字符串
base_string = BASE_PATTERN * (TARGET_LENGTH // len(BASE_PATTERN) + 1)
base_string = base_string[:TARGET_LENGTH]

# 2. 解析多区间（支持逗号分隔的多个区间，支持 :count 指定数量）
ranges = []
has_count_specified = False

for range_str in NEEDLE_RANGE.split(','):
    range_str = range_str.strip()
    
    # 检查是否指定了数量（格式：start-end:count）
    if ':' in range_str:
        has_count_specified = True
        range_part, count_part = range_str.split(':')
        specified_count = int(count_part)
    else:
        range_part = range_str
        specified_count = None
    
    range_parts = range_part.split('-')
    range_start = float(range_parts[0])
    range_end = float(range_parts[1])
    
    # 计算该区间的实际位置和长度
    insert_start_pos = int(len(base_string) * range_start)
    insert_end_pos = int(len(base_string) * range_end)
    insert_length = insert_end_pos - insert_start_pos
    
    ranges.append({
        'start': insert_start_pos,
        'end': insert_end_pos,
        'length': insert_length,
        'ratio': range_start,
        'ratio_end': range_end,
        'count': specified_count  # None表示使用权重分配
    })

# 检查是否所有区间都指定了数量
if has_count_specified:
    # 如果有区间指定了数量，检查是否所有区间都指定了
    if not all(r['count'] is not None for r in ranges):
        print("错误: 如果使用指定数量模式，所有区间都必须指定数量（格式：start-end:count）")
        sys.exit(1)
    # 使用指定的总数量
    ACTUAL_NUM_INSERTIONS = sum(r['count'] for r in ranges)
else:
    # 使用传入的 NUM_INSERTIONS 参数
    ACTUAL_NUM_INSERTIONS = NUM_INSERTIONS
    # 计算总长度用于权重分配
    total_length = sum(r['length'] for r in ranges)

# 3. 按权重或指定数量为每个区间分配针数
positions = []
allocated_needles = 0

for idx, range_info in enumerate(ranges):
    # 确定当前区间的针数
    if range_info['count'] is not None:
        # 使用指定的数量
        needles_for_range = range_info['count']
    else:
        # 按权重分配
        if idx == len(ranges) - 1:
            # 最后一个区间：分配剩余的所有针
            needles_for_range = ACTUAL_NUM_INSERTIONS - allocated_needles
        else:
            # 其他区间：按权重比例分配
            needles_for_range = round(ACTUAL_NUM_INSERTIONS * range_info['length'] / total_length)
            needles_for_range = max(1, needles_for_range)  # 至少分配1个针
    
    allocated_needles += needles_for_range
    
    # 在当前区间内生成插针位置
    insert_start_pos = range_info['start']
    insert_end_pos = range_info['end']
    insert_length = range_info['length']
    
    if needles_for_range == 0:
        # 如果该区间分配了0个针，跳过
        continue
    elif needles_for_range == 1:
        # 只有一个针，放在区间中间
        positions.append(insert_start_pos + insert_length // 2)
    else:
        # 多个针：均匀分布 + 小范围随机
        interval = insert_length // (needles_for_range - 1)
        random_range = interval // 20  # 随机范围为间隔的5%
        
        for i in range(needles_for_range):
            base_pos = insert_start_pos + i * interval
            
            # 添加小范围随机偏移
            if i == 0:
                # 第一个针：只能向右偏移
                random_offset = random.randint(0, random_range) if random_range > 0 else 0
            elif i == needles_for_range - 1:
                # 最后一个针：只能向左偏移
                random_offset = random.randint(-random_range, 0) if random_range > 0 else 0
            else:
                # 中间的针：可以双向偏移
                random_offset = random.randint(-random_range, random_range) if random_range > 0 else 0
            
            actual_pos = max(insert_start_pos, min(insert_end_pos, base_pos + random_offset))
            positions.append(actual_pos)

# 4. 排序位置以便从后向前插入（避免位置偏移）
positions.sort(reverse=True)

# 5. 生成随机4位数并插入
# 先生成所有数字并记录（按正序）
numbers_list = []
result_string = list(base_string)

for idx, pos in enumerate(positions):
    # 生成4位随机数
    random_num = random.randint(1000, 9999)
    # 插入到字符串中
    result_string.insert(pos, str(random_num))
    # 记录数字（注意positions是倒序的，所以序号需要反转）
    numbers_list.append((ACTUAL_NUM_INSERTIONS - idx, random_num))

# 转换回字符串
final_string = ''.join(result_string)

# 按序号排序并构建字典（确保键按正序）
numbers_list.sort(key=lambda x: x[0])
inserted_numbers = {str(num): val for num, val in numbers_list}

# 6. 输出到md文件（包含提示信息）
prompt_text = """Please give me an answer worth $200, think very carefully, and give me the best possible response.Extract all pure four-digit numbers (i.e., 1000–9999) interspersed within the text below, and output the numbers and their order of appearance in a JSON format following the example below:
{
"1": 123,
"2": 234,
"3": 345
}
---
"""

# 构造输出文件的完整路径（相对于脚本目录）
output_md_path = os.path.join(SCRIPT_DIR, 'output.md')
numbers_json_path = os.path.join(SCRIPT_DIR, 'numbers.json')

with open(output_md_path, 'w', encoding='utf-8') as f:
    f.write(prompt_text)
    f.write(final_string)

# 7. 输出json文件
with open(numbers_json_path, 'w', encoding='utf-8') as f:
    json.dump(inserted_numbers, f, indent=2, ensure_ascii=False)

# 8. 输出统计信息
print(f"生成完成！")
print(f"目标长度: {TARGET_LENGTH} 字符")
print(f"基础字符串长度: {len(base_string)} 字符")
print(f"最终字符串长度: {len(final_string)} 字符")
print(f"字节数: {len(final_string.encode('utf-8'))} bytes")
print(f"插针范围: {NEEDLE_RANGE}")
# 输出每个区间的详细信息
for idx, r in enumerate(ranges, 1):
    needles_in_range = sum(1 for pos in positions if r['start'] <= pos <= r['end'])
    if r['count'] is not None:
        print(f"  区间{idx}: {r['ratio']:.2f}-{r['ratio_end']:.2f} (位置 {r['start']}-{r['end']}, 长度 {r['length']}, 指定 {r['count']} 个针)")
    else:
        print(f"  区间{idx}: {r['ratio']:.2f}-{r['ratio_end']:.2f} (位置 {r['start']}-{r['end']}, 长度 {r['length']}, 分配 {needles_in_range} 个针)")
print(f"实际插入: {ACTUAL_NUM_INSERTIONS} 个4位数字" + (" (由区间指定)" if has_count_specified else f" (原计划 {NUM_INSERTIONS})"))
print(f"输出文件: {output_md_path} 和 {numbers_json_path}")