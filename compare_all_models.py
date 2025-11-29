#!/usr/bin/env python3
"""
对比所有模型的结果
"""

import pandas as pd
import numpy as np

print("="*80)
print("三模型对比分析")
print("="*80)

# 加载三个模型的结果
print("\n加载数据...")

# 1. 无POA约束模型
no_poa = pd.read_csv('optimization_results_new_params/detailed_results.csv')
print(f"[1] 无POA约束模型: {len(no_poa)} 行")

# 2. 带POA约束模型
with_poa = pd.read_csv('optimization_results_poa_constraints/detailed_results.csv')
print(f"[2] 带POA约束模型: {len(with_poa)} 行")

# 3. Excel 1117版本
excel_orig = pd.read_csv('excel_1117版本.csv')
excel_orig.columns = excel_orig.columns.str.strip()
print(f"[3] Excel 1117版本: {len(excel_orig)} 行")

# ==================== 收益对比 ====================
print("\n" + "="*80)
print("收益对比（31天，7月1日-31日）")
print("="*80)

comparison = pd.DataFrame({
    '模型': [
        'Excel 1117版本',
        'LP无POA约束',
        'LP带POA约束',
    ],
    '累计净收益': [
        excel_orig['总收益'].sum(),
        no_poa['Net_Revenue'].sum(),
        with_poa['Net_Revenue'].sum(),
    ],
    '平均日收益': [
        excel_orig['总收益'].sum() / 31,
        no_poa['Net_Revenue'].sum() / 31,
        with_poa['Net_Revenue'].sum() / 31,
    ]
})

comparison['年化收益'] = comparison['平均日收益'] * 365
comparison['vs Excel (%)'] = (comparison['累计净收益'] / comparison.loc[0, '累计净收益'] - 1) * 100
comparison['vs 无POA (%)'] = (comparison['累计净收益'] / comparison.loc[1, '累计净收益'] - 1) * 100

print("\n收益汇总:")
print(comparison.to_string(index=False))

# ==================== 能量对比 ====================
print("\n" + "="*80)
print("能量流动对比")
print("="*80)

energy_comparison = pd.DataFrame({
    '模型': [
        'Excel 1117版本',
        'LP无POA约束',
        'LP带POA约束',
    ],
    '光伏发电': [
        excel_orig['光伏发电量'].sum(),
        no_poa['PV_Energy_kWh'].sum(),
        with_poa['PV_Energy_kWh'].sum(),
    ],
    '总充电量': [
        excel_orig['实际充电量'].sum(),
        (no_poa['Charge_PV_kWh'] + no_poa['Charge_Grid_kWh']).sum(),
        (with_poa['Charge_PV_kWh'] + with_poa['Charge_Grid_kWh']).sum(),
    ],
    '总放电量': [
        excel_orig['实际放电量'].sum(),
        no_poa['Discharge_kWh'].sum(),
        with_poa['Discharge_kWh'].sum(),
    ],
    '从电网购电': [
        excel_orig['电网充电量'].sum(),
        no_poa['Charge_Grid_kWh'].sum(),
        with_poa['Charge_Grid_kWh'].sum(),
    ],
})

energy_comparison['充放电效率'] = (
    energy_comparison['总放电量'] * 0.95 / 
    (energy_comparison['总充电量'] / 0.95) * 100
)

print("\n能量统计:")
print(energy_comparison.to_string(index=False))

# ==================== POA约束验证 ====================
print("\n" + "="*80)
print("POA约束验证")
print("="*80)

print("\n[无POA约束模型]")
no_poa['Can_Charge'] = no_poa['POA'] > 10
charge_in_poa_no = (
    no_poa[no_poa['Can_Charge']]['Charge_PV_kWh'].sum() + 
    no_poa[no_poa['Can_Charge']]['Charge_Grid_kWh'].sum()
)
charge_out_poa_no = (
    no_poa[~no_poa['Can_Charge']]['Charge_PV_kWh'].sum() + 
    no_poa[~no_poa['Can_Charge']]['Charge_Grid_kWh'].sum()
)
total_charge_no = charge_in_poa_no + charge_out_poa_no

print(f"  POA > 10时充电: {charge_in_poa_no:,.2f} kWh ({charge_in_poa_no/total_charge_no*100:.1f}%)")
print(f"  POA <= 10时充电: {charge_out_poa_no:,.2f} kWh ({charge_out_poa_no/total_charge_no*100:.1f}%)")

