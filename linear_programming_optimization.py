#!/usr/bin/env python3
"""
线性规划优化模型 - 完美收益计算
基于完整业务逻辑，使用数学优化求解全局最优方案

时间范围：2025-07-01 09:00:00 到 2025-07-31 08:55:00
作者：AI Assistant
日期：2025-11-28
"""

import pandas as pd
import numpy as np
from pulp import *
import os
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

print("="*80)
print("线性规划优化模型 - 完美收益计算")
print("="*80)

# ==================== 配置参数 ====================
class OptimizationConfig:
    """优化模型配置参数"""
    
    # 电网限制
    NEL = 3880.0  # kW - 对电网最大输出功率
    NIL = 670.0   # kW - 从电网最大输入功率
    
    # 电池参数
    BATTERY_MAX_CHARGE_POWER = 670.0    # kW - 电池最大充电功率
    BATTERY_MAX_DISCHARGE_POWER = 2400.0  # kW - 电池最大放电功率
    BATTERY_CAPACITY = 4000.0  # kWh - 电池储能总量
    
    # 效率
    CHARGE_EFFICIENCY = 0.95   # 充电效率
    DISCHARGE_EFFICIENCY = 0.95  # 放电效率
    
    # 价格限制
    LGC = -10.0  # AUD/MWh - 对电网放电的最低价格
    
    # 光伏参数
    PV_CAPACITY = 1000.0  # kW - 光伏装机容量
    POA_TO_POWER_RATIO = 0.17  # POA与实际能量产出比
    
    # 时间参数
    INTERVAL_MINUTES = 5  # 数据间隔（分钟）
    INTERVAL_HOURS = INTERVAL_MINUTES / 60.0  # 数据间隔（小时）
    
    def print_config(self):
        """打印配置信息"""
        print("\n配置参数:")
        print(f"  电网输出限制(NEL): {self.NEL} kW")
        print(f"  电网输入限制(NIL): {self.NIL} kW")
        print(f"  电池充电功率: {self.BATTERY_MAX_CHARGE_POWER} kW")
        print(f"  电池放电功率: {self.BATTERY_MAX_DISCHARGE_POWER} kW")
        print(f"  电池容量: {self.BATTERY_CAPACITY} kWh")
        print(f"  充电效率: {self.CHARGE_EFFICIENCY * 100}%")
        print(f"  放电效率: {self.DISCHARGE_EFFICIENCY * 100}%")
        print(f"  LGC限制: {self.LGC} AUD/MWh")
        print(f"  光伏容量: {self.PV_CAPACITY} kW")
        print(f"  数据间隔: {self.INTERVAL_MINUTES} 分钟")

config = OptimizationConfig()
config.print_config()

# ==================== 加载数据 ====================
print("\n" + "="*80)
print("加载数据")
print("="*80)

data_file = 'merged_aemo_mannum_data.csv'

if not os.path.exists(data_file):
    print(f"\n错误: 找不到数据文件 {data_file}")
    print("请确保已运行以下脚本生成数据:")
    print("  1. process_mannum_simple.py")
    print("  2. merge_aemo_mannum_simple.py")
    exit(1)

print(f"\n加载文件: {data_file}")
df = pd.read_csv(data_file)
df['Timestamp'] = pd.to_datetime(df['Timestamp'])

# 筛选特定时间范围（与Excel 1117版本一致）
start_time = pd.to_datetime('2025-07-01 09:00:00')
end_time = pd.to_datetime('2025-07-31 08:55:00')

df_filtered = df[(df['Timestamp'] >= start_time) & (df['Timestamp'] <= end_time)].copy()
df_filtered = df_filtered.reset_index(drop=True)

print(f"\n时间范围: {start_time} 到 {end_time}")
print(f"数据行数: {len(df_filtered):,}")
print(f"覆盖天数: {df_filtered['Timestamp'].dt.date.nunique()}")
print(f"POA范围: {df_filtered['POA'].min():.2f} - {df_filtered['POA'].max():.2f} W/m²")
print(f"RRP范围: ${df_filtered['RRP'].min():.2f} - ${df_filtered['RRP'].max():.2f} /MWh")

# ==================== 计算光伏发电 ====================
print("\n计算光伏发电量...")

# 光伏功率 = POA × 光伏容量 × 转换比 / 1000
df_filtered['PV_Power_kW'] = (
    df_filtered['POA'] * config.PV_CAPACITY * config.POA_TO_POWER_RATIO
) / 1000.0

