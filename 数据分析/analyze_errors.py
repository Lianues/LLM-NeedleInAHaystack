import sqlite3
import json
import os
import sys

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def longest_common_subsequence(seq1, seq2):
    """
    计算两个序列的最长公共子序列（LCS）
    
    参数:
        seq1: 序列1（标准答案的键列表）
        seq2: 序列2（模型回答的键列表）
    
    返回:
        LCS列表（按顺序正确的键）
    """
    m, n = len(seq1), len(seq2)
    
    # 创建DP表
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    # 填充DP表
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq1[i-1] == seq2[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    
    # 回溯找出LCS
    lcs = []
    i, j = m, n
    while i > 0 and j > 0:
        if seq1[i-1] == seq2[j-1]:
            lcs.append(seq1[i-1])
            i -= 1
            j -= 1
        elif dp[i-1][j] > dp[i][j-1]:
            i -= 1
        else:
            j -= 1
    
    # 反转结果（因为是从后往前回溯的）
    lcs.reverse()
    return lcs

def analyze_misorder_errors(db_path, table_name, byte_count):
    """
    分析错位错误：在正确答案中的数字但顺序不对
    
    新算法：
    1. 应用LCS算法找到AI回答中顺序正确的数字（锚点）
    2. 在模型回答中值正确但不在LCS中的数字就是错位数字
    3. 记录这些错位数字在正确答案中的键位置
    
    参数:
        db_path: 数据库文件路径
        table_name: 表名
        byte_count: 字节数
    
    返回:
        错位统计字典 {key_position: frequency}
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute(f"""
        SELECT standard_json, model_response_json
        FROM {table_name}
    """)
    
    records = cursor.fetchall()
    conn.close()
    
    if not records:
        return {}, 0
    
    # 统计每个键位的错位频数
    misorder_frequency = {}
    total_records = 0
    
    for standard_json, model_response_json in records:
        try:
            # 解析JSON
            standard_answers = json.loads(standard_json)
            model_answers = json.loads(model_response_json)
            
            # 获取标准答案的键序列（按数字顺序）
            standard_keys = sorted([int(k) for k in standard_answers.keys()])
            
            # 获取模型回答中值正确的键序列（按数字顺序）
            correct_model_keys = []
            for k in sorted([int(k) for k in model_answers.keys()]):
                k_str = str(k)
                if k_str in standard_answers and model_answers[k_str] == standard_answers[k_str]:
                    correct_model_keys.append(k)
            
            # 计算LCS（顺序正确的键，作为锚点）
            lcs = longest_common_subsequence(standard_keys, correct_model_keys)
            lcs_set = set(lcs)
            
            # 找出错位的键：在correct_model_keys中但不在LCS中
            misorder_keys = [k for k in correct_model_keys if k not in lcs_set]
            
            # 记录每个错位键的位置
            for key in misorder_keys:
                misorder_frequency[key] = misorder_frequency.get(key, 0) + 1
            
            total_records += 1
            
        except Exception as e:
            print(f"  警告: 记录解析失败 - {str(e)}")
            continue
    
    return misorder_frequency, total_records

def analyze_hallucination_errors(db_path, table_name, byte_count):
    """
    分析幻觉错误：模型回答了不在正确答案中的数字
    
    新算法：
    1. 应用LCS算法找到AI回答中顺序正确的数字（锚点）
    2. 模型回答中不在正确答案里的数字就是幻觉数字
    3. 对于每个幻觉数字，找出它在LCS锚点中的前后位置（在正确答案中的键）
    4. 给这个区间内的所有相邻键对的频数都加1
    5. 边缘区间：0-1（起始前）和40-41（结束后）
    
    参数:
        db_path: 数据库文件路径
        table_name: 表名
        byte_count: 字节数
    
    返回:
        幻觉统计字典 {(key1, key2): frequency}
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute(f"""
        SELECT standard_json, model_response_json
        FROM {table_name}
    """)
    
    records = cursor.fetchall()
    conn.close()
    
    if not records:
        return {}, 0
    
    # 统计每个键位区间的幻觉频数
    hallucination_frequency = {}
    total_records = 0
    
    for standard_json, model_response_json in records:
        try:
            # 解析JSON
            standard_answers = json.loads(standard_json)
            model_answers = json.loads(model_response_json)
            
            # 获取标准答案的键序列（按数字顺序）
            standard_keys = sorted([int(k) for k in standard_answers.keys()])
            standard_keys_set = set(standard_keys)
            
            # 获取模型回答的所有键（按数字顺序）
            all_model_keys = sorted([int(k) for k in model_answers.keys()])
            
            # 获取模型回答中值正确的键序列
            correct_model_keys = []
            for k in all_model_keys:
                k_str = str(k)
                if k_str in standard_answers and model_answers[k_str] == standard_answers[k_str]:
                    correct_model_keys.append(k)
            
            # 计算LCS（顺序正确的键，作为锚点）
            lcs = longest_common_subsequence(standard_keys, correct_model_keys)
            
            # 找出幻觉键：不在标准答案中的键
            hallucination_keys = [k for k in all_model_keys if k not in standard_keys_set]
            
            if not hallucination_keys:
                total_records += 1
                continue
            
            # 对于每个幻觉键，找出它在模型回答中的位置
            # 然后确定它在LCS锚点中的前后位置
            for halluc_key in hallucination_keys:
                # 找出幻觉键在模型回答中的位置
                halluc_pos = all_model_keys.index(halluc_key)
                
                # 找出幻觉键前后的LCS锚点
                left_anchor = None
                right_anchor = None
                
                # 向左查找最近的LCS锚点
                for i in range(halluc_pos - 1, -1, -1):
                    if all_model_keys[i] in lcs:
                        left_anchor = all_model_keys[i]
                        break
                
                # 向右查找最近的LCS锚点
                for i in range(halluc_pos + 1, len(all_model_keys)):
                    if all_model_keys[i] in lcs:
                        right_anchor = all_model_keys[i]
                        break
                
                # 确定区间（使用方案B：只记录起点和终点，不展开）
                # 边缘情况使用特殊标记：0表示起始，41表示结束
                if left_anchor is None and right_anchor is None:
                    # 跳过：既没有左锚点也没有右锚点（不太可能出现）
                    continue
                elif left_anchor is None:
                    # 幻觉在起始边缘（第一个锚点之前）
                    key_from = 0
                    key_to = right_anchor
                elif right_anchor is None:
                    # 幻觉在结束边缘（最后一个锚点之后）
                    key_from = left_anchor
                    key_to = 41
                else:
                    # 正常情况：有明确的左右锚点
                    key_from = left_anchor
                    key_to = right_anchor
                
                # 只记录这一个区间，不展开
                interval = (key_from, key_to)
                hallucination_frequency[interval] = hallucination_frequency.get(interval, 0) + 1
            
            total_records += 1
            
        except Exception as e:
            print(f"  警告: 记录解析失败 - {str(e)}")
            continue
    
    return hallucination_frequency, total_records

def analyze_missing_errors(db_path, table_name, byte_count):
    """
    分析缺失错误：标准答案中的某个位置（键位）的正确数字没有在模型回答中出现
    
    定义：如果模型在任意位置未给出该键位对应的“正确值”，则视为该键位缺失一次
    注：顺序不影响缺失统计，只要值正确地出现即不计为缺失。
    
    返回:
        缺失统计字典 {key_position: frequency}, total_records
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT standard_json, model_response_json
        FROM {table_name}
    """)
    records = cursor.fetchall()
    conn.close()
    if not records:
        return {}, 0

    missing_frequency = {}
    total_records = 0

    for standard_json, model_response_json in records:
        try:
            standard_answers = json.loads(standard_json)
            model_answers = json.loads(model_response_json)

            # 标准键序列（数字化）
            standard_keys = sorted([int(k) for k in standard_answers.keys()])

            # 找出模型给出的“值正确”的键集合（键在标准中且值完全一致）
            correct_keys = set()
            for k_str, v in model_answers.items():
                if k_str.isdigit() and k_str in standard_answers and model_answers[k_str] == standard_answers[k_str]:
                    correct_keys.add(int(k_str))

            # 对每个标准键，若未出现在correct_keys中，则计为缺失
            for key in standard_keys:
                if key not in correct_keys:
                    missing_frequency[key] = missing_frequency.get(key, 0) + 1

            total_records += 1

        except Exception as e:
            print(f"  警告: 记录解析失败 - {str(e)}")
            continue

    return missing_frequency, total_records

