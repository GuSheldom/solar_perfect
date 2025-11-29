"""
运行储能优化 - 可配置参数
"""

import sys
sys.path.append('.')

from perfect_revenue_optimization import EnergyStorageOptimizer

def run_optimization(
    data_file='excel_1117版本.csv',
    max_periods=None,  # None表示使用全部数据
    lgc_price=10,
    battery_max_charge=250,
    battery_max_discharge=250,
    battery_capacity=1000,
    charge_efficiency=0.95,
    discharge_efficiency=0.95,
    ramp_rate=16.67,
    time_limit=300,  # 求解时间限制（秒）
):
    """
    运行储能优化
    
    参数说明：
    - data_file: 数据文件路径
    - max_periods: 最大时间段数（用于测试）
    - lgc_price: LGC价格 (AUD/MWh)
    - battery_max_charge: 电池最大充电功率 (kW)
    - battery_max_discharge: 电池最大放电功率 (kW)
    - battery_capacity: 电池容量 (kWh)
    - charge_efficiency: 充电效率
    - discharge_efficiency: 放电效率
    - ramp_rate: 功率变化速率 (kW/s)
    - time_limit: 求解时间限制 (秒)
    """
    
    print("\n" + "="*80)
    print("储能电站完美收益优化")
    print("="*80 + "\n")
    
    # 创建优化器
    optimizer = EnergyStorageOptimizer(
        lgc_price=lgc_price,
        poa_to_power_ratio=3.79,
        battery_max_charge=battery_max_charge,
        battery_max_discharge=battery_max_discharge,
        battery_capacity=battery_capacity,
        charge_efficiency=charge_efficiency,
        discharge_efficiency=discharge_efficiency,
        ramp_rate=ramp_rate,
        min_arbitrage_spread=0.05,
        initial_soc=0.5
    )
    
    # 加载数据
    data = optimizer.load_data(data_file)
    
    # 如果指定了最大时间段，则截取数据
    if max_periods is not None and max_periods < optimizer.n_periods:
        print(f"注意: 仅使用前 {max_periods} 个时间段进行优化\n")
        optimizer.data = optimizer.data.iloc[:max_periods].copy()
        optimizer.n_periods = max_periods
    
    # 构建模型
    prob = optimizer.build_optimization_model()
    
    # 求解
    status = optimizer.solve(time_limit=time_limit)
    
    if status == 1:
        # 提取结果
        results = optimizer.extract_results()
        
        # 打印摘要
        optimizer.print_summary()
        
        # 保存结果
        optimizer.save_results('optimization_results.csv')
        
        # 绘制图表
        days = min(3, optimizer.n_periods // 288)
        if days > 0:
            optimizer.plot_results(days=days)
        
        print("\n" + "="*80)
        print("优化完成!")
        print("="*80)
        
        return optimizer, results
    else:
        print("\n优化未能找到最优解")
        return optimizer, None


if __name__ == "__main__":
    # 方案1: 使用前7天数据进行快速测试
    print("开始优化（使用前7天数据）...")
    optimizer, results = run_optimization(
        max_periods=288 * 7,  # 7天数据
        time_limit=600  # 10分钟时间限制
    )


