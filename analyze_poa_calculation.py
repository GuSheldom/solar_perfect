#!/usr/bin/env python3
"""分析Excel中POA的计算方法"""

import pandas as pd

print("="*70)
print("分析Excel中POA的计算方法")
print("="*70)

# 读取数据
df = pd.read_csv('excel_1117版本.csv', nrows=100)

# 分析POA和其他列的关系
df['POA/PV'] = df['POA'] / df['PV功率']
df['PV/POA'] = df['PV功率'] / df['POA']

# 检查辐照状态列
irr_col = '辐照状态' if '辐照状态' in df.columns else ' 辐照状态'
df['POA/辐照'] = df['POA'] / df[irr_col]
df['PV/辐照'] = df['PV功率'] / df[irr_col]

print("\n前10行数据分析:")
print(df[['日期', irr_col, 'POA', 'PV功率', 'POA/PV', 'PV/POA', 'POA/辐照', 'PV/辐照']].head(10).to_string(index=False))

print("\n" + "="*70)
print("统计分析")
print("="*70)

print(f"\nPOA / PV功率 比值:")
print(f"  平均值: {df['POA/PV'].mean():.6f}")
print(f"  标准差: {df['POA/PV'].std():.6f}")
print(f"  最小值: {df['POA/PV'].min():.6f}")
print(f"  最大值: {df['POA/PV'].max():.6f}")

print(f"\nPV功率 / POA 比值:")
print(f"  平均值: {df['PV/POA'].mean():.6f}")
print(f"  标准差: {df['PV/POA'].std():.6f}")

print(f"\nPOA / 辐照状态 比值:")
print(f"  平均值: {df['POA/辐照'].mean():.6f}")
print(f"  标准差: {df['POA/辐照'].std():.6f}")

print(f"\nPV功率 / 辐照状态 比值:")
print(f"  平均值: {df['PV/辐照'].mean():.6f}")
print(f"  标准差: {df['PV/辐照'].std():.6f}")

# 验证第一行数据
print("\n" + "="*70)
print("第一行数据详细验证")
print("="*70)

first_row = df.iloc[0]
print(f"\n日期: {first_row['日期']}")
print(f"辐照状态: {first_row[irr_col]}")
print(f"POA: {first_row['POA']:.2f} W/m²")
print(f"PV功率: {first_row['PV功率']:.2f} kW")
print(f"光伏发电量: {first_row['光伏发电量']:.2f} kWh")

print(f"\n计算验证:")
print(f"  POA = PV功率 × 0.263574")
print(f"      = {first_row['PV功率']:.2f} × 0.263574")
print(f"      = {first_row['PV功率'] * 0.263574:.2f}")
print(f"  实际POA = {first_row['POA']:.2f}")
print(f"  误差 = {abs(first_row['PV功率'] * 0.263574 - first_row['POA']):.4f}")

print(f"\n反向验证:")
print(f"  PV功率 = POA × 3.794")
print(f"         = {first_row['POA']:.2f} × 3.794")
print(f"         = {first_row['POA'] * 3.794:.2f}")
print(f"  实际PV功率 = {first_row['PV功率']:.2f}")
print(f"  误差 = {abs(first_row['POA'] * 3.794 - first_row['PV功率']):.4f}")

# 检查辐照状态和POA的关系
print(f"\n辐照状态与POA关系:")
print(f"  POA / 辐照状态 = {first_row['POA']:.2f} / {first_row[irr_col]}")
print(f"                   = {first_row['POA'] / first_row[irr_col]:.4f}")

print(f"\n辐照状态与PV功率关系:")
print(f"  PV功率 / 辐照状态 = {first_row['PV功率']:.2f} / {first_row[irr_col]}")
print(f"                      = {first_row['PV功率'] / first_row[irr_col]:.4f}")

# 尝试找出POA的原始来源
print("\n" + "="*70)
print("推测POA的计算公式")
print("="*70)

print("\n可能性1: POA是从PV功率反推的")
print("  公式: POA = PV功率 / 3.794")
print("  特点: POA和PV功率比例恒定")

print("\n可能性2: PV功率是从某个原始POA值计算的")
print("  如果原始数据中有真实的辐照度数据,")
print("  那么Excel可能使用了不同的转换参数")

print("\n" + "="*70)


