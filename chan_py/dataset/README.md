# 5分钟股票数据下载工具

## 文件说明

| 文件 | 用途 |
|------|------|
| `baostockdata.py` | Baostock 全量下载 + 每日增量更新（网络 API） |
| `tdx_convert.py` | 通达信本地 5 分钟数据转 Parquet + delta 合并 |
| `test_stock_data.py` | 数据完整性验证工具 |

---

## baostockdata.py

### 用法

```bash
python baostockdata.py
```

### 功能
- 从 Baostock 下载 A 股（沪/深/京）5 分钟 K 线 + 复权因子
- 首次运行：全量下载 2020 年至今所有数据
- 后续运行：自动增量拉取新交易日数据
- 支持 `Ctrl+C` 中断，断点续传

### 配置

编辑脚本头部全局变量：

```python
TEST_MODE = False          # 设为 True 仅下载 3 只测试股票
START_YEAR = 2020          # 起始年份
OUTPUT_BASE_DIR = "./baostock_5min_raw"        # K 线输出目录
FACTOR_OUTPUT_BASE_DIR = "./baostock_5min_factors"  # 复权因子输出目录
```

### 输出文件

```
baostock_5min_raw/
├── sh_2026.parquet                   # 沪市 2026 年全部 5 分钟 K 线
├── sh_2026_delta_20260517.parquet    # 增量数据副本（仅新增部分）
├── sh_2026_sync_dates.json           # 同步日期记录
├── sh_2026_metadata.json             # 已完成标记
├── sh_2026_no_data.json              # 无数据股票记录
├── sz_*.parquet / sz_*_delta_*.parquet ...
├── bj_*.parquet / bj_*_delta_*.parquet ...
└── stock_list_cache.parquet          # 股票列表缓存

baostock_5min_factors/
├── sh_adjust_factors.parquet         # 沪市复权因子
├── sh_adjust_factors_delta_20260517.parquet
├── sz_adjust_factors.parquet
└── ...
```

### Parquet 数据格式

| 列名 | 类型 | 说明 |
|------|------|------|
| code | str | 股票代码，如 `sh.600036` |
| datetime | datetime64[us] | K 线时间 |
| open | float64 | 开盘价 |
| high | float64 | 最高价 |
| low | float64 | 最低价 |
| close | float64 | 收盘价 |
| volume | int64 | 成交量 |
| amount | float64 | 成交额 |

---

## tdx_convert.py

### 用法

```bash
# 从通达信本地文件转换指定日期的 5 分钟数据
python tdx_convert.py --date 20260515

# 指定通达信安装路径
python tdx_convert.py --tdxdir "D:\gjzq\gjty" --date 20260515

# 指定输出目录
python tdx_convert.py --date 20260515 --output ./my_output

# 合并所有 delta 文件到年份主文件
python tdx_convert.py --merge

# 合并 2026 年的 delta，完成后删除 delta 文件
python tdx_convert.py --merge --year 2026 --delete
```

### 模式说明

| 模式 | 参数 | 说明 |
|------|------|------|
| 转换模式 | `--date 20260515` | 读取通达信 `.lc5` 文件，追加到年份文件 + 生成 delta |
| 合并模式 | `--merge` | 将 delta 文件合并到对应年份主文件 |

### 配置

```python
TDX_DIR = r"D:\gjzq\gjty"            # 通达信安装目录
OUTPUT_BASE_DIR = "./baostock_5min_raw"  # 输出目录（与主脚本共用）
```

### 前提条件

- 安装通达信（或国金等套壳版本）
- 通达信已下载目标日期的 5 分钟数据（打开通达信自动同步）
- `pip install mootdx pandas pyarrow`

### 输出

与 `baostockdata.py` 共用同一目录，生成相同的文件格式：
- 追加数据到 `{market}_{year}.parquet`（主文件，去重保护）
- 生成 `{market}_{year}_delta_{日期}.parquet`（增量文件，便于传输）
- 更新 `{market}_{year}_sync_dates.json`（同步状态）

---

## 典型工作流

### 首次部署

```bash
# 1. 全量下载历史数据（一次，耗时较长）
python baostockdata.py

# 2. 补齐当日数据（从通达信）
python tdx_convert.py --date 20260517
```

### 每日盘后

```bash
# 方式 A：通达信本地转换（快，~1分钟）
# 先打开通达信让它同步当日数据，然后：
python tdx_convert.py --date 20260518

# 方式 B：Baostock 网络增量（较慢）
python baostockdata.py
```

### 传输增量数据

```bash
# delta 文件仅包含当日新数据，体积小
# 将 delta 文件复制到其他机器后：
python tdx_convert.py --merge --delete
```

### 数据验证

```bash
# 查看指定年份的数据概况
python test_stock_data.py --year 2026

# 查看所有年份
python test_stock_data.py --year all
```

---

## 数据安全

两个脚本共用相同的安全机制：

1. **去重保护**：追加数据时自动 `drop_duplicates(['code', 'datetime'])`，不产生重复行
2. **原子写入**：先写 `.tmp` 临时文件，成功后 `os.replace` 替换，写不坏原文件
3. **损坏恢复**：读取 parquet 失败时自动 `.bak` 备份，从当前数据重建
4. **断点续传**：同步状态记录在 `sync_dates.json`，失败的任务下次自动重试