print("\n[带POA约束模型]")
charge_in_poa_with = (
    with_poa[with_poa['Can_Charge']]['Charge_PV_kWh'].sum() + 
    with_poa[with_poa['Can_Charge']]['Charge_Grid_kWh'].sum()
)
charge_out_poa_with = (
    with_poa[~with_poa['Can_Charge']]['Charge_PV_kWh'].sum() + 
    with_poa[~with_poa['Can_Charge']]['Charge_Grid_kWh'].sum()
)
total_charge_with = charge_in_poa_with + charge_out_poa_with

print(f"  POA > 10时充电: {charge_in_poa_with:,.2f} kWh ({charge_in_poa_with/total_charge_with*100:.1f}%)")
print(f"  POA <= 10时充电: {charge_out_poa_with:,.2f} kWh ({charge_out_poa_with/total_charge_with*100:.1f}%)")
print(f"  ✓ POA约束{'有效' if charge_out_poa_with < 0.01 else '失效'}")

# ==================== 每日对比 ====================
print("\n" + "="*80)
print("每日收益对比（前10天）")
print("="*80)

no_poa['Date'] = pd.to_datetime(no_poa['Timestamp']).dt.date.astype(str)
with_poa['Date'] = pd.to_datetime(with_poa['Timestamp']).dt.date.astype(str)
excel_orig['Date'] = pd.to_datetime(excel_orig['日期']).dt.date.astype(str)

daily_no_poa = no_poa.groupby('Date')['Net_Revenue'].sum()
daily_with_poa = with_poa.groupby('Date')['Net_Revenue'].sum()
daily_excel = excel_orig.groupby('Date')['总收益'].sum()

daily_comp = pd.DataFrame({
    'Date': daily_excel.index,
    'Excel': daily_excel.values,
    'LP无POA': daily_no_poa.values,
    'LP带POA': daily_with_poa.values,
})

daily_comp['最优'] = daily_comp[['Excel', 'LP无POA', 'LP带POA']].idxmax(axis=1)

print("\n前10天每日收益:")
print(daily_comp.head(10).to_string(index=False))

# 统计哪个模型最优的天数
print(f"\n最优模型统计:")
for model in ['Excel', 'LP无POA', 'LP带POA']:
    count = (daily_comp['最优'] == model).sum()
    print(f"  {model}: {count} 天 ({count/31*100:.1f}%)")

# ==================== 关键结论 ====================
print("\n" + "="*80)
print("关键结论")
print("="*80)

print("\n1. 收益对比:")
print(f"   - LP无POA约束: ${no_poa['Net_Revenue'].sum():,.2f} (基准)")
print(f"   - LP带POA约束: ${with_poa['Net_Revenue'].sum():,.2f} ({(with_poa['Net_Revenue'].sum()/no_poa['Net_Revenue'].sum()-1)*100:+.1f}%)")
print(f"   - POA约束导致收益下降: ${no_poa['Net_Revenue'].sum() - with_poa['Net_Revenue'].sum():,.2f}")

print("\n2. POA约束影响:")
print(f"   - 无POA约束模型在夜间充电: {charge_out_poa_no:,.2f} kWh")
print(f"   - 这部分夜间充电贡献额外收益: ~${no_poa['Net_Revenue'].sum() - with_poa['Net_Revenue'].sum():,.0f}")

print("\n3. 充电策略差异:")
print(f"   - 无POA约束: 总充电 {energy_comparison.loc[1, '总充电量']:,.0f} kWh")
print(f"   - 带POA约束: 总充电 {energy_comparison.loc[2, '总充电量']:,.0f} kWh")
print(f"   - 差异: {energy_comparison.loc[1, '总充电量'] - energy_comparison.loc[2, '总充电量']:,.0f} kWh")

print("\n4. 年化收益估算:")
print(f"   - LP无POA约束: ${comparison.loc[1, '年化收益']:,.2f}/年")
print(f"   - LP带POA约束: ${comparison.loc[2, '年化收益']:,.2f}/年")

print("\n" + "="*80)

# 保存对比结果
output_file = 'model_comparison_summary.xlsx'
with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
    comparison.to_excel(writer, sheet_name='收益对比', index=False)
    energy_comparison.to_excel(writer, sheet_name='能量对比', index=False)
    daily_comp.to_excel(writer, sheet_name='每日对比', index=False)

print(f"\n对比结果已保存: {output_file}")
print("="*80)

