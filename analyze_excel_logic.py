"""
分析excel_1117版本.csv的整体逻辑
"""

import pandas as pd
import numpy as np

# 读取数据
df = pd.read_csv('excel_1117版本.csv', encoding='utf-8')
# 清理列名中的空格
df.columns = df.columns.str.strip()

print("="*80)
print("Excel数据逻辑分析")
print("="*80)

# 1. 基本信息
print("\n📊 1. 数据基本信息")
print(f"   时间范围: {df['日期'].min()} 到 {df['日期'].max()}")
print(f"   总时段数: {len(df)} 个（每5分钟一个）")
print(f"   天数: 约 {len(df)/288:.0f} 天")

# 2. 状态编码分析
print("\n🔢 2. 状态编码分析")
print("\n充电状态分布:")
charge_status = df['充电状态'].value_counts().sort_index()
for status, count in charge_status.items():
    pct = count / len(df) * 100
    print(f"   {status}: {count:>5} 次 ({pct:>5.1f}%)")

print("\n电网状态分布:")
grid_status = df['电网状态'].value_counts().sort_index()
for status, count in grid_status.items():
    pct = count / len(df) * 100
    print(f"   {status}: {count:>5} 次 ({pct:>5.1f}%)")

print("\n辐照状态分布:")
irr_status = df['辐照状态'].value_counts().sort_index()
for status, count in irr_status.items():
    pct = count / len(df) * 100
    print(f"   {status}: {count:>5} 次 ({pct:>5.1f}%)")

# 3. 各状态特征分析
print("\n" + "="*80)
print("🔍 3. 各充电状态的特征分析")
print("="*80)

for status in sorted(df['充电状态'].unique()):
    status_data = df[df['充电状态'] == status]
    print(f"\n充电状态 = {status} ({len(status_data)} 个时段, {len(status_data)/len(df)*100:.1f}%)")
    print(f"   POA范围:         {status_data['POA'].min():.1f} ~ {status_data['POA'].max():.1f}")
    print(f"   实际充电量:      {status_data['实际充电量'].sum():.2f} kWh (平均 {status_data['实际充电量'].mean():.3f})")
    print(f"   实际放电量:      {status_data['实际放电量'].sum():.2f} kWh (平均 {status_data['实际放电量'].mean():.3f})")
    print(f"   光伏发电量:      {status_data['光伏发电量'].sum():.2f} kWh")
    print(f"   电网充电量:      {status_data['电网充电量'].sum():.2f} kWh")
    print(f"   光伏收益:        ${status_data['光伏收益'].sum():.2f}")
    print(f"   电网收益:        ${status_data['电网收益'].sum():.2f}")
    print(f"   电池收益:        ${status_data['电池收益'].sum():.2f}")
    print(f"   总收益:          ${status_data['总收益'].sum():.2f}")
    print(f"   SOC范围:         {status_data['SOC'].min():.2%} ~ {status_data['SOC'].max():.2%}")

# 4. 辐照状态分析
print("\n" + "="*80)
print("☀️ 4. 辐照状态分析")
print("="*80)

for irr_status in sorted(df['辐照状态'].unique()):
    irr_data = df[df['辐照状态'] == irr_status]
    print(f"\n辐照状态 = {irr_status} ({len(irr_data)} 个时段, {len(irr_data)/len(df)*100:.1f}%)")
    print(f"   POA范围:         {irr_data['POA'].min():.1f} ~ {irr_data['POA'].max():.1f}")
    print(f"   平均POA:         {irr_data['POA'].mean():.1f}")
    print(f"   光伏发电总量:    {irr_data['光伏发电量'].sum():.2f} kWh")
    
    # 统计各充电状态的分布
    charge_dist = irr_data['充电状态'].value_counts().sort_index()
    print(f"   充电状态分布:")
    for cs, cnt in charge_dist.items():
        print(f"      状态{cs}: {cnt} 次")

# 5. 典型时段示例
print("\n" + "="*80)
print("📝 5. 典型时段示例")
print("="*80)

# 示例1: 充电状态=0
sample_0 = df[df['充电状态'] == 0].iloc[0]
print("\n示例1 - 充电状态=0 (无辐照/夜间):")
print(f"   时间: {sample_0['日期']}")
print(f"   POA: {sample_0['POA']}")
print(f"   充电状态: {sample_0['充电状态']}, 辐照状态: {sample_0['辐照状态']}")
print(f"   实际充电量: {sample_0['实际充电量']}, 实际放电量: {sample_0['实际放电量']}")
print(f"   光伏发电量: {sample_0['光伏发电量']}, 电网充电量: {sample_0['电网充电量']}")
print(f"   SOC: {sample_0['SOC']:.2%}, RRP: ${sample_0['电价RRP']:.4f}")
print(f"   总收益: ${sample_0['总收益']:.2f}")

