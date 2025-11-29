"""
线性规划模型复杂度分析
解释为什么需要这么多变量和约束
"""

import pandas as pd
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

def analyze_model_complexity():
    """分析模型复杂度"""
    
    n_periods = 8640  # 时间段数
    
    print("="*80)
    print("线性规划模型复杂度分析")
    print("="*80)
    
    print(f"\n📊 基本信息:")
    print(f"   时间段数: {n_periods:,} 个")
    print(f"   时间跨度: 30天")
    print(f"   时间分辨率: 5分钟")
    
    # 决策变量分析
    print(f"\n🔢 决策变量分析:")
    print(f"\n每个时间段 t 的连续变量（6个）:")
    print(f"   1. P_charge[t]        - 电池充电功率 (kW)")
    print(f"   2. P_discharge[t]     - 电池放电功率 (kW)")
    print(f"   3. P_grid_import[t]   - 从电网导入功率(NIL) (kW)")
    print(f"   4. P_grid_export[t]   - 向电网输出功率(NEL) (kW)")
    print(f"   5. is_charging[t]     - 是否充电 (0或1)")
    print(f"   6. is_discharging[t]  - 是否放电 (0或1)")
    
    vars_per_period = 6
    total_period_vars = n_periods * vars_per_period
    
    print(f"\n   小计: {n_periods:,} × {vars_per_period} = {total_period_vars:,} 个")
    
    print(f"\n全局状态变量:")
    print(f"   SOC[0] 到 SOC[{n_periods}] - 电池荷电状态")
    
    soc_vars = n_periods + 1
    total_vars = total_period_vars + soc_vars
    
    print(f"   小计: {soc_vars:,} 个")
    
    print(f"\n✅ 决策变量总数: {total_vars:,} 个")
    print(f"   ├─ 连续变量: {n_periods * 4 + soc_vars:,} 个")
    print(f"   └─ 二进制变量: {n_periods * 2:,} 个")
    
    # 约束条件分析
    print(f"\n📋 约束条件分析:")
    
    constraints = {
        "初始SOC约束": 1,
        "SOC平衡方程": n_periods,
        "功率平衡方程": n_periods,
        "不能同时充放电": n_periods,
        "充电逻辑约束(Big M)": n_periods,
        "放电逻辑约束(Big M)": n_periods,
        "Ramp Rate上升约束": n_periods - 1,
        "Ramp Rate下降约束": n_periods - 1,
        "充电功率上限": n_periods,
        "最低放电价格约束": 2063,  # 根据实际负电价时段数
    }
    
    print(f"\n约束类型及数量:")
    total_constraints = 0
    for name, count in constraints.items():
        print(f"   {name:<25} {count:>7,} 个")
        total_constraints += count
    
    print(f"\n✅ 约束条件总数: {total_constraints:,} 个")
    
    # 为什么不能简化
    print(f"\n" + "="*80)
    print("🤔 为什么不能简化？")
    print("="*80)
    
    print("""
1️⃣ 时间耦合（最关键）
   ═══════════════════
   
   SOC[t+1] = SOC[t] + 充电×效率 - 放电/效率
   
   ➜ 每个时刻的SOC依赖于前一时刻
   ➜ t时刻的决策影响t+1, t+2, ..., t+n所有未来时刻
   ➜ 必须同时优化所有时段才能找到全局最优解
   
   例子：
   ├─ t=100  RRP=-0.5  → 应该充电吗？
   ├─ t=200  RRP=10.0  → 如果t=100充电，现在可以放电获利
   └─ 如果独立优化每个时段，就错过了这个套利机会！

2️⃣ Ramp Rate约束
   ═══════════════
   
   |P_export[t] - P_export[t-1]| ≤ 16.67×300 kW
   
   ➜ 相邻时刻的功率输出不能变化太快
   ➜ 必须考虑前后时刻的功率水平
   
3️⃣ 不能同时充放电
   ═══════════════════
   
   需要二进制变量 is_charging 和 is_discharging
   ➜ 增加了问题的组合复杂度
   ➜ 从线性规划(LP)变成混合整数线性规划(MILP)
   ➜ MILP的求解难度呈指数级增长

4️⃣ 为什么贪心算法快？
   ═══════════════════
   
   贪心算法：
   ├─ 按时间顺序逐个决策
   ├─ 不需要求解器
   ├─ 时间复杂度: O(n) ≈ 8,640次计算
   └─ 2.35秒完成
   
   线性规划：
   ├─ 同时优化所有时段
   ├─ 需要探索大量组合
   ├─ 时间复杂度: 指数级 O(2^k × n^3)
   └─ 可能需要数小时
""")
    
    # 不同时间段数的模型规模对比
    print(f"\n" + "="*80)
    print("📈 不同时间跨度的模型规模")
    print("="*80 + "\n")
    
    time_spans = [
        ("1天", 288),
        ("3天", 288*3),
        ("7天", 288*7),
        ("14天", 288*14),
        ("30天", 288*30),
    ]
    
    print(f"{'时间跨度':<10} {'时间段':<10} {'变量数':<12} {'约束数':<12} {'求解难度'}")
    print("-" * 70)
    
    for span_name, periods in time_spans:
        variables = periods * 6 + (periods + 1)
        constraints_est = periods * 8 + 1
        
        if periods <= 288:
            difficulty = "简单 ✅"
        elif periods <= 288*7:
            difficulty = "中等 ⚠️"
        elif periods <= 288*14:
            difficulty = "困难 ❌"
        else:
            difficulty = "非常困难 💀"
        
        print(f"{span_name:<10} {periods:<10,} {variables:<12,} {constraints_est:<12,} {difficulty}")
    
    print("\n建议:")
    print("  ✅ 1-3天数据: 可以用完整线性规划（几分钟内求解）")
    print("  ⚠️  7天数据: 可以尝试，但可能需要较长时间")
    print("  ❌ 14天以上: 建议使用贪心算法或其他启发式方法")
    
    # 可视化
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    
    # 左图：模型规模随时间段增长
    periods_list = [s[1] for s in time_spans]
    vars_list = [p * 6 + (p + 1) for p in periods_list]
    const_list = [p * 8 + 1 for p in periods_list]
    
    x = range(len(time_spans))
    labels = [s[0] for s in time_spans]
    
    ax1.bar([i-0.2 for i in x], vars_list, 0.4, label='决策变量数', alpha=0.8)
    ax1.bar([i+0.2 for i in x], const_list, 0.4, label='约束条件数', alpha=0.8)
    ax1.set_xlabel('时间跨度', fontsize=11)
    ax1.set_ylabel('数量', fontsize=11)
    ax1.set_title('模型规模随时间跨度增长', fontsize=12, fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.legend()
    ax1.grid(True, alpha=0.3, axis='y')
    
    # 右图：每个时间段的变量和约束结构
    categories = ['连续变量\n(4个)', '二进制变量\n(2个)', 'SOC状态\n(1个)', 
                  '平衡约束\n(2个)', '逻辑约束\n(3个)', 'Ramp约束\n(2个)']
    values = [4, 2, 1/n_periods*1000, 2, 3, 2]
    colors = ['steelblue', 'coral', 'lightgreen', 'gold', 'lightcoral', 'plum']
    
    ax2.bar(range(len(categories)), values, color=colors, alpha=0.8, edgecolor='black')
    ax2.set_ylabel('数量', fontsize=11)
    ax2.set_title('单个时间段的结构', fontsize=12, fontweight='bold')
    ax2.set_xticks(range(len(categories)))
    ax2.set_xticklabels(categories, fontsize=9)
    ax2.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig('model_complexity_analysis.png', dpi=300, bbox_inches='tight')
    print(f"\n图表已保存: model_complexity_analysis.png")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    analyze_model_complexity()


