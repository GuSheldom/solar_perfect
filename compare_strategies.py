#!/usr/bin/env python3
"""
对比不同优化策略的结果
"""

import pandas as pd
import os

print("="*80)
print("优化策略对比分析")
print("="*80)

# 加载不同策略的结果
strategies = {
    'POA约束（线性规划）': 'optimization_results_poa_constraints/daily_summary.csv',
    '贪心放电策略V2': 'optimization_results_greedy_v2/daily_summary.csv'
}

results = {}
for name, file_path in strategies.items():
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        results[name] = df
        print(f"✓ 加载 {name}: {len(df)} 天")
    else:
        print(f"✗ 未找到 {name}")

print("\n" + "="*80)
print("收益对比")
print("="*80)

comparison = []

for name, df in results.items():
    total_revenue = df['Net_Revenue'].sum()
    avg_daily = df['Net_Revenue'].mean()
    max_daily = df['Net_Revenue'].max()
    min_daily = df['Net_Revenue'].min()
    annual_estimate = (total_revenue / len(df)) * 365
    
    comparison.append({
        '策略': name,
        '累计净收益': f"${total_revenue:,.2f}",
        '平均日收益': f"${avg_daily:,.2f}",
        '最高日收益': f"${max_daily:,.2f}",
        '最低日收益': f"${min_daily:,.2f}",
        '年化估算': f"${annual_estimate:,.2f}"
    })
    
    print(f"\n{name}:")
    print(f"  累计净收益: ${total_revenue:,.2f}")
    print(f"  平均日收益: ${avg_daily:,.2f}")
    print(f"  年化估算: ${annual_estimate:,.2f}/年")

# 加载详细数据进行能量对比
print("\n" + "="*80)
print("能量流对比")
print("="*80)

detailed_files = {
    'POA约束（线性规划）': 'optimization_results_poa_constraints/detailed_results.csv',
    '贪心放电策略V2': 'optimization_results_greedy_v2/detailed_results.csv'
}

energy_comparison = []

for name, file_path in detailed_files.items():
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        
        total_pv = df['PV_Energy_kWh'].sum()
        total_charge_pv = df['Charge_PV_kWh'].sum() if 'Charge_PV_kWh' in df.columns else 0
        total_charge_grid = df['Charge_Grid_kWh'].sum() if 'Charge_Grid_kWh' in df.columns else 0
        total_discharge = df['Discharge_kWh'].sum() if 'Discharge_kWh' in df.columns else 0
        total_export_pv = df['Export_PV_kWh'].sum() if 'Export_PV_kWh' in df.columns else 0
        total_export_battery = df['Export_Battery_kWh'].sum() if 'Export_Battery_kWh' in df.columns else 0
        total_curtail = df['Curtail_kWh'].sum() if 'Curtail_kWh' in df.columns else 0
        total_export = total_export_pv + total_export_battery
        
        energy_comparison.append({
            '策略': name,
            '光伏总发电': f"{total_pv:,.0f} kWh",
            '光伏用于充电': f"{total_charge_pv:,.0f} kWh ({total_charge_pv/total_pv*100:.1f}%)",
            '光伏直接上网': f"{total_export_pv:,.0f} kWh ({total_export_pv/total_pv*100:.1f}%)",
            '弃电': f"{total_curtail:,.0f} kWh ({total_curtail/total_pv*100:.1f}%)",
            '从电网购电': f"{total_charge_grid:,.0f} kWh",
            '总放电量': f"{total_discharge:,.0f} kWh",
            '储能上网': f"{total_export_battery:,.0f} kWh",
            '总上网量': f"{total_export:,.0f} kWh"
        })
        
        print(f"\n{name}:")
        print(f"  光伏总发电: {total_pv:,.0f} kWh")
        print(f"    用于充电: {total_charge_pv:,.0f} kWh ({total_charge_pv/total_pv*100:.1f}%)")
        print(f"    直接上网: {total_export_pv:,.0f} kWh ({total_export_pv/total_pv*100:.1f}%)")
        print(f"    弃电: {total_curtail:,.0f} kWh ({total_curtail/total_pv*100:.1f}%)")
        print(f"  从电网购电: {total_charge_grid:,.0f} kWh")
        print(f"  储能放电: {total_discharge:,.0f} kWh")
        print(f"  储能上网: {total_export_battery:,.0f} kWh")
        print(f"  总上网量: {total_export:,.0f} kWh")

# 保存对比结果
comparison_df = pd.DataFrame(comparison)
energy_df = pd.DataFrame(energy_comparison)

output_file = 'strategy_comparison.xlsx'
with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
    comparison_df.to_excel(writer, sheet_name='收益对比', index=False)
    energy_df.to_excel(writer, sheet_name='能量流对比', index=False)
    
    # 每日收益对比
    if len(results) >= 2:
        names = list(results.keys())
        daily_comp = pd.DataFrame({
            'Date': results[names[0]]['Date'],
            f'{names[0]}_收益': results[names[0]]['Net_Revenue'],
            f'{names[1]}_收益': results[names[1]]['Net_Revenue'] if len(names) > 1 else 0
        })
        if len(names) > 1:
            daily_comp['差异'] = daily_comp[f'{names[1]}_收益'] - daily_comp[f'{names[0]}_收益']
        daily_comp.to_excel(writer, sheet_name='每日收益对比', index=False)

print(f"\n对比结果已保存到: {output_file}")
print("="*80)

# 打印关键差异
print("\n关键差异分析:")
print("-"*80)

if len(results) >= 2:
    names = list(results.keys())
    rev1 = results[names[0]]['Net_Revenue'].sum()
    rev2 = results[names[1]]['Net_Revenue'].sum()
    diff = rev2 - rev1
    diff_pct = (diff / rev1) * 100
    
    print(f"\n{names[1]} vs {names[0]}:")
    print(f"  累计收益差异: ${diff:+,.2f} ({diff_pct:+.1f}%)")
    
    if 'POA约束（线性规划）' in detailed_files and '贪心放电策略V2' in detailed_files:
        df1 = pd.read_csv(detailed_files['POA约束（线性规划）'])
        df2 = pd.read_csv(detailed_files['贪心放电策略V2'])
        
        curtail1 = df1['Curtail_kWh'].sum()
        curtail2 = df2['Curtail_kWh'].sum()
        curtail_diff = curtail2 - curtail1
        
        discharge1 = df1['Discharge_kWh'].sum()
        discharge2 = df2['Discharge_kWh'].sum()
        discharge_diff = discharge2 - discharge1
        
        print(f"  弃电差异: {curtail_diff:+,.0f} kWh ({(curtail_diff/curtail1)*100:+.1f}%)")
        print(f"  放电差异: {discharge_diff:+,.0f} kWh ({(discharge_diff/discharge1)*100:+.1f}%)")

print("\n" + "="*80)

