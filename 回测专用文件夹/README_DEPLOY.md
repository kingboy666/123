# 🚀 一键部署指南

## 快速开始

### 方法1: 使用部署脚本（推荐）
```bash
# 运行部署脚本
bash deploy.sh
```

### 方法2: 手动部署步骤

#### 1. 初始化Git仓库
```bash
git init
git add .
git commit -m "feat: 部署交易策略回测系统"
```

#### 2. 推送到GitHub
```bash
git remote add origin https://github.com/您的用户名/仓库名.git
git branch -M main
git push -u origin main
```

#### 3. 部署到Railway
1. 访问 [Railway](https://railway.app/)
2. 点击 "New Project"
3. 选择 "Deploy from GitHub repo"
4. 选择您的仓库
5. Railway会自动开始部署

#### 4. 配置环境变量
在Railway项目设置中配置：
```
OKX_API_KEY=您的API密钥
OKX_API_SECRET=您的API密钥  
OKX_API_PASSPHRASE=您的API密码
```

## 📋 部署前检查

运行配置检查脚本：
```bash
python railway-setup.py
```

## 🌐 访问系统

部署完成后，访问Railway提供的URL：
- 主界面：`https://您的项目名.railway.app`
- API文档：`https://您的项目名.railway.app/api`

## 🔧 故障排除

### 常见问题

**部署失败：**
- 检查 `requirements.txt` 中的依赖版本
- 查看Railway部署日志
- 确保所有文件都在根目录

**环境变量错误：**
- 确认API密钥格式正确
- 检查密钥权限设置

**服务无法启动：**
- 检查 `main.py` 中的端口配置
- 确认Procfile格式正确

## 📞 技术支持

如需帮助：
1. 查看部署日志
2. 运行 `python railway-setup.py` 检查配置
3. 检查环境变量设置

---
**部署完成后即可开始使用真实数据回测交易策略！**