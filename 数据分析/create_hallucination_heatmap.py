import sqlite3
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

def get_hallucination_data(db_path):
    """
    从错误统计数据库中读取幻觉数据
    
    参数:
        db_path: error_stats数据库路径
    
    返回:
        byte_counts: 字节数列表（排序后）
        heatmap_data: 热力图数据矩阵 [字节数 x 区间]
        intervals: 区间列表 [(key_from, key_to), ...]
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取所有hallucination表
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name LIKE '%_hallucination_errors'
        ORDER BY name
    """)
    
    tables = [row[0] for row in cursor.fetchall()]
    
    if not tables:
        print("错误: 数据库中没有找到幻觉错误表")
        conn.close()
        return None, None, None
    
    # 收集所有出现过的区间
    all_intervals = set()
    byte_data = {}  # {byte_count: {(key_from, key_to): probability}}
    
    for table_name in tables:
        # 从表名提取字节数 (bytes_12345_hallucination_errors -> 12345)
        original_table = table_name.replace('_hallucination_errors', '')
        if original_table.startswith('bytes_'):
            byte_str = original_table.replace('bytes_', '')
            if byte_str.isdigit():
                byte_count = int(byte_str)
            else:
                continue
        else:
            continue
        
        # 查询该表的所有区间数据
        cursor.execute(f"""
            SELECT key_from, key_to, probability
            FROM {table_name}
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            continue
        
        # 存储数据
        interval_dict = {}
        for key_from, key_to, prob in rows:
            interval = (key_from, key_to)
            all_intervals.add(interval)
            interval_dict[interval] = prob
        
        byte_data[byte_count] = interval_dict
    
    conn.close()
    
    if not byte_data:
        print("错误: 没有找到有效的数据")
        return None, None, None
    
    # 排序字节数和区间
    byte_counts = sorted(byte_data.keys())
    # 按key_from排序，然后按key_to排序
    intervals = sorted(list(all_intervals), key=lambda x: (x[0], x[1]))
    
    # 创建热力图数据矩阵 (字节数 x 区间)
    heatmap_data = np.zeros((len(byte_counts), len(intervals)))
    
    for i, byte_count in enumerate(byte_counts):
        for j, interval in enumerate(intervals):
            # 如果该区间有数据，使用实际值；否则保持为0
            if interval in byte_data[byte_count]:
                heatmap_data[i, j] = byte_data[byte_count][interval]
    
    return byte_counts, heatmap_data, intervals

def create_hallucination_heatmap(db_path, output_path=None):
    """
    创建幻觉错误热力图
    
    参数:
        db_path: error_stats数据库路径
        output_path: 输出图片路径（如果为None，则显示图片）
    """
    print("正在读取幻觉数据...")
    byte_counts, heatmap_data, intervals = get_hallucination_data(db_path)
    
    if byte_counts is None or heatmap_data is None:
        return
    
    print(f"找到 {len(byte_counts)} 个字节表")
    print(f"字节数范围: {min(byte_counts)} - {max(byte_counts)}")
    print(f"区间数量: {len(intervals)}")
    
    # 创建图表，根据区间数量调整宽度
    fig_width = max(16, len(intervals) * 0.3)
    plt.figure(figsize=(fig_width, 10))
    
    # 将字节数转换为k单位并四舍五入
    byte_labels = [f"{round(bc / 1000)}k" for bc in byte_counts]
    
    # 创建区间标签（格式：1-2, 2-3等，特殊处理0和41）
    interval_labels = []
    for k1, k2 in intervals:
        if k1 == 0:
            label = f"起始-{k2}"
        elif k2 == 41:
            label = f"{k1}-结束"
        else:
            label = f"{k1}-{k2}"
        interval_labels.append(label)
    
    # 使用seaborn绘制热力图
    ax = sns.heatmap(
        heatmap_data,
        xticklabels=interval_labels,
        yticklabels=byte_labels,
        cmap='YlOrRd',  # 黄-橙-红色渐变
        cbar_kws={'label': '幻觉概率 (%)'},
        linewidths=0.5,
        linecolor='lightgray',
        vmin=0
    )
    
    # 设置标题和标签
    plt.title('Hallucination幻觉错误热力图\n(横轴: 键位区间, 纵轴: 字符数)', fontsize=16, pad=20)
    plt.xlabel('键位区间 (Key Interval)', fontsize=12)
    plt.ylabel('字符数 (Byte Count)', fontsize=12)
    
    # 旋转x轴标签以便阅读
    plt.xticks(rotation=45, ha='right')
    
    # 如果区间太多，调整显示
    if len(intervals) > 40:
        # 每隔几个显示一个标签
        step = max(1, len(intervals) // 40)
        x_labels = [interval_labels[i] if i % step == 0 else '' for i in range(len(interval_labels))]
        ax.set_xticklabels(x_labels, rotation=45, ha='right')
    
    # 调整布局
    plt.tight_layout()
    
    # 保存或显示
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"\n热力图已保存到: {output_path}")
    else:
        print("\n显示热力图...")
        plt.show()
    
    plt.close()

def main():
    """主函数"""
    import sys
    
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python create_hallucination_heatmap.py <error_stats数据库路径> [输出图片路径]")
        print("\n示例:")
        print("  python create_hallucination_heatmap.py 数据分析/分析结果/error_stats_gemini_2_5_pro.db")
        print("  python create_hallucination_heatmap.py 数据分析/分析结果/error_stats_gemini_2_5_pro.db hallucination_heatmap.png")
        return
    
    db_path = sys.argv[1]
    
    if not os.path.exists(db_path):
        print(f"错误: 数据库文件不存在: {db_path}")
        return
    
    # 默认输出路径
    output_path = None
    if len(sys.argv) > 2:
        output_path = sys.argv[2]
    else:
        # 自动生成输出路径
        db_dir = os.path.dirname(db_path)
        db_name = os.path.basename(db_path).replace('.db', '')
        output_path = os.path.join(db_dir, f"{db_name}_hallucination_heatmap.png")
    
    create_hallucination_heatmap(db_path, output_path)

if __name__ == "__main__":
    main()