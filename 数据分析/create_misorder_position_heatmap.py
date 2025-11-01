import sqlite3
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

def get_misorder_position_data(db_path):
    """
    从错误统计数据库中读取misorder数据（按键位）
    
    参数:
        db_path: error_stats数据库路径
    
    返回:
        byte_counts: 字节数列表（排序后）
        heatmap_data: 热力图数据矩阵 [字节数 x 键位]
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取所有misorder表
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name LIKE '%_misorder_errors'
        ORDER BY name
    """)
    
    tables = [row[0] for row in cursor.fetchall()]
    
    if not tables:
        print("错误: 数据库中没有找到错位错误表")
        conn.close()
        return None, None
    
    # 提取字节数和数据
    byte_data = {}  # {byte_count: {position: probability}}
    
    for table_name in tables:
        # 从表名提取字节数
        original_table = table_name.replace('_misorder_errors', '')
        if original_table.startswith('bytes_'):
            byte_str = original_table.replace('bytes_', '')
            if byte_str.isdigit():
                byte_count = int(byte_str)
            else:
                continue
        else:
            continue
        
        # 查询该表的所有位置数据
        cursor.execute(f"""
            SELECT key_position, probability
            FROM {table_name}
            ORDER BY key_position
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            continue
        
        # 存储数据
        position_dict = {}
        for key_pos, prob in rows:
            position_dict[key_pos] = prob
        
        byte_data[byte_count] = position_dict
    
    conn.close()
    
    if not byte_data:
        print("错误: 没有找到有效的数据")
        return None, None
    
    # 排序字节数
    byte_counts = sorted(byte_data.keys())
    
    # 创建热力图数据矩阵 (字节数 x 位置)
    # 位置范围是1-40
    positions = list(range(1, 41))
    heatmap_data = np.zeros((len(byte_counts), len(positions)))
    
    for i, byte_count in enumerate(byte_counts):
        for j, position in enumerate(positions):
            # 如果该位置有数据，使用实际值；否则保持为0
            if position in byte_data[byte_count]:
                heatmap_data[i, j] = byte_data[byte_count][position]
    
    return byte_counts, heatmap_data

def create_misorder_position_heatmap(db_path, output_path=None):
    """
    创建错位错误热力图（按键位）
    
    参数:
        db_path: error_stats数据库路径
        output_path: 输出图片路径（如果为None，则显示图片）
    """
    print("正在读取错位数据...")
    byte_counts, heatmap_data = get_misorder_position_data(db_path)
    
    if byte_counts is None or heatmap_data is None:
        return
    
    print(f"找到 {len(byte_counts)} 个字节表")
    print(f"字节数范围: {min(byte_counts)} - {max(byte_counts)}")
    
    # 创建图表
    plt.figure(figsize=(16, 10))
    
    # 位置列表
    positions = list(range(1, 41))
    
    # 将字节数转换为k单位并四舍五入
    byte_labels = [f"{round(bc / 1000)}k" for bc in byte_counts]
    
    # 使用seaborn绘制热力图
    ax = sns.heatmap(
        heatmap_data,
        xticklabels=positions,
        yticklabels=byte_labels,
        cmap='YlOrRd',  # 黄-橙-红色渐变
        cbar_kws={'label': '错位概率 (%)'},
        linewidths=0.5,
        linecolor='lightgray',
        vmin=0,
        vmax=100
    )
    
    # 设置标题和标签
    plt.title('Misorder错位错误热力图\n(横轴: 键位, 纵轴: 字符数)', fontsize=16, pad=20)
    plt.xlabel('键位 (Key Position)', fontsize=12)
    plt.ylabel('字符数 (Byte Count)', fontsize=12)
    
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
        print("  python create_misorder_position_heatmap.py <error_stats数据库路径> [输出图片路径]")
        print("\n示例:")
        print("  python create_misorder_position_heatmap.py 数据分析/分析结果/error_stats_gemini_2_5_pro.db")
        print("  python create_misorder_position_heatmap.py 数据分析/分析结果/error_stats_gemini_2_5_pro.db misorder_position_heatmap.png")
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
        output_path = os.path.join(db_dir, f"{db_name}_misorder_position_heatmap.png")
    
    create_misorder_position_heatmap(db_path, output_path)

if __name__ == "__main__":
    main()