# 光伏能量 = 光伏功率 × 时间间隔
df_filtered['PV_Energy_kWh'] = df_filtered['PV_Power_kW'] * config.INTERVAL_HOURS

print(f"总光伏发电量: {df_filtered['PV_Energy_kWh'].sum():,.2f} kWh")

# ==================== 构建线性规划模型 ====================
print("\n" + "="*80)
print("构建线性规划模型")
print("="*80)

print("\n创建优化问题...")
prob = LpProblem("Battery_Optimization_Perfect_Revenue", LpMaximize)

# 时段索引
T = range(len(df_filtered))
print(f"优化时段数: {len(T):,}")

# ==================== 定义决策变量 ====================
print("\n定义决策变量...")

# 充电变量
charge_grid = [
    LpVariable(f"charge_grid_{t}", lowBound=0, 
               upBound=config.NIL * config.INTERVAL_HOURS) 
    for t in T
]  # 从电网充电能量 (kWh)

charge_pv = [
    LpVariable(f"charge_pv_{t}", lowBound=0, 
               upBound=df_filtered.loc[t, 'PV_Energy_kWh']) 
    for t in T
]  # 从光伏充电能量 (kWh)

# 放电变量
discharge = [
    LpVariable(f"discharge_{t}", lowBound=0, 
               upBound=config.BATTERY_MAX_DISCHARGE_POWER * config.INTERVAL_HOURS) 
    for t in T
]  # 放电能量 (kWh)

# 电池SOC
soc = [
    LpVariable(f"soc_{t}", lowBound=0, upBound=config.BATTERY_CAPACITY) 
    for t in T
]  # 电池电量 (kWh)

# 上网变量
export_pv = [
    LpVariable(f"export_pv_{t}", lowBound=0, 
               upBound=df_filtered.loc[t, 'PV_Energy_kWh']) 
    for t in T
]  # 光伏上网能量 (kWh)

export_battery = [
    LpVariable(f"export_battery_{t}", lowBound=0) 
    for t in T
]  # 储能上网能量 (kWh)

# 弃电变量
curtail = [
    LpVariable(f"curtail_{t}", lowBound=0, 
               upBound=df_filtered.loc[t, 'PV_Energy_kWh']) 
    for t in T
]  # 弃电量 (kWh)

print(f"  充电变量: {len(charge_grid) + len(charge_pv):,} 个")
print(f"  放电变量: {len(discharge):,} 个")
print(f"  SOC变量: {len(soc):,} 个")
print(f"  上网变量: {len(export_pv) + len(export_battery):,} 个")
print(f"  总决策变量: {len(T) * 7:,} 个")

# ==================== 定义目标函数 ====================
print("\n定义目标函数...")

# 最大化：上网收益 - 购电成本
revenue_terms = []
cost_terms = []

for t in T:
    rrp = df_filtered.loc[t, 'RRP']
    
    # 上网收益（转换为AUD：RRP单位是$/MWh，需要除以1000）
    revenue_terms.append((export_pv[t] + export_battery[t]) * rrp / 1000.0)
    
    # 购电成本
    cost_terms.append(charge_grid[t] * rrp / 1000.0)

prob += lpSum(revenue_terms) - lpSum(cost_terms), "Total_Revenue"
print("  目标: 最大化(上网收益 - 购电成本)")

# ==================== 定义约束条件 ====================
print("\n定义约束条件...")

# 1. 光伏能量平衡约束
print("  [1/5] 光伏能量平衡...")
for t in T:
    prob += (
        charge_pv[t] + export_pv[t] + curtail[t] == df_filtered.loc[t, 'PV_Energy_kWh'],
        f"PV_Balance_{t}"
    )

# 2. 电池SOC递推约束
print("  [2/5] 电池SOC递推...")
for t in T:
    if t == 0:
        # 初始SOC为0
        prob += (
            soc[t] == (charge_pv[t] + charge_grid[t]) * config.CHARGE_EFFICIENCY 
                      - discharge[t] / config.DISCHARGE_EFFICIENCY,
            f"SOC_Initial"
        )
    else:
        # SOC递推公式
        prob += (
            soc[t] == soc[t-1] 
                      + (charge_pv[t] + charge_grid[t]) * config.CHARGE_EFFICIENCY 
                      - discharge[t] / config.DISCHARGE_EFFICIENCY,
            f"SOC_{t}"
        )

