# BuyPulse 部署指南

## 一、本地开发环境搭建

### 前置条件

- macOS (Apple Silicon 或 Intel)
- Python 3.12+
- Homebrew (`brew`)

### Step 1：安装工具

```bash
# 安装 uv（Python 包管理器）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装 Tesseract（OCR 引擎，用于图表文字识别）
brew install tesseract

# 安装 Docker Desktop
# 下载地址：https://www.docker.com/products/docker-desktop/
# 安装后启动，等待鲸鱼图标不再转动
```

### Step 2：启动数据库

```bash
cd /path/to/BuyPulse
docker compose up -d
```

验证数据库已就绪：

```bash
docker compose ps
# 应显示 db (5432) 和 db-test (5433) 都是 healthy
```

### Step 3：配置环境变量

```bash
cp .env.example .env
```

默认值适用于本地开发，无需修改。如需自定义，编辑 `.env` 文件。

### Step 4：安装依赖 + 建表

```bash
# 安装所有 Python 依赖
uv sync

# 运行数据库迁移（建表）
uv run cps db init
```

### Step 5：验证安装

```bash
# 运行单元测试（110个，不需要 Docker）
uv run pytest tests/unit/ -v

# 运行集成测试（需要 Docker 数据库运行中）
uv run pytest tests/integration/ -v

# 试跑 CLI
uv run cps seed add B08N5WRWNW        # 添加一个测试 ASIN
uv run cps crawl run --limit 1        # 下载并分析一个图表
uv run cps crawl status               # 查看进度
```

### 日常开发命令

```bash
docker compose up -d        # 启动数据库
docker compose stop         # 停止数据库（保留数据）
docker compose down         # 停止并删除容器（数据卷保留）
docker compose down -v      # 停止并删除所有数据（慎用）

uv run cps --help           # 查看所有 CLI 命令
uv run cps seed --help      # 查看 seed 子命令
uv run cps crawl --help     # 查看 crawl 子命令
```

---

## 二、VPS 生产环境部署

### Step 1：购买 VPS

推荐配置：
- **Hetzner CPX22**：3 vCPU, 4GB RAM, 80GB SSD
- **区域**：US East (Ashburn) — 离 Amazon 服务器近
- **系统**：Ubuntu 22.04 LTS
- **费用**：约 $8-10/月

### Step 2：服务器初始化

```bash
# SSH 进入
ssh root@<VPS_IP>

# 更新系统
apt update && apt upgrade -y

# 安装系统依赖
apt install -y python3.12 python3.12-venv git postgresql tesseract-ocr

# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# 创建专用用户（不用 root 跑服务）
adduser cps
usermod -aG sudo cps
```

### Step 3：配置 PostgreSQL

```bash
# 切换到 postgres 用户建库
sudo -u postgres createuser cps
sudo -u postgres createdb cps -O cps
sudo -u postgres psql -c "ALTER USER cps PASSWORD '<生成一个强密码>';"
```

### Step 4：部署代码

```bash
# 切换到 cps 用户
su - cps

# 拉代码
git clone https://github.com/munn/BuyPulse.git
cd BuyPulse

# 创建配置
cp .env.example .env
```

编辑 `.env`，修改数据库连接：

```
DATABASE_URL=postgresql+asyncpg://cps:<你的密码>@localhost:5432/cps
```

如果需要邮件告警，填写 Resend 配置：

```
RESEND_API_KEY=re_xxxxxxxxxxxx
ALERT_EMAIL_TO=your-email@example.com
ALERT_EMAIL_FROM=alerts@yourdomain.com
```

### Step 5：安装依赖 + 建表

```bash
uv sync
uv run cps db init
uv run cps db check-partitions    # 检查分区表
```

### Step 6：首次运行（烟雾测试）

```bash
# 添加几个测试 ASIN
uv run cps seed add B08N5WRWNW
uv run cps seed add B09V3KXJPB
uv run cps seed add B0BSHF7WHW

# 跑 3 个
uv run cps crawl run --limit 3

# 查看结果
uv run cps crawl status
uv run cps db stats
```

### Step 7：设置定时爬取

```bash
crontab -e
```

添加：

```cron
# 每6小时爬取100个ASIN
0 */6 * * * cd /home/cps/BuyPulse && /home/cps/.local/bin/uv run cps crawl run --limit 100 >> /home/cps/cps-crawl.log 2>&1

# 每天检查分区表
0 9 * * * cd /home/cps/BuyPulse && /home/cps/.local/bin/uv run cps db check-partitions >> /home/cps/cps-check.log 2>&1
```

### Step 8：批量导入 ASIN

准备一个文本文件 `asins.txt`（每行一个 ASIN）：

```bash
uv run cps seed import --file asins.txt
uv run cps seed stats
```

---

## 三、从本地迁移到 VPS

当 VPS 验证通过后，清理本地环境：

### 1. 停止并删除本地 Docker 数据

```bash
cd /path/to/BuyPulse
docker compose down -v          # 删除容器和数据卷
docker system prune -f          # 清理无用的 Docker 镜像
```

### 2. 删除本地爬取数据

```bash
rm -rf data/                    # 删除本地下载的 PNG 图表
```

### 3. 保留代码目录

代码继续留在本地用于开发，只需清理 Docker 和数据。
日后继续开发时重新 `docker compose up -d` 即可。

如果确定不再本地开发：

```bash
# 卸载 Docker Desktop（在 Applications 中拖到废纸篓）
# 删除项目目录（可选，代码在 GitHub 上有备份）
rm -rf /path/to/BuyPulse
```

---

## 四、常用运维命令

```bash
# 查看爬取进度
uv run cps crawl status

# 查看数据库统计
uv run cps db stats

# 重试失败的任务
uv run cps crawl retry-failed

# 检查分区表
uv run cps db check-partitions

# 查看 ASIN 分布
uv run cps seed stats
```
