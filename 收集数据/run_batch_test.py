import asyncio
import aiohttp
import json
import re
import sqlite3
import time
import os
import sys

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 配置参数
API_URL = "http://127.0.0.1"
MODEL_ID = "gemini-2.5-pro"      # 模型ID（用于数据库文件名）
API_MODEL = "gemini-2.5-pro"     # 发送给API的模型名称

# 默认生成参数
DEFAULT_TARGET_LENGTH = 100000
DEFAULT_NUM_INSERTIONS = 40
DEFAULT_BASE_PATTERN = "a|"
DEFAULT_REQUEST_DELAY = 0  # 默认请求延迟（秒）
DEFAULT_NEEDLE_RANGE = "0-0.1:1,0.9-1:39"  # 默认插针返回范围（0-1表示全部，0.5-1表示后半部分，支持多区间：0-0.25,0.75-1）

# HTTP 请求头
HEADERS = {
    'accept': 'application/json',
    'accept-language': 'zh-CN',
    'authorization': 'Bearer sk-PYBojZzEeRnS82077cIAgv1XMT31Uz7oq7a_QDpuZMKeqZXQ',
    'content-type': 'application/json',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) CherryStudio/1.5.11 Chrome/138.0.7204.243 Electron/37.4.0 Safari/537.36',
}

