# 整理记录

来源目录：

- `C:\Users\jin\Desktop\BatteryServer`
- `C:\Users\jin\Desktop\better`
- `C:\Users\jin\Desktop\树莓派`

整理后的主项目放在桌面 `BatteryServer_GitHub_整理`。本目录面向 GitHub 上传，只保留主线源码、模型、配置示例、部署文档和数据库建表脚本。

## 保留内容

- 客户端采用 `better\dist\dist_client`，因为这版支持配置文件、日志、离线补传和摄像头参数。
- 服务端采用 `better\server`，因为这版包含登录限流、主题切换、数据看板、导出和用户管理等更新。
- 数据库只保留建表脚本，未保留原始 `localhost.sql` 的模拟数据 dump。
- `client/best.pt` 保留为客户端推理必需模型。

## 排除内容

- `__pycache__`、`logs`、运行图片、上传图片、打包后的 `dist` 重复内容。
- Tailscale 安装包、快捷方式、软著源码生成工具、内置 JDK 和第三方示例文档。
- 旧版/实验脚本中硬编码公网 IP、数据库密码和本地路径的副本。
- SolidWorks 零件、现场照片、临时 Word 锁文件和非源码资料。

## 上传建议

1. 在本目录初始化 Git 仓库。
2. 如果要提交 `client/best.pt`，先安装并启用 Git LFS。
3. 本地复制配置示例为真实配置文件，真实配置文件不要提交。
