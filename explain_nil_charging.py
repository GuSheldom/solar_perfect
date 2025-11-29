import pandas as pd
import numpy as np

# 读取原始数据
df = pd.read_csv('excel_1117版本.csv', encoding='utf-8')

# 查看列名
print("数据列名：")
print(df.columns.tolist())
print("\n" + "="*80)

# 假设参数（根据您的数据推断）
BATTERY_MAX_CHARGE_POWER = 250  # 电池最大充电功率 (kW)，需要根据实际调整
POA_TO_POWER_RATIO = 3.79  # POA到功率的转换比例（之前计算的）

# 提取关键列并重命名
df_analysis = df[['日期', 'POA', 'PV功率', '充电状态', '电网状态', 
                   '实际充电量', '电网充电量', '光伏发电量', '电价RRP']].copy()

# 计算POA推算的发电功率（单位换算：W转kW）
df_analysis['POA推算功率_kW'] = df_analysis['POA'] * POA_TO_POWER_RATIO / 1000

# 查看几行实际数据
print("\n原始数据示例（前5行）：")
print(df_analysis.head().to_string())

print("\n" + "="*80)
print("NIL充电策略解释")
print("="*80)

# 筛选一个具体的例子来说明
# 找到光伏发电但充电功率小于最大值的时刻
sample_row = df_analysis[
    (df_analysis['POA'] > 0) & 
    (df_analysis['POA'] < 500)
].iloc[0] if len(df_analysis[(df_analysis['POA'] > 0) & (df_analysis['POA'] < 500)]) > 0 else df_analysis.iloc[10]

print(f"\n示例时刻: {sample_row['日期']}")
print(f"POA辐照度: {sample_row['POA']:.2f} W/m²")
print(f"POA推算发电功率: {sample_row['POA推算功率_kW']:.2f} kW")
print(f"PV实际功率: {sample_row['PV功率']:.2f} W = {sample_row['PV功率']/1000:.2f} kW")
print(f"电价RRP: ${sample_row['电价RRP']:.4f}/kWh")

# 计算NIL
poa_power_kw = sample_row['POA推算功率_kW']
if poa_power_kw < BATTERY_MAX_CHARGE_POWER:
    NIL = BATTERY_MAX_CHARGE_POWER - poa_power_kw
    print(f"\n{'='*80}")
    print("NIL计算逻辑：")
    print(f"{'='*80}")
    print(f"✓ 条件：POA推算功率 ({poa_power_kw:.2f} kW) < 电池最大充电功率 ({BATTERY_MAX_CHARGE_POWER} kW)")
    print(f"✓ NIL（从电网补充充电功率）= {BATTERY_MAX_CHARGE_POWER} - {poa_power_kw:.2f} = {NIL:.2f} kW")
    print(f"✓ 总充电功率 = {poa_power_kw:.2f} + {NIL:.2f} = {BATTERY_MAX_CHARGE_POWER:.2f} kW ✓")
    
    # 计算成本/收益
    time_interval_hours = 5/60  # 5分钟 = 5/60小时
    energy_from_grid = NIL * time_interval_hours  # kWh
    cost = energy_from_grid * sample_row['电价RRP']
    
    print(f"\n{'='*80}")
    print("成本/收益计算（5分钟时间段）：")
    print(f"{'='*80}")
    print(f"从电网充电能量: {energy_from_grid:.4f} kWh")
    print(f"电价: ${sample_row['电价RRP']:.4f}/kWh")
    
    if sample_row['电价RRP'] >= 0:
        print(f"充电成本: ${cost:.4f}")
    else:
        print(f"充电收益: ${abs(cost):.4f} (负电价，充电获得收益！)")

print("\n" + "="*80)
print("NIL策略的应用场景")
print("="*80)
print("""
1. **正电价时**：
   - 如果电价低廉，可以从电网补充充电以充分利用电池容量
   - 为后续高电价时段的放电做准备
   
2. **负电价时（最重要）**：
   - 充电不仅不花钱，还能获得收益！
   - 应该最大化从电网充电：NIL应该尽可能大
   - 约束：POA发电 + NIL ≤ 电池最大充电功率
   
3. **优化目标**：
   - 在负电价时段：最大化总充电功率（光伏+电网）
   - 在低电价时段：考虑套利机会，储能以待高价时段放电
""")

# 查找负电价时段
negative_price = df_analysis[df_analysis['电价RRP'] < 0]
print(f"\n数据中负电价时段数量: {len(negative_price)} 个")

if len(negative_price) > 0:
    print("\n负电价时段示例（前3个）：")
    for idx, row in negative_price.head(3).iterrows():
        poa_kw = row['POA'] * POA_TO_POWER_RATIO / 1000
        potential_nil = max(0, BATTERY_MAX_CHARGE_POWER - poa_kw)
        print(f"\n时间: {row['日期']}")
        print(f"  电价: ${row['电价RRP']:.4f}/kWh (负电价！)")
        print(f"  POA发电: {poa_kw:.2f} kW")
        print(f"  可从电网充电(NIL): {potential_nil:.2f} kW")
        print(f"  5分钟充电收益: ${abs(potential_nil * (5/60) * row['电价RRP']):.4f}")

print("\n" + "="*80)
print("总结")
print("="*80)
print("""
NIL = Network Import Level（从电网导入的功率）

含义：当光伏发电不足以达到电池最大充电功率时，从电网补充充电的功率

计算公式：
  NIL = 电池最大充电功率 - POA推算发电功率
  
约束条件：
  NIL + POA发电功率 ≤ 电池最大充电功率
  NIL ≥ 0
  
决策逻辑：
  - 负电价时：NIL应该尽可能大（最大化充电获利）
  - 低电价时：根据套利空间决定NIL
  - 高电价时：NIL = 0（不从电网充电）
""")