# 3. 储能上网能量 = 放电能量 × 放电效率
print("  [3/5] 储能上网能量...")
for t in T:
    prob += (
        export_battery[t] == discharge[t] * config.DISCHARGE_EFFICIENCY,
        f"Battery_Export_{t}"
    )

# 4. 对电网输出功率限制 (NEL)
print("  [4/5] 电网输出限制(NEL)...")
for t in T:
    total_export_power = (export_pv[t] + export_battery[t]) / config.INTERVAL_HOURS
    prob += (
        total_export_power <= config.NEL,
        f"NEL_Limit_{t}"
    )

# 5. LGC限制：RRP <= -10 时不能上网
print("  [5/5] LGC限制...")
lgc_count = 0
for t in T:
    if df_filtered.loc[t, 'RRP'] <= config.LGC:
        prob += (export_pv[t] == 0, f"LGC_PV_{t}")
        prob += (export_battery[t] == 0, f"LGC_Battery_{t}")
        lgc_count += 1

print(f"      受LGC限制时段: {lgc_count} / {len(T)} ({lgc_count/len(T)*100:.1f}%)")

total_constraints = len(T) * 5  # 每个时段5类约束
print(f"\n  总约束数: {total_constraints:,} 个")

# ==================== 求解优化问题 ====================
print("\n" + "="*80)
print("求解优化问题")
print("="*80)

print("\n开始求解（这可能需要几秒到几分钟）...")
start_solve = datetime.now()

# 使用CBC求解器，设置10分钟超时
solver = PULP_CBC_CMD(msg=1, timeLimit=600)
prob.solve(solver)

end_solve = datetime.now()
solve_time = (end_solve - start_solve).total_seconds()

# ==================== 输出结果 ====================
status = LpStatus[prob.status]
print(f"\n求解状态: {status}")
print(f"求解时间: {solve_time:.1f} 秒")

if status != 'Optimal':
    print(f"\n错误: 优化失败，状态为 {status}")
    print("请检查约束条件是否合理")
    exit(1)

print("\n" + "="*80)
print("优化结果")
print("="*80)

# ==================== 提取结果 ====================
print("\n提取优化结果...")

results = []
for t in T:
    results.append({
        'Timestamp': df_filtered.loc[t, 'Timestamp'],
        'RRP': df_filtered.loc[t, 'RRP'],
        'POA': df_filtered.loc[t, 'POA'],
        'PV_Energy_kWh': df_filtered.loc[t, 'PV_Energy_kWh'],
        'Charge_PV_kWh': value(charge_pv[t]),
        'Charge_Grid_kWh': value(charge_grid[t]),
        'Discharge_kWh': value(discharge[t]),
        'Export_PV_kWh': value(export_pv[t]),
        'Export_Battery_kWh': value(export_battery[t]),
        'Curtail_kWh': value(curtail[t]),
        'SOC_kWh': value(soc[t]),
    })

results_df = pd.DataFrame(results)

# 计算收益
results_df['Export_Revenue'] = (
    (results_df['Export_PV_kWh'] + results_df['Export_Battery_kWh']) 
    * results_df['RRP'] / 1000.0
)
results_df['Charge_Cost'] = results_df['Charge_Grid_kWh'] * results_df['RRP'] / 1000.0
results_df['Net_Revenue'] = results_df['Export_Revenue'] - results_df['Charge_Cost']
results_df['Date'] = results_df['Timestamp'].dt.date.astype(str)

# ==================== 统计分析 ====================
print("\n收益统计:")
print("-"*80)

total_revenue = results_df['Net_Revenue'].sum()
total_export_revenue = results_df['Export_Revenue'].sum()
total_charge_cost = results_df['Charge_Cost'].sum()

print(f"累计净收益: ${total_revenue:,.2f}")
print(f"  上网收益: ${total_export_revenue:,.2f}")
print(f"  购电成本: ${total_charge_cost:,.2f}")

print("\n能量统计:")
print("-"*80)

total_pv = results_df['PV_Energy_kWh'].sum()
total_charge_pv = results_df['Charge_PV_kWh'].sum()
total_charge_grid = results_df['Charge_Grid_kWh'].sum()
total_charge = total_charge_pv + total_charge_grid
total_discharge = results_df['Discharge_kWh'].sum()
total_export = (results_df['Export_PV_kWh'] + results_df['Export_Battery_kWh']).sum()
total_curtail = results_df['Curtail_kWh'].sum()

