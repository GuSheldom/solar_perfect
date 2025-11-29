import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']  # 用来正常显示中文标签
plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号

# 读取数据
df = pd.read_csv('extracted_data.csv')

# 计算POA与PV功率的比值（PV功率 / POA）
# 只计算POA > 0的情况，避免除以0
df['PV_Power_per_POA'] = df['PV_Power'] / df['POA']

# 过滤掉POA太小的数据（比如小于100 W/m²）以获得更有意义的比值
df_filtered = df[df['POA'] > 100].copy()

print("=" * 60)
print("POA与实际能量产出比分析")
print("=" * 60)

print("\n数据统计：")
print(f"总数据量: {len(df)} 条")
print(f"有效数据量 (POA > 100): {len(df_filtered)} 条")

print("\n数据范围：")
print(f"POA范围: {df['POA'].min():.2f} ~ {df['POA'].max():.2f} W/m²")
print(f"PV功率范围: {df['PV_Power'].min():.2f} ~ {df['PV_Power'].max():.2f} W")

print("\nPV功率/POA 比值统计 (POA > 100)：")
print(f"平均值: {df_filtered['PV_Power_per_POA'].mean():.4f} W/(W/m²)")
print(f"中位数: {df_filtered['PV_Power_per_POA'].median():.4f} W/(W/m²)")
print(f"标准差: {df_filtered['PV_Power_per_POA'].std():.4f}")
print(f"最小值: {df_filtered['PV_Power_per_POA'].min():.4f}")
print(f"最大值: {df_filtered['PV_Power_per_POA'].max():.4f}")

print("\n示例数据（前10条有效数据）：")
sample_df = df_filtered.head(10)[['Date', 'POA', 'PV_Power', 'PV_Power_per_POA']]
print(sample_df.to_string(index=False))

# 如果假设光伏阵列面积为A（m²），组件效率为η
# 则理论功率 = POA × A × η
# 实际测得 PV_Power / POA ≈ A × η × 系统效率
print("\n" + "=" * 60)
print("物理意义解释：")
print("=" * 60)
print("PV功率/POA 比值 ≈ 光伏阵列面积 × 组件效率 × 系统效率")
print(f"\n根据您的数据，该比值约为: {df_filtered['PV_Power_per_POA'].mean():.2f} W/(W/m²)")
print("\n这个比值相当于光伏阵列的有效发电面积（考虑了所有损失因素）")

# 创建可视化
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle('POA与PV功率关系分析', fontsize=16, fontweight='bold')

# 1. POA vs PV功率散点图
ax1 = axes[0, 0]
ax1.scatter(df_filtered['POA'], df_filtered['PV_Power'], alpha=0.3, s=1)
ax1.set_xlabel('POA (W/m²)', fontsize=11)
ax1.set_ylabel('PV功率 (W)', fontsize=11)
ax1.set_title('POA与PV功率关系', fontsize=12)
ax1.grid(True, alpha=0.3)

# 添加线性拟合
z = np.polyfit(df_filtered['POA'], df_filtered['PV_Power'], 1)
p = np.poly1d(z)
ax1.plot(df_filtered['POA'], p(df_filtered['POA']), "r--", 
         label=f'拟合: y={z[0]:.2f}x+{z[1]:.2f}', linewidth=2)
ax1.legend()

# 2. PV功率/POA比值分布直方图
ax2 = axes[0, 1]
ax2.hist(df_filtered['PV_Power_per_POA'], bins=50, edgecolor='black', alpha=0.7)
ax2.axvline(df_filtered['PV_Power_per_POA'].mean(), color='r', 
            linestyle='--', linewidth=2, label=f'平均值: {df_filtered["PV_Power_per_POA"].mean():.3f}')
ax2.set_xlabel('PV功率/POA (W/(W/m²))', fontsize=11)
ax2.set_ylabel('频次', fontsize=11)
ax2.set_title('功率比值分布', fontsize=12)
ax2.legend()
ax2.grid(True, alpha=0.3, axis='y')

# 3. 时间序列 - POA
ax3 = axes[1, 0]
df_filtered['DateTime'] = pd.to_datetime(df_filtered['Date'])
sample_days = df_filtered.iloc[:288*3]  # 显示前3天的数据
ax3.plot(range(len(sample_days)), sample_days['POA'], linewidth=1)
ax3.set_xlabel('时间索引 (5分钟间隔)', fontsize=11)
ax3.set_ylabel('POA (W/m²)', fontsize=11)
ax3.set_title('POA时间序列（前3天）', fontsize=12)
ax3.grid(True, alpha=0.3)

# 4. 时间序列 - PV功率/POA比值
ax4 = axes[1, 1]
ax4.plot(range(len(sample_days)), sample_days['PV_Power_per_POA'], linewidth=1, color='green')
ax4.axhline(df_filtered['PV_Power_per_POA'].mean(), color='r', 
            linestyle='--', linewidth=2, alpha=0.7)
ax4.set_xlabel('时间索引 (5分钟间隔)', fontsize=11)
ax4.set_ylabel('PV功率/POA', fontsize=11)
ax4.set_title('功率比值时间序列（前3天）', fontsize=12)
ax4.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('poa_power_analysis.png', dpi=300, bbox_inches='tight')
print(f"\n图表已保存为: poa_power_analysis.png")

# 保存分析结果到CSV
analysis_df = df[['Date', 'POA', 'PV_Power', 'RRP']].copy()
analysis_df['PV_Power_per_POA'] = df['PV_Power_per_POA']
analysis_df.to_csv('poa_power_ratio_analysis.csv', index=False, encoding='utf-8')
print(f"详细分析数据已保存为: poa_power_ratio_analysis.csv")