# 示例2: 充电状态=340
sample_340 = df[df['充电状态'] == 340].iloc[0]
print("\n示例2 - 充电状态=340 (光伏直接并网):")
print(f"   时间: {sample_340['日期']}")
print(f"   POA: {sample_340['POA']}")
print(f"   充电状态: {sample_340['充电状态']}, 辐照状态: {sample_340['辐照状态']}")
print(f"   实际充电量: {sample_340['实际充电量']}, 实际放电量: {sample_340['实际放电量']}")
print(f"   光伏发电量: {sample_340['光伏发电量']}, 电网充电量: {sample_340['电网充电量']}")
print(f"   光伏收益: ${sample_340['光伏收益']:.2f}")
print(f"   SOC: {sample_340['SOC']:.2%}, RRP: ${sample_340['电价RRP']:.4f}")

# 示例3: 充电状态=341
sample_341 = df[df['充电状态'] == 341].iloc[0]
print("\n示例3 - 充电状态=341 (光伏充电):")
print(f"   时间: {sample_341['日期']}")
print(f"   POA: {sample_341['POA']}")
print(f"   充电状态: {sample_341['充电状态']}, 辐照状态: {sample_341['辐照状态']}")
print(f"   实际充电量: {sample_341['实际充电量']}, 实际放电量: {sample_341['实际放电量']}")
print(f"   光伏发电量: {sample_341['光伏发电量']}, 电网充电量: {sample_341['电网充电量']}")
print(f"   光伏收益: ${sample_341['光伏收益']:.2f}")
print(f"   SOC: {sample_341['SOC']:.2%}, RRP: ${sample_341['电价RRP']:.4f}")

# 示例4: 充电状态=342
if 342 in df['充电状态'].values:
    sample_342 = df[df['充电状态'] == 342].iloc[0]
    print("\n示例4 - 充电状态=342:")
    print(f"   时间: {sample_342['日期']}")
    print(f"   POA: {sample_342['POA']}")
    print(f"   充电状态: {sample_342['充电状态']}, 辐照状态: {sample_342['辐照状态']}")
    print(f"   实际充电量: {sample_342['实际充电量']}, 实际放电量: {sample_342['实际放电量']}")
    print(f"   光伏发电量: {sample_342['光伏发电量']}, 电网充电量: {sample_342['电网充电量']}")
    print(f"   电网收益: ${sample_342['电网收益']:.2f}, 电池收益: ${sample_342['电池收益']:.2f}")
    print(f"   SOC: {sample_342['SOC']:.2%}, RRP: ${sample_342['电价RRP']:.4f}")

# 示例5: 充电状态=343
if 343 in df['充电状态'].values:
    sample_343 = df[df['充电状态'] == 343].iloc[0]
    print("\n示例5 - 充电状态=343:")
    print(f"   时间: {sample_343['日期']}")
    print(f"   POA: {sample_343['POA']}")
    print(f"   充电状态: {sample_343['充电状态']}, 辐照状态: {sample_343['辐照状态']}")
    print(f"   实际充电量: {sample_343['实际充电量']}, 实际放电量: {sample_343['实际放电量']}")
    print(f"   光伏发电量: {sample_343['光伏发电量']}, 电网充电量: {sample_343['电网充电量']}")
    print(f"   电网收益: ${sample_343['电网收益']:.2f}, 电池收益: ${sample_343['电池收益']:.2f}")
    print(f"   SOC: {sample_343['SOC']:.2%}, RRP: ${sample_343['电价RRP']:.4f}")

# 6. 总体收益汇总
print("\n" + "="*80)
print("💰 6. 总体收益汇总")
print("="*80)
print(f"\n光伏总收益:      ${df['光伏收益'].sum():,.2f}")
print(f"电网总收益:      ${df['电网收益'].sum():,.2f}")
print(f"电池总收益:      ${df['电池收益'].sum():,.2f}")
print(f"总收益:          ${df['总收益'].sum():,.2f}")
print(f"\nPerfect Ratio平均: {df['perfect ratio'].mean():.4f}")

# 7. 能量平衡
print("\n" + "="*80)
print("⚡ 7. 能量平衡")
print("="*80)
print(f"\n光伏总发电:      {df['光伏发电量'].sum():,.2f} kWh")
print(f"电池总充电:      {df['实际充电量'].sum():,.2f} kWh")
print(f"电池总放电:      {df['实际放电量'].sum():,.2f} kWh")
print(f"电网充电:        {df['电网充电量'].sum():,.2f} kWh")
print(f"Real Export总量: {df['Real Export'].sum():,.2f} kWh")

print("\n" + "="*80)
print("分析完成!")
print("="*80)

