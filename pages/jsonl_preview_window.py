"""
JSONL 预览窗口 - 使用 pygame 和 live2d 预览 JSONL 文件中的所有模型
"""
import os
import json
import pygame
import tempfile

try:
    import live2d.v2 as live2d_v2
    LIVE2D_V2_AVAILABLE = True
except ImportError:
    LIVE2D_V2_AVAILABLE = False
    live2d_v2 = None

try:
    import live2d.v3 as live2d_v3
    LIVE2D_V3_AVAILABLE = True
except ImportError:
    LIVE2D_V3_AVAILABLE = False
    live2d_v3 = None
# 搞不好jsonl会支持moc3呢
# 哈哈，进军pjsk

LIVE2D_AVAILABLE = LIVE2D_V2_AVAILABLE or LIVE2D_V3_AVAILABLE

from sections.py_live2d_editor import _load_json_without_motions_expressions


class JsonlPreviewWindow:
    """JSONL 模型预览窗口"""
    
    def __init__(self, jsonl_path: str, data: list):
        """
        Args:
            jsonl_path: JSONL 文件路径
            data: 已解析的模型数据列表（不包含 summary 行）
        """
        self.running = True  # 运行标志，用于外部控制关闭
        self.jsonl_path = jsonl_path
        self.data = data
        self.jsonl_base_dir = os.path.dirname(os.path.abspath(jsonl_path))
        
        # 解析 JSONL 获取 import 参数
        self.param_import = None
        self._parse_import_from_jsonl()
        
        # 模型列表
        self.models_v2 = []  # Live2D v2 模型
        self.models_v3 = []  # Live2D v3 模型
        self.temp_files = []  # 临时文件列表，用于清理
        # 保存每个模型的配置信息（用于在 Resize 后重新应用）
        self.model_configs = []  # [(model, x, y, xscale, yscale, is_v3)]
        
        # 坐标系参数（参考 WebGAL 的实现）
        # Live2D 目标画布尺寸（2560x1440）
        self.base_width = 2560.0
        self.base_height = 1440.0
        # 预览窗口尺寸（按比例缩放，保持 16:9 比例）
        preview_scale = 0.4  # 预览窗口缩放比例（降低以提高性能）
        self.canvas_width = int(self.base_width * preview_scale)  # 1024
        self.canvas_height = int(self.base_height * preview_scale)  # 576
        
    def _parse_import_from_jsonl(self):
        """从 JSONL 文件中解析 import 参数"""
        try:
            with open(self.jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        # 检查是否是 summary 行（包含 motions 或 expressions）
                        if (obj.get("motions") is not None or 
                            obj.get("expressions") is not None):
                            if "import" in obj:
                                self.param_import = int(obj["import"])
                                print(f"检测到汇总 import = {self.param_import}")
                                break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"解析 import 参数失败: {e}")
    
    def _resolve_path(self, path: str) -> str:
        """解析相对路径为绝对路径"""
        normalized = path.replace("\\", "/").lstrip("./")
        
        # 如果是绝对路径或 URL，直接返回
        if os.path.isabs(normalized) or normalized.startswith(("http://", "https://")):
            return normalized
        
        # 处理 "game/" 前缀：尝试在 JSONL 目录的父目录中查找 game 目录
        if normalized.startswith("game/"):
            # 移除 "game/" 前缀
            rel_path = normalized[5:]  # len("game/") = 5
            # 尝试在 JSONL 目录的父目录中查找 game 目录
            current_dir = self.jsonl_base_dir
            while current_dir and current_dir != os.path.dirname(current_dir):
                game_dir = os.path.join(current_dir, "game")
                if os.path.isdir(game_dir):
                    full_path = os.path.join(game_dir, rel_path)
                    if os.path.isfile(full_path):
                        return os.path.normpath(full_path)
                current_dir = os.path.dirname(current_dir)
            # 如果找不到，返回原始路径
            return normalized
        
        # 相对路径：基于 JSONL 文件所在目录
        return os.path.normpath(os.path.join(self.jsonl_base_dir, normalized))
    
    def _load_models(self):
        """加载所有模型"""
        if not LIVE2D_AVAILABLE:
            print("错误: live2d 库不可用")
            return False
        
        for idx, obj in enumerate(self.data):
            model_path = obj.get("path", "")
            if not model_path:
                print(f"警告: 第 {idx + 1} 行缺少 path 字段")
                continue
            
            full_path = self._resolve_path(model_path)
            
            # 判断是 v2 还是 v3 模型
            is_v3 = full_path.endswith(".model3.json")
            
            try:
                # 创建临时文件（移除 motions 和 expressions）
                temp_path = _load_json_without_motions_expressions(full_path)
                self.temp_files.append(temp_path)
                
                if is_v3:
                    if not LIVE2D_V3_AVAILABLE:
                        print(f"警告: 模型 {model_path} 是 v3 格式，但 live2d.v3 不可用，跳过")
                        continue
                    model = live2d_v3.LAppModel()
                else:
                    if not LIVE2D_V2_AVAILABLE:
                        print(f"警告: live2d.v2 不可用，无法加载模型 {model_path}")
                        continue
                    model = live2d_v2.LAppModel()
                
                model.LoadModelJson(temp_path)
                
                # 读取配置
                x = float(obj.get("x", 0.0))
                y = float(obj.get("y", 0.0))
                xscale = float(obj.get("xscale", 1.0))
                yscale = float(obj.get("yscale", 1.0))
                
                # 保存配置信息（在 Resize 后重新应用）
                self.model_configs.append((model, x, y, xscale, yscale, is_v3))
                
                # 设置 PARAM_IMPORT（参照 update_parameter 方法）
                if self.param_import is not None:
                    try:
                        # 使用 SetParameterValue 方法，传入参数 ID（字符串）和权重值
                        # 参考: model.SetParameterValue(param_id, value, 1.0)
                        if hasattr(model, "SetParameterValue"):
                            # 直接使用参数 ID 字符串
                            model.SetParameterValue("PARAM_IMPORT", float(self.param_import), 1.0)
                            print(f"✅ 设置 PARAM_IMPORT={self.param_import} 给模型: {model_path}")
                        else:
                            # 如果没有 SetParameterValue，尝试使用索引方式
                            param_count = model.GetParameterCount()
                            for i in range(param_count):
                                param = model.GetParameter(i)
                                param_id = getattr(param, "id", None) or str(getattr(param, "id", ""))
                                if param_id == "PARAM_IMPORT":
                                    if hasattr(model, "SetParameter"):
                                        model.SetParameter(i, float(self.param_import))
                                        print(f"✅ 设置 PARAM_IMPORT={self.param_import} 给模型: {model_path}")
                                    break
                    except Exception as e:
                        print(f"❌ 设置 PARAM_IMPORT 失败: {e}")
                        import traceback
                        traceback.print_exc()
                
                # 模型已添加到 model_configs，这里只需要分类
                if is_v3:
                    self.models_v3.append(model)
                else:
                    self.models_v2.append(model)
                    
                print(f"✅ 已加载模型 {idx + 1}/{len(self.data)}: {model_path}")
                
            except Exception as e:
                print(f"❌ 加载模型失败 {model_path}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        return len(self.models_v2) + len(self.models_v3) > 0
    
    def run(self):
        """运行预览窗口"""
        if not LIVE2D_AVAILABLE:
            print("错误: live2d 库不可用，无法预览")
            return
        
        # 初始化 pygame
        pygame.init()
        
        # 初始化 live2d
        try:
            if LIVE2D_V2_AVAILABLE:
                live2d_v2.init()
            if LIVE2D_V3_AVAILABLE:
                live2d_v3.init()
        except Exception as e:
            print(f"初始化 live2d 失败: {e}")
            pygame.quit()
            return
        
        # 创建窗口
        display = (self.canvas_width, self.canvas_height)
        # 尝试使用硬件加速和 VSync
        try:
            screen = pygame.display.set_mode(display, pygame.DOUBLEBUF | pygame.OPENGL | pygame.HWSURFACE)
        except:
            # 如果硬件加速失败，回退到基本模式
            screen = pygame.display.set_mode(display, pygame.DOUBLEBUF | pygame.OPENGL)
        pygame.display.set_caption("JSONL 模型预览 - 按 ESC 退出")
        
        # 计算缩放比例（参考 WebGAL 的实现）
        # scaleX = canvasWidth / baseWidth
        # scaleY = canvasHeight / baseHeight
        self.scale_x = self.canvas_width / self.base_width
        self.scale_y = self.canvas_height / self.base_height
        
        # 基线位置（画布中心）
        self.base_x = self.canvas_width / 2
        self.base_y = self.canvas_height / 2
        
        try:
            if LIVE2D_V2_AVAILABLE:
                live2d_v2.glewInit()
            if LIVE2D_V3_AVAILABLE:
                live2d_v3.glewInit()
        except Exception as e:
            print(f"初始化 GLEW 失败: {e}")
            if LIVE2D_V2_AVAILABLE:
                live2d_v2.dispose()
            if LIVE2D_V3_AVAILABLE:
                live2d_v3.dispose()
            pygame.quit()
            return
        
        # 加载模型
        if not self._load_models():
            print("错误: 没有成功加载任何模型")
            if LIVE2D_V2_AVAILABLE:
                live2d_v2.dispose()
            if LIVE2D_V3_AVAILABLE:
                live2d_v3.dispose()
            pygame.quit()
            return
        
        # 调整所有模型大小并应用配置
        # 注意：Resize 可能会重置位置和缩放，所以需要在 Resize 之后重新设置
        for model, x, y, xscale, yscale, is_v3 in self.model_configs:
            # 先调整大小
            model.Resize(*display)
            
            # 坐标转换：参考 WebGAL 的实现
            # JSONL 中的 x, y 是基于 baseWidth/baseHeight (2560x1440) 的坐标
            # WebGAL 中的转换逻辑：
            # px = (position.x ?? 0) * scaleX  // scaleX = canvasWidth / baseWidth
            # py = (position.y ?? 0) * scaleY  // scaleY = canvasHeight / baseHeight
            # container.x = baseX + px  // baseX = canvasWidth / 2
            # container.y = baseY + py  // baseY = canvasHeight / 2
            #
            # 但是 SetOffset 的参数可能是基于模型尺寸的归一化坐标
            # 参考代码中 SetOffset(-0.5, 0.0) 表示向左移动模型宽度的一半
            
            # 步骤1: 将 JSONL 坐标转换为预览窗口的像素坐标
            px = x * self.scale_x  # 基于 2560x1440 的 x 转换为预览窗口像素
            py = y * self.scale_y  # 基于 2560x1440 的 y 转换为预览窗口像素
            
            # 步骤2: 转换为归一化坐标
            # SetOffset 的参数可能是基于 baseWidth/baseHeight 的归一化坐标
            # 即：normalized = (JSONL坐标) / (baseWidth或baseHeight / 2)
            # 这样可以直接使用 JSONL 中的 x, y 值进行归一化
            normalized_x = -x / (self.base_width / 2.0) if self.base_width > 0 else 0.0
            normalized_y = -y / (self.base_height / 2.0) if self.base_height > 0 else 0.0
            
            # 使用归一化坐标设置位置
            model.SetOffset(normalized_x, normalized_y)
            
            # 设置缩放（注意：SetScale 可能只设置一个方向的缩放）
            model.SetScale(xscale)
            
            # 如果 yscale 与 xscale 不同，可能需要特殊处理
            # 但大多数情况下，Live2D 的 SetScale 可能只支持统一缩放
            if abs(yscale - xscale) > 0.001:
                print(f"警告: 模型 yscale ({yscale}) 与 xscale ({xscale}) 不同，但 SetScale 可能只支持统一缩放")
            
            print(f"模型位置: JSONL(x={x}, y={y}) -> 偏移(px={px:.1f}, py={py:.1f}) -> 归一化(nx={normalized_x:.3f}, ny={normalized_y:.3f}), 缩放={xscale}")
            
            # 调试：检查模型是否在可见范围内
            if abs(normalized_x) > 1.0 or abs(normalized_y) > 1.0:
                print(f"⚠️ 警告: 归一化坐标超出范围，已限制")
        
        # 主循环
        clock = pygame.time.Clock()
        
        print("预览窗口已启动，按 ESC 或关闭窗口退出")
        print(f"目标帧率: 30 FPS，窗口尺寸: {self.canvas_width}x{self.canvas_height}")
        
        # 性能统计
        frame_count = 0
        last_fps_time = pygame.time.get_ticks()
        
        while self.running:
            # 批量处理事件，提高效率
            events = pygame.event.get()
            mouse_moved = False
            mouse_x, mouse_y = 0, 0
            
            for event in events:
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                elif event.type == pygame.MOUSEMOTION:
                    # 记录鼠标位置，稍后统一处理
                    mouse_moved = True
                    mouse_x, mouse_y = pygame.mouse.get_pos()
            
            # 只在鼠标移动时处理拖拽（减少不必要的调用）
            if mouse_moved:
                if LIVE2D_V2_AVAILABLE:
                    for model in self.models_v2:
                        model.Drag(mouse_x, mouse_y)
                if LIVE2D_V3_AVAILABLE:
                    for model in self.models_v3:
                        model.Drag(mouse_x, mouse_y)
            
            # 清空缓冲区（每帧都需要）
            if LIVE2D_V3_AVAILABLE:
                live2d_v3.clearBuffer()
            if LIVE2D_V2_AVAILABLE:
                live2d_v2.clearBuffer()
            
            # 更新和绘制所有模型
            # 先绘制 v2 模型
            if LIVE2D_V2_AVAILABLE:
                for model in self.models_v2:
                    model.Update()
                    model.Draw()
            
            # 再绘制 v3 模型
            if LIVE2D_V3_AVAILABLE:
                for model in self.models_v3:
                    model.Update()
                    model.Draw()
            
            # 刷新显示
            pygame.display.flip()
            
            # 限制帧率为 30 FPS（提高稳定性）
            clock.tick(30)
            
            # 每 60 帧输出一次 FPS（可选，用于调试）
            frame_count += 1
            if frame_count % 60 == 0:
                current_time = pygame.time.get_ticks()
                elapsed = (current_time - last_fps_time) / 1000.0
                if elapsed > 0:
                    fps = 60 / elapsed 
                    print(f"当前 FPS: {fps:.1f}")
                last_fps_time = current_time
        
        # 设置运行标志为 False
        self.running = False
        
        # 清理资源
        print("正在清理资源...")
        for model in self.models_v2:
            try:
                model = None
            except:
                pass
        for model in self.models_v3:
            try:
                model = None
            except:
                pass
        
        # 删除临时文件
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                print(f"删除临时文件失败 {temp_file}: {e}")
        
        if LIVE2D_V2_AVAILABLE:
            live2d_v2.dispose()
        if LIVE2D_V3_AVAILABLE:
            live2d_v3.dispose()
        pygame.quit()
        
        print("预览窗口已关闭")

