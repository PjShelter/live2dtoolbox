"""
单个模型预览窗口 - 使用 pygame 和 live2d 预览单个 Live2D 模型（带预设的 init_opacities）
"""
import os
import json
import pygame
import tempfile
import threading

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

LIVE2D_AVAILABLE = LIVE2D_V2_AVAILABLE or LIVE2D_V3_AVAILABLE

from sections.py_live2d_editor import _load_json_without_motions_expressions


class SingleModelPreviewWindow:
    """单个模型预览窗口"""
    
    def __init__(self, model_json_path: str, init_opacities: list = None):
        """
        Args:
            model_json_path: model.json 文件路径
            init_opacities: init_opacities 列表，格式为 [{"id": "PARTS_XXX", "value": 1.0}, ...]
                           如果为 None，则使用原始 JSON 中的 init_opacities
        """
        self.running = True  # 运行标志，用于外部控制关闭
        self.model_json_path = model_json_path
        self.init_opacities = init_opacities
        self.temp_file = None  # 临时文件路径，用于清理
        
        # 模型
        self.model = None
        self.is_v3 = False
        
        # 窗口尺寸
        self.canvas_width = 800
        self.canvas_height = 600
        
    def _create_virtual_json(self) -> str:
        """创建虚拟 JSON 文件（包含预设的 init_opacities，移除 motions/expressions）"""
        try:
            # 读取原始 JSON
            with open(self.model_json_path, "r", encoding="utf-8") as f:
                model_data = json.load(f)
            
            # 移除 motions 和 expressions
            model_data.pop("motions", None)
            model_data.pop("expressions", None)
            
            # 应用预设的 init_opacities
            if self.init_opacities is not None:
                model_data["init_opacities"] = self.init_opacities
                print(f"✅ 已应用预设的 init_opacities: 共 {len(self.init_opacities)} 个部件")
                # 打印前几个部件的信息用于调试
                visible_parts = [item for item in self.init_opacities if item.get("value", 0.0) == 1.0]
                print(f"   可见部件数量: {len(visible_parts)}")
                if visible_parts:
                    print(f"   前5个可见部件: {[item['id'] for item in visible_parts[:5]]}")
            else:
                print("📌 使用原始 JSON 中的 init_opacities")
            
            # 创建临时文件
            temp_dir = os.path.dirname(self.model_json_path)
            temp_fd, temp_path = tempfile.mkstemp(suffix=".json", dir=temp_dir, text=True)
            try:
                with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                    json.dump(model_data, f, ensure_ascii=False, indent=2)
                return temp_path
            except Exception:
                os.close(temp_fd)
                raise
        except Exception as e:
            print(f"创建虚拟 JSON 失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _apply_opacities(self, label: str = ""):
        """将 init_opacities 应用到当前模型"""
        if self.init_opacities is None or not self.model:
            return
        try:
            part_id_to_index = {pid: idx for idx, pid in enumerate(self.model.GetPartIds())}
            applied = 0
            for item in self.init_opacities:
                part_id = item.get("id")
                opacity = float(item.get("value", 0.0))
                if part_id in part_id_to_index:
                    idx = part_id_to_index[part_id]
                    if hasattr(self.model, "SetPartOpacity"):
                        self.model.SetPartOpacity(idx, opacity)
                    elif hasattr(self.model, "SetPart"):
                        self.model.SetPart(idx, opacity)
                    applied += 1
            print(f"✅ {label}应用了 {applied} 个部件的透明度设置")
        except Exception as e:
            print(f"⚠️ {label}应用透明度设置时出错: {e}")

    def _load_model(self) -> bool:
        """加载模型"""
        if not LIVE2D_AVAILABLE:
            print("错误: live2d 库不可用")
            return False
        
        # 创建虚拟 JSON
        temp_path = self._create_virtual_json()
        if not temp_path:
            return False
        self.temp_file = temp_path
        
        # 判断是 v2 还是 v3 模型
        self.is_v3 = self.model_json_path.endswith(".model3.json")
        
        try:
            if self.is_v3:
                if not LIVE2D_V3_AVAILABLE:
                    print(f"警告: 模型是 v3 格式，但 live2d.v3 不可用")
                    return False
                self.model = live2d_v3.LAppModel()
            else:
                if not LIVE2D_V2_AVAILABLE:
                    print(f"警告: live2d.v2 不可用")
                    return False
                self.model = live2d_v2.LAppModel()
            
            # 加载模型
            self.model.LoadModelJson(temp_path)
            print(f"✅ 已加载模型: {self.model_json_path}")

            self._apply_opacities("加载后")
            return True
            
        except Exception as e:
            print(f"❌ 加载模型失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
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
        try:
            screen = pygame.display.set_mode(display, pygame.DOUBLEBUF | pygame.OPENGL | pygame.HWSURFACE)
        except:
            screen = pygame.display.set_mode(display, pygame.DOUBLEBUF | pygame.OPENGL)
        pygame.display.set_caption("模型预览 - 按 ESC 退出")

        try:
            if LIVE2D_V2_AVAILABLE:
                live2d_v2.glewInit()
            if LIVE2D_V3_AVAILABLE:
                # v3 使用 glInit，不是 glewInit
                if hasattr(live2d_v3, 'glInit'):
                    live2d_v3.glInit()
                else:
                    live2d_v3.glewInit()
        except Exception as e:
            print(f"初始化 GL 失败: {e}")
            if LIVE2D_V2_AVAILABLE:
                live2d_v2.dispose()
            if LIVE2D_V3_AVAILABLE:
                live2d_v3.dispose()
            pygame.quit()
            return
        
        # 加载模型
        if not self._load_model():
            print("错误: 没有成功加载模型")
            if LIVE2D_V2_AVAILABLE:
                live2d_v2.dispose()
            if LIVE2D_V3_AVAILABLE:
                live2d_v3.dispose()
            pygame.quit()
            return
        
        # 调整模型大小
        self.model.Resize(*display)
        # Resize 可能会重置部件状态，重新应用透明度
        self._apply_opacities("Resize 后")
        
        # 主循环
        print("预览窗口已启动，按 ESC 或关闭窗口退出")

        while self.running:
            # 处理事件
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                elif event.type == pygame.MOUSEMOTION:
                    mouse_x, mouse_y = pygame.mouse.get_pos()
                    self.model.Drag(mouse_x, mouse_y)

            # 清空缓冲区并渲染
            if self.model:
                if self.is_v3 and LIVE2D_V3_AVAILABLE:
                    live2d_v3.clearBuffer()
                elif not self.is_v3 and LIVE2D_V2_AVAILABLE:
                    live2d_v2.clearBuffer()
                self.model.Update()
                self.model.Draw()

            # 刷新显示
            pygame.display.flip()

            # 使用 wait 而非 clock.tick，让 live2d 内部时钟自然推进
            # 10ms ≈ 100 FPS 上限，live2d 内部会按实际时间插值动画
            pygame.time.wait(10)
        
        # 设置运行标志为 False
        self.running = False
        
        # 清理资源
        print("正在清理资源...")
        if self.model:
            try:
                self.model = None
            except:
                pass
        
        # 删除临时文件
        if self.temp_file and os.path.exists(self.temp_file):
            try:
                os.remove(self.temp_file)
            except Exception as e:
                print(f"删除临时文件失败 {self.temp_file}: {e}")
        
        if LIVE2D_V2_AVAILABLE:
            live2d_v2.dispose()
        if LIVE2D_V3_AVAILABLE:
            live2d_v3.dispose()
        pygame.quit()
        
        print("预览窗口已关闭")

