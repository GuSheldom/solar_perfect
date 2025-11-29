"""
使用实际电池参数运行白天储能充电优化
"""

from daytime_storage_optimization import DaytimeStorageOptimizer

def main():
    """使用实际参数运行"""
    print("\n" + "="*80)
    print("白天储能充电+辐照放电优化策略 - 实际参数")
    print("="*80 + "\n")
    
    # 实际参数
    optimizer = DaytimeStorageOptimizer(
        lgc_price=10,  # AUD/MWh
        poa_to_power_ratio=3.79,  # W/(W/m²)
        battery_max_charge=2752,  # kW (5504kWh / 2h)
        battery_max_discharge=2752,  # kW
        battery_capacity=5504,  # kWh
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        ramp_rate=16.67,  # kW/s
        min_export_price=-10,  # AUD/MWh
        initial_soc=0.0  # 初始SOC为0
    )
    
    # 加载全部30天数据
    print("正在加载数据...")
    data = optimizer.load_data('excel_1117版本.csv', max_periods=None)
    
    # 优化
    print("开始优化...")
    results = optimizer.optimize_daily()
    
    # 打印摘要
    optimizer.print_summary()
    
    # 保存结果
    optimizer.save_results('daytime_storage_actual_results.csv')
    
    # 绘制图表
    optimizer.plot_results(days=3)
    
    print("\n✅ 优化完成!")
    print(f"\n💡 提示:")
    print(f"   - 电池容量: 5,504 kWh")
    print(f"   - 充放电功率: 2,752 kW (2C倍率)")
    print(f"   - 结果文件: daytime_storage_actual_results.csv")
    print(f"   - 图表文件: daytime_storage_results.png")


if __name__ == "__main__":
    main()


