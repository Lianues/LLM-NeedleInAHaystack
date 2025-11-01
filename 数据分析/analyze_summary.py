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
    获取数据库中所有字节表的名称和字节数，仅匹配 bytes_数字 的表
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
        suffix = table_name.replace('bytes_', '')
        if not suffix.isdigit():
            continue
        byte_count = int(suffix)
        tables.append((table_name, byte_count))
    conn.close()
    return tables

def analyze_byte_table(db_path, table_name, byte_count):
    """
    分析单个字节表的数据，计算准确率统计（参考 analyze_database.py）
    返回: dict
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
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

    for standard_json, model_response_json, elapsed_time in records:
        try:
            std = json.loads(standard_json)
            mdl = json.loads(model_response_json)
            grade_result = grade_answers(mdl, std)
            accuracies.append(grade_result['accuracy'])
            if elapsed_time:
                elapsed_times.append(elapsed_time)
        except Exception as e:
            # 跳过解析失败的记录
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

    return {
        'byte_count': byte_count,
        'record_count': len(accuracies),
        'avg_accuracy': statistics.mean(accuracies),
        'median_accuracy': statistics.median(accuracies),
        'min_accuracy': min(accuracies),
        'max_accuracy': max(accuracies),
        'avg_elapsed_time': statistics.mean(elapsed_times) if elapsed_times else 0.0
    }

def open_summary_database(model_id):
    """
    创建/打开 概览结果数据库: 数据分析/分析结果/model_summary_{model}.db
    并确保存在 summary 表
    """
    results_dir = os.path.join(SCRIPT_DIR, '分析结果')
    os.makedirs(results_dir, exist_ok=True)
    safe_model_id = "".join(c if c.isalnum() else '_' for c in model_id)
    summary_db_path = os.path.join(results_dir, f"model_summary_{safe_model_id}.db")
    conn = sqlite3.connect(summary_db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS summary (
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
    conn.commit()
    return summary_db_path, conn, cursor

def upsert_summary_row(cursor, stats):
    """
    将单个字节表的汇总统计写入/更新到 summary 表
    """
    cursor.execute("""
        INSERT INTO summary
        (byte_count, record_count, avg_accuracy, median_accuracy, 
         min_accuracy, max_accuracy, avg_elapsed_time, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(byte_count) DO UPDATE SET
            record_count=excluded.record_count,
            avg_accuracy=excluded.avg_accuracy,
            median_accuracy=excluded.median_accuracy,
            min_accuracy=excluded.min_accuracy,
            max_accuracy=excluded.max_accuracy,
            avg_elapsed_time=excluded.avg_elapsed_time,
            last_updated=CURRENT_TIMESTAMP
    """, (
        stats['byte_count'],
        stats['record_count'],
        stats['avg_accuracy'],
        stats['median_accuracy'],
        stats['min_accuracy'],
        stats['max_accuracy'],
        stats['avg_elapsed_time']
    ))

def analyze_model_database(model_db_path):
    """
    读取模型数据库，计算各字节数下的准确率统计，写入独立的概览结果库
    """
    print("=" * 70)
    print("模型概览统计工具（平均/中位/范围/频数）")
    print("=" * 70)

    if not os.path.exists(model_db_path):
        print(f"错误: 数据库文件不存在: {model_db_path}")
        return

    # 提取模型ID
    model_filename = os.path.basename(model_db_path)
    if model_filename.startswith('test_results_') and model_filename.endswith('.db'):
        model_id = model_filename[13:-3]
    else:
        model_id = model_filename.replace('.db', '')

    print(f"\n模型ID: {model_id}")
    print(f"数据库: {model_db_path}")

    # 获取字节表
    byte_tables = get_all_byte_tables(model_db_path)
    if not byte_tables:
        print("\n错误: 数据库中没有找到任何字节表")
        return
    print(f"找到 {len(byte_tables)} 个字节表")

    # 打开结果库
    summary_db_path, conn, cursor = open_summary_database(model_id)
    print(f"结果数据库: {summary_db_path}")

    print("\n" + "=" * 70)
    print("开始分析...")
    print("=" * 70)

    all_stats = []
    for table_name, byte_count in byte_tables:
        print(f"\n分析 {table_name} (字节数: {byte_count})")
        stats = analyze_byte_table(model_db_path, table_name, byte_count)
        print(f"  记录数: {stats['record_count']}")
        print(f"  平均准确率: {stats['avg_accuracy']:.2f}%")
        print(f"  中位数: {stats['median_accuracy']:.2f}%")
        print(f"  范围: {stats['min_accuracy']:.2f}% - {stats['max_accuracy']:.2f}%")
        print(f"  平均耗时: {stats['avg_elapsed_time']:.2f}秒")
        upsert_summary_row(cursor, stats)
        all_stats.append(stats)

    conn.commit()

    # 总体信息
    print("\n" + "=" * 70)
    print("分析完成！")
    print("=" * 70)

    if all_stats:
        total_records = sum(s['record_count'] for s in all_stats)
        non_empty = [s for s in all_stats if s['record_count'] > 0]
        overall_avg = statistics.mean([s['avg_accuracy'] for s in non_empty]) if non_empty else 0.0
        print(f"\n总体统计:")
        print(f"  字节表数量: {len(all_stats)}")
        print(f"  总记录数: {total_records}")
        print(f"  按字节表平均的平均准确率: {overall_avg:.2f}%")
        print(f"\n结果已保存到: {summary_db_path}")
        print("  表名: summary")

    conn.close()
    print("=" * 70)

def list_summary(db_or_model_path=None):
    """
    列出概览结果数据库中的统计
    支持两种路径：
      1) 直接传 model_summary_*.db
      2) 传模型库路径，自动推导 model_summary_*.db
    """
    if not db_or_model_path:
        print("错误: 需要提供数据库路径")
        return

    if not os.path.exists(db_or_model_path):
        print(f"错误: 路径不存在: {db_or_model_path}")
        return

    base = os.path.basename(db_or_model_path)
    if base.startswith("model_summary_") and base.endswith(".db"):
        summary_db_path = db_or_model_path
    else:
        model_filename = base
        if model_filename.startswith('test_results_') and model_filename.endswith('.db'):
            model_id = model_filename[13:-3]
        else:
            model_id = model_filename.replace('.db', '')
        results_dir = os.path.join(SCRIPT_DIR, '分析结果')
        safe_model_id = "".join(c if c.isalnum() else '_' for c in model_id)
        summary_db_path = os.path.join(results_dir, f"model_summary_{safe_model_id}.db")
        if not os.path.exists(summary_db_path):
            print(f"未找到概览结果数据库: {summary_db_path}")
            print("请先运行: python analyze_summary.py <模型数据库路径>")
            return

    conn = sqlite3.connect(summary_db_path)
    cursor = conn.cursor()

    # 读取 summary 表
    try:
        cursor.execute("""
            SELECT byte_count, record_count, avg_accuracy, median_accuracy,
                   min_accuracy, max_accuracy, avg_elapsed_time
            FROM summary
            ORDER BY byte_count
        """)
    except sqlite3.OperationalError:
        print(f"概览库中缺少 summary 表: {summary_db_path}")
        conn.close()
        return

    rows = cursor.fetchall()
    print("=" * 70)
    print("模型概览统计")
    print("=" * 70)
    print(f"数据库: {summary_db_path}\n")

    if not rows:
        print("(无数据)")
        conn.close()
        print("\n" + "=" * 70)
        return

    print(f"{'字节数':<12} {'记录数':<8} {'平均准确率':<12} {'中位数':<12} {'最小值':<10} {'最大值':<10} {'平均耗时':<10}")
    print("-" * 70)
    for row in rows:
        byte_count, record_count, avg_acc, median_acc, min_acc, max_acc, avg_time = row
        print(f"{byte_count:<12} {record_count:<8} {avg_acc:>10.2f}% {median_acc:>10.2f}% "
              f"{min_acc:>8.2f}% {max_acc:>8.2f}% {avg_time:>8.2f}秒")

    conn.close()
    print("\n" + "=" * 70)

def main():
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  生成概览统计:")
        print("    python analyze_summary.py <模型数据库路径>")
        print("\n  查看概览统计:")
        print("    python analyze_summary.py --list <模型数据库路径|概览结果库路径>")
        print("\n示例:")
        print("  python analyze_summary.py 收集数据/数据库/gemini_2_5_pro.db")
        print("  python analyze_summary.py --list 收集数据/数据库/gemini_2_5_pro.db")
        return

    if sys.argv[1] == '--list':
        if len(sys.argv) < 3:
            print("错误: --list 需要指定路径")
            print("使用方法: python analyze_summary.py --list <模型数据库路径|概览结果库路径>")
            return
        list_summary(sys.argv[2])
    else:
        analyze_model_database(sys.argv[1])

if __name__ == "__main__":
    main()