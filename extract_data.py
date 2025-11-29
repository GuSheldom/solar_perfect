import pandas as pd

# 读取CSV文件
df = pd.read_csv('excel_1117版本.csv', encoding='utf-8')

# 提取需要的列并重命名
extracted_df = df[['日期', 'POA', 'PV功率', '电价RRP']].copy()

# 将列名改成英文
extracted_df.columns = ['Date', 'POA', 'PV_Power', 'RRP']

# 显示前几行数据
print("提取的数据预览：")
print(extracted_df.head(10))
print(f"\n总共有 {len(extracted_df)} 行数据")
print(f"\n数据信息：")
print(extracted_df.info())

# 保存为新的CSV文件
output_file = 'extracted_data.csv'
extracted_df.to_csv(output_file, index=False, encoding='utf-8')
print(f"\n数据已保存到 {output_file}")