class DatabaseManager:
    """数据库管理类（包含按字节数的统计汇总）"""

    def __init__(self, model_id, script_dir):
        """
        初始化数据库管理器

        参数:
            model_id: 模型ID，用于生成数据库文件名
            script_dir: 脚本所在目录
        """
        safe_model_id = "".join(c if c.isalnum() else '_' for c in model_id)
        db_dir = os.path.join(script_dir, '数据库')
        os.makedirs(db_dir, exist_ok=True)
        self.db_filename = os.path.join(db_dir, f"{safe_model_id}.db")
        self.conn = None
        self.cursor = None

    def connect(self):
        """连接到数据库（如果不存在则创建）"""
        is_new = not os.path.exists(self.db_filename)
        self.conn = sqlite3.connect(self.db_filename)
        self.cursor = self.conn.cursor()
        if is_new:
            print(f"创建新数据库: {self.db_filename}")
        else:
            print(f"使用现有数据库: {self.db_filename}")
        return is_new

    def create_table_if_not_exists(self, byte_count):
        """
        为指定的字节数创建表（如果不存在）

        参数:
            byte_count: 字节数量
        """
        table_name = f"bytes_{byte_count}"
        self.cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                standard_json TEXT NOT NULL,
                model_response_json TEXT NOT NULL,
                elapsed_time REAL
            )
        """)
        self.conn.commit()
        return table_name

    def create_stats_table(self):
        """
        创建（或确保存在）按字节数聚合的统计表：
        - answered_count: 统计“已有模型回答”的条目数（成功入库 + 解析失败）
        - parse_fail_count: 统计“解析失败（无法提取有效JSON）”的条目数
        """
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS bytes_stats (
                byte_count INTEGER PRIMARY KEY,
                answered_count INTEGER NOT NULL DEFAULT 0,
                parse_fail_count INTEGER NOT NULL DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def update_stats(self, byte_count, answered_delta=0, parse_fail_delta=0):
        """
        更新统计计数（使用UPSERT）:
        - answered_delta: 本次增加的“已回答”数量（成功+解析失败）
        - parse_fail_delta: 本次增加的“解析失败”数量
        """
        # 确保记录存在（若不存在则插入初始行）
        self.cursor.execute("""
            INSERT INTO bytes_stats (byte_count, answered_count, parse_fail_count, last_updated)
            VALUES (?, 0, 0, CURRENT_TIMESTAMP)
            ON CONFLICT(byte_count) DO NOTHING
        """, (byte_count,))
        # 增量更新
        self.cursor.execute("""
            UPDATE bytes_stats
            SET answered_count = answered_count + ?,
                parse_fail_count = parse_fail_count + ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE byte_count = ?
        """, (answered_delta, parse_fail_delta, byte_count))
        self.conn.commit()

    def insert_result(self, byte_count, standard_json, model_response_json, elapsed_time=None):
        """
        插入成功的测试结果

        参数:
            byte_count: 字节数
            standard_json: 标准答案JSON字符串
            model_response_json: 模型回答JSON字符串
            elapsed_time: 耗时（秒）
        """
        table_name = f"bytes_{byte_count}"
        self.cursor.execute(f"""
            INSERT INTO {table_name}
            (standard_json, model_response_json, elapsed_time)
            VALUES (?, ?, ?)
        """, (standard_json, model_response_json, elapsed_time))
        self.conn.commit()

    def get_table_stats(self, byte_count):
        """获取表的统计信息"""
        table_name = f"bytes_{byte_count}"
        try:
            self.cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            total = self.cursor.fetchone()[0]
            return {'total': total}
        except sqlite3.OperationalError:
            return {'total': 0}

    def get_bytes_stats(self, byte_count):
        """获取bytes_stats中的聚合统计"""
        try:
            self.cursor.execute(
                "SELECT answered_count, parse_fail_count FROM bytes_stats WHERE byte_count = ?",
                (byte_count,)
            )
            row = self.cursor.fetchone()
            if row:
                return {'answered_count': row[0], 'parse_fail_count': row[1]}
            else:
                return {'answered_count': 0, 'parse_fail_count': 0}
        except sqlite3.OperationalError:
            return {'answered_count': 0, 'parse_fail_count': 0}

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()

def extract_and_clean_json(response_text):
    """
    从响应文本中提取JSON并清理，只保留纯JSON内容

    支持以下格式：
    1. ```json ... ```
    2. ``` ... ```
    3. 纯JSON文本（以{开头}结尾）

    返回纯JSON字符串，失败返回None
    """
    try:
        json_pattern = r'```json\s*(\{[\s\S]*?\})\s*```'
        match = re.search(json_pattern, response_text, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
            json.loads(json_str)
            return json_str
        code_block_pattern = r'```\s*(\{[\s\S]*?\})\s*```'
        match = re.search(code_block_pattern, response_text, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
            json.loads(json_str)
            return json_str
        json_pattern2 = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern2, response_text, re.DOTALL)
        for match_str in matches:
            try:
                json_str = match_str.strip()
                parsed = json.loads(json_str)
                if any(key.isdigit() for key in parsed.keys()):
                    return json_str
            except:
                continue
        return None
    except Exception:
        return None

def get_byte_count(text):
    """获取文本的字节数（UTF-8编码）"""
    return len(text.encode('utf-8'))

def generate_test_case(target_length, num_insertions, base_pattern=DEFAULT_BASE_PATTERN, needle_range=DEFAULT_NEEDLE_RANGE):
    """
    生成一次测试用例（不落盘）

    参数:
        target_length: 目标文本长度
        num_insertions: 插入数量（当区间指定了数量时会被覆盖）
        base_pattern: 基础填充模式
        needle_range: 插针插入范围
                     格式："start-end" 或 "start1-end1,start2-end2,..."
                     支持指定数量："start-end:count" 如 "0-0.1:1,0.9-1:20"
                     如"0-1"表示全文，"0.5-1"表示后半部分，"0-0.25,0.75-1"表示前后两段

    返回: (prompt_content, standard_json_str, byte_count, actual_num_insertions)
    """
    import random
    base_string = (base_pattern * (target_length // len(base_pattern) + 1))[:target_length]

    # 解析多区间（支持逗号分隔的多个区间，支持 :count 指定数量）
    ranges = []
    has_count_specified = False
    
    for range_str in needle_range.split(','):
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
            raise ValueError("如果使用指定数量模式，所有区间都必须指定数量（格式：start-end:count）")
        # 使用指定的总数量
        actual_num_insertions = sum(r['count'] for r in ranges)
    else:
        # 使用传入的 num_insertions 参数
        actual_num_insertions = num_insertions
        # 计算总长度用于权重分配
        total_length = sum(r['length'] for r in ranges)
    
    # 按权重或指定数量为每个区间分配针数
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
                needles_for_range = actual_num_insertions - allocated_needles
            else:
                # 其他区间：按权重比例分配
                needles_for_range = round(actual_num_insertions * range_info['length'] / total_length)
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
    
    # 按位置排序（从大到小，便于插入）
    positions.sort(reverse=True)

    # 生成随机4位数并插入
    numbers_list = []
    result_string = list(base_string)
    for idx, pos in enumerate(positions):
        random_num = random.randint(1000, 9999)
        result_string.insert(pos, str(random_num))
        numbers_list.append((actual_num_insertions - idx, random_num))

    final_string = ''.join(result_string)
    numbers_list.sort(key=lambda x: x[0])
    inserted_numbers = {str(num): val for num, val in numbers_list}

    prompt_text = """Please give me an answer worth $200, think very carefully, and give me the best possible response.Extract all pure four-digit numbers (i.e., 1000–9999) interspersed within the text below, and output the numbers and their order of appearance in a JSON format following the example below:
{
"1": 123,
"2": 234,
"3": 345
}
---
"""

    prompt_content = prompt_text + final_string
    standard_json_str = json.dumps(inserted_numbers, ensure_ascii=False)
    byte_count = get_byte_count(prompt_content)
    return prompt_content, standard_json_str, byte_count, actual_num_insertions

async def make_api_request(session, request_id, semaphore, db_manager,
                          target_length, num_insertions, base_pattern, needle_range, stats):
    """
    发送单个API请求（每次生成独立的测试用例）
    """
    async with semaphore:
        print(f"→ 请求 #{request_id}: 开始发送...")

        prompt_content, standard_answers_json, byte_count, actual_num_insertions = generate_test_case(
            target_length, num_insertions, base_pattern, needle_range
        )

        db_manager.create_table_if_not_exists(byte_count)

        payload = {
            "model": API_MODEL,
            "messages": [
                {"role": "user", "content": prompt_content}
            ],
            "stream": True
        }

        try:
            start_time = time.time()
            async with session.post(API_URL, headers=HEADERS, json=payload, timeout=900) as response:
                if response.status == 200:
                    content = ""
                    
                    if payload["stream"]:
                        # 流式响应处理
                        async for line in response.content:
                            line_text = line.decode('utf-8').strip()
                            
                            # 跳过空行
                            if not line_text:
                                continue
                            
                            # 处理完成标记
                            if line_text == "data: [DONE]":
                                break
                            
                            # 解析data:开头的JSON
                            if line_text.startswith("data: "):
                                json_str = line_text[6:]  # 移除"data: "前缀
                                try:
                                    chunk_data = json.loads(json_str)
                                    if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                        delta = chunk_data['choices'][0].get('delta', {})
                                        chunk_content = delta.get('content', '')
                                        if chunk_content:
                                            content += chunk_content
                                except json.JSONDecodeError:
                                    continue
                        
                        elapsed_time = time.time() - start_time
                    else:
                        # 非流式响应处理
                        data = await response.json()
                        elapsed_time = time.time() - start_time
                        
                        if 'choices' in data and len(data['choices']) > 0:
                            content = data['choices'][0]['message']['content']
                        else:
                            stats['failed'] += 1
                            print(f"✗ 请求 #{request_id}: 失败 - No content in response (不写入数据库)")
                            return False
                    
                    # 统一处理内容（流式和非流式）
                    if content:
                        clean_json = extract_and_clean_json(content)
                        if clean_json:
                            db_manager.insert_result(
                                byte_count=byte_count,
                                standard_json=standard_answers_json,
                                model_response_json=clean_json,
                                elapsed_time=elapsed_time
                            )
                            # 成功入库：计入"已回答"一次（不增加解析失败）
                            db_manager.update_stats(byte_count, answered_delta=1, parse_fail_delta=0)
                            stats['success'] += 1
                            stream_mode = "流式" if payload["stream"] else "非流式"
                            print(f"✓ 请求 #{request_id}: 成功 ({stream_mode}), 耗时 {elapsed_time:.2f}秒 - 已存入数据库 "
                                  f"(成功: {stats['success']}/{stats['success'] + stats['failed']})")
                            return True
                        else:
                            # 解析失败：计入"已回答"一次 + "解析失败"一次
                            db_manager.update_stats(byte_count, answered_delta=1, parse_fail_delta=1)
                            stats['failed'] += 1
                            print(f"✗ 请求 #{request_id}: 失败 - 无法提取有效JSON (不写入数据库)")
                            return False
                    else:
                        stats['failed'] += 1
                        print(f"✗ 请求 #{request_id}: 失败 - 空内容 (不写入数据库)")
                        return False
                else:
                    elapsed_time = time.time() - start_time
                    error_text = await response.text()
                    stats['failed'] += 1
                    print(f"✗ 请求 #{request_id}: 失败 - HTTP {response.status}: {error_text[:100]} (不写入数据库)")
                    return False
        except asyncio.TimeoutError:
            stats['failed'] += 1
            print(f"✗ 请求 #{request_id}: 失败 - Request timeout (不写入数据库)")
            return False
        except Exception as e:
            stats['failed'] += 1
            print(f"✗ 请求 #{request_id}: 失败 - {str(e)} (不写入数据库)")
            return False

async def main():
    """主函数"""
    # 默认参数：10次运行，1并发
    total_requests = 10
    max_concurrent = 10

    if len(sys.argv) > 1:
        try:
            total_requests = int(sys.argv[1])
            if total_requests <= 0:
                raise ValueError
        except ValueError:
            print("错误: 运行次数必须是大于0的整数")
            print("使用方法: python run_batch_test.py [运行次数] [并发数] [请求延迟] [上下文长度] [插入数量] [基础模式] [插针范围]")
            print("示例:")
            print("  python run_batch_test.py                         # 使用默认值：10次，1并发，0延迟")
            print("  python run_batch_test.py 20                      # 20次，1并发，0延迟")
            print("  python run_batch_test.py 20 5                    # 20次，5并发，0延迟")
            print("  python run_batch_test.py 20 5 1                  # 20次，5并发，1秒延迟")
            print("  python run_batch_test.py 20 5 1 30000 50         # 20次，5并发，1秒延迟，30000字节，50个插入")
            print("  python run_batch_test.py 20 5 1 30000 50 a| 0.5-1             # 后半部分插针")
            print("  python run_batch_test.py 20 5 1 30000 50 a| 0-0.25,0.75-1     # 前后两段插针（多区间）")
            print("  python run_batch_test.py 20 5 1 30000 50 a| 0-0.1:1,0.9-1:20  # 指定数量：前1个，后20个")
            sys.exit(1)

    if len(sys.argv) > 2:
        try:
            max_concurrent = int(sys.argv[2])
            if max_concurrent <= 0:
                raise ValueError
        except ValueError:
            print("错误: 并发数必须是大于0的整数")
            sys.exit(1)

    request_delay = DEFAULT_REQUEST_DELAY
    if len(sys.argv) > 3:
        try:
            request_delay = float(sys.argv[3])
            if request_delay < 0:
                raise ValueError
        except ValueError:
            print("错误: 请求延迟必须是大于等于0的数字")
            sys.exit(1)

    target_length = DEFAULT_TARGET_LENGTH
    if len(sys.argv) > 4:
        try:
            target_length = int(sys.argv[4])
            if target_length <= 0:
                raise ValueError
        except ValueError:
            print("错误: 上下文长度必须是大于0的整数")
            sys.exit(1)

    num_insertions = DEFAULT_NUM_INSERTIONS
    if len(sys.argv) > 5:
        try:
            num_insertions = int(sys.argv[5])
            if num_insertions <= 0:
                raise ValueError
        except ValueError:
            print("错误: 插入数量必须是大于0的整数")
            sys.exit(1)

    base_pattern = DEFAULT_BASE_PATTERN
    if len(sys.argv) > 6:
        base_pattern = sys.argv[6]
        if not base_pattern:
            base_pattern = DEFAULT_BASE_PATTERN

    needle_range = DEFAULT_NEEDLE_RANGE
    if len(sys.argv) > 7:
        needle_range = sys.argv[7]
        # 验证格式（支持单区间、多区间、指定数量）
        try:
            for range_str in needle_range.split(','):
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

    db_manager = DatabaseManager(MODEL_ID, SCRIPT_DIR)
    db_manager.connect()
    # 确保统计表存在（用于记录"已回答/解析失败"计数）
    db_manager.create_stats_table()

    # 先生成一个测试用例以获取实际的插入数量
    sample_prompt, sample_standard_json, sample_byte_count, actual_num_insertions = generate_test_case(
        target_length, num_insertions, base_pattern, needle_range
    )

    print("=" * 70)
    print("批量API数据收集脚本（SQLite版本 - 动态并发）")
    print("=" * 70)
    print(f"API地址: {API_URL}")
    print(f"模型ID（数据库）: {MODEL_ID}")
    print(f"API模型名称: {API_MODEL}")
    print(f"最大并发数: {max_concurrent}")
    print(f"请求延迟: {request_delay}秒")
    print(f"总请求数: {total_requests}")
    print(f"上下文长度: {target_length}")
    # 检查是否使用了指定数量模式
    if ':' in needle_range:
        print(f"插入数量: {actual_num_insertions} (由区间指定)")
    else:
        print(f"插入数量: {num_insertions}")
    print(f"基础模式: {base_pattern}")
    print(f"插针返回范围: {needle_range}")
    print("=" * 70)
    table_name = db_manager.create_table_if_not_exists(sample_byte_count)

    stats_before = db_manager.get_table_stats(sample_byte_count)
    print(f"\n字节数: {sample_byte_count} bytes")
    print(f"表 {table_name} 当前统计:")
    print(f"  已有记录数: {stats_before['total']}")

    print("\n开始批量测试（动态并发模式）...\n")

    semaphore = asyncio.Semaphore(max_concurrent)
    stats = {'success': 0, 'failed': 0}
    start_time = time.time()

    async with aiohttp.ClientSession() as session:
        tasks = []
        for i in range(1, total_requests + 1):
            task = asyncio.create_task(
                make_api_request(
                    session, i, semaphore, db_manager,
                    target_length, num_insertions, base_pattern, needle_range, stats
                )
            )
            tasks.append(task)
            # 在创建下一个任务前添加延迟（错开任务启动时间）
            if request_delay > 0 and i < total_requests:
                await asyncio.sleep(request_delay)
        await asyncio.gather(*tasks)

    total_time = time.time() - start_time

    stats_after = db_manager.get_table_stats(sample_byte_count)
    bytes_stats = db_manager.get_bytes_stats(sample_byte_count)
    db_manager.close()

    print("\n" + "=" * 70)
    print("数据收集完成！")
    print("=" * 70)
    print(f"数据库文件: {db_manager.db_filename}")
    print(f"数据表: {table_name}")
    print(f"数据库总记录数: {stats_after['total']}")
    print(f"本次尝试请求: {total_requests}")
    print(f"本次成功写入: {stats['success']}")
    print(f"本次失败(未写入): {stats['failed']}")
    print(f"成功率: {(stats['success']/total_requests*100):.2f}%")
    print(f"总耗时: {total_time:.2f}秒")
    print(f"平均耗时: {(total_time/total_requests):.2f}秒/请求")
    # 统计汇总（含解析失败统计，仅统计HTTP 200且模型有回答的请求）
    print(f"已回答计数（成功+解析失败）: {bytes_stats.get('answered_count', 0)}")
    print(f"解析失败计数: {bytes_stats.get('parse_fail_count', 0)}")
    print(f"\n请运行 'python 数据分析/analyze_database.py {db_manager.db_filename}' 进行分析")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())