# 🎉 [gen_model](https://github.com/KonshinHaoshin/gen_model)

> 如果你觉得这个工具对你有帮助，欢迎关注 B 站 UP 主 **东山燃灯寺**！  
> 💖 你的支持是我持续改进的动力！  
> 🔗 B 站链接：[https://space.bilibili.com/296330875](https://space.bilibili.com/296330875?spm_id_from=333.1007.0.0)

✨ 本项目是一个专为 **Live2D Cubism 2 SDK 模型** 开发的资源管理与自动化工具，帮助用户轻松创建、更新并批量整理 `model.json` 配置文件，极大地减少手动编辑负担。

> ⚠️ 本工具**仅支持 Cubism 2 时代的模型结构**。

---

## 🔥 主要功能

### 1. ✅ 生成 `model.json`

- 自动扫描指定的 Live2D 模型目录，生成标准格式的 `model.json`。
- 自动分类并导入：
  - `.moc` 模型文件
  - `.physics.json` 物理配置
  - `.png` 贴图纹理
  - `.mtn` 动作
  - `.exp.json` 表情文件

### 2. ➕ 添加单个动作或表情

- 向已有的 `model.json` 添加单个 `.mtn` 或 `.exp.json` 文件。
- 自动路径相对化，方便跨平台使用。

### 3. 📦 批量添加动作或表情

- 支持输入一个文件夹或多个文件路径（用 `;` 分隔）进行批量导入。
- 可自定义名称前缀，便于组织管理。

### 4. 🧹 去重 + 删除无效路径（全新功能！）

- 自动检测并去重 `model.json` 中的重复动作/表情。
- 自动检测文件是否实际存在，**集中列出所有缺失项**，并询问是否一键删除对应记录。
- 自动备份原始 `model.json` 为 `.bak` 文件。

### 5. 🛠 批量修改 `.mtn` 文件中的 `PARAM_IMPORT` 参数

- 快速替换指定目录下所有 `.mtn` 文件中的 `PARAM_IMPORT` 值，用于调整动作权重或合成行为。

---

## 🚀 使用方法

1. **运行 `live2d_tool.py`**：

   ```bash
   python live2d_tool.py
   ```

2. **根据菜单提示选择功能**：

   ```
   1. 生成新的 model.json
   2. 添加单个动作/表情到 model.json
   3. 批量添加动作/表情到 model.json
   4. 去重 model.json 中重复的动作/表情，并删除不存在的路径
   5. 批量更改 mtn 文件中的 PARAM_IMPORT 参数
   q. 退出程序
   ```

3. **按照提示输入文件路径、参数等信息**，等待程序执行完成。

---

## 📂 推荐文件结构（示例）

```
your_model_folder/
├── model.moc
├── model.json
├── physics.json
├── texture_00.png
├── idle.mtn
├── happy.exp.json
└── ...
```

---

## 💡 小贴士

- 使用前请备份模型目录，避免误操作。
- 工具默认会对 `model.json` 进行 `.bak` 备份，放心修改。
- 建议在模型制作后期使用本工具进行资源整理与批量修复。

## 🎨 新功能：`color_transfer.py` — 图像色调匹配 & WebGAL 色调指令生成

> 快速将一张图像的整体色调迁移为另一张图像的风格，并自动生成 WebGAL 使用的 `setTransform` 指令！

------

### 🔧 功能介绍

- 对比源图与参考图的 RGB 色彩分布，自动生成“匹配风格”的新图像。
- 自动构造 WebGAL 指令：根据参考图相对于源图的亮度差异，生成精确的 `colorRed` / `colorGreen` / `colorBlue` 参数。
- 支持交互式选择图像，输出图像自动保存并可视化预览。

------

### 📦 使用方式

1. 将源图像（需要调整风格）准备好；

2. 将参考图像放入 `png/` 文件夹（支持多个 .png）；

3. 运行安装依赖

   ```bash
   pip install pillow numpy matplotlib
   ```

4. 运行

   ```bash
   python color_transfer.py
   ```

5. 按照命令行提示操作：

6. 程序将输出：

   - 一张新的色调匹配图：保存在 `output/` 文件夹中；
   - 一条 WebGAL 可用的 `setTransform` 指令，直接复制使用。

### 📌 示例输出

```bash
✅ Color matching done. Saved to: output/matched_background_cool.png

🎬 Suggested WebGAL Transform Command:
setTransform:{"colorRed": 130, "colorGreen": 210, "colorBlue": 255} -target=bg-main -duration=0 -next;
```

### 🔄 数学原理：**标准化 + 分布转换**

这一步是核心：

1. 将源图的每个像素先标准化为 **零均值单位方差**

   ```math
   z=x−μsrcσsrcz = \frac{x - \mu_{\text{src}}}{\sigma_{\text{src}}}z=σsrcx−μsrc
   ```

   

   

2. 再重构为目标图的分布：

   ```math
   xnew=z⋅σtgt+μtgtx_{\text{new}} = z \cdot \sigma_{\text{tgt}} + \mu_{\text{tgt}}xnew=z⋅σtgt+μtgt
   ```

   

这相当于将源图的色彩分布“平移+拉伸”为参考图的色彩分布。

即对每个 RGB 通道：

- 将源图像的亮度“拉平”为标准分布；
- 然后再“拉回”成目标图的风格。

 🧠 WebGAL 色调分析：

每个通道（R/G/B）默认值为 `255`，程序将根据参考图的相对亮度变化与源图进行对比，输出：

```python
colorX = 255 - (source_mean - target_mean)
```

并保证结果范围在 `[0, 255]`，自动向 WebGAL 样式靠拢。

### ✅ 示例

![1](readme/1.png)

![2](readme/2.png)

![3](readme/3.png)

> ```webgal
> changeBg:E（live house）/E6.png;
> setTransform:{"colorRed": 139, "colorGreen": 174, "colorBlue": 204} -target=bg-main -duration=0 -next;
> ```

![4](readme/4.png)

## 📜 License

本项目遵循 MIT 协议，欢迎自由使用、修改和分发。

---

如需自动化脚本、图形界面或与 Live2D Viewer 配套使用的功能，欢迎发起 Issue 或 PR！  
有更多想法也欢迎联系我，我会持续维护和优化。




```bash
pyinstaller -w -F main_ui.py --icon=icon.ico --name Live2DToolbox --add-data "style.qss;."                                   
                                                                                    
```