def create_error_tables(cursor, table_name):
    """
    创建错误统计表
    
    参数:
        cursor: 数据库游标
        table_name: 原始字节表名
    
    返回:
        (错位表名, 幻觉表名, 缺失表名)
    """
    # 错位错误表（现在按键位统计）
    misorder_table = f"{table_name}_misorder_errors"
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {misorder_table} (
            key_position INTEGER PRIMARY KEY,
            frequency INTEGER NOT NULL,
            probability REAL NOT NULL,
            total_records INTEGER NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 幻觉错误表（按区间统计）
    hallucination_table = f"{table_name}_hallucination_errors"
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {hallucination_table} (
            key_from INTEGER NOT NULL,
            key_to INTEGER NOT NULL,
            frequency INTEGER NOT NULL,
            probability REAL NOT NULL,
            total_records INTEGER NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (key_from, key_to)
        )
    """)

    # 缺失错误表（按键位聚合）
    missing_table = f"{table_name}_missing_errors"
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {missing_table} (
            key_position INTEGER PRIMARY KEY,
            frequency INTEGER NOT NULL,
            probability REAL NOT NULL,
            total_records INTEGER NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    return misorder_table, hallucination_table, missing_table

def insert_interval_error_stats(cursor, error_table, error_frequency, total_records):
    """
    插入或更新区间类错误统计（幻觉）
    """
    for (key_from, key_to), frequency in error_frequency.items():
        probability = (frequency / total_records * 100) if total_records > 0 else 0.0
        
        cursor.execute(f"""
            INSERT OR REPLACE INTO {error_table}
            (key_from, key_to, frequency, probability, total_records, last_updated)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (key_from, key_to, frequency, probability, total_records))