print(f"光伏总发电: {total_pv:,.2f} kWh")
print(f"  用于充电: {total_charge_pv:,.2f} kWh ({total_charge_pv/total_pv*100:.1f}%)")
print(f"  直接上网: {results_df['Export_PV_kWh'].sum():,.2f} kWh ({results_df['Export_PV_kWh'].sum()/total_pv*100:.1f}%)")
print(f"  弃电: {total_curtail:,.2f} kWh ({total_curtail/total_pv*100:.1f}%)")

print(f"\n从电网购电: {total_charge_grid:,.2f} kWh")
print(f"总充电量: {total_charge:,.2f} kWh")
print(f"总放电量: {total_discharge:,.2f} kWh")
print(f"总上网量: {total_export:,.2f} kWh")

if total_charge > 0:
    # 理论效率 = 充电效率 × 放电效率
    theoretical_efficiency = config.CHARGE_EFFICIENCY * config.DISCHARGE_EFFICIENCY
    # 实际效率
    actual_efficiency = (total_discharge * config.DISCHARGE_EFFICIENCY) / (total_charge / config.CHARGE_EFFICIENCY)
    print(f"\n充放电效率: {actual_efficiency*100:.2f}% (理论: {theoretical_efficiency*100:.2f}%)")

# ==================== 每日汇总 ====================
print("\n每日统计:")
print("-"*80)

daily = results_df.groupby('Date').agg({
    'Net_Revenue': 'sum',
    'Export_Revenue': 'sum',
    'Charge_Cost': 'sum',
    'PV_Energy_kWh': 'sum',
    'Charge_PV_kWh': 'sum',
    'Charge_Grid_kWh': 'sum',
    'Discharge_kWh': 'sum',
    'Curtail_kWh': 'sum',
    'SOC_kWh': 'max'
}).reset_index()

daily.columns = [
    'Date', 'Net_Revenue', 'Export_Revenue', 'Charge_Cost',
    'PV_Total', 'Charge_PV', 'Charge_Grid', 'Discharge', 'Curtail', 'Max_SOC'
]

print(f"覆盖天数: {len(daily)}")
print(f"平均日收益: ${daily['Net_Revenue'].mean():,.2f}")
print(f"最高日收益: ${daily['Net_Revenue'].max():,.2f} ({daily.loc[daily['Net_Revenue'].idxmax(), 'Date']})")
print(f"最低日收益: ${daily['Net_Revenue'].min():,.2f} ({daily.loc[daily['Net_Revenue'].idxmin(), 'Date']})")

# 年化估算
annual_estimate = (total_revenue / len(daily)) * 365
print(f"\n年化估算: ${annual_estimate:,.2f}/年")

# ==================== 保存结果 ====================
print("\n" + "="*80)
print("保存结果")
print("="*80)

output_folder = 'optimization_results_final'
if not os.path.exists(output_folder):
    os.makedirs(output_folder)
    print(f"\n创建输出文件夹: {output_folder}/")

# 1. 详细时段数据
detail_file = f'{output_folder}/detailed_results.csv'
results_df.to_csv(detail_file, index=False, encoding='utf-8-sig')
print(f"\n[1] 保存详细时段数据: {detail_file}")
print(f"    ({len(results_df):,} 行 × {len(results_df.columns)} 列)")

# 2. 每日汇总
daily_file = f'{output_folder}/daily_summary.csv'
daily.to_csv(daily_file, index=False, encoding='utf-8-sig')
print(f"[2] 保存每日汇总: {daily_file}")
print(f"    ({len(daily)} 天)")

# 3. Excel格式对比文件
print(f"[3] 生成Excel格式对比文件...")

combined = pd.DataFrame()
combined['日期'] = results_df['Timestamp']
combined['POA'] = results_df['POA']
combined['PV功率'] = results_df['PV_Energy_kWh'] / config.INTERVAL_HOURS
combined['充电状态'] = np.where(
    (results_df['Charge_PV_kWh'] > 0.01) | (results_df['Charge_Grid_kWh'] > 0.01),
    340, np.where(results_df['Discharge_kWh'] > 0.01, 341, 0)
)
combined['电网状态'] = 350
combined['电池充电量'] = results_df['Charge_PV_kWh'] + results_df['Charge_Grid_kWh']
combined['电池放电量'] = results_df['Discharge_kWh']
combined['光伏发电量'] = results_df['PV_Energy_kWh']
combined['电网充电量'] = results_df['Charge_Grid_kWh']
combined['辐照状态'] = np.where(results_df['POA'] > 10, 321, 0)
combined['光伏收益'] = results_df['Export_PV_kWh'] * results_df['RRP'] / 1000.0
combined['电网收益'] = -results_df['Charge_Cost']
combined['电池收益'] = results_df['Export_Battery_kWh'] * results_df['RRP'] / 1000.0
combined['SOC'] = results_df['SOC_kWh'] / config.BATTERY_CAPACITY
combined['电价RRP'] = results_df['RRP'] / 1000.0
combined['总收益'] = results_df['Net_Revenue']
combined['总放电量'] = results_df['Export_PV_kWh'] + results_df['Export_Battery_kWh']
combined['Real Export'] = combined['总放电量']
combined['Revenue'] = results_df['Export_Revenue']

