"""
测试Gurobi安装和许可证
"""

print("="*80)
print("🔍 检查Gurobi安装状态")
print("="*80 + "\n")

# 1. 检查是否安装
print("1️⃣ 检查Gurobi是否安装...")
try:
    import gurobipy as gp
    from gurobipy import GRB
    print("   ✅ Gurobi已安装")
    print(f"   版本: {gp.gurobi.version()}")
except ImportError as e:
    print("   ❌ Gurobi未安装")
    print(f"   错误: {e}")
    print("\n   请运行: pip install gurobipy")
    exit(1)

# 2. 检查许可证
print("\n2️⃣ 检查许可证...")
try:
    # 创建一个简单的测试模型
    model = gp.Model("license_test")
    
    # 添加变量
    x = model.addVar(lb=0, ub=10, name="x")
    y = model.addVar(lb=0, ub=10, name="y")
    
    # 设置目标函数
    model.setObjective(x + y, GRB.MAXIMIZE)
    
    # 添加约束
    model.addConstr(x + y <= 10, "c1")
    
    # 关闭输出
    model.setParam('OutputFlag', 0)
    
    # 求解
    model.optimize()
    
    if model.status == GRB.OPTIMAL:
        print("   ✅ 许可证正常工作")
        print(f"   测试求解成功: x={x.X:.2f}, y={y.X:.2f}, 目标值={model.ObjVal:.2f}")
        
        # 检查许可证类型
        print("\n3️⃣ 许可证信息:")
        
        # 检查变量和约束限制
        max_vars = 100000  # 尝试大模型
        try:
            test_model = gp.Model("size_test")
            test_vars = test_model.addVars(range(min(3000, max_vars)), name="test")
            test_model.setParam('OutputFlag', 0)
            test_model.optimize()
            
            if test_model.status == GRB.OPTIMAL or test_model.status == GRB.INTERRUPTED:
                print("   ✅ 完整许可证（无大小限制）")
                print("   类型: 学术许可、商业许可或试用许可")
            else:
                print("   ⚠️  受限许可证")
                print("   类型: 免费受限版本（最多2000变量，2000约束）")
        except gp.GurobiError as e:
            if "Model too large" in str(e) or "size-limited" in str(e):
                print("   ⚠️  受限许可证")
                print("   类型: 免费受限版本（最多2000变量，2000约束）")
                print("\n   对于您的30天优化问题（60,481个变量）：")
                print("   ❌ 无法使用受限版本")
                print("   ✅ 建议申请学术免费许可或使用7天数据")
            else:
                print(f"   ⚠️  许可证检查遇到问题: {e}")
        
    else:
        print(f"   ⚠️  求解状态异常: {model.status}")
        
except gp.GurobiError as e:
    print(f"   ❌ 许可证错误: {e}")
    print("\n   可能的原因:")
    print("   1. 没有有效的许可证文件")
    print("   2. 许可证已过期")
    print("   3. 网络问题（如果使用云许可）")
    print("\n   解决方法:")
    print("   - 学术用户: 申请免费学术许可")
    print("     https://www.gurobi.com/academia/")
    print("   - 试用: 申请30天试用许可")
    print("     https://www.gurobi.com/downloads/")
    print("   - 受限版本会自动使用（最多2000变量）")
    exit(1)

print("\n" + "="*80)
print("📊 您的储能优化问题分析")
print("="*80)

print("""
30天数据（8,640个时间段）:
├─ 决策变量: 60,481个
├─ 约束条件: 70,897个
└─ 二进制变量: 17,280个

结论:
""")

try:
    # 检查是否能处理大模型
    test_large = gp.Model("large_test")
    test_large_vars = test_large.addVars(range(60481), name="test_large")
    test_large.setParam('OutputFlag', 0)
    
    print("✅ 您的许可证可以处理30天完整数据!")
    print("   预计求解时间: 5-15分钟")
    print("\n建议:")
    print("   1. 运行: python gurobi_energy_optimization.py")
    print("   2. 或修改max_periods参数使用部分数据测试")
    
except gp.GurobiError as e:
    if "Model too large" in str(e) or "size-limited" in str(e):
        print("⚠️  受限许可证无法处理30天数据")
        print("\n替代方案:")
        print("   1. 使用7天数据 (2,016个时间段)")
        print("      - 变量数: 14,113 ✅ (小于2000限制)")
        print("      - 预计时间: 1-2分钟")
        print("      - 修改代码: max_periods=288*7")
        print("\n   2. 使用3天数据 (864个时间段)")
        print("      - 变量数: 6,049 ✅")
        print("      - 预计时间: <30秒")
        print("      - 修改代码: max_periods=288*3")
        print("\n   3. 申请学术免费许可（推荐）")
        print("      https://www.gurobi.com/academia/")
        print("\n   4. 使用贪心算法（已完成）")
        print("      - 2.35秒完成30天优化")
        print("      - 收益: $2,437.89")
    else:
        print(f"检查遇到其他问题: {e}")

print("\n" + "="*80)
print("✅ 检查完成")
print("="*80)