def insert_position_error_stats(cursor, error_table, error_frequency, total_records):
    """
    插入或更新键位类错误统计（错位）
    """
    for key_position, frequency in error_frequency.items():
        probability = (frequency / total_records * 100) if total_records > 0 else 0.0
        
        cursor.execute(f"""
            INSERT OR REPLACE INTO {error_table}
            (key_position, frequency, probability, total_records, last_updated)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (key_position, frequency, probability, total_records))

def insert_missing_stats(cursor, missing_table, missing_frequency, total_records):
    """
    插入或更新缺失统计（按键位）
    """
    for key_position, frequency in missing_frequency.items():
        probability = (frequency / total_records * 100) if total_records > 0 else 0.0
        cursor.execute(f"""
            INSERT OR REPLACE INTO {missing_table}
            (key_position, frequency, probability, total_records, last_updated)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (key_position, frequency, probability, total_records))

def get_all_byte_tables(db_path):
    """
    获取数据库中所有字节表的名称和字节数
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name GLOB 'bytes_[0-9]*'
        ORDER BY CAST(SUBSTR(name, 7) AS INTEGER)
    """)
    tables = []
    for row in cursor.fetchall():
        table_name = row[0]
        # 忽略非数字后缀（如 bytes_stats）
        suffix = table_name.replace('bytes_', '')
        if not suffix.isdigit():
            continue
        byte_count = int(suffix)
        tables.append((table_name, byte_count))
    conn.close()
    return tables

