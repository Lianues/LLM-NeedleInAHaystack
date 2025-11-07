import sqlite3
import json
import os
import sys

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def longest_common_subsequence_with_indices(seq1, seq2):
    """
    计算两个序列的最长公共子序列（LCS），并返回 seq1 中匹配元素的索引
    
    参数:
        seq1: 标准序列
        seq2: 模型序列
    
    返回:
        seq1 中属于 LCS 的元素索引列表
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
    
    # 回溯找出 LCS，记录 seq1 中的索引
    indices = []
    i, j = m, n
    while i > 0 and j > 0:
        if seq1[i-1] == seq2[j-1]:
            indices.append(i-1)  # 记录 seq1 的索引
            i -= 1
            j -= 1
        elif dp[i-1][j] > dp[i][j-1]:
            i -= 1
        else:
            j -= 1
    
    # 反转结果（因为是从后往前回溯的）
    indices.reverse()
    return indices

def analyze_position_accuracy(db_path, table_name, byte_count):
    """
    分析单个字节表的位置准确率
    使用 LCS 算法找出标准序列中按顺序正确出现的值
    
    例如：
    - 标准答案：{0: "A", 1: "B", 2: "C"} → ["A", "B", "C"]
    - 模型回答：{0: "A", 1: "X", 2: "B", 3: "C"} → ["A", "X", "B", "C"]
    - LCS 结果：["A", "B", "C"] 都正确（即使中间插入了 X）
    
    参数:
        db_path: 数据库文件路径
        table_name: 表名
        byte_count: 字节数
    
    返回:
        位置准确率统计字典 {sequence_position: frequency}
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 查询表中所有记录
    cursor.execute(f"""
        SELECT standard_json, model_response_json
        FROM {table_name}
    """)
    
    records = cursor.fetchall()
    conn.close()
    
    if not records:
        return {}, 0
    
    # 统计每个序列位置的正答频数
    position_frequency = {}
    total_records = 0
    
    for standard_json, model_response_json in records:
        try:
            # 解析JSON
            standard_answers = json.loads(standard_json)
            model_answers = json.loads(model_response_json)
            
            # 将字典转换为值序列（按键排序）
            try:
                standard_keys = sorted([int(k) for k in standard_answers.keys()])
                standard_sequence = [standard_answers[str(k)] for k in standard_keys]
                
                model_keys = sorted([int(k) for k in model_answers.keys()])
                model_sequence = [model_answers[str(k)] for k in model_keys]
            except (ValueError, TypeError):
                # 如果键不是数字，使用字符串排序
                standard_keys = sorted(standard_answers.keys())
                standard_sequence = [standard_answers[k] for k in standard_keys]
                
                model_keys = sorted(model_answers.keys())
                model_sequence = [model_answers[k] for k in model_keys]
            
            # 使用 LCS 算法找出标准序列中按顺序正确出现的值
            # 返回的是标准序列中属于 LCS 的元素索引
            lcs_indices = longest_common_subsequence_with_indices(standard_sequence, model_sequence)
            
            # 统计 LCS 中的每个位置
            for idx in lcs_indices:
                position = standard_keys[idx]
                # 确保键类型一致：如果是字符串形式的数字，转换为整数
                if isinstance(position, str) and position.isdigit():
                    position = int(position)
                if position not in position_frequency:
                    position_frequency[position] = 0
                position_frequency[position] += 1
            
            total_records += 1
            
        except Exception as e:
            print(f"  警告: 记录解析失败 - {str(e)}")
            continue
    
    return position_frequency, total_records

def create_position_accuracy_table(cursor, table_name):
    """
    创建位置准确率表
    
    参数:
        cursor: 数据库游标
        table_name: 原始字节表名
    
    返回:
        位置准确率表名
    """
    # 生成位置准确率表名
    position_table_name = f"{table_name}_position_accuracy"
    
    # 创建表
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {position_table_name} (
            key_position INTEGER PRIMARY KEY,
            frequency INTEGER NOT NULL,
            probability REAL NOT NULL,
            total_records INTEGER NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    return position_table_name

def insert_position_stats(cursor, position_table_name, position_frequency, total_records):
    """
    插入或更新位置准确率统计
    
    参数:
        cursor: 数据库游标
        position_table_name: 位置准确率表名
        position_frequency: 位置频数字典
        total_records: 总记录数
    """
    for key_position, frequency in position_frequency.items():
        probability = (frequency / total_records * 100) if total_records > 0 else 0.0
        
        cursor.execute(f"""
            INSERT OR REPLACE INTO {position_table_name}
            (key_position, frequency, probability, total_records, last_updated)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (key_position, frequency, probability, total_records))

def get_all_byte_tables(db_path):
    """
    获取数据库中所有字节表的名称和字节数
    
    参数:
        db_path: 数据库文件路径
    
    返回:
        字节表列表 [(表名, 字节数), ...]
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 查询所有以bytes_开头的表
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name GLOB 'bytes_[0-9]*'
        ORDER BY CAST(SUBSTR(name, 7) AS INTEGER)
    """)
    
    tables = []
    for row in cursor.fetchall():
        table_name = row[0]
        # 从表名中提取字节数，忽略非数字后缀（如 bytes_stats）
        suffix = table_name.replace('bytes_', '')
        if not suffix.isdigit():
            continue
        byte_count = int(suffix)
        tables.append((table_name, byte_count))
    
    conn.close()
    return tables

def analyze_model_position_accuracy(model_db_path):
    """
    分析模型数据库的位置准确率
    
    参数:
        model_db_path: 模型数据库路径
    """
    print("=" * 70)
    print("位置准确率分析工具（基于 LCS 算法，与 grading_utils.py 编辑距离一致）")
    print("=" * 70)
    
    # 检查模型数据库是否存在
    if not os.path.exists(model_db_path):
        print(f"错误: 数据库文件不存在: {model_db_path}")
        return
    
    # 从文件名提取模型ID
    model_filename = os.path.basename(model_db_path)
    if model_filename.startswith('test_results_') and model_filename.endswith('.db'):
        model_id = model_filename[13:-3]
    else:
        model_id = model_filename.replace('.db', '')
    
    print(f"\n模型ID: {model_id}")
    print(f"数据库: {model_db_path}")

    # 准备结果数据库（写入位置准确率的独立数据库）
    results_dir = os.path.join(SCRIPT_DIR, '分析结果')
    os.makedirs(results_dir, exist_ok=True)
    safe_model_id = "".join(c if c.isalnum() else '_' for c in model_id)
    out_db_path = os.path.join(results_dir, f"position_accuracy_{safe_model_id}.db")
    out_conn = sqlite3.connect(out_db_path)
    out_cursor = out_conn.cursor()

    # 准备结果数据库（写入位置准确率的独立数据库）
    results_dir = os.path.join(SCRIPT_DIR, '分析结果')
    os.makedirs(results_dir, exist_ok=True)
    safe_model_id = "".join(c if c.isalnum() else '_' for c in model_id)
    out_db_path = os.path.join(results_dir, f"position_accuracy_{safe_model_id}.db")
    out_conn = sqlite3.connect(out_db_path)
    out_cursor = out_conn.cursor()
    
    # 获取所有字节表
    byte_tables = get_all_byte_tables(model_db_path)
    
    if not byte_tables:
        print("\n错误: 数据库中没有找到任何字节表")
        return
    
    print(f"找到 {len(byte_tables)} 个字节表")
    
    # 连接数据库
    conn = sqlite3.connect(model_db_path)
    cursor = conn.cursor()
    
    print("\n" + "=" * 70)
    print("开始分析位置准确率...")
    print("=" * 70)
    
    # 分析每个字节表
    for table_name, byte_count in byte_tables:
        print(f"\n分析 {table_name} (字节数: {byte_count})")
        
        # 分析位置准确率
        position_frequency, total_records = analyze_position_accuracy(
            model_db_path, table_name, byte_count
        )
        
        if not position_frequency:
            print(f"  无有效记录")
            continue
        
        print(f"  总记录数: {total_records}")
        print(f"  分析的键位数: {len(position_frequency)}")
        
        # 创建位置准确率表（写入独立结果数据库）
        position_table_name = create_position_accuracy_table(out_cursor, table_name)
        
        # 插入统计数据（写入独立结果数据库）
        insert_position_stats(out_cursor, position_table_name, position_frequency, total_records)
        
        # 显示前10个键位的统计
        # 确保排序键统一为整数类型（如果可能），否则按字符串排序
        try:
            sorted_positions = sorted(position_frequency.items(), key=lambda x: (int(x[0]) if isinstance(x[0], str) else x[0]))
        except (ValueError, TypeError):
            # 如果无法转换为整数，则按字符串排序
            sorted_positions = sorted(position_frequency.items(), key=lambda x: str(x[0]))
        print(f"  位置准确率（前10个键位）:")
        print(f"    {'键位':<8} {'频数':<8} {'概率':<10}")
        print(f"    {'-'*26}")
        
        for key_pos, freq in sorted_positions[:10]:
            prob = (freq / total_records * 100) if total_records > 0 else 0.0
            print(f"    {key_pos:<8} {freq:<8} {prob:>8.2f}%")
        
        if len(sorted_positions) > 10:
            print(f"    ... 还有 {len(sorted_positions) - 10} 个键位")
        
        print(f"  结果已保存到表: {position_table_name}")
    
    # 提交更改（写入结果数据库）
    out_conn.commit()
    out_conn.close()
    conn.close()
    
    print("\n" + "=" * 70)
    print("分析完成！")
    print("=" * 70)
    print(f"\n所有位置准确率结果已保存到: {out_db_path}")
    print("每个字节表对应一个 _position_accuracy 表（保存在独立结果数据库中）")
    print("=" * 70)

def list_position_accuracy(model_or_result_db_path, table_name=None):
    """
    列出位置准确率统计
    
    参数:
        model_or_result_db_path: 模型数据库路径 或 结果数据库(position_accuracy_*.db)路径
        table_name: 要查看的字节表名（如果为None，显示所有表）
    """
    # 解析传入路径，支持两种：直接传结果库 或 传模型库自动推导结果库
    if not os.path.exists(model_or_result_db_path):
        print(f"错误: 数据库文件不存在: {model_or_result_db_path}")
        return

    base = os.path.basename(model_or_result_db_path)
    if base.startswith("position_accuracy_") and base.endswith(".db"):
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
        out_db_path = os.path.join(results_dir, f"position_accuracy_{safe_model_id}.db")
        if not os.path.exists(out_db_path):
            print(f"未找到位置准确率结果数据库: {out_db_path}")
            print("请先运行: python analyze_position_accuracy.py <模型数据库路径>")
            return

    conn = sqlite3.connect(out_db_path)
    cursor = conn.cursor()
    
    # 获取所有位置准确率表
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name LIKE '%_position_accuracy'
        ORDER BY name
    """)
    
    position_tables = [row[0] for row in cursor.fetchall()]
    
    if not position_tables:
        print("数据库中没有位置准确率表")
        print("请先运行分析: python analyze_position_accuracy.py <数据库路径>")
        conn.close()
        return
    
    print("=" * 70)
    print("位置准确率统计")
    print("=" * 70)
    print(f"数据库: {out_db_path}")
    print(f"位置准确率表数量: {len(position_tables)}\n")
    
    for pos_table_name in position_tables:
        # 提取原始表名
        original_table = pos_table_name.replace('_position_accuracy', '')
        
        # 如果指定了表名，只显示该表
        if table_name and original_table != table_name:
            continue
        
        print(f"\n表: {original_table}")
        print("-" * 70)
        
        cursor.execute(f"""
            SELECT key_position, frequency, probability, total_records
            FROM {pos_table_name}
            ORDER BY key_position
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            print("  (无数据)")
            continue
        
        total_records = rows[0][3] if rows else 0
        print(f"总记录数: {total_records}")
        print(f"\n{'键位':<8} {'频数':<8} {'正答概率':<12}")
        print("-" * 30)
        
        for key_pos, freq, prob, _ in rows:
            print(f"{key_pos:<8} {freq:<8} {prob:>10.2f}%")
    
    conn.close()
    print("\n" + "=" * 70)

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  分析模型数据库:")
        print("    python analyze_position_accuracy.py <模型数据库路径>")
        print("\n  查看位置准确率统计:")
        print("    python analyze_position_accuracy.py --list <模型数据库路径> [表名]")
        print("\n示例:")
        print("  python analyze_position_accuracy.py 收集数据/数据库/gemini_2_5_pro.db")
        print("  python analyze_position_accuracy.py --list 收集数据/数据库/gemini_2_5_pro.db")
        print("  python analyze_position_accuracy.py --list 收集数据/数据库/gemini_2_5_pro.db bytes_12345")
        return
    
    if sys.argv[1] == '--list':
        if len(sys.argv) < 3:
            print("错误: --list 需要指定数据库路径")
            print("使用方法: python analyze_position_accuracy.py --list <数据库路径> [表名]")
            return
        model_db_path = sys.argv[2]
        table_name = sys.argv[3] if len(sys.argv) > 3 else None
        list_position_accuracy(model_db_path, table_name)
    else:
        model_db_path = sys.argv[1]
        analyze_model_position_accuracy(model_db_path)

if __name__ == "__main__":
    main()