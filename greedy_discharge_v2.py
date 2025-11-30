#!/usr/bin/env python3
"""
贪心放电策略优化模型 V2
更清晰的充放电逻辑，避免冲突
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

print("="*80)
print("贪心放电策略优化模型 V2")
print("="*80)

# ==================== 配置参数 ====================
class OptimizationConfig:
    """优化模型配置参数"""
    
    NEL = 4440.0  # kW
    NIL = 670.0   # kW
    BATTERY_CAPACITY = 5504.0  # kWh
    BATTERY_MAX_CHARGE_POWER = 2752.0  # kW
    BATTERY_MAX_DISCHARGE_POWER = 2752.0  # kW
    CHARGE_EFFICIENCY = 0.95
    DISCHARGE_EFFICIENCY = 0.95
    LGC = -10.0  # AUD/MWh
    POA_CHARGE_THRESHOLD = 10.0  # POA > 10 才能充电
    POA_DAYTIME_THRESHOLD = 5.0  # POA > 5 认为是白天
    INTERVAL_MINUTES = 5
    INTERVAL_HOURS = INTERVAL_MINUTES / 60.0

config = OptimizationConfig()

# ==================== 加载数据 ====================
excel_file = 'excel_1117.csv'
df = pd.read_csv(excel_file)
df.columns = df.columns.str.strip()
df['Timestamp'] = pd.to_datetime(df['日期'])
df = df.sort_values('Timestamp').reset_index(drop=True)

if df['电价RRP'].mean() < 1:
    df['RRP_MWh'] = df['电价RRP'] * 1000
else:
    df['RRP_MWh'] = df['电价RRP']

df['PV_Energy_kWh'] = df['光伏发电量']
df['PV_Power_kW'] = df['PV功率']
df['Date'] = df['Timestamp'].dt.date
df['Date_Str'] = df['Date'].astype(str)
df['Can_Charge'] = df['POA'] > config.POA_CHARGE_THRESHOLD
df['Is_Daytime'] = df['POA'] > config.POA_DAYTIME_THRESHOLD

print(f"\n数据加载完成: {len(df)} 行, {df['Date_Str'].nunique()} 天")

# ==================== 优化逻辑 ====================
def optimize_daily(day_data, next_day_data, soc_start):
    """
    每日优化策略：
    1. 先识别POA>10的可充电时段，按RRP从低到高排序，充满电池
    2. 从POA>5到次日POA>5的范围内，按RRP从高到低排序放电
    3. 充电时段不参与放电，放电时段不参与充电
    """
    
    day_results = []
    soc = soc_start
    
    # ==================== 阶段1：充电 ====================
    chargeable = day_data[day_data['Can_Charge']].copy()
    
    if len(chargeable) > 0 and soc < config.BATTERY_CAPACITY:
        # 按RRP从低到高排序（低价充电）
        chargeable = chargeable.sort_values('RRP_MWh')
        
        charged_indices = set()  # 记录已用于充电的时段
        
        for idx, row in chargeable.iterrows():
            if soc >= config.BATTERY_CAPACITY * 0.999:
                break  # 已充满
            
            # 计算可充电量
            available_capacity = config.BATTERY_CAPACITY - soc
            max_charge_power = config.BATTERY_MAX_CHARGE_POWER * config.INTERVAL_HOURS
            
            # 优先光伏充电
            pv_available = row['PV_Energy_kWh']
            charge_from_pv = min(pv_available, max_charge_power, 
                               available_capacity / config.CHARGE_EFFICIENCY)
            
            # 电网补充充电
            remaining_power = max_charge_power - charge_from_pv
            remaining_capacity = available_capacity - charge_from_pv * config.CHARGE_EFFICIENCY
            
            charge_from_grid = 0
            if remaining_capacity > 0.01 and remaining_power > 0.01:
                max_grid = config.NIL * config.INTERVAL_HOURS
                charge_from_grid = min(max_grid, remaining_power,
                                      remaining_capacity / config.CHARGE_EFFICIENCY)
            
            # 更新SOC
            total_charge = charge_from_pv + charge_from_grid
            soc += total_charge * config.CHARGE_EFFICIENCY
            
            # 剩余光伏处理
            remaining_pv = pv_available - charge_from_pv
            if row['RRP_MWh'] > config.LGC:
                export_pv = min(remaining_pv, config.NEL * config.INTERVAL_HOURS)
                curtail = max(0, remaining_pv - export_pv)
            else:
                export_pv = 0
                curtail = remaining_pv
            
            day_results.append({
                'index': idx,
                'Charge_PV_kWh': charge_from_pv,
                'Charge_Grid_kWh': charge_from_grid,
                'Discharge_kWh': 0,
                'Export_PV_kWh': export_pv,
                'Export_Battery_kWh': 0,
                'Curtail_kWh': curtail,
                'SOC_kWh': soc,
                'Action': 'Charging'
            })
            
            charged_indices.add(idx)
    else:
        charged_indices = set()
    
    # ==================== 阶段2：放电 ====================
    # 确定放电窗口：从当天POA>5到次日POA>5
    combined = pd.concat([day_data, next_day_data], ignore_index=False) if len(next_day_data) > 0 else day_data
    daytime_mask = combined['Is_Daytime']
    
    if daytime_mask.sum() > 0:
        first_daytime_idx = combined[daytime_mask].index[0]
        last_daytime_idx = combined[daytime_mask].index[-1]
        
        # 提取当天在窗口内的数据
        discharge_window = combined.loc[first_daytime_idx:last_daytime_idx]
        discharge_candidates = discharge_window[
            discharge_window.index.isin(day_data.index) &  # 只处理当天数据
            ~discharge_window.index.isin(charged_indices)  # 排除充电时段
        ].copy()
        
        if len(discharge_candidates) > 0 and soc > 0.01:
            # 按RRP从高到低排序（高价放电）
            discharge_candidates = discharge_candidates.sort_values('RRP_MWh', ascending=False)
            
            for idx, row in discharge_candidates.iterrows():
                if soc <= 0.01:
                    # 电池已空，剩余时段只处理光伏
                    if row['RRP_MWh'] > config.LGC:
                        export_pv = min(row['PV_Energy_kWh'], config.NEL * config.INTERVAL_HOURS)
                        curtail = max(0, row['PV_Energy_kWh'] - export_pv)
                    else:
                        export_pv = 0
                        curtail = row['PV_Energy_kWh']
                    
                    day_results.append({
                        'index': idx,
                        'Charge_PV_kWh': 0,
                        'Charge_Grid_kWh': 0,
                        'Discharge_kWh': 0,
                        'Export_PV_kWh': export_pv,
                        'Export_Battery_kWh': 0,
                        'Curtail_kWh': curtail,
                        'SOC_kWh': 0,
                        'Action': 'Battery_Empty'
                    })
                    continue
                
                # 检查电价
                if row['RRP_MWh'] <= config.LGC:
                    # 电价过低，不上网
                    day_results.append({
                        'index': idx,
                        'Charge_PV_kWh': 0,
                        'Charge_Grid_kWh': 0,
                        'Discharge_kWh': 0,
                        'Export_PV_kWh': 0,
                        'Export_Battery_kWh': 0,
                        'Curtail_kWh': row['PV_Energy_kWh'],
                        'SOC_kWh': soc,
                        'Action': 'Price_Too_Low'
                    })
                    continue
                
                pv_power = row['PV_Power_kW']
                is_daytime = row['Is_Daytime']
                
                discharge_energy = 0
                export_pv = 0
                curtail = 0
                
                if is_daytime:
                    # 白天：POA > 5
                    if pv_power >= config.NEL:
                        # 光伏功率充足，按NEL发电
                        export_pv = config.NEL * config.INTERVAL_HOURS
                        curtail = row['PV_Energy_kWh'] - export_pv
                        discharge_energy = 0
                        action = 'PV_Only'
                    else:
                        # 光伏不足，储能补充至NEL
                        export_pv = pv_power * config.INTERVAL_HOURS
                        
                        # 储能补充到NEL
                        needed_power = config.NEL - pv_power
                        max_discharge_power = min(config.BATTERY_MAX_DISCHARGE_POWER, needed_power)
                        max_discharge_energy = max_discharge_power * config.INTERVAL_HOURS
                        
                        # 考虑SOC限制
                        available_energy = soc * config.DISCHARGE_EFFICIENCY
                        discharge_energy = min(max_discharge_energy, 
                                             available_energy / config.DISCHARGE_EFFICIENCY)
                        
                        curtail = row['PV_Energy_kWh'] - export_pv
                        action = 'PV_Battery_Mix'
                else:
                    # 夜间：POA <= 5，按最大功率放电
                    max_discharge_energy = config.BATTERY_MAX_DISCHARGE_POWER * config.INTERVAL_HOURS
                    available_energy = soc * config.DISCHARGE_EFFICIENCY
                    discharge_energy = min(max_discharge_energy,
                                         available_energy / config.DISCHARGE_EFFICIENCY)
                    export_pv = 0
                    curtail = row['PV_Energy_kWh']  # 夜间通常POA=0
                    action = 'Battery_Only'
                
                # 更新SOC
                soc -= discharge_energy / config.DISCHARGE_EFFICIENCY
                soc = max(0, soc)
                
                export_battery = discharge_energy * config.DISCHARGE_EFFICIENCY
                
                day_results.append({
                    'index': idx,
                    'Charge_PV_kWh': 0,
                    'Charge_Grid_kWh': 0,
                    'Discharge_kWh': discharge_energy,
                    'Export_PV_kWh': export_pv,
                    'Export_Battery_kWh': export_battery,
                    'Curtail_kWh': curtail,
                    'SOC_kWh': soc,
                    'Action': action
                })
    
    # ==================== 阶段3：处理剩余时段 ====================
    # 处理既不充电也不放电的时段
    processed_indices = {r['index'] for r in day_results}
    
    for idx, row in day_data.iterrows():
        if idx not in processed_indices:
            # 只处理光伏
            if row['RRP_MWh'] > config.LGC:
                export_pv = min(row['PV_Energy_kWh'], config.NEL * config.INTERVAL_HOURS)
                curtail = max(0, row['PV_Energy_kWh'] - export_pv)
            else:
                export_pv = 0
                curtail = row['PV_Energy_kWh']
            
            day_results.append({
                'index': idx,
                'Charge_PV_kWh': 0,
                'Charge_Grid_kWh': 0,
                'Discharge_kWh': 0,
                'Export_PV_kWh': export_pv,
                'Export_Battery_kWh': 0,
                'Curtail_kWh': curtail,
                'SOC_kWh': soc,
                'Action': 'PV_Only_Idle'
            })
    
    return pd.DataFrame(day_results), soc

# ==================== 运行优化 ====================
print("\n开始运行优化...")

results = []
dates = sorted(df['Date_Str'].unique())
soc = config.BATTERY_CAPACITY * 0.5  # 初始50% SOC

for day_idx, date in enumerate(dates):
    day_data = df[df['Date_Str'] == date].copy()
    
    if day_idx + 1 < len(dates):
        next_date = dates[day_idx + 1]
        next_day_data = df[df['Date_Str'] == next_date].copy()
    else:
        next_day_data = pd.DataFrame()
    
    day_results_df, soc_end = optimize_daily(day_data, next_day_data, soc)
    
    # 合并到原始数据
    for idx, row in day_data.iterrows():
        if idx in day_results_df['index'].values:
            result_row = day_results_df[day_results_df['index'] == idx].iloc[0]
        else:
            # 理论上不应该到这里
            result_row = {
                'Charge_PV_kWh': 0, 'Charge_Grid_kWh': 0, 'Discharge_kWh': 0,
                'Export_PV_kWh': 0, 'Export_Battery_kWh': 0, 'Curtail_kWh': row['PV_Energy_kWh'],
                'SOC_kWh': soc, 'Action': 'Error'
            }
        
        results.append({
            'Timestamp': row['Timestamp'],
            'Date': row['Date_Str'],
            'RRP_MWh': row['RRP_MWh'],
            'POA': row['POA'],
            'PV_Power_kW': row['PV_Power_kW'],
            'PV_Energy_kWh': row['PV_Energy_kWh'],
            'Charge_PV_kWh': result_row['Charge_PV_kWh'],
            'Charge_Grid_kWh': result_row['Charge_Grid_kWh'],
            'Discharge_kWh': result_row['Discharge_kWh'],
            'Export_PV_kWh': result_row['Export_PV_kWh'],
            'Export_Battery_kWh': result_row['Export_Battery_kWh'],
            'Curtail_kWh': result_row['Curtail_kWh'],
            'SOC_kWh': result_row['SOC_kWh'],
            'Action': result_row['Action']
        })
    
    soc = soc_end
    if (day_idx + 1) % 5 == 0:
        print(f"  处理完成 {day_idx+1}/{len(dates)} 天, 当前SOC: {soc:.1f} kWh ({soc/config.BATTERY_CAPACITY*100:.1f}%)")

# ==================== 计算结果 ====================
results_df = pd.DataFrame(results)

results_df['Export_Revenue'] = (
    (results_df['Export_PV_kWh'] + results_df['Export_Battery_kWh']) 
    * results_df['RRP_MWh'] / 1000.0
)
results_df['Charge_Cost'] = results_df['Charge_Grid_kWh'] * results_df['RRP_MWh'] / 1000.0
results_df['Net_Revenue'] = results_df['Export_Revenue'] - results_df['Charge_Cost']
results_df['SOC_Percent'] = results_df['SOC_kWh'] / config.BATTERY_CAPACITY * 100

# ==================== 统计输出 ====================
print("\n" + "="*80)
print("优化结果统计")
print("="*80)

total_revenue = results_df['Net_Revenue'].sum()
total_export_revenue = results_df['Export_Revenue'].sum()
total_charge_cost = results_df['Charge_Cost'].sum()

print(f"\n收益统计:")
print(f"  累计净收益: ${total_revenue:,.2f}")
print(f"  上网收益: ${total_export_revenue:,.2f}")
print(f"  购电成本: ${total_charge_cost:,.2f}")

total_pv = results_df['PV_Energy_kWh'].sum()
total_charge_pv = results_df['Charge_PV_kWh'].sum()
total_charge_grid = results_df['Charge_Grid_kWh'].sum()
total_charge = total_charge_pv + total_charge_grid
total_discharge = results_df['Discharge_kWh'].sum()
total_export_pv = results_df['Export_PV_kWh'].sum()
total_export_battery = results_df['Export_Battery_kWh'].sum()
total_export = total_export_pv + total_export_battery
total_curtail = results_df['Curtail_kWh'].sum()

print(f"\n能量统计:")
print(f"  光伏总发电: {total_pv:,.2f} kWh")
print(f"    用于充电: {total_charge_pv:,.2f} kWh ({total_charge_pv/total_pv*100:.1f}%)")
print(f"    直接上网: {total_export_pv:,.2f} kWh ({total_export_pv/total_pv*100:.1f}%)")
print(f"    弃电: {total_curtail:,.2f} kWh ({total_curtail/total_pv*100:.1f}%)")
print(f"  从电网购电: {total_charge_grid:,.2f} kWh")
print(f"  总充电量: {total_charge:,.2f} kWh")
print(f"  总放电量: {total_discharge:,.2f} kWh")
print(f"  储能上网: {total_export_battery:,.2f} kWh")
print(f"  总上网量: {total_export:,.2f} kWh")

print(f"\n动作统计:")
action_counts = results_df['Action'].value_counts()
for action, count in action_counts.items():
    print(f"  {action}: {count} ({count/len(results_df)*100:.1f}%)")

# 每日汇总
daily = results_df.groupby('Date').agg({
    'Net_Revenue': 'sum',
    'Export_Revenue': 'sum',
    'Charge_Cost': 'sum',
    'PV_Energy_kWh': 'sum',
    'Discharge_kWh': 'sum',
    'Export_Battery_kWh': 'sum',
    'Curtail_kWh': 'sum',
    'SOC_kWh': 'last'
}).reset_index()

daily.columns = ['Date', 'Net_Revenue', 'Export_Revenue', 'Charge_Cost',
                'PV_Total', 'Discharge', 'Export_Battery', 'Curtail', 'End_SOC_kWh']
daily['End_SOC_Percent'] = daily['End_SOC_kWh'] / config.BATTERY_CAPACITY * 100

print(f"\n每日统计:")
print(f"  平均日收益: ${daily['Net_Revenue'].mean():,.2f}")
print(f"  最高日收益: ${daily['Net_Revenue'].max():,.2f}")
print(f"  最低日收益: ${daily['Net_Revenue'].min():,.2f}")
print(f"  年化估算: ${(total_revenue / len(daily)) * 365:,.2f}/年")

# 保存结果
output_folder = 'optimization_results_greedy_v2'
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

results_df.to_csv(f'{output_folder}/detailed_results.csv', index=False, encoding='utf-8-sig')
daily.to_csv(f'{output_folder}/daily_summary.csv', index=False, encoding='utf-8-sig')

with pd.ExcelWriter(f'{output_folder}/optimization_results.xlsx', engine='openpyxl') as writer:
    results_df.to_excel(writer, sheet_name='详细数据', index=False)
    daily.to_excel(writer, sheet_name='每日汇总', index=False)

print(f"\n结果已保存到 {output_folder}/ 文件夹")
print("="*80)