def analyze_model_errors(model_db_path):
    """
    分析模型数据库的错误统计（错位、幻觉、缺失）
    """
    print("=" * 70)
    print("错误统计分析工具")
    print("=" * 70)
    
    if not os.path.exists(model_db_path):
        print(f"错误: 数据库文件不存在: {model_db_path}")
        return
    
    model_filename = os.path.basename(model_db_path)
    if model_filename.startswith('test_results_') and model_filename.endswith('.db'):
        model_id = model_filename[13:-3]
    else:
        model_id = model_filename.replace('.db', '')
    
    print(f"\n模型ID: {model_id}")
    print(f"数据库: {model_db_path}")

    # 准备错误统计结果独立数据库
    results_dir = os.path.join(SCRIPT_DIR, '分析结果')
    os.makedirs(results_dir, exist_ok=True)
    safe_model_id = "".join(c if c.isalnum() else '_' for c in model_id)
    out_db_path = os.path.join(results_dir, f"error_stats_{safe_model_id}.db")
    out_conn = sqlite3.connect(out_db_path)
    out_cursor = out_conn.cursor()
    
    byte_tables = get_all_byte_tables(model_db_path)
    if not byte_tables:
        print("\n错误: 数据库中没有找到任何字节表")
        return
    print(f"找到 {len(byte_tables)} 个字节表")
    
    conn = sqlite3.connect(model_db_path)
    cursor = conn.cursor()
    
    print("\n" + "=" * 70)
    print("开始分析错误...")
    print("=" * 70)
    
    for table_name, byte_count in byte_tables:
        print(f"\n分析 {table_name} (字节数: {byte_count})")
        
        # 错位
        print("  分析错位错误...")
        misorder_freq, total_misorder = analyze_misorder_errors(model_db_path, table_name, byte_count)
        # 幻觉
        print("  分析幻觉错误...")
        halluc_freq, total_halluc = analyze_hallucination_errors(model_db_path, table_name, byte_count)
        # 缺失
        print("  分析缺失错误...")
        missing_freq, total_missing = analyze_missing_errors(model_db_path, table_name, byte_count)
        
        total_records = max(total_misorder, total_halluc, total_missing)
        print(f"  总记录数: {total_records}")
        print(f"  错位错误数: {len(misorder_freq)}")
        print(f"  幻觉错误数: {len(halluc_freq)}")
        print(f"  缺失错误数: {len(missing_freq)}")
        
        # 创建错误表（写入独立结果数据库）
        misorder_table, hallucination_table, missing_table = create_error_tables(out_cursor, table_name)
        
        # 写入错位（按键位）
        if misorder_freq:
            insert_position_error_stats(out_cursor, misorder_table, misorder_freq, total_misorder)
            print(f"  结果已保存到表: {misorder_table}")
            sorted_misorder = sorted(misorder_freq.items(), key=lambda x: x[1], reverse=True)
            print(f"  错位最多的键位（前5个）:")
            print(f"    {'键位':<8} {'频数':<8} {'概率':<10}")
            print(f"    {'-'*30}")
            for key_pos, freq in sorted_misorder[:5]:
                prob = (freq / total_misorder * 100) if total_misorder > 0 else 0.0
                print(f"    {key_pos:<8} {freq:<8} {prob:>8.2f}%")
        else:
            print("  无错位错误")
        
        # 写入幻觉（按区间）
        if halluc_freq:
            insert_interval_error_stats(out_cursor, hallucination_table, halluc_freq, total_halluc)
            print(f"  结果已保存到表: {hallucination_table}")
            sorted_halluc = sorted(halluc_freq.items(), key=lambda x: x[1], reverse=True)
            print(f"  最频繁的幻觉区间（前5个）:")
            print(f"    {'区间':<12} {'频数':<8} {'概率':<10}")
            print(f"    {'-'*30}")
            for (k1, k2), freq in sorted_halluc[:5]:
                prob = (freq / total_halluc * 100) if total_halluc > 0 else 0.0
                print(f"    ({k1},{k2}){' '*(8-len(str(k1))-len(str(k2)))} {freq:<8} {prob:>8.2f}%")
        else:
            print("  无幻觉错误")

        # 写入缺失
        if missing_freq:
            insert_missing_stats(out_cursor, missing_table, missing_freq, total_missing)
            print(f"  结果已保存到表: {missing_table}")
            sorted_missing = sorted(missing_freq.items(), key=lambda x: x[1], reverse=True)
            print(f"  缺失最多的键位（前5个）:")
            print(f"    {'键位':<8} {'频数':<8} {'概率':<10}")
            print(f"    {'-'*30}")
            for key_pos, freq in sorted_missing[:5]:
                prob = (freq / total_missing * 100) if total_missing > 0 else 0.0
                print(f"    {key_pos:<8} {freq:<8} {prob:>8.2f}%")
        else:
            print("  无缺失错误")
    
    conn.commit()
    conn.close()
    out_conn.commit()
    out_conn.close()
    
    print("\n" + "=" * 70)
    print("分析完成！")
    print("=" * 70)
    print(f"\n所有错误统计结果已保存到: {out_db_path}")
    print("每个字节表对应三个错误表（保存在独立结果数据库中）:")
    print("  - *_misorder_errors: 错位错误（按键位）")
    print("  - *_hallucination_errors: 幻觉错误（按区间）")
    print("  - *_missing_errors: 缺失错误（按键位）")
    print("=" * 70)

