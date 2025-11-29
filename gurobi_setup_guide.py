"""
Gurobi 使用完整指南
从安装到实际应用
"""

print("="*80)
print("📚 Gurobi 完整使用指南")
print("="*80)

print("""
## 🎯 Step 1: 安装 Gurobi

### 方法一：使用 pip 安装（推荐）

```bash
pip install gurobipy
```

这会安装最新版本的Gurobi（包含求解器）。

### 方法二：从官网下载完整安装包

1. 访问：https://www.gurobi.com/downloads/
2. 下载适合您系统的版本（Windows/Mac/Linux）
3. 运行安装程序
4. 然后安装Python接口：
   ```bash
   pip install gurobipy
   ```

""")

print("="*80)
print("🔑 Step 2: 获取许可证")
print("="*80)

print("""
### 选项A：学术免费许可（推荐）

1. 访问：https://www.gurobi.com/academia/academic-program-and-licenses/

2. 使用 .edu 邮箱注册账号

3. 登录后，申请 "Academic Named-User License"

4. 获得激活命令（类似这样）：
   ```bash
   grbgetkey xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```

5. 在命令行中运行该命令（需要联网）

6. 许可证文件会保存到：
   - Windows: C:\\Users\\YourName\\gurobi.lic
   - Mac/Linux: /home/username/gurobi.lic

### 选项B：免费试用许可

- 30天全功能试用
- 无需学术邮箱
- 访问：https://www.gurobi.com/downloads/

### 选项C：受限免费版本

- Gurobi的Python包自带受限免费许可
- 限制：最多2000个变量，2000个约束
- 对于小规模问题足够使用
- 无需额外配置

""")

print("="*80)
print("✅ Step 3: 验证安装")
print("="*80)

print("""
运行以下Python代码测试：

```python
import gurobipy as gp
from gurobipy import GRB

# 显示Gurobi版本
print(f"Gurobi version: {gp.gurobi.version()}")

# 创建一个简单的测试模型
try:
    model = gp.Model("test")
    x = model.addVar(name="x")
    model.setObjective(x, GRB.MAXIMIZE)
    model.addConstr(x <= 10)
    model.optimize()
    print(f"Test successful! Optimal x = {x.X}")
except gp.GurobiError as e:
    print(f"Error: {e}")
```

如果成功，应该看到：
```
Gurobi version: (11, 0, 0)
Test successful! Optimal x = 10.0
```

""")

print("="*80)
print("💻 Step 4: 基础使用示例")
print("="*80)

print("""
### 简单示例：求解线性规划

```python
import gurobipy as gp
from gurobipy import GRB

# 创建模型
model = gp.Model("simple_lp")

# 添加变量
x = model.addVar(lb=0, ub=10, name="x")
y = model.addVar(lb=0, ub=10, name="y")

# 设置目标函数: maximize 3x + 4y
model.setObjective(3*x + 4*y, GRB.MAXIMIZE)

# 添加约束
model.addConstr(2*x + y <= 20, "c1")
model.addConstr(x + 2*y <= 20, "c2")

# 求解
model.optimize()

# 输出结果
if model.status == GRB.OPTIMAL:
    print(f"最优解: x = {x.X:.2f}, y = {y.X:.2f}")
    print(f"最优值: {model.ObjVal:.2f}")
```

""")

print("="*80)
print("🔋 Step 5: 应用到储能优化项目")
print("="*80)

print("""
我会为您创建一个使用Gurobi的储能优化模型。

关键优势：
├─ 比CBC快10-100倍
├─ 可以处理30天完整数据
├─ 5-10分钟得到全局最优解
└─ 代码更简洁高效

文件：gurobi_energy_optimization.py
""")

print("\n" + "="*80)


