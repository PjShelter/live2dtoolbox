# 🎉 Live2D 工具箱

> 如果你觉得这个工具对你有帮助，欢迎关注 B 站 UP 主 **东山燃灯寺**！
> 💖 你的支持是我持续改进的动力！
> 🔗 B 站链接：[https://space.bilibili.com/296330875](https://space.bilibili.com/296330875?spm_id_from=333.1007.0.0)

一个专为 **Live2D Cubism 2 模型** 和 **WebGAL 视觉小说引擎** 开发的图形化工具箱。

> ⚠️ 本工具**仅支持 Cubism 2 时代的模型结构**（.moc 格式）

---

## 🔥 主要功能

### 🎨 色彩匹配工具
- 图像色调迁移：将源图像的色调匹配到参考图像的风格
- 自动生成 WebGAL `setTransform` 色调指令
- 可视化对比图表，直观查看 RGB 参数变化
- 支持从 `png/` 文件夹快速选择参考图

### 🧰 Live2D 模型管理
- **扫描生成**：自动扫描目录生成标准 `model.json` 配置
- **去重清理**：检测并删除重复项和无效路径，自动备份
- **批量添加**：批量导入动作(.mtn)和表情(.exp.json)文件，支持自定义前缀
- **MTN 参数编辑**：批量修改 `.mtn` 文件中的 `PARAM_IMPORT` 等参数
- **支持 JSONL**：可对 JSONL 文件中的所有模型批量操作

### 📄 JSONL 生成与编辑
- **生成器**：为"拼好模"生成 JSONL 配置文件
- **可视化编辑**：图形界面编辑 JSONL 中的模型列表
- **部件管理**：调整部件顺序、添加/删除子模型
- **统一配置**：批量设置 import 参数、动作和表情列表

### 🔧 其他工具
- **Import 参数表**：查看 Live2D 表情参数对照表
- **透明度预设**：快速配置模型透明度
- **L2DW 配置**：Live2D Widget 配置文件生成
- **自动更新检查**：一键检查 GitHub 最新版本

---

## 🚀 快速开始

### 方式一：直接运行（推荐）

下载 [Release](https://github.com/KonshinHaoshin/gen_model/releases) 中的 `Live2DToolbox.exe`，双击运行即可。

### 方式二：从源码运行

1. **安装依赖**：
   ```bash
   pip install PyQt5 pillow numpy matplotlib requests python-dotenv
   ```

2. **运行主程序**：
   ```bash
   python main_ui.py
   ```

3. **使用图形界面**：
   - 顶部标签页切换不同功能模块
   - 所有操作都有图形界面引导
   - 配置会自动保存到 `config.json`

---

## 📖 功能详解


### 🧰 Live2D 模型管理

**扫描生成 model.json**：
- 自动识别 `.moc`、`.physics.json`、`.png`、`.mtn`、`.exp.json` 文件
- 生成标准格式的 `model.json` 配置文件

**去重清理**：
- 检测重复的动作/表情条目
- 检查文件路径是否存在
- 自动备份为 `.bak` 文件
- 支持单个 `model.json` 或整个 JSONL 文件

**批量添加动作/表情**：
- 选择文件夹，勾选需要添加的文件
- 支持自定义名称前缀
- 可对 JSONL 中的所有模型批量操作

**MTN 参数编辑**：
- 批量修改指定目录下所有 `.mtn` 文件
- 常用于调整 `PARAM_IMPORT` 参数值

---

### 📄 JSONL 生成器

**什么是"拼好模"**：将多个 Live2D 模型部件（头发、身体、脸等）组合成一个完整角色。

**使用步骤**：
1. 选择包含多个子目录的根目录
2. 点击"列出子目录"查看所有子文件夹
3. 选择需要包含的子目录（可调整顺序）
4. 设置 ID 前缀
5. 可选：勾选"统一 import"并设置数值
6. 点击"生成 JSONL"

**生成的文件格式**：
```json
{"index": 0, "id": "myid0", "path": "1.头发/model.json", "folder": "1.头发"}
{"index": 1, "id": "myid1", "path": "2.身体/model.json", "folder": "2.身体"}
{"motions": ["idle01"], "expressions": ["default"]}
```

**JSONL 编辑器**：
- 可视化编辑已有的 JSONL 文件
- 添加/删除部件
- 调整部件顺序
- 编辑动作和表情列表

---

## 📂 推荐目录结构

```
your_model_folder/
├── model.json          # 模型配置文件
├── model.moc           # 模型文件
├── physics.json        # 物理配置（可选）
├── texture_00.png      # 贴图
├── idle.mtn            # 动作文件
├── happy.exp.json      # 表情文件
└── ...
```

**拼好模目录结构**：
```
character_name/
├── 1.头发/
│   ├── model.json
│   ├── model.moc
│   └── texture_00.png
├── 2.身体/
│   ├── model.json
│   └── ...
├── 3.脸/
│   └── ...
└── character_name.jsonl  # 生成的配置文件
```

---

## 🎭 JSONL 文件格式说明

### 字段说明

| 字段名        | 类型   | 描述                                                         |
| ------------- | ------ | ------------------------------------------------------------ |
| `index`       | int    | 模型部件在组合中的顺序（用于排序）                           |
| `id`          | string | 每个部件的唯一 ID（通常由 `prefix + index` 构成）           |
| `path`        | string | 指向每个部件的 `model.json` 路径（相对路径）                 |
| `folder`      | string | 部件所在子目录名称                                           |
| `motions`     | array  | **仅出现在最后一行**，表示所有部件支持的共通动作名称列表     |
| `expressions` | array  | **仅出现在最后一行**，表示所有部件中至少有一个支持的表情名称列表 |
| `import`      | int    | **可选字段**，表示默认的 import 参数值                       |

### 引擎支持

目前仅在 **Eastmount 系列引擎**（基于 WebGAL 的修改版）中支持。

---

## 💡 使用技巧

- 工具会自动保存上次使用的路径到 `config.json`
- 所有修改 `model.json` 的操作都会自动备份为 `.bak` 文件
- 色彩匹配的参考图放在 `png/` 文件夹中可快速选择
- JSONL 生成时，子目录名称建议使用数字前缀（如 `1.头发`）便于排序

---

## 🛠 开发相关

### 打包为 exe

```bash
pyinstaller -w -F main_ui.py --icon=icon.ico --name Live2DToolbox --add-data "icon.png;."
```

### 项目结构

```
gen_model/
├── main_ui.py              # 主界面
├── pages/                  # 各功能页面
│   ├── batch_tool_page.py
│   ├── jsonl_generator_page.py
│   ├── jsonl_editor_page.py
│   └── ...
├── sections/               # 核心功能模块
│   ├── live2d_tool.py
│   ├── color_transfer.py
│   └── gen_jsonl.py
└── utils/                  # 工具函数
```

---

## 📜 License

本项目遵循 MIT 协议，欢迎自由使用、修改和分发。

---

## 🤝 贡献与反馈

欢迎发起 Issue 或 PR！有更多想法也欢迎联系我，我会持续维护和优化。

**GitHub**: [https://github.com/KonshinHaoshin/gen_model](https://github.com/KonshinHaoshin/gen_model)
