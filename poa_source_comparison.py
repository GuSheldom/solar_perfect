#!/usr/bin/env python3
"""对比两种POA来源和计算方式"""

print("="*70)
print("POA数据来源对比")
print("="*70)

# 以2025-07-01 09:00为例
print("\n示例：2025-07-01 09:00:00")
print("-"*70)

print("\n【方法1】您代码中的方式 - 从真实POA计算PV功率")
print("-"*70)
real_poa = 616.8  # W/m² (Mannum传感器5分钟平均值)
capacity = 1000   # kW
efficiency = 0.17

pv_power_calculated = real_poa * capacity * efficiency / 1000
pv_energy_5min = pv_power_calculated * (5/60)

print(f"步骤1: 从Mannum传感器获取真实POA")
print(f"  → POA = {real_poa} W/m² (直接测量)")

print(f"\n步骤2: 使用标准公式计算PV功率")
print(f"  公式: PV功率 = POA × 容量 × 效率 / 1000")
print(f"  参数: 容量={capacity} kW, 效率={efficiency}")
print(f"  → PV功率 = {real_poa} × {capacity} × {efficiency} / 1000")
print(f"  → PV功率 = {pv_power_calculated:.2f} kW")

print(f"\n步骤3: 计算5分钟发电量")
print(f"  → 发电量 = {pv_power_calculated:.2f} × (5/60)")
print(f"  → 发电量 = {pv_energy_5min:.2f} kWh")

print("\n" + "="*70)
print("【方法2】Excel中的方式 - 从PV功率反推POA")
print("-"*70)

excel_energy = 178.76  # kWh (Excel中的值)
excel_pv_power = excel_energy / (5/60)
conversion_factor = 3.794
excel_poa = excel_pv_power / conversion_factor

print(f"步骤1: 获取光伏发电量（来源不明）")
print(f"  → 发电量 = {excel_energy} kWh")

print(f"\n步骤2: 计算PV功率")
print(f"  → PV功率 = {excel_energy} / (5/60)")
print(f"  → PV功率 = {excel_pv_power:.2f} kW")

print(f"\n步骤3: 使用固定系数反推POA")
print(f"  公式: POA = PV功率 / {conversion_factor}")
print(f"  → POA = {excel_pv_power:.2f} / {conversion_factor}")
print(f"  → POA = {excel_poa:.2f} W/m²")

print("\n" + "="*70)
print("两种方法的差异")
print("="*70)

print(f"\nPOA值:")
print(f"  代码方法（真实测量）: {real_poa:.2f} W/m²")
print(f"  Excel方法（反推）:    {excel_poa:.2f} W/m²")
print(f"  差异: {real_poa - excel_poa:.2f} W/m² ({(real_poa/excel_poa - 1)*100:+.1f}%)")

print(f"\nPV功率:")
print(f"  代码方法: {pv_power_calculated:.2f} kW")
print(f"  Excel方法: {excel_pv_power:.2f} kW")
print(f"  差异: {excel_pv_power - pv_power_calculated:.2f} kW ({(excel_pv_power/pv_power_calculated - 1)*100:+.1f}%)")

print(f"\n发电量:")
print(f"  代码方法: {pv_energy_5min:.2f} kWh")
print(f"  Excel方法: {excel_energy:.2f} kWh")
print(f"  差异: {excel_energy - pv_energy_5min:.2f} kWh ({(excel_energy/pv_energy_5min - 1)*100:+.1f}%)")

print("\n" + "="*70)
print("结论")
print("="*70)

print(f"\n1. POA数据来源不同：")
print(f"   代码：Mannum/SEN/SEN1/Radiation 传感器直接测量")
print(f"   Excel：从某个光伏发电量数据反推")

print(f"\n2. 计算方向相反：")
print(f"   代码：POA (测量) → 计算 → PV功率")
print(f"   Excel：PV功率 (已知) → 反推 → POA")

print(f"\n3. 转换系数差异：")
print(f"   代码系数：{efficiency} (POA to Power)")
print(f"   Excel系数：{conversion_factor} (Power to POA)")
print(f"   比例：{conversion_factor / efficiency:.2f}倍")

print(f"\n4. Excel的PV功率是代码的 {excel_pv_power/pv_power_calculated:.2f} 倍")
print(f"   这说明Excel可能使用了:")
print(f"   - 更大的装机容量")
print(f"   - 或不同的效率参数")
print(f"   - 或实际测量的发电量（已含所有系统损耗）")

print("\n" + "="*70)


