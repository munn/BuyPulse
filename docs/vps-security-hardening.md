# VPS 安全加固指南

> 适用于：Hetzner Cloud CPX22 / Ubuntu 24.04 LTS
> 技术栈：Python 3.12+ (uv) + PostgreSQL 16 + python-telegram-bot (polling) + systemd
> 目标读者：非技术背景创始人，曾遭受过攻击，安全意识强

---

## 目录

1. [初始服务器设置（Day 0）](#1-初始服务器设置day-0)
2. [SSH 加固](#2-ssh-加固)
3. [应用安全](#3-应用安全)
4. [网络安全](#4-网络安全)
5. [监控与告警](#5-监控与告警)
6. [备份与恢复](#6-备份与恢复)
7. [持续维护](#7-持续维护)
8. [常见攻击向量与防御](#8-常见攻击向量与防御)
9. [一键部署脚本](#9-一键部署脚本)

---

## 1. 初始服务器设置（Day 0）

### 1.1 创建非 root 用户 【MUST】

**为什么重要**：root 用户拥有系统的一切权限。一旦 root 被攻破，攻击者可以做任何事——安装后门、删除数据、挖矿。你之前被黑，很可能就是因为攻击者拿到了 root 权限。用一个普通用户 + sudo 的方式，即使密码泄露，攻击者还需要额外一步才能获得 root 权限，而且所有提权操作都会被记录在日志中。

```bash
# 以 root 登录后立即执行
adduser cps                    # 创建专用用户（按提示设置密码）
usermod -aG sudo cps           # 赋予 sudo 权限

# 验证
su - cps
sudo whoami                    # 应输出 "root"
```

### 1.2 SSH 密钥认证（禁用密码登录）【MUST】

**为什么重要**：密码可以被暴力破解。互联网上有无数自动化脚本 24 小时不停地尝试常见密码组合。SSH 密钥是一个 256 位的加密文件，暴力破解需要的时间超过宇宙的年龄。这是阻止绝大多数自动化攻击的第一道防线。

**在你的本地电脑上执行**：

```bash
# 生成 Ed25519 密钥（比 RSA 更安全、更快）
ssh-keygen -t ed25519 -C "cps-hetzner" -f ~/.ssh/cps_hetzner

# 复制公钥到服务器
ssh-copy-id -i ~/.ssh/cps_hetzner.pub cps@<VPS_IP>

# 测试密钥登录（不输入密码应该能登录）
ssh -i ~/.ssh/cps_hetzner cps@<VPS_IP>
```

**配置本地 SSH 快捷方式**（~/.ssh/config）：

```
Host cps
    HostName <VPS_IP>
    User cps
    IdentityFile ~/.ssh/cps_hetzner
    Port 22
    # 后续改端口后把 22 改成新端口号
```

这样以后只需 `ssh cps` 就能连接。

### 1.3 禁用密码登录和 root 远程登录 【MUST】

**为什么重要**：即使设置了密钥，如果密码登录仍然开着，攻击者还是可以暴力破解密码。彻底关掉密码登录，只允许密钥，是最关键的一步。

> 警告：执行这一步前，务必确认密钥登录已经测试成功！否则你会被锁在服务器外面。

```bash
# 在服务器上，备份原始配置
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup

# 编辑 SSH 配置
sudo nano /etc/ssh/sshd_config
```

修改以下设置（找到对应行，取消注释并修改值）：

```
# 禁用密码登录（MUST）
PasswordAuthentication no
PermitEmptyPasswords no

# 禁止 root 远程登录（MUST）
PermitRootLogin no

# 只允许密钥认证（MUST）
PubkeyAuthentication yes

# 禁用不安全的认证方式
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no

# 限制认证尝试次数
MaxAuthTries 3
LoginGraceTime 20

# 禁用不需要的功能
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no

# 只允许特定用户登录
AllowUsers cps

# 只用 IPv4（减少攻击面，除非你需要 IPv6）
AddressFamily inet
```

```bash
# 验证配置没有语法错误
sudo sshd -t

# 重启 SSH 服务
sudo systemctl restart ssh.socket
```

> 关键：修改后不要关闭当前终端！新开一个终端测试连接，确认能登录后再关闭旧终端。

### 1.4 更改 SSH 端口 【SHOULD】

**为什么重要**：绝大多数自动化扫描工具只扫描默认的 22 端口。改端口不是真正的安全措施（安全专家称之为 "security through obscurity"），但它能过滤掉 98% 的自动化扫描噪音，让你的日志更干净，更容易发现真正的攻击行为。

**优点**：
- 大幅减少暴力破解日志噪音
- 自动化扫描几乎不会触及非标准端口

**缺点**：
- 需要记住端口号（用 SSH config 解决）
- 某些网络环境可能封锁非标准端口

**建议**：改到一个 1024-65535 之间的端口，比如 `2222` 或 `52222`。

```bash
# 编辑 SSH 配置
sudo nano /etc/ssh/sshd_config

# 修改端口
Port 52222

# 先在防火墙放行新端口（重要！）
sudo ufw allow 52222/tcp comment 'SSH custom port'

# 验证并重启
sudo sshd -t
sudo systemctl restart ssh.socket

# 在新终端测试新端口
ssh -p 52222 cps@<VPS_IP>

# 确认能连接后，删除旧端口
sudo ufw delete allow 22/tcp
```

更新本地 `~/.ssh/config` 中的 Port 为 `52222`。

### 1.5 防火墙（UFW）配置 【MUST】

**为什么重要**：防火墙是你服务器的"围墙"。没有防火墙，服务器上所有端口都对外开放。攻击者可以扫描到 PostgreSQL、探测到各种服务。防火墙让你只暴露真正需要的端口。

对于这个技术栈（Telegram bot 使用 polling 模式，不需要接收外部请求），你的服务器几乎不需要对外开放任何端口：

```bash
# 安装 UFW（Ubuntu 24.04 通常已预装）
sudo apt install ufw -y

# 重置规则
sudo ufw --force reset

# 默认策略：拒绝所有入站，允许所有出站
sudo ufw default deny incoming
sudo ufw default allow outgoing

# 放行 SSH（用你的实际端口！）
sudo ufw allow 52222/tcp comment 'SSH'

# 启用防火墙
sudo ufw enable

# 验证
sudo ufw status verbose
```

**你的技术栈需要开放的端口**：

| 端口 | 方向 | 用途 | 是否需要开放 |
|------|------|------|-------------|
| 52222 (SSH) | 入站 | 远程管理 | **是** |
| 5432 (PostgreSQL) | 入站 | 数据库 | **否**（只本地访问） |
| 443 (HTTPS) | 出站 | Telegram API / CCC | 默认允许 |

注意：PostgreSQL 不需要对外开放！它只监听 localhost，应用和数据库在同一台服务器上。

### 1.6 fail2ban 设置 【MUST】

**为什么重要**：即使改了端口、禁用了密码，仍然可能有人找到你的 SSH 端口并尝试暴力破解密钥（虽然概率极低）。fail2ban 监控登录日志，一旦发现某个 IP 连续失败多次，就自动封禁该 IP。这是你的"自动保安"。

```bash
# 安装
sudo apt install fail2ban -y

# 创建本地配置（不直接修改 jail.conf，避免更新被覆盖）
sudo tee /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
# 封禁 24 小时（1 小时太短，攻击者等一下就能重试）
bantime = 86400
# 10 分钟内
findtime = 600
# 失败 3 次就封
maxretry = 3
# 白名单（本机）
ignoreip = 127.0.0.1/8 ::1

# 封禁动作：用 UFW
banaction = ufw

[sshd]
enabled = true
port = 52222
logpath = %(sshd_log)s
backend = %(sshd_backend)s
maxretry = 3

# 累进封禁：24 小时内被封 3 次的 IP → 永久封禁
[recidive]
enabled  = true
filter   = recidive
logpath  = /var/log/fail2ban.log
action   = ufw
bantime  = -1
findtime = 86400
maxretry = 3
EOF

# 启动
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# 验证
sudo fail2ban-client status
sudo fail2ban-client status sshd
```

### 1.7 自动安全更新 【MUST】

**为什么重要**：安全漏洞被发现后，补丁通常在 24-48 小时内发布。如果你不及时更新，攻击者可以利用公开的漏洞攻击你。自动安全更新确保你的系统在你睡觉的时候也在被保护。

```bash
# 安装（Ubuntu 24.04 通常已预装）
sudo apt install unattended-upgrades -y

# 配置
sudo nano /etc/apt/apt.conf.d/50unattended-upgrades
```

确保以下行未被注释：

```
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}";
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
};

// 自动清理旧内核
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";

// 不自动重启（避免 bot 意外下线，手动重启更可控）
Unattended-Upgrade::Automatic-Reboot "false";
```

启用自动更新：

```bash
sudo dpkg-reconfigure -plow unattended-upgrades

# 测试（干跑）
sudo unattended-upgrades --dry-run --debug
```

---

## 2. SSH 加固

### 2.1 密钥类型选择 【MUST】

**Ed25519 vs RSA**：

| 特性 | Ed25519 | RSA-4096 |
|------|---------|----------|
| 安全性 | 256 位椭圆曲线，等效 ~128 位安全 | 4096 位，等效 ~140 位安全 |
| 密钥长度 | 很短（68 字符） | 很长（数百字符） |
| 性能 | 非常快 | 较慢 |
| 抗侧信道攻击 | 好（固定时间运算） | 一般 |
| 兼容性 | OpenSSH 6.5+（2014 年后） | 几乎所有系统 |
| 推荐 | **首选** | 需要兼容旧系统时用 |

**结论**：用 Ed25519，没有理由再用 RSA。

### 2.2 SSH 完整加固配置 【SHOULD】

在第 1.3 节的基础上，以下是更完整的 `/etc/ssh/sshd_config`：

```bash
# === 基础设置 ===
Port 52222
AddressFamily inet
# 注意：不写 Protocol 2，现代 OpenSSH 默认只支持 v2，显式写反而可能报警告

# === 认证设置 ===
PermitRootLogin no
PasswordAuthentication no
PermitEmptyPasswords no
PubkeyAuthentication yes
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
MaxAuthTries 3
LoginGraceTime 20
AuthenticationMethods publickey

# === 用户限制 ===
AllowUsers cps

# === 加密算法（2025 推荐） ===
# 密钥交换算法（含后量子）
KexAlgorithms sntrup761x25519-sha512@openssh.com,curve25519-sha256@libssh.org,curve25519-sha256,diffie-hellman-group16-sha512,diffie-hellman-group18-sha512

# 主机密钥算法
HostKeyAlgorithms ssh-ed25519,ssh-ed25519-cert-v01@openssh.com,rsa-sha2-512,rsa-sha2-256

# 加密算法
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com

# MAC 算法（Encrypt-then-MAC）
MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com

# === 会话设置 ===
ClientAliveInterval 300
ClientAliveCountMax 2
MaxSessions 2
MaxStartups 3:50:10

# === 禁用不需要的功能 ===
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
PermitTunnel no
GatewayPorts no
PrintMotd no

# === 日志 ===
LogLevel VERBOSE
```

```bash
# 验证
sudo sshd -t

# 重启
sudo systemctl restart ssh.socket
```

### 2.3 双因素认证（2FA）【NICE】

**对 solo dev 是否值得**：对于个人使用的服务器，SSH 密钥 + 非标准端口 + fail2ban 已经足够安全。2FA 增加了额外安全层，但也增加了每次登录的麻烦。

**建议**：如果你经常从不同设备登录或者服务器存有敏感数据（如用户个人信息），值得开启。对于 CPS 这个阶段（价格数据爬虫），先不开，等有用户数据时再加。

如果将来要开启：

```bash
sudo apt install libpam-google-authenticator -y
google-authenticator
# 按提示设置，用手机 app（如 Authy、Google Authenticator）扫码
```

### 2.4 客户端密钥安全管理 【MUST】

**为什么重要**：SSH 密钥就是你的"门钥匙"。如果电脑被偷或密钥文件泄露，攻击者可以直接登录你的服务器。

```bash
# 本地密钥文件权限（macOS/Linux）
chmod 700 ~/.ssh
chmod 600 ~/.ssh/cps_hetzner          # 私钥：只有自己能读
chmod 644 ~/.ssh/cps_hetzner.pub      # 公钥：可以公开

# 给私钥加密码保护（生成时就应该设置）
# 如果当初没设，可以后补：
ssh-keygen -p -f ~/.ssh/cps_hetzner
```

**密钥管理最佳实践**：
- 私钥永远不要通过任何渠道传输（邮件、Slack、微信等）
- 不要把私钥放在云盘（iCloud、Google Drive）
- 如果换电脑，在新电脑生成新密钥，把新公钥加到服务器，然后在服务器上删除旧公钥
- 定期检查 `~/.ssh/authorized_keys`，删除不认识的公钥

---

## 3. 应用安全

### 3.1 专用服务用户（非 root）【MUST】

**为什么重要**：如果你的 Python 程序有 bug 或被注入恶意代码，它能做的事情取决于运行它的用户的权限。root 运行意味着攻击者直接获得完全控制。专用用户运行意味着攻击者只能在有限的沙盒内活动。

```bash
# 创建无登录权限的服务用户
sudo useradd --system --shell /usr/sbin/nologin --home /opt/cps --create-home cps-service

# 设置项目目录
sudo mkdir -p /opt/cps/app /opt/cps/data /opt/cps/logs
sudo chown -R cps-service:cps-service /opt/cps
```

### 3.2 systemd 服务加固 【SHOULD】

**为什么重要**：systemd 提供了类似 Docker 容器的沙盒功能，但更轻量。它可以限制你的程序只能访问特定目录、不能加载内核模块、不能修改系统文件。即使程序被攻破，攻击者也被困在沙盒里。

创建 `/etc/systemd/system/cps-crawler.service`：

```ini
[Unit]
Description=CPS Price Crawler
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=cps-service
Group=cps-service
WorkingDirectory=/opt/cps/app

# 环境和启动
EnvironmentFile=/opt/cps/app/.env
ExecStart=/opt/cps/app/.venv/bin/python -m cps crawl run

# 自动重启
Restart=on-failure
RestartSec=30

# === 安全沙盒 ===
# 禁止提权
NoNewPrivileges=yes

# 文件系统保护（整个系统只读，只允许写指定目录）
ProtectSystem=strict
ReadWritePaths=/opt/cps/data /opt/cps/logs

# 禁止访问 /home
ProtectHome=yes

# 隔离临时目录
PrivateTmp=yes

# 禁止访问物理设备
PrivateDevices=yes
DevicePolicy=closed

# 禁止修改内核参数
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes

# 禁止修改 cgroups
ProtectControlGroups=yes

# 禁止修改主机名和时钟
ProtectHostname=yes
ProtectClock=yes

# 限制网络（只允许 TCP/UDP/Unix socket）
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6

# 限制命名空间
RestrictNamespaces=yes

# 禁止实时调度
RestrictRealtime=yes

# 禁止设置 SUID/SGID
RestrictSUIDSGID=yes

# 注意：不启用 MemoryDenyWriteExecute=yes
# curl_cffi (基于 cffi) 需要 W^X 内存，启用此选项会导致 EPERM 崩溃

# 锁定 personality
LockPersonality=yes

# 限制系统调用（只允许常见调用）
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM

# 删除所有不需要的 Linux capabilities
CapabilityBoundingSet=
AmbientCapabilities=

[Install]
WantedBy=multi-user.target
```

Telegram Bot 的 service 文件类似，创建 `/etc/systemd/system/cps-bot.service`：

```ini
[Unit]
Description=CPS Telegram Bot
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=cps-service
Group=cps-service
WorkingDirectory=/opt/cps/app

EnvironmentFile=/opt/cps/app/.env
ExecStart=/opt/cps/app/.venv/bin/python -m cps bot run

Restart=always
RestartSec=10

# 同样的安全沙盒设置
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/opt/cps/data /opt/cps/logs
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
DevicePolicy=closed
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectHostname=yes
ProtectClock=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
# MemoryDenyWriteExecute=yes  # 如果 bot 也用 cffi 库则需注释掉，部署后用 systemd-analyze security cps-bot 验证
LockPersonality=yes
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM
CapabilityBoundingSet=
AmbientCapabilities=

[Install]
WantedBy=multi-user.target
```

```bash
# 启用并启动
sudo systemctl daemon-reload
sudo systemctl enable cps-crawler cps-bot
sudo systemctl start cps-bot

# 检查安全评分
systemd-analyze security cps-crawler
systemd-analyze security cps-bot
# 分数越低越好，目标 < 4.0（MEDIUM exposure）
```

### 3.3 环境变量 / 密钥管理 【MUST】

**为什么重要**：`.env` 文件里包含数据库密码、Telegram Bot Token、API Key 等。如果文件权限设置不对，任何用户都能读到你的所有密钥。你之前被黑可能就是因为密钥泄露。

```bash
# .env 文件权限：只有服务用户能读
sudo chown cps-service:cps-service /opt/cps/app/.env
sudo chmod 600 /opt/cps/app/.env

# 验证
ls -la /opt/cps/app/.env
# 应该显示 -rw------- 1 cps-service cps-service
```

**密钥安全原则**：
- `.env` 文件永远不提交到 Git（确认 `.gitignore` 包含 `.env`）
- 定期轮换密钥（每 3-6 个月）
- 如果怀疑泄露，立即轮换所有密钥
- 不要在日志中打印密钥（检查代码中是否有 `print(os.environ['...'])` 这样的行）

**密钥轮换步骤**：
1. 生成新密钥（Telegram: @BotFather；数据库：ALTER USER）
2. 更新 `.env` 文件
3. 重启服务 `sudo systemctl restart cps-bot cps-crawler`
4. 验证服务正常运行
5. 确认旧密钥已失效

### 3.4 PostgreSQL 认证加固 【MUST】

**为什么重要**：数据库是你所有数据的核心。如果 PostgreSQL 配置不当，攻击者可以远程连接你的数据库，读取所有价格数据，甚至修改数据。

#### listen_addresses — 只监听本地

编辑 `/etc/postgresql/16/main/postgresql.conf`：

```
# 只监听本地连接（MUST）
listen_addresses = 'localhost'

# 使用 SCRAM-SHA-256 密码加密
password_encryption = scram-sha-256

# 日志记录连接
log_connections = on
log_disconnections = on
```

#### pg_hba.conf — 认证规则

编辑 `/etc/postgresql/16/main/pg_hba.conf`：

```
# TYPE  DATABASE        USER            ADDRESS                 METHOD

# 本地 socket 连接（系统用户名匹配数据库用户名）
local   all             postgres                                peer
local   cps             cps_app                                 peer

# 本地 TCP 连接（需要密码）
host    cps             cps_app         127.0.0.1/32            scram-sha-256
host    cps             cps_app         ::1/128                 scram-sha-256

# 禁止所有其他连接（删除或注释掉所有其他 host 行）
```

> 关键：删除所有 `trust` 方法的行！`trust` 意味着不需要密码就能连接。

```bash
sudo systemctl restart postgresql
```

### 3.5 最小权限数据库用户 【MUST】

**为什么重要**：如果应用使用 `postgres` 超级用户，一旦应用被攻破（比如 SQL 注入），攻击者获得的是超级管理员权限——可以删库、创建后门用户、读取任何数据。用一个只有必要权限的用户，攻击者的活动范围被严格限制。

```bash
sudo -u postgres psql << 'EOF'
-- 创建应用专用用户（不是 superuser！）
CREATE USER cps_app WITH PASSWORD '生成一个强随机密码';

-- 创建数据库
CREATE DATABASE cps OWNER cps_app;

-- 连接到 cps 数据库
\c cps

-- 只给必要权限
GRANT CONNECT ON DATABASE cps TO cps_app;
GRANT USAGE ON SCHEMA public TO cps_app;
-- 临时给 CREATE 权限用于 alembic migration（之后必须撤销！）
GRANT CREATE ON SCHEMA public TO cps_app;

-- 撤销 public 的默认权限
REVOKE ALL ON DATABASE cps FROM PUBLIC;
EOF
```

**Migration 完成后必须撤销 CREATE 权限** 【MUST】：

```bash
# 运行完 alembic upgrade head 之后立即执行
sudo -u postgres psql -d cps << 'EOF'
-- 撤销 CREATE 权限（运行时不需要建表）
REVOKE CREATE ON SCHEMA public FROM cps_app;

-- 只保留运行时需要的 DML 权限
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cps_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cps_app;

-- 未来新建表也自动授权
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cps_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO cps_app;
EOF
```

> 如果以后需要跑新的 migration，临时授予 CREATE → 跑 migration → 再次撤销。

**生成强密码**：

```bash
# 在本地电脑上生成 32 字符随机密码
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 4. 网络安全

### 4.1 UFW 规则详解 【MUST】

对于 CPS 这个技术栈，UFW 规则极其简单，因为你几乎不需要接受外部连接：

```bash
# 查看当前规则
sudo ufw status numbered

# 理想的规则表：
# [1] 52222/tcp    ALLOW IN    Anywhere    # SSH
# （就这一条！）
```

**为什么这么少**：
- **Telegram Bot 用 polling 模式**：Bot 主动向 Telegram 服务器发请求（出站），不需要开入站端口
- **PostgreSQL 只本地访问**：应用和数据库在同一台机器上，走 localhost
- **CCC 图表下载**：出站 HTTPS 请求，默认允许
- **没有 Web 服务器**：不需要 80/443 入站

这是安全架构的一大优势——攻击面极小。

### 4.2 Hetzner Cloud Firewall（双层防火墙）【SHOULD】

**为什么重要**：Hetzner Cloud Firewall 在虚拟化层过滤流量——恶意流量根本不会到达你的服务器。即使攻击者在服务器上获得了 root 权限并关掉了 UFW，Hetzner Firewall 仍然在保护你。这就是"纵深防御"。

在 Hetzner Cloud Console 中配置：

**入站规则**：

| 协议 | 端口 | 来源 | 说明 |
|------|------|------|------|
| TCP | 52222 | 你的家庭IP/32 | SSH（只允许你的 IP） |

**出站规则**：

| 协议 | 端口 | 目标 | 说明 |
|------|------|------|------|
| TCP | 443 | 0.0.0.0/0 | HTTPS（Telegram API、CCC） |
| TCP | 53 | 0.0.0.0/0 | DNS |
| UDP | 53 | 0.0.0.0/0 | DNS |
| TCP | 80 | 0.0.0.0/0 | HTTP（apt 更新） |

> 技巧：Hetzner Firewall 中限制 SSH 来源为你的 IP，UFW 中不限制。这样万一你的 IP 变了，可以通过 Hetzner Console 修改，不会被锁在外面。

### 4.3 是否需要 VPN？【NICE】

**对于当前阶段：不需要。** 理由：
- SSH 密钥认证 + 非标准端口 + fail2ban 已经足够安全
- 只有一个人管理一台服务器
- VPN 增加复杂性和维护成本
- 如果 VPN 服务挂了，你就无法连接服务器

**什么时候需要 VPN**：
- 多人团队需要访问服务器
- 需要从不可信网络（公共 WiFi）访问
- 服务器上有多个内部服务需要互联

### 4.4 内核网络加固（sysctl）【SHOULD】

**为什么重要**：这些内核参数防止常见的网络攻击，如 IP 欺骗、ICMP 重定向攻击等。

创建 `/etc/sysctl.d/99-security.conf`：

```bash
sudo tee /etc/sysctl.d/99-security.conf << 'EOF'
# 防止 IP 欺骗
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1

# 禁止 ICMP 重定向（防止中间人攻击）
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0

# 禁止 source routing（防止路由劫持）
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0
net.ipv6.conf.default.accept_source_route = 0

# 忽略 ICMP 广播请求（防止 Smurf 攻击）
net.ipv4.icmp_echo_ignore_broadcasts = 1

# 记录异常数据包
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1

# 启用 SYN cookies（防止 SYN flood 攻击）
net.ipv4.tcp_syncookies = 1

# 禁止 IP 转发（这不是路由器）
net.ipv4.ip_forward = 0
net.ipv6.conf.all.forwarding = 0
EOF

# 应用
sudo sysctl --system
```

---

## 5. 监控与告警

### 5.1 SSH 登录通知 【MUST】（曾被入侵的用户必须启用）

**为什么重要**：即使你设置了所有防护，也需要知道谁在什么时候登录了你的服务器。如果你收到一个不是自己发起的登录通知，说明服务器可能已被攻破。

创建 `/opt/cps/scripts/ssh-login-notify.sh`：

```bash
#!/bin/bash
# SSH 登录通知脚本 — 通过 Telegram Bot 发送
# Token 从 .env 读取，不硬编码在脚本中

if [ -f /opt/cps/app/.env ]; then
    TELEGRAM_BOT_TOKEN=$(grep '^TELEGRAM_BOT_TOKEN=' /opt/cps/app/.env | cut -d= -f2-)
    TELEGRAM_CHAT_ID=$(grep '^TELEGRAM_CHAT_ID=' /opt/cps/app/.env | cut -d= -f2-)
fi

if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    exit 0  # 没有配置通知，静默退出
fi

if [ "$PAM_TYPE" != "close_session" ]; then
    HOSTNAME=$(hostname)
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S %Z')

    MESSAGE="🚨 *SSH 登录告警*

服务器: \`${HOSTNAME}\`
用户: \`${PAM_USER}\`
来源 IP: \`${PAM_RHOST}\`
时间: \`${TIMESTAMP}\`"

    curl -s -X POST \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d text="${MESSAGE}" \
        -d parse_mode="Markdown" \
        > /dev/null 2>&1
fi
```

```bash
# 设置权限
sudo chmod 750 /opt/cps/scripts/ssh-login-notify.sh

# 添加到 PAM
echo "session optional pam_exec.so /opt/cps/scripts/ssh-login-notify.sh" | sudo tee -a /etc/pam.d/sshd

# 测试：注销并重新登录，你应该收到 Telegram 通知
```

### 5.2 日志监控 【SHOULD】

**重点关注的日志**：

```bash
# SSH 认证日志（有人在尝试登录吗？）
sudo tail -f /var/log/auth.log

# 系统日志
sudo journalctl -u cps-bot -f        # Bot 日志
sudo journalctl -u cps-crawler -f    # Crawler 日志
sudo journalctl -u postgresql -f     # 数据库日志

# fail2ban 日志（谁被封了？）
sudo tail -f /var/log/fail2ban.log
```

**每周检查脚本**（创建 `/opt/cps/scripts/weekly-security-check.sh`）：

```bash
#!/bin/bash
echo "=== 安全周报 $(date '+%Y-%m-%d') ==="
echo ""
echo "--- 过去 7 天 SSH 登录 ---"
last -7 | head -20
echo ""
echo "--- fail2ban 统计 ---"
sudo fail2ban-client status sshd
echo ""
echo "--- 当前活跃连接 ---"
ss -tulpn
echo ""
echo "--- 磁盘使用 ---"
df -h /
echo ""
echo "--- 异常进程（高 CPU）---"
ps aux --sort=-%cpu | head -10
echo ""
echo "--- 需要重启？ ---"
if [ -f /var/run/reboot-required ]; then
    echo "是！有安全更新需要重启。"
else
    echo "不需要。"
fi
echo ""
echo "--- 未应用的安全更新 ---"
apt list --upgradable 2>/dev/null | grep -i security
```

### 5.3 入侵检测 【NICE】

**简单方案：lynis（推荐）**

比 AIDE/rkhunter 更现代、更全面，且易于使用：

```bash
# 安装
sudo apt install lynis -y

# 运行安全审计
sudo lynis audit system

# 查看报告
cat /var/log/lynis-report.dat
```

lynis 会给你一个安全评分和具体的改进建议。每月跑一次即可。

**检测可疑进程**：

```bash
# 查看是否有异常的高 CPU 进程（矿机特征）
ps aux --sort=-%cpu | head -5

# 查看是否有异常的网络连接（矿池连接通常用 3333、4444、8333 端口）
ss -tulpn | grep -E '3333|4444|8333|stratum'

# 查看是否有异常的定时任务
for user in $(cut -f1 -d: /etc/passwd); do
    crontab -l -u "$user" 2>/dev/null | grep -v '^#'
done
```

### 5.4 资源监控（检测挖矿）【SHOULD】

**为什么重要**：被黑最常见的后果就是服务器被用来挖矿。挖矿会让 CPU 长期 100%，你的正常服务变慢甚至崩溃，而且你还要为多余的计算资源付费。

创建 `/opt/cps/scripts/cpu-alert.sh`：

```bash
#!/bin/bash
# CPU 使用率告警（超过 85% 持续 5 分钟就告警）

THRESHOLD=85

# Token 从 .env 读取
if [ -f /opt/cps/app/.env ]; then
    TELEGRAM_BOT_TOKEN=$(grep '^TELEGRAM_BOT_TOKEN=' /opt/cps/app/.env | cut -d= -f2-)
    TELEGRAM_CHAT_ID=$(grep '^TELEGRAM_CHAT_ID=' /opt/cps/app/.env | cut -d= -f2-)
fi
[ -z "$TELEGRAM_BOT_TOKEN" ] && exit 0

CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print int($2 + $4)}')

if [ "$CPU_USAGE" -gt "$THRESHOLD" ]; then
    TOP_PROCS=$(ps aux --sort=-%cpu | head -6)
    MESSAGE="⚠️ *CPU 告警*

CPU 使用率: ${CPU_USAGE}%（阈值: ${THRESHOLD}%）

前 5 进程:
\`\`\`
${TOP_PROCS}
\`\`\`"

    curl -s -X POST \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d text="${MESSAGE}" \
        -d parse_mode="Markdown" \
        > /dev/null 2>&1
fi
```

```bash
sudo chmod 750 /opt/cps/scripts/cpu-alert.sh

# 每 5 分钟检查一次
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/cps/scripts/cpu-alert.sh") | crontab -
```

### 5.5 Hetzner 内置监控 【SHOULD】

Hetzner Cloud Console 提供基础监控：
- CPU 使用率
- 网络流量（入/出）
- 磁盘 I/O

在 Hetzner Console → 你的服务器 → Graphs 查看。

**建议**：设置 Hetzner 的告警功能（如果可用），当 CPU 持续高负载时自动通知。

---

## 6. 备份与恢复

### 6.0 备份加密密钥初始化 【MUST】

**为什么重要**：备份文件包含你的全部数据。如果备份泄露（异地存储被攻破、传输中被截获），未加密的备份 = 全部数据暴露。使用 age（现代加密工具）进行公钥加密，只有持有私钥的人能解密。

```bash
# 安装 age（现代替代 GPG 的加密工具）
sudo apt install age -y

# 生成密钥对（在你的本地电脑上执行，私钥不要放在服务器上！）
age-keygen -o ~/cps_backup_key.txt
# 输出类似：
# Public key: age1xxxxxxxxx...

# 在服务器上创建公钥文件
sudo mkdir -p /opt/cps/keys
echo "age1xxxxxxxxx..." | sudo tee /opt/cps/keys/backup_pubkey.txt
sudo chmod 644 /opt/cps/keys/backup_pubkey.txt

# 解密备份（在本地电脑上，需要时执行）
# age -d -i ~/cps_backup_key.txt < backup_file.sql.gz.age | gunzip > restored.sql
```

> **关键**：私钥 `cps_backup_key.txt` 保存在你的本地电脑上，绝对不要上传到服务器。服务器只有公钥（只能加密，不能解密）。即使服务器被完全攻破，攻击者也无法解密备份。

### 6.1 PostgreSQL 备份策略 【MUST】

**为什么重要**：硬件故障、误操作、被黑——任何一种情况都可能让你的数据丢失。没有备份 = 从零开始。价格历史数据是你的核心资产，丢了就无法恢复。

创建 `/opt/cps/scripts/backup-db.sh`：

```bash
#!/bin/bash
# PostgreSQL 每日备份脚本（加密 + 告警）

BACKUP_DIR="/opt/cps/backups/db"
RETENTION_DAYS=30
DB_NAME="cps"
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
BACKUP_FILE="${BACKUP_DIR}/cps_${TIMESTAMP}.sql.gz.age"

# Token 从 .env 读取
if [ -f /opt/cps/app/.env ]; then
    TELEGRAM_BOT_TOKEN=$(grep '^TELEGRAM_BOT_TOKEN=' /opt/cps/app/.env | cut -d= -f2-)
    TELEGRAM_CHAT_ID=$(grep '^TELEGRAM_CHAT_ID=' /opt/cps/app/.env | cut -d= -f2-)
fi

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 导出 → 压缩 → 加密（age 公钥加密，只有持有私钥的人能解密）
sudo -u postgres pg_dump "$DB_NAME" | gzip | \
    age -r "$(cat /opt/cps/keys/backup_pubkey.txt)" > "$BACKUP_FILE"

# 检查备份是否成功
if [ $? -eq 0 ] && [ -s "$BACKUP_FILE" ]; then
    echo "[$(date)] 备份成功: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

    # 清理过期备份
    find "$BACKUP_DIR" -name "cps_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
    echo "[$(date)] 已清理 ${RETENTION_DAYS} 天前的备份"
else
    echo "[$(date)] 备份失败！" >&2

    # 发送告警（Token 已在脚本开头从 .env 读取）
    curl -s -X POST \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d text="❌ 数据库备份失败！请立即检查。" \
        > /dev/null 2>&1
fi
```

```bash
sudo chmod 750 /opt/cps/scripts/backup-db.sh

# 每天凌晨 3 点备份
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/cps/scripts/backup-db.sh >> /opt/cps/logs/backup.log 2>&1") | crontab -
```

### 6.2 配置文件备份 【SHOULD】

```bash
# 创建配置备份脚本 /opt/cps/scripts/backup-config.sh
#!/bin/bash
BACKUP_DIR="/opt/cps/backups/config"
TIMESTAMP=$(date '+%Y%m%d')
mkdir -p "$BACKUP_DIR"

tar -czf "${BACKUP_DIR}/config_${TIMESTAMP}.tar.gz" \
    /etc/ssh/sshd_config \
    /etc/fail2ban/jail.local \
    /etc/postgresql/16/main/postgresql.conf \
    /etc/postgresql/16/main/pg_hba.conf \
    /etc/sysctl.d/99-security.conf \
    /etc/systemd/system/cps-*.service \
    /opt/cps/app/.env \
    2>/dev/null

# 保留 90 天
find "$BACKUP_DIR" -name "config_*.tar.gz" -mtime +90 -delete
```

### 6.3 异地备份 【SHOULD】

**为什么重要**：如果你的 VPS 被完全攻破或 Hetzner 出问题，本地备份也没了。异地备份是最后的救命稻草。

**推荐方案**：Hetzner Storage Box（便宜，同生态，通过 SSH/SFTP 传输）

```bash
# 安装 rclone
sudo apt install rclone -y

# 配置 rclone（按提示添加 SFTP 到 Hetzner Storage Box）
rclone config

# 在备份脚本末尾添加异地同步
rclone sync /opt/cps/backups/ hetzner-storage:/cps-backups/ --transfers 1
```

**替代方案**：
- Backblaze B2（每 GB $0.005/月，非常便宜）
- 本地电脑定期 rsync 下载

### 6.4 恢复测试 【MUST】

**为什么重要**：没有测试过的备份等于没有备份。

**每月恢复测试流程**：

```bash
# 1. 在本地电脑创建测试数据库
createdb cps_restore_test

# 2. 下载最新备份
scp cps:/opt/cps/backups/db/cps_latest.sql.gz ./

# 3. 恢复
gunzip -c cps_latest.sql.gz | psql cps_restore_test

# 4. 验证数据完整性
psql cps_restore_test -c "SELECT COUNT(*) FROM asin_seeds;"
psql cps_restore_test -c "SELECT COUNT(*) FROM price_history;"

# 5. 清理
dropdb cps_restore_test
rm cps_latest.sql.gz
```

---

## 7. 持续维护

### 7.1 更新频率 【MUST】

| 类型 | 频率 | 方式 |
|------|------|------|
| 安全补丁 | 自动（每日） | unattended-upgrades |
| 系统更新 | 每周手动检查 | `sudo apt update && sudo apt upgrade` |
| 内核更新 | 需要重启时 | 检查 `/var/run/reboot-required` |
| Python 依赖 | 每月 | `uv lock --upgrade` + 测试 |
| PostgreSQL | 跟随系统更新 | 小版本自动，大版本手动 |

### 7.2 月度安全检查清单 【SHOULD】

每月花 30 分钟做一次：

```
□ 检查 fail2ban 日志，是否有异常模式
  sudo fail2ban-client status sshd

□ 审查 authorized_keys，删除不认识的密钥
  cat ~/.ssh/authorized_keys

□ 检查是否有异常用户
  cat /etc/passwd | grep -v nologin | grep -v false

□ 检查是否有异常的定时任务
  sudo crontab -l
  crontab -l
  ls /etc/cron.d/

□ 检查活跃网络连接
  ss -tulpn

□ 检查是否有异常的 SUID 文件
  sudo find / -perm /4000 -type f 2>/dev/null

□ 运行 lynis 审计
  sudo lynis audit system

□ 检查磁盘空间（备份是否在增长？）
  df -h

□ 验证备份可用
  ls -la /opt/cps/backups/db/ | tail -5

□ 检查是否有待安装的安全更新
  apt list --upgradable 2>/dev/null

□ 审查 sudo 操作记录（检测异常提权）
  sudo grep "sudo:" /var/log/auth.log | grep -v "pam_unix" | tail -50

□ 检查 PostgreSQL 是否有非本地连接
  sudo journalctl -u postgresql --since "30 days ago" | grep "connection received" | grep -v "127.0.0.1"

□ 扫描 Python 依赖安全漏洞
  cd /opt/cps/app && uv run pip-audit 2>/dev/null || echo "pip-audit 未安装"

□ 检查 systemd 服务状态
  systemctl status cps-bot cps-crawler

□ 检查 PostgreSQL 日志是否有异常
  sudo journalctl -u postgresql --since "1 month ago" | grep -i error
```

### 7.3 如果再次被入侵，怎么办 【MUST 了解】

**立即行动**（前 30 分钟）：

1. **不要恐慌，不要关机**——关机会销毁内存中的取证证据
2. **截断网络**——在 Hetzner Console 中移除 Cloud Firewall 的所有入站规则（保留出站以便你操作）
3. **记录你发现了什么**——截图、记录时间线
4. **保存证据**：
   ```bash
   # 保存当前进程列表
   ps auxf > /tmp/processes.txt
   # 保存网络连接
   ss -tulpn > /tmp/connections.txt
   # 保存最近的登录记录
   last -100 > /tmp/logins.txt
   # 保存 crontab
   crontab -l > /tmp/crontab.txt
   ```

**评估范围**（第 1 小时）：

5. 检查是否有新增用户：`cat /etc/passwd`
6. 检查是否有新增 SSH 密钥：`cat ~/.ssh/authorized_keys`
7. 检查是否有异常定时任务：`crontab -l` 和 `ls /etc/cron.d/`
8. 检查是否有异常进程：`ps aux | grep -v '\[' | sort -k3 -rn | head`

**恢复**（确认入侵范围后）：

9. **最安全的做法：销毁服务器，从头搭建新的**
   - 在 Hetzner Console 创建新服务器
   - 用本指南重新加固
   - 从异地备份恢复数据
10. **轮换所有密钥**：
    - 新的 SSH 密钥对
    - 新的数据库密码
    - 新的 Telegram Bot Token（@BotFather → /revoke）
    - 新的所有 API Key
11. **分析入侵原因，堵上漏洞**

---

## 8. 常见攻击向量与防御

### 8.1 针对这个技术栈的威胁分析

| 攻击向量 | 可能性 | 影响 | 防御措施 | 分类 |
|----------|--------|------|----------|------|
| SSH 暴力破解 | 极高 | 完全控制 | 密钥认证 + fail2ban + 改端口 | **MUST** |
| PostgreSQL 外部暴露 | 中 | 数据泄露/删除 | listen_addresses=localhost + UFW | **MUST** |
| .env 文件泄露 | 中 | 密钥全部暴露 | 文件权限 600 + .gitignore | **MUST** |
| pip 供应链攻击 | 低-中 | 代码执行 | 锁定依赖版本 + hash 校验 | **SHOULD** |
| 内核漏洞利用 | 低 | 完全控制 | 自动安全更新 | **MUST** |
| 密钥意外提交 Git | 中 | 密钥暴露 | .gitignore + pre-commit hook | **MUST** |
| 服务器被当矿机 | 高（如果被入侵） | 性能/费用 | CPU 监控 + 告警 | **SHOULD** |

### 8.2 SSH 暴力破解

**现实**：一台新 VPS 上线后几分钟内就会收到来自全球的 SSH 暴力破解尝试。这不是有人针对你，是自动化僵尸网络在全网扫描。

**防御措施**：
- 禁用密码登录（MUST）— 密钥不可暴力破解
- fail2ban（MUST）— 封禁失败的 IP
- 改端口（SHOULD）— 过滤 98% 自动扫描
- Hetzner Firewall 限制 IP（SHOULD）— 只允许你的 IP

### 8.3 PostgreSQL 暴露

**现实**：Shodan（网络设备搜索引擎）上有大量暴露在公网的 PostgreSQL 实例。攻击者有现成的工具批量扫描和利用。

**防御措施**：
- `listen_addresses = 'localhost'`（MUST）
- UFW 不开放 5432 端口（MUST）
- 不使用 `trust` 认证方法（MUST）
- 使用 scram-sha-256（SHOULD）
- 非超级用户运行应用（MUST）

### 8.4 .env 文件泄露

**现实**：GitHub 上有大量意外提交的 `.env` 文件。攻击者使用自动化工具实时监控新提交中的密钥，发现后几分钟内就会利用。

**防御措施**：
- `.gitignore` 包含 `.env`（MUST）
- 文件权限 `chmod 600`（MUST）
- 使用 `gitleaks` pre-commit hook 防止意外提交（SHOULD）
- 定期检查 GitHub 仓库是否有泄露（NICE）

```bash
# 安装 gitleaks（比 git-secrets 更全面、仍在活跃维护）
brew install gitleaks          # macOS

# 扫描现有仓库
cd /path/to/project
gitleaks detect --source . --verbose

# 设置 pre-commit hook（每次 commit 自动扫描）
cat > .git/hooks/pre-commit << 'HOOK'
#!/bin/bash
gitleaks protect --staged --verbose
HOOK
chmod +x .git/hooks/pre-commit
```

### 8.5 pip 供应链攻击

**现实**：2024-2025 年 PyPI 上发现了大量恶意包，包括名字和正规包很像的"typosquatting"包。安装一个恶意包 = 攻击者在你服务器上执行任意代码。

**防御措施**：

```bash
# 使用 uv.lock 锁定精确版本（MUST）
# uv 默认就会生成 lock 文件

# 安装时验证 hash（SHOULD）
# uv.lock 已经包含 hash 校验

# 定期审计依赖安全漏洞（SHOULD）
uv pip install pip-audit
pip-audit

# 安装前仔细检查包名（MUST）
# 不要 cURLI cffi → curl-cffi（注意大小写和连字符）
```

---

## 9. 一键部署脚本

> 这个脚本实现所有 MUST 和 SHOULD 级别的安全措施。可以多次运行（幂等）。

> **使用前**：你需要先用密钥方式登录服务器（Hetzner 创建 VPS 时可以直接添加 SSH Key）。

创建 `scripts/harden-server.sh`（在你的项目仓库中）：

```bash
#!/bin/bash
set -euo pipefail

# ============================================================
# CPS VPS 安全加固脚本
# 适用于：Ubuntu 24.04 LTS on Hetzner Cloud
# 用法：以 root 身份运行，或通过 sudo 运行
# ============================================================

# --- 配置 ---
APP_USER="cps"                 # 管理用户
SERVICE_USER="cps-service"     # 服务运行用户
SSH_PORT="52222"               # SSH 端口
DB_NAME="cps"                  # 数据库名
DB_USER="cps_app"              # 数据库用户
APP_DIR="/opt/cps"             # 应用目录

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] WARNING:${NC} $1"; }
err() { echo -e "${RED}[$(date '+%H:%M:%S')] ERROR:${NC} $1"; }

# 检查是否以 root 运行
if [ "$(id -u)" -ne 0 ]; then
    err "请以 root 身份运行此脚本"
    exit 1
fi

# ============================================================
# 1. 系统更新
# ============================================================
log "=== 1/10 系统更新 ==="
apt update -qq
DEBIAN_FRONTEND=noninteractive apt upgrade -y -qq
log "系统更新完成"

# ============================================================
# 2. 安装必要软件
# ============================================================
log "=== 2/10 安装必要软件 ==="
DEBIAN_FRONTEND=noninteractive apt install -y -qq \
    ufw \
    fail2ban \
    unattended-upgrades \
    postgresql-16 \
    tesseract-ocr \
    lynis \
    curl \
    git \
    > /dev/null 2>&1

# 安装 uv（下载到文件后再执行，避免 curl | sh 供应链风险）
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh
    log "uv 安装脚本 SHA256: $(sha256sum /tmp/uv-install.sh | cut -d' ' -f1)"
    log "请对比 https://github.com/astral-sh/uv/releases 确认哈希值"
    bash /tmp/uv-install.sh
    rm /tmp/uv-install.sh
    export PATH="$HOME/.local/bin:$PATH"
fi
log "软件安装完成"

# ============================================================
# 3. 创建用户
# ============================================================
log "=== 3/10 创建用户 ==="

# 管理用户
if ! id "$APP_USER" &>/dev/null; then
    adduser --disabled-password --gecos "" "$APP_USER"
    usermod -aG sudo "$APP_USER"
    log "管理用户 $APP_USER 已创建"

    # 复制 root 的 SSH 密钥到新用户
    if [ -f /root/.ssh/authorized_keys ]; then
        mkdir -p "/home/$APP_USER/.ssh"
        cp /root/.ssh/authorized_keys "/home/$APP_USER/.ssh/"
        chown -R "$APP_USER:$APP_USER" "/home/$APP_USER/.ssh"
        chmod 700 "/home/$APP_USER/.ssh"
        chmod 600 "/home/$APP_USER/.ssh/authorized_keys"
        log "SSH 密钥已复制到 $APP_USER"
    fi
else
    log "管理用户 $APP_USER 已存在，跳过"
fi

# 服务用户
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --shell /usr/sbin/nologin --home "$APP_DIR" --create-home "$SERVICE_USER"
    log "服务用户 $SERVICE_USER 已创建"
else
    log "服务用户 $SERVICE_USER 已存在，跳过"
fi

# 创建目录
mkdir -p "$APP_DIR"/{app,data,logs,backups/db,backups/config,scripts}
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
# 管理用户需要能进入 app 目录部署代码
chmod 755 "$APP_DIR" "$APP_DIR/app"
log "目录结构已创建"

# ============================================================
# 4. SSH 加固
# ============================================================
log "=== 4/10 SSH 加固 ==="

# 备份
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup.$(date '+%Y%m%d') 2>/dev/null || true

cat > /etc/ssh/sshd_config << SSHEOF
# CPS 安全加固 SSH 配置 — 生成于 $(date '+%Y-%m-%d')
Port ${SSH_PORT}
AddressFamily inet

# 认证
PermitRootLogin no
PasswordAuthentication no
PermitEmptyPasswords no
PubkeyAuthentication yes
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
MaxAuthTries 3
LoginGraceTime 20
AuthenticationMethods publickey

# 用户限制
AllowUsers ${APP_USER}

# 加密算法
KexAlgorithms sntrup761x25519-sha512@openssh.com,curve25519-sha256@libssh.org,curve25519-sha256,diffie-hellman-group16-sha512,diffie-hellman-group18-sha512
HostKeyAlgorithms ssh-ed25519,ssh-ed25519-cert-v01@openssh.com,rsa-sha2-512,rsa-sha2-256
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com
MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com

# 会话
ClientAliveInterval 300
ClientAliveCountMax 2
MaxSessions 2
MaxStartups 3:50:10

# 禁用不需要的功能
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
PermitTunnel no
GatewayPorts no
PrintMotd no

# 日志
LogLevel VERBOSE
SSHEOF

# 验证
sshd -t
if [ $? -eq 0 ]; then
    # 自动检测 SSH 服务单元名称（Ubuntu 24.04 用 ssh.socket，旧版用 ssh.service）
    if systemctl is-active --quiet ssh.socket 2>/dev/null; then
        systemctl restart ssh.socket
    elif systemctl is-active --quiet ssh.service 2>/dev/null; then
        systemctl restart ssh.service
    else
        systemctl restart sshd.service
    fi
    log "SSH 加固完成（端口: ${SSH_PORT}）"
else
    err "SSH 配置有误！恢复备份..."
    cp /etc/ssh/sshd_config.backup.$(date '+%Y%m%d') /etc/ssh/sshd_config
    systemctl restart ssh.socket
    exit 1
fi

# ============================================================
# 5. 防火墙
# ============================================================
log "=== 5/10 防火墙配置 ==="
# 重要：先放行新旧 SSH 端口，防止锁死
ufw --force reset > /dev/null 2>&1
ufw default deny incoming > /dev/null 2>&1
ufw default allow outgoing > /dev/null 2>&1
ufw allow 22/tcp comment 'SSH old port - temporary safety' > /dev/null 2>&1
ufw allow "${SSH_PORT}/tcp" comment 'SSH' > /dev/null 2>&1
ufw --force enable > /dev/null 2>&1
log "UFW 防火墙已启用（开放端口: 22 + ${SSH_PORT}/tcp）"
log "⚠️  测试新端口连接成功后，手动执行: sudo ufw delete allow 22/tcp"
ufw status

# ============================================================
# 6. fail2ban
# ============================================================
log "=== 6/10 fail2ban 配置 ==="
cat > /etc/fail2ban/jail.local << F2BEOF
[DEFAULT]
bantime = 86400
findtime = 600
maxretry = 3
ignoreip = 127.0.0.1/8 ::1
banaction = ufw

[sshd]
enabled = true
port = ${SSH_PORT}
logpath = %(sshd_log)s
backend = %(sshd_backend)s
maxretry = 3

[recidive]
enabled  = true
filter   = recidive
logpath  = /var/log/fail2ban.log
action   = ufw
bantime  = -1
findtime = 86400
maxretry = 3
F2BEOF

systemctl enable fail2ban > /dev/null 2>&1
systemctl restart fail2ban
log "fail2ban 已配置并启动"

# ============================================================
# 7. 自动安全更新
# ============================================================
log "=== 7/10 自动安全更新 ==="
cat > /etc/apt/apt.conf.d/20auto-upgrades << UUEOF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
UUEOF

log "自动安全更新已配置"

# ============================================================
# 8. 内核网络加固
# ============================================================
log "=== 8/10 内核网络加固 ==="
cat > /etc/sysctl.d/99-security.conf << SYSEOF
# 防止 IP 欺骗
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1

# 禁止 ICMP 重定向
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0

# 禁止 source routing
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0
net.ipv6.conf.default.accept_source_route = 0

# 防止 Smurf 攻击
net.ipv4.icmp_echo_ignore_broadcasts = 1

# 记录异常数据包
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1

# SYN cookies
net.ipv4.tcp_syncookies = 1

# 禁止 IP 转发
net.ipv4.ip_forward = 0
net.ipv6.conf.all.forwarding = 0
SYSEOF

sysctl --system > /dev/null 2>&1
log "内核网络参数已加固"

# ============================================================
# 9. PostgreSQL 安全配置
# ============================================================
log "=== 9/10 PostgreSQL 安全配置 ==="

PG_CONF="/etc/postgresql/16/main/postgresql.conf"
PG_HBA="/etc/postgresql/16/main/pg_hba.conf"

if [ -f "$PG_CONF" ]; then
    # listen_addresses
    sed -i "s/^#*listen_addresses.*/listen_addresses = 'localhost'/" "$PG_CONF"
    # password_encryption
    sed -i "s/^#*password_encryption.*/password_encryption = scram-sha-256/" "$PG_CONF"
    # 日志
    sed -i "s/^#*log_connections.*/log_connections = on/" "$PG_CONF"
    sed -i "s/^#*log_disconnections.*/log_disconnections = on/" "$PG_CONF"

    log "postgresql.conf 已更新"
fi

if [ -f "$PG_HBA" ]; then
    # 备份
    cp "$PG_HBA" "${PG_HBA}.backup.$(date '+%Y%m%d')"

    cat > "$PG_HBA" << PGEOF
# CPS 安全 pg_hba.conf — 生成于 $(date '+%Y-%m-%d')
# TYPE  DATABASE  USER       ADDRESS         METHOD
local   all       postgres                   peer
local   ${DB_NAME}  ${DB_USER}               peer
host    ${DB_NAME}  ${DB_USER}  127.0.0.1/32 scram-sha-256
host    ${DB_NAME}  ${DB_USER}  ::1/128      scram-sha-256
PGEOF

    log "pg_hba.conf 已更新"
fi

systemctl restart postgresql
log "PostgreSQL 已重启"

# ============================================================
# 10. systemd 服务模板
# ============================================================
log "=== 10/10 systemd 服务模板 ==="

# Crawler service
cat > /etc/systemd/system/cps-crawler.service << CRAWLEOF
[Unit]
Description=CPS Price Crawler
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=oneshot
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}/app
EnvironmentFile=${APP_DIR}/app/.env
ExecStart=${APP_DIR}/app/.venv/bin/python -m cps crawl run

NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=${APP_DIR}/data ${APP_DIR}/logs
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
DevicePolicy=closed
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectHostname=yes
ProtectClock=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM
CapabilityBoundingSet=
AmbientCapabilities=

[Install]
WantedBy=multi-user.target
CRAWLEOF

# Bot service
cat > /etc/systemd/system/cps-bot.service << BOTEOF
[Unit]
Description=CPS Telegram Bot
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}/app
EnvironmentFile=${APP_DIR}/app/.env
ExecStart=${APP_DIR}/app/.venv/bin/python -m cps bot run

Restart=always
RestartSec=10

NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=${APP_DIR}/data ${APP_DIR}/logs
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
DevicePolicy=closed
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectHostname=yes
ProtectClock=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM
CapabilityBoundingSet=
AmbientCapabilities=

[Install]
WantedBy=multi-user.target
BOTEOF

systemctl daemon-reload
log "systemd 服务模板已创建"

# ============================================================
# 完成
# ============================================================
echo ""
echo "========================================"
echo -e "${GREEN}  VPS 安全加固完成！${NC}"
echo "========================================"
echo ""
echo "重要后续步骤："
echo "1. 用新端口测试 SSH 连接: ssh -p ${SSH_PORT} ${APP_USER}@<IP>"
echo "   ⚠️  不要关闭当前终端！先测试新连接！"
echo ""
echo "2. 创建数据库用户（需要手动设置密码）:"
echo "   sudo -u postgres createuser ${DB_USER}"
echo "   sudo -u postgres createdb ${DB_NAME} -O ${DB_USER}"
echo "   sudo -u postgres psql -c \"ALTER USER ${DB_USER} PASSWORD '你的强密码';\""
echo ""
echo "3. 在 Hetzner Console 配置 Cloud Firewall:"
echo "   入站: TCP ${SSH_PORT} from 你的IP"
echo "   出站: TCP 443, TCP/UDP 53, TCP 80"
echo ""
echo "4. 部署代码到 ${APP_DIR}/app/"
echo ""
echo "5. 运行安全审计: sudo lynis audit system"
echo ""
```

---

## 安全措施分级汇总

### MUST（不做就会被黑）

| 措施 | 章节 | 一句话说明 |
|------|------|-----------|
| 创建非 root 用户 | 1.1 | root 被破 = 全部丢失 |
| SSH 密钥认证 | 1.2 | 密码可暴力破解，密钥不行 |
| 禁用密码登录 | 1.3 | 关掉密码入口，只留密钥 |
| UFW 防火墙 | 1.5 | 关闭不必要的端口 |
| fail2ban | 1.6 | 自动封禁暴力破解 IP |
| 自动安全更新 | 1.7 | 漏洞补丁不能等 |
| Ed25519 密钥 | 2.1 | 最安全的密钥类型 |
| 客户端密钥安全 | 2.4 | 私钥泄露 = 门钥匙被偷 |
| 专用服务用户 | 3.1 | 限制被攻破后的影响范围 |
| .env 文件权限 | 3.3 | 密钥文件不能被其他用户读 |
| PostgreSQL 本地监听 | 3.4 | 数据库不能暴露在公网 |
| 最小权限 DB 用户 | 3.5 | 不用超级用户跑应用 |
| 数据库备份 | 6.1 | 数据丢了无法恢复 |
| 备份恢复测试 | 6.4 | 没测试的备份 = 没有备份 |

### SHOULD（显著降低风险）

| 措施 | 章节 | 一句话说明 |
|------|------|-----------|
| 更改 SSH 端口 | 1.4 | 过滤 98% 自动扫描噪音 |
| 完整 SSH 加固配置 | 2.2 | 现代加密算法 + 连接限制 |
| systemd 沙盒 | 3.2 | 即使程序被攻破也被困住 |
| Hetzner Cloud Firewall | 4.2 | 双层防火墙，纵深防御 |
| 内核网络加固 | 4.4 | 防止网络层攻击 |
| SSH 登录通知 | 5.1 | 第一时间知道有人登录 |
| 日志监控 | 5.2 | 发现异常行为 |
| CPU 告警 | 5.4 | 检测挖矿 |
| 配置备份 | 6.2 | 快速重建服务器 |
| 异地备份 | 6.3 | 服务器没了还有数据 |
| 月度安全检查 | 7.2 | 持续维护安全状态 |
| pip 依赖审计 | 8.5 | 防止供应链攻击 |

### NICE（纵深防御，有时间就做）

| 措施 | 章节 | 一句话说明 |
|------|------|-----------|
| SSH 双因素认证 | 2.3 | 额外安全层 |
| lynis 安全审计 | 5.3 | 全面安全评分 |
| VPN 访问 | 4.3 | 当前阶段不需要 |
| gitleaks | 8.4 | 防止意外提交密钥 |

---

## Sources

- [How to Keep Your Ubuntu Server Safe | Hetzner Community](https://community.hetzner.com/tutorials/security-ubuntu-settings-firewall-tools/)
- [Frank's Blog - Hardening Ubuntu Server 24.04 LTS](https://frankschmidt-bruecken.com/en/blog/ubuntu-server-hardening/)
- [Ultimate Initial Server Setup with Ubuntu 2025-2026](https://www.progressiverobot.com/2026/02/15/ultimate-initial-server-setup-with-ubuntu/)
- [SSH Hardening Guides - ssh-audit.com](https://www.sshaudit.com/hardening_guides.html)
- [SSH Hardening: Best Practices | Linuxize](https://linuxize.com/post/ssh-hardening-best-practices/)
- [Securing SSH Server Configuration in 2025](https://farrokhi.net/posts/2025/11/securing-ssh-server-configuration-in-2025/)
- [sshd-hardening-ed25519 | GitHub](https://github.com/krabelize/sshd-hardening-ed25519/blob/master/sshd_config)
- [Options for hardening systemd service units | GitHub Gist](https://gist.github.com/ageis/f5595e59b1cddb1513d1b425a323db04)
- [systemd/Sandboxing - ArchWiki](https://wiki.archlinux.org/title/Systemd/Sandboxing)
- [PostgreSQL Security Best Practices | Bytebase](https://www.bytebase.com/reference/postgres/how-to/postgres-security-best-practices/)
- [How To Secure PostgreSQL Against Automated Attacks | DigitalOcean](https://www.digitalocean.com/community/tutorials/how-to-secure-postgresql-against-automated-attacks)
- [How to Install Fail2ban for SSH Security on Ubuntu 24.04 | TecMint](https://www.tecmint.com/install-fail2ban-ubuntu-24-04/)
- [Automatic Updates - Ubuntu Server Documentation](https://documentation.ubuntu.com/server/how-to/software/automatic-updates/)
- [Fortify Your VPS Against Brute-Force Attacks | VPS.DO](https://vps.do/brute-force-attacks/)
- [5 Easy Steps to Secure your Cloud Server | DEV Community](https://dev.to/code42cate/5-easy-steps-to-secure-your-cloud-server-i17)
- [Hetzner Cloud Firewall Docs](https://docs.hetzner.com/robot/dedicated-server/firewall/)
- [Detecting Cryptomining Attacks in the Wild | Sysdig](https://www.sysdig.com/blog/detecting-cryptomining-attacks-in-the-wild)
- [PYPI Security: Supply Chain Attacks in Python | Bolster](https://bolster.ai/blog/pypi-supply-chain-attacks)
- [pip-audit | PyPI](https://pypi.org/project/pip-audit/)