def list_error_stats(model_or_result_db_path, table_name=None, error_type='all'):
    """
    列出错误统计
    
    参数:
        model_or_result_db_path: 模型数据库路径 或 结果数据库(error_stats_*.db)路径
        table_name: 要查看的字节表名（如果为None，显示所有表）
        error_type: 错误类型 ('misorder', 'hallucination', 'missing', 'all')
    """
    if not os.path.exists(model_or_result_db_path):
        print(f"错误: 数据库文件不存在: {model_or_result_db_path}")
        return

    base = os.path.basename(model_or_result_db_path)
    if base.startswith("error_stats_") and base.endswith(".db"):
        out_db_path = model_or_result_db_path
    else:
        # 从模型库推导结果库路径
        model_filename = base
        if model_filename.startswith('test_results_') and model_filename.endswith('.db'):
            model_id = model_filename[13:-3]
        else:
            model_id = model_filename.replace('.db', '')
        safe_model_id = "".join(c if c.isalnum() else '_' for c in model_id)
        results_dir = os.path.join(SCRIPT_DIR, '分析结果')
        out_db_path = os.path.join(results_dir, f"error_stats_{safe_model_id}.db")
        if not os.path.exists(out_db_path):
            print(f"未找到错误统计结果数据库: {out_db_path}")
            print("请先运行: python analyze_errors.py <模型数据库路径>")
            return

    conn = sqlite3.connect(out_db_path)
    cursor = conn.cursor()
    
    misorder_tables = []
    halluc_tables = []
    missing_tables = []

    if error_type in ['misorder', 'all']:
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name LIKE '%_misorder_errors'
            ORDER BY name
        """)
        misorder_tables = [row[0] for row in cursor.fetchall()]
    if error_type in ['hallucination', 'all']:
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name LIKE '%_hallucination_errors'
            ORDER BY name
        """)
        halluc_tables = [row[0] for row in cursor.fetchall()]
    if error_type in ['missing', 'all']:
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name LIKE '%_missing_errors'
            ORDER BY name
        """)
        missing_tables = [row[0] for row in cursor.fetchall()]
    
    if not (misorder_tables or halluc_tables or missing_tables):
        print("数据库中没有错误统计表")
        print("请先运行分析: python analyze_errors.py <数据库路径>")
        conn.close()
        return
    
    print("=" * 70)
    print("错误统计")
    print("=" * 70)
    print(f"数据库: {out_db_path}\n")
    
    # 错位（按键位）
    if misorder_tables:
        print("\n【错位错误统计】")
        print("=" * 70)
        for error_table in misorder_tables:
            original_table = error_table.replace('_misorder_errors', '')
            if table_name and original_table != table_name:
                continue
            print(f"\n表: {original_table}")
            print("-" * 70)
            cursor.execute(f"""
                SELECT key_position, frequency, probability, total_records
                FROM {error_table}
                ORDER BY frequency DESC
            """)
            rows = cursor.fetchall()
            if not rows:
                print("  (无数据)")
                continue
            total_records = rows[0][3] if rows else 0
            print(f"总记录数: {total_records}")
            print(f"\n{'键位':<8} {'频数':<8} {'概率':<10}")
            print("-" * 30)
            for key_pos, freq, prob, _ in rows:
                print(f"{key_pos:<8} {freq:<8} {prob:>8.2f}%")
    
    # 幻觉（按区间）
    if halluc_tables:
        print("\n【幻觉错误统计】")
        print("=" * 70)
        for error_table in halluc_tables:
            original_table = error_table.replace('_hallucination_errors', '')
            if table_name and original_table != table_name:
                continue
            print(f"\n表: {original_table}")
            print("-" * 70)
            cursor.execute(f"""
                SELECT key_from, key_to, frequency, probability, total_records
                FROM {error_table}
                ORDER BY frequency DESC
            """)
            rows = cursor.fetchall()
            if not rows:
                print("  (无数据)")
                continue
            total_records = rows[0][4] if rows else 0
            print(f"总记录数: {total_records}")
            print(f"\n{'键位区间':<15} {'频数':<8} {'概率':<10}")
            print("-" * 35)
            for k1, k2, freq, prob, _ in rows:
                print(f"({k1}, {k2}){' '*(12-len(str(k1))-len(str(k2)))} {freq:<8} {prob:>8.2f}%")

    # 缺失
    if missing_tables:
        print("\n【缺失错误统计】")
        print("=" * 70)
        for error_table in missing_tables:
            original_table = error_table.replace('_missing_errors', '')
            if table_name and original_table != table_name:
                continue
            print(f"\n表: {original_table}")
            print("-" * 70)
            cursor.execute(f"""
                SELECT key_position, frequency, probability, total_records
                FROM {error_table}
                ORDER BY frequency DESC
            """)
            rows = cursor.fetchall()
            if not rows:
                print("  (无数据)")
                continue
            total_records = rows[0][3] if rows else 0
            print(f"总记录数: {total_records}")
            print(f"\n{'键位':<8} {'频数':<8} {'概率':<10}")
            print("-" * 30)
            for key_pos, freq, prob, _ in rows:
                print(f"{key_pos:<8} {freq:<8} {prob:>8.2f}%")
    
    conn.close()
    print("\n" + "=" * 70)

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  分析错误:")
        print("    python analyze_errors.py <模型数据库路径>")
        print("\n  查看错误统计:")
        print("    python analyze_errors.py --list <模型数据库路径> [表名] [错误类型]")
        print("\n错误类型: misorder (错位), hallucination (幻觉), missing (缺失), all (全部，默认)")
        print("\n示例:")
        print("  python analyze_errors.py 收集数据/数据库/gemini_2_5_pro.db")
        print("  python analyze_errors.py --list 收集数据/数据库/gemini_2_5_pro.db")
        print("  python analyze_errors.py --list 收集数据/数据库/gemini_2_5_pro.db bytes_12345")
        print("  python analyze_errors.py --list 收集数据/数据库/gemini_2_5_pro.db bytes_12345 misorder")
        print("  python analyze_errors.py --list 收集数据/数据库/gemini_2_5_pro.db bytes_12345 missing")
        return
    
    if sys.argv[1] == '--list':
        if len(sys.argv) < 3:
            print("错误: --list 需要指定数据库路径")
            print("使用方法: python analyze_errors.py --list <数据库路径> [表名] [错误类型]")
            return
        model_db_path = sys.argv[2]
        table_name = sys.argv[3] if len(sys.argv) > 3 else None
        error_type = sys.argv[4] if len(sys.argv) > 4 else 'all'
        
        if error_type not in ['misorder', 'hallucination', 'missing', 'all']:
            print(f"错误: 无效的错误类型 '{error_type}'")
            print("有效的错误类型: misorder, hallucination, missing, all")
            return
        
        list_error_stats(model_db_path, table_name, error_type)
    else:
        model_db_path = sys.argv[1]
        analyze_model_errors(model_db_path)

if __name__ == "__main__":
    main()