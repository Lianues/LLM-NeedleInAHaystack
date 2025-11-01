import sqlite3
import json
import os
import sys
import statistics
from grading_utils import grade_answers

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

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
        WHERE type='table' AND name LIKE 'bytes_%'
        ORDER BY CAST(SUBSTR(name, 7) AS INTEGER)
    """)
    
    tables = []
    for row in cursor.fetchall():
        table_name = row[0]
        # 从表名中提取字节数 (例如: bytes_12345 -> 12345)
        byte_count = int(table_name.replace('bytes_', ''))
        tables.append((table_name, byte_count))
    
    conn.close()
    return tables

def analyze_byte_table(db_path, table_name, byte_count):
    """
    分析单个字节表的数据，计算准确率统计
    
    参数:
        db_path: 数据库文件路径
        table_name: 表名
        byte_count: 字节数
    
    返回:
        统计结果字典
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 查询表中所有记录
    cursor.execute(f"""
        SELECT standard_json, model_response_json, elapsed_time 
        FROM {table_name}
    """)
    
    records = cursor.fetchall()
    conn.close()
    
    if not records:
        return {
            'byte_count': byte_count,
            'record_count': 0,
            'avg_accuracy': 0.0,
            'median_accuracy': 0.0,
            'min_accuracy': 0.0,
            'max_accuracy': 0.0,
            'avg_elapsed_time': 0.0
        }
    
    accuracies = []
    elapsed_times = []
    
    # 对每条记录进行评分
    for standard_json, model_response_json, elapsed_time in records:
        try:
            # 解析JSON
            standard_answers = json.loads(standard_json)
            model_answers = json.loads(model_response_json)
            
            # 评分
            grade_result = grade_answers(model_answers, standard_answers)
            accuracies.append(grade_result['accuracy'])
            
            if elapsed_time:
                elapsed_times.append(elapsed_time)
        except Exception as e:
            print(f"  警告: 记录解析失败 - {str(e)}")
            continue
    
    if not accuracies:
        return {
            'byte_count': byte_count,
            'record_count': len(records),
            'avg_accuracy': 0.0,
            'median_accuracy': 0.0,
            'min_accuracy': 0.0,
            'max_accuracy': 0.0,
            'avg_elapsed_time': 0.0
        }
    
    # 计算统计数据
    avg_accuracy = statistics.mean(accuracies)
    median_accuracy = statistics.median(accuracies)
    min_accuracy = min(accuracies)
    max_accuracy = max(accuracies)
    avg_elapsed_time = statistics.mean(elapsed_times) if elapsed_times else 0.0
    
    return {
        'byte_count': byte_count,
        'record_count': len(accuracies),
        'avg_accuracy': avg_accuracy,
        'median_accuracy': median_accuracy,
        'min_accuracy': min_accuracy,
        'max_accuracy': max_accuracy,
        'avg_elapsed_time': avg_elapsed_time
    }

def create_summary_database(summary_db_path=None):
    """
    创建或打开汇总数据库
    
    参数:
        summary_db_path: 汇总数据库路径（如果为None，使用默认路径）
    
    返回:
        数据库连接、游标和实际使用的路径
    """
    if summary_db_path is None:
        # 创建分析结果目录（相对于脚本目录）
        results_dir = os.path.join(SCRIPT_DIR, '分析结果')
        os.makedirs(results_dir, exist_ok=True)
        summary_db_path = os.path.join(results_dir, 'test_results_summary.db')
    
    conn = sqlite3.connect(summary_db_path)
    cursor = conn.cursor()
    
    return conn, cursor, summary_db_path

def create_model_table(cursor, model_id):
    """
    为指定模型创建汇总表（如果不存在）
    
    参数:
        cursor: 数据库游标
        model_id: 模型ID
    
    返回:
        表名
    """
    # 清理模型ID，生成安全的表名（只保留字母数字）
    safe_model_id = "".join(c if c.isalnum() else '_' for c in model_id)
    table_name = f"model_{safe_model_id}"
    
    # 创建表
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            byte_count INTEGER PRIMARY KEY,
            record_count INTEGER NOT NULL,
            avg_accuracy REAL NOT NULL,
            median_accuracy REAL NOT NULL,
            min_accuracy REAL NOT NULL,
            max_accuracy REAL NOT NULL,
            avg_elapsed_time REAL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    return table_name

