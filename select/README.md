# 锂电池外观缺陷检测与智能分拣系统

这是一个云端管理平台 + 树莓派边缘端的锂电池外观缺陷检测项目。边缘端负责摄像头采集、YOLO 缺陷识别、传送带与分拣机构控制，并把检测结果上传到服务端；服务端负责 MySQL 入库、Web 可视化、人员管理、数据查询和导出。

## 目录结构

```text
client/    树莓派边缘端程序、硬件驱动、YOLO 权重
server/    Flask + Waitress 服务端和配置示例
database/  初始化建表 SQL
docs/      部署说明和使用手册
tools/     模拟数据、索引、文档生成等辅助脚本
```

## 快速开始

### 服务端

```bash
cd server
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
copy server_config.example.json server_config.json
python server.py
```

Linux/macOS 将激活命令换成 `source .venv/bin/activate`。部署前请修改 `server_config.json` 里的数据库密码、上传目录、`app_secret_key` 和初始管理员密码。

### 客户端

```bash
cd client
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements_client.txt
copy config.example.json config.json
python final.py
```

在树莓派上运行时，把 `config.json` 中的 `server_ip` 改为服务端地址，并按现场硬件调整摄像头、步进电机和传感器参数。离线登录默认关闭，如确需现场脱网调试，可在本地 `config.json` 中开启并设置离线口令。

## 上传 GitHub 前说明

整理版已排除运行日志、缓存、打包目录、安装程序、照片样本、软著工具和真实运行配置。`client/best.pt` 是运行客户端 AI 推理所需模型，建议启用 Git LFS 后再提交。