excel_file = f'{output_folder}/optimization_results.xlsx'
with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
    combined.to_excel(writer, sheet_name='优化结果', index=False)
    results_df.to_excel(writer, sheet_name='详细数据', index=False)
    daily.to_excel(writer, sheet_name='每日汇总', index=False)

print(f"    {excel_file}")
print(f"    (包含3个工作表)")

# 4. 生成报告
report_file = f'{output_folder}/optimization_report.txt'
report = []
report.append("="*80)
report.append("线性规划优化结果报告")
report.append("="*80)
report.append(f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
report.append(f"时间范围: {start_time} 到 {end_time}")
report.append(f"数据行数: {len(results_df):,}")
report.append(f"覆盖天数: {len(daily)}")
report.append(f"求解时间: {solve_time:.1f} 秒")

report.append("\n" + "-"*80)
report.append("收益统计")
report.append("-"*80)
report.append(f"累计净收益: ${total_revenue:,.2f}")
report.append(f"  上网收益: ${total_export_revenue:,.2f}")
report.append(f"  购电成本: ${total_charge_cost:,.2f}")
report.append(f"\n平均日收益: ${daily['Net_Revenue'].mean():,.2f}")
report.append(f"最高日收益: ${daily['Net_Revenue'].max():,.2f} ({daily.loc[daily['Net_Revenue'].idxmax(), 'Date']})")
report.append(f"最低日收益: ${daily['Net_Revenue'].min():,.2f} ({daily.loc[daily['Net_Revenue'].idxmin(), 'Date']})")

report.append("\n" + "-"*80)
report.append("年化估算")
report.append("-"*80)
report.append(f"估算年收益: ${annual_estimate:,.2f}")
report.append(f"估算月收益: ${annual_estimate/12:,.2f}")

report.append("\n" + "-"*80)
report.append("能量统计")
report.append("-"*80)
report.append(f"光伏总发电: {total_pv:,.2f} kWh")
report.append(f"  用于充电: {total_charge_pv:,.2f} kWh ({total_charge_pv/total_pv*100:.1f}%)")
report.append(f"  直接上网: {results_df['Export_PV_kWh'].sum():,.2f} kWh")
report.append(f"  弃电: {total_curtail:,.2f} kWh ({total_curtail/total_pv*100:.1f}%)")
report.append(f"\n从电网购电: {total_charge_grid:,.2f} kWh")
report.append(f"总充电量: {total_charge:,.2f} kWh")
report.append(f"总放电量: {total_discharge:,.2f} kWh")
report.append(f"总上网量: {total_export:,.2f} kWh")
if total_charge > 0:
    report.append(f"\n充放电效率: {actual_efficiency*100:.2f}%")

report.append("\n" + "="*80)

report_text = '\n'.join(report)

with open(report_file, 'w', encoding='utf-8') as f:
    f.write(report_text)

print(f"[4] 保存优化报告: {report_file}")

# ==================== 完成 ====================
print("\n" + "="*80)
print("优化完成！")
print("="*80)

print(f"\n所有结果已保存到: {output_folder}/")
print(f"  - detailed_results.csv: 每个5分钟时段的详细数据")
print(f"  - daily_summary.csv: 每日汇总统计")
print(f"  - optimization_results.xlsx: Excel格式（含3个工作表）")
print(f"  - optimization_report.txt: 完整优化报告")

print("\n关键指标:")
print(f"  累计总收益: ${total_revenue:,.2f}")
print(f"  平均日收益: ${daily['Net_Revenue'].mean():,.2f}")
print(f"  估算年收益: ${annual_estimate:,.2f}")

print("\n" + "="*80)