def insert_or_update_stats(cursor, table_name, stats):
    """
    插入或更新统计数据
    
    参数:
        cursor: 数据库游标
        table_name: 表名
        stats: 统计数据字典
    """
    cursor.execute(f"""
        INSERT OR REPLACE INTO {table_name}
        (byte_count, record_count, avg_accuracy, median_accuracy, 
         min_accuracy, max_accuracy, avg_elapsed_time, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        stats['byte_count'],
        stats['record_count'],
        stats['avg_accuracy'],
        stats['median_accuracy'],
        stats['min_accuracy'],
        stats['max_accuracy'],
        stats['avg_elapsed_time']
    ))

def analyze_model_database(model_db_path, summary_db_path=None):
    """
    分析模型数据库并将结果存入汇总数据库
    
    参数:
        model_db_path: 模型数据库路径
        summary_db_path: 汇总数据库路径（如果为None，使用默认路径）
    """
    print("=" * 70)
    print("模型数据库分析工具")
    print("=" * 70)
    
    # 检查模型数据库是否存在
    if not os.path.exists(model_db_path):
        print(f"错误: 数据库文件不存在: {model_db_path}")
        return
    
    # 从文件名提取模型ID
    model_filename = os.path.basename(model_db_path)
    if model_filename.startswith('test_results_') and model_filename.endswith('.db'):
        model_id = model_filename[13:-3]  # 移除 "test_results_" 和 ".db"
    else:
        model_id = model_filename.replace('.db', '')
    
    print(f"\n模型ID: {model_id}")
    print(f"数据库: {model_db_path}")
    
    # 获取所有字节表
    byte_tables = get_all_byte_tables(model_db_path)
    
    if not byte_tables:
        print("\n错误: 数据库中没有找到任何字节表")
        return
    
    print(f"找到 {len(byte_tables)} 个字节表")
    
    # 创建或打开汇总数据库
    summary_conn, summary_cursor, summary_db_path = create_summary_database(summary_db_path)
    model_table = create_model_table(summary_cursor, model_id)
    
    print(f"汇总数据库: {summary_db_path}")
    print(f"模型表: {model_table}")
    
    print("\n" + "=" * 70)
    print("开始分析...")
    print("=" * 70)
    
    # 分析每个字节表
    all_stats = []
    for table_name, byte_count in byte_tables:
        print(f"\n分析 {table_name} (字节数: {byte_count})")
        
        stats = analyze_byte_table(model_db_path, table_name, byte_count)
        
        print(f"  记录数: {stats['record_count']}")
        print(f"  平均准确率: {stats['avg_accuracy']:.2f}%")
        print(f"  准确率中位数: {stats['median_accuracy']:.2f}%")
        print(f"  准确率范围: {stats['min_accuracy']:.2f}% - {stats['max_accuracy']:.2f}%")
        print(f"  平均耗时: {stats['avg_elapsed_time']:.2f}秒")
        
        # 存入汇总数据库
        insert_or_update_stats(summary_cursor, model_table, stats)
        all_stats.append(stats)
    
    # 提交更改
    summary_conn.commit()
    
    # 显示汇总信息
    print("\n" + "=" * 70)
    print("分析完成！")
    print("=" * 70)
    
    if all_stats:
        total_records = sum(s['record_count'] for s in all_stats)
        overall_avg_accuracy = statistics.mean([s['avg_accuracy'] for s in all_stats if s['record_count'] > 0])
        
        print(f"\n总体统计:")
        print(f"  字节表数量: {len(all_stats)}")
        print(f"  总记录数: {total_records}")
        print(f"  整体平均准确率: {overall_avg_accuracy:.2f}%")
        print(f"\n结果已保存到: {summary_db_path}")
        print(f"模型表: {model_table}")
    
    # 关闭数据库
    summary_conn.close()
    
    print("=" * 70)

def list_summary_database(summary_db_path=None):
    """
    列出汇总数据库中的所有模型和统计信息
    
    参数:
        summary_db_path: 汇总数据库路径（如果为None，使用默认路径）
    """
    if summary_db_path is None:
        results_dir = os.path.join(SCRIPT_DIR, '分析结果')
        summary_db_path = os.path.join(results_dir, 'test_results_summary.db')
    
    if not os.path.exists(summary_db_path):
        print(f"汇总数据库不存在: {summary_db_path}")
        return
    
    conn = sqlite3.connect(summary_db_path)
    cursor = conn.cursor()
    
    # 获取所有模型表
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name LIKE 'model_%'
        ORDER BY name
    """)
    
    tables = [row[0] for row in cursor.fetchall()]
    
    if not tables:
        print("汇总数据库中没有模型表")
        conn.close()
        return
    
    print("=" * 70)
    print("汇总数据库内容")
    print("=" * 70)
    print(f"数据库: {summary_db_path}")
    print(f"模型数量: {len(tables)}\n")
    
    for table_name in tables:
        model_id = table_name.replace('model_', '')
        print(f"\n模型: {model_id}")
        print("-" * 70)
        
        cursor.execute(f"""
            SELECT byte_count, record_count, avg_accuracy, median_accuracy,
                   min_accuracy, max_accuracy, avg_elapsed_time
            FROM {table_name}
            ORDER BY byte_count
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            print("  (无数据)")
            continue
        
        print(f"{'字节数':<12} {'记录数':<8} {'平均准确率':<12} {'中位数':<12} {'最小值':<10} {'最大值':<10} {'平均耗时':<10}")
        print("-" * 70)
        
        for row in rows:
            byte_count, record_count, avg_acc, median_acc, min_acc, max_acc, avg_time = row
            print(f"{byte_count:<12} {record_count:<8} {avg_acc:>10.2f}% {median_acc:>10.2f}% "
                  f"{min_acc:>8.2f}% {max_acc:>8.2f}% {avg_time:>8.2f}秒")
    
    conn.close()
    print("\n" + "=" * 70)

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python analyze_database.py <模型数据库路径> [汇总数据库路径]")
        print("  python analyze_database.py --list [汇总数据库路径]")
        print("\n示例:")
        print("  python analyze_database.py test_results_gpt4.db")
        print("  python analyze_database.py test_results_gpt4.db my_summary.db")
        print("  python analyze_database.py --list")
        print("  python analyze_database.py --list my_summary.db")
        return
    
    if sys.argv[1] == '--list':
        summary_db_path = sys.argv[2] if len(sys.argv) > 2 else None
        list_summary_database(summary_db_path)
    else:
        model_db_path = sys.argv[1]
        summary_db_path = sys.argv[2] if len(sys.argv) > 2 else None
        analyze_model_database(model_db_path, summary_db_path)

if __name__ == "__main__":
    main()