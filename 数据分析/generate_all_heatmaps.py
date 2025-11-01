import os
import sys
import subprocess

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def run_script(script_name, db_path, output_path):
    """
    运行指定的热力图生成脚本
    
    参数:
        script_name: 脚本名称
        db_path: 数据库路径
        output_path: 输出图片路径
    """
    script_path = os.path.join(SCRIPT_DIR, script_name)
    
    print(f"\n{'='*70}")
    print(f"正在运行: {script_name}")
    print(f"{'='*70}")
    
    try:
        # 直接继承当前进程的输出，避免编码问题
        result = subprocess.run(
            [sys.executable, script_path, db_path, output_path],
            check=False
        )
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"运行失败: {str(e)}")
        return False

def generate_all_heatmaps(error_stats_db_path):
    """
    生成所有错误类型的热力图
    
    参数:
        error_stats_db_path: error_stats数据库路径
    """
    print("="*70)
    print("热力图批量生成工具")
    print("="*70)
    
    if not os.path.exists(error_stats_db_path):
        print(f"错误: 数据库文件不存在: {error_stats_db_path}")
        return
    
    # 获取数据库所在目录和基础名称
    db_dir = os.path.dirname(error_stats_db_path)
    db_name = os.path.basename(error_stats_db_path).replace('.db', '')
    
    print(f"\n数据库: {error_stats_db_path}")
    print(f"输出目录: {db_dir}")
    
    # 定义要生成的热力图
    heatmaps = [
        {
            'script': 'create_missing_heatmap.py',
            'name': 'Missing缺失错误',
            'output': f"{db_name}_missing_heatmap.png"
        },
        {
            'script': 'create_misorder_position_heatmap.py',
            'name': 'Misorder错位错误',
            'output': f"{db_name}_misorder_position_heatmap.png"
        },
        {
            'script': 'create_hallucination_heatmap.py',
            'name': 'Hallucination幻觉错误',
            'output': f"{db_name}_hallucination_heatmap.png"
        }
    ]
    
    # 运行所有热力图生成脚本
    success_count = 0
    total_count = len(heatmaps)
    
    for heatmap in heatmaps:
        output_path = os.path.join(db_dir, heatmap['output'])
        
        print(f"\n正在生成 {heatmap['name']} 热力图...")
        
        if run_script(heatmap['script'], error_stats_db_path, output_path):
            success_count += 1
            print(f"✓ {heatmap['name']} 热力图生成成功")
        else:
            print(f"✗ {heatmap['name']} 热力图生成失败")
    
    # 总结
    print("\n" + "="*70)
    print("生成完成")
    print("="*70)
    print(f"成功: {success_count}/{total_count}")
    
    if success_count == total_count:
        print("\n所有热力图已保存到:")
        print(f"  {db_dir}/")
        for heatmap in heatmaps:
            print(f"  - {heatmap['output']}")
    
    print("="*70)

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python generate_all_heatmaps.py <error_stats数据库路径>")
        print("\n示例:")
        print("  python generate_all_heatmaps.py 数据分析/分析结果/error_stats_gemini_2_5_pro.db")
        print("\n说明:")
        print("  此脚本将自动生成三个热力图:")
        print("  1. Missing缺失错误热力图")
        print("  2. Misorder错位错误热力图（按键位）")
        print("  3. Hallucination幻觉错误热力图（按区间）")
        return
    
    error_stats_db_path = sys.argv[1]
    generate_all_heatmaps(error_stats_db_path)

if __name__ == "__main__":
    main()