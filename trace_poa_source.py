#!/usr/bin/env python3
"""追踪Excel中POA的数据来源"""

import pandas as pd

print("="*70)
print("追踪Excel中POA的数据来源")
print("="*70)

# 读取Excel数据第一行
excel_df = pd.read_csv('excel_1117版本.csv', nrows=1)
first_row = excel_df.iloc[0]

print("\n第一行数据 (2025-07-01 09:00:00):")
print(f"  POA: {first_row['POA']:.2f} W/m²")
print(f"  PV功率: {first_row['PV功率']:.2f} kW")
print(f"  光伏发电量: {first_row['光伏发电量']:.2f} kWh")

# 读取Mannum真实辐照数据
print("\n读取Mannum真实测量数据...")
mannum_df = pd.read_csv('Mannum电站辐照数据/Mannum电站辐照数据/mannum_20250701_000000_20250801_000000.csv')
mannum_df['t_stamp'] = pd.to_datetime(mannum_df['t_stamp'])

# 重采样到5分钟平均值
mannum_df = mannum_df.set_index('t_stamp')
mannum_5min = mannum_df[['Mannum/SEN/SEN1/Radiation', 'Mannum/PQM/PQM/P']].resample('5T').mean()
mannum_5min.columns = ['POA', 'Power_kW']
mannum_5min = mannum_5min.reset_index()

# 找到09:00的数据
target_row = mannum_5min[mannum_5min['t_stamp'] == '2025-07-01 09:00:00']

if not target_row.empty:
    real_poa = target_row['POA'].values[0]
    real_power = target_row['Power_kW'].values[0]
    
    print("\nMannum真实测量（5分钟平均）:")
    print(f"  真实POA: {real_poa:.2f} W/m²")
    print(f"  真实功率: {real_power:.2f} kW")
    
    print("\n" + "="*70)
    print("数据对比与分析")
    print("="*70)
    
    print(f"\nPOA差异:")
    print(f"  Excel中: {first_row['POA']:.2f} W/m²")
    print(f"  真实值: {real_poa:.2f} W/m²")
    print(f"  差异: {real_poa - first_row['POA']:.2f} W/m²")
    print(f"  比例: {first_row['POA'] / real_poa:.4f}")
    
    print(f"\n功率差异:")
    print(f"  Excel中PV功率: {first_row['PV功率']:.2f} kW")
    print(f"  真实测量功率: {real_power:.2f} kW")
    print(f"  差异: {real_power - first_row['PV功率']:.2f} kW")
    print(f"  比例: {first_row['PV功率'] / real_power:.4f}")
    
    # 检查是否使用了某个缩放因子
    print("\n" + "="*70)
    print("推测计算逻辑")
    print("="*70)
    
    # 假设1：Excel中的光伏发电量是从真实功率计算的
    real_energy_5min = real_power * (5/60)
    print(f"\n假设1: 使用真实功率计算能量")
    print(f"  真实功率 × 5分钟 = {real_power:.2f} × (5/60) = {real_energy_5min:.2f} kWh")
    print(f"  Excel中光伏发电量 = {first_row['光伏发电量']:.2f} kWh")
    print(f"  差异: {abs(real_energy_5min - first_row['光伏发电量']):.2f} kWh")
    
    # 假设2：Excel中的数据使用了某个效率系数
    efficiency = first_row['PV功率'] / real_power
    print(f"\n假设2: 应用了效率系数")
    print(f"  效率系数 = Excel功率 / 真实功率")
    print(f"            = {first_row['PV功率']:.2f} / {real_power:.2f}")
    print(f"            = {efficiency:.4f} ({efficiency*100:.2f}%)")
    
    # 如果应用这个系数到POA
    adjusted_poa = real_poa * efficiency
    print(f"\n  如果真实POA也应用这个系数:")
    print(f"    调整后POA = {real_poa:.2f} × {efficiency:.4f} = {adjusted_poa:.2f} W/m²")
    print(f"    Excel中POA = {first_row['POA']:.2f} W/m²")
    print(f"    差异: {abs(adjusted_poa - first_row['POA']):.2f} W/m²")
    
    if abs(adjusted_poa - first_row['POA']) < 1:
        print(f"\n  ✓ 匹配！Excel中的POA是从真实POA乘以效率系数得到的")
    
    # 假设3：检查Excel中PV功率和POA的关系
    print("\n假设3: Excel内部PV功率和POA的关系")
    ratio = first_row['PV功率'] / first_row['POA']
    print(f"  Excel中: PV功率 / POA = {first_row['PV功率']:.2f} / {first_row['POA']:.2f}")
    print(f"                       = {ratio:.4f}")
    
    print(f"\n  真实数据: 功率 / POA = {real_power:.2f} / {real_poa:.2f}")
    print(f"                       = {real_power / real_poa:.4f}")
    
    print("\n" + "="*70)
    print("结论")
    print("="*70)
    
    print(f"\nExcel中的POA ({first_row['POA']:.2f} W/m²) 的计算方式是：")
    print(f"  1. 从Mannum真实POA开始: {real_poa:.2f} W/m²")
    print(f"  2. 应用某个效率/缩放系数: {efficiency:.4f} ({efficiency*100:.2f}%)")
    print(f"  3. 得到Excel中的POA: {adjusted_poa:.2f} W/m²")
    
    print(f"\n可能的原因:")
    print(f"  - 系统效率损耗（逆变器、线缆等）")
    print(f"  - 温度系数修正")
    print(f"  - 组件老化或污损")
    print(f"  - 或者这是一个数据处理/缩放的人为设定")

else:
    print("\n找不到对应的时间点数据")

print("\n" + "="*70)


