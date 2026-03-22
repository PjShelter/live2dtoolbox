"""
JSONL 预览窗口 - 使用 pygame + live2d 预览 JSONL 文件中的所有图层
"""
import json
import os
import tempfile

import pygame
from PIL import Image, ImageSequence

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

try:
    import imageio.v2 as imageio

    IMAGEIO_AVAILABLE = True
except ImportError:
    IMAGEIO_AVAILABLE = False
    imageio = None

try:
    from OpenGL.GL import (
        GL_BLEND,
        GL_CLAMP_TO_EDGE,
        GL_COLOR_BUFFER_BIT,
        GL_DEPTH_BUFFER_BIT,
        GL_DEPTH_TEST,
        GL_LINEAR,
        GL_MODELVIEW,
        GL_ONE_MINUS_SRC_ALPHA,
        GL_PROJECTION,
        GL_QUADS,
        GL_RGBA,
        GL_SRC_ALPHA,
        GL_TEXTURE_2D,
        GL_TEXTURE_MAG_FILTER,
        GL_TEXTURE_MIN_FILTER,
        GL_TEXTURE_WRAP_S,
        GL_TEXTURE_WRAP_T,
        GL_UNSIGNED_BYTE,
        glBegin,
        glBindTexture,
        glBlendFunc,
        glClear,
        glClearColor,
        glColor4f,
        glDeleteTextures,
        glDisable,
        glEnable,
        glEnd,
        glGenTextures,
        glLoadIdentity,
        glMatrixMode,
        glOrtho,
        glTexCoord2f,
        glTexImage2D,
        glTexParameteri,
        glVertex2f,
        glViewport,
    )

    OPENGL_AVAILABLE = True
except ImportError:
    OPENGL_AVAILABLE = False

LIVE2D_AVAILABLE = LIVE2D_V2_AVAILABLE or LIVE2D_V3_AVAILABLE
MEDIA_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".bmp"}
MEDIA_VIDEO_EXTS = {".webm", ".mp4", ".ogv", ".mov", ".mkv"}

from sections.py_live2d_editor import _load_json_without_motions_expressions
from utils.composite_jsonl import parse_composite_jsonl


class JsonlPreviewWindow:
    """JSONL 模型预览窗口"""

    def __init__(self, jsonl_path: str, data: list):
        self.running = True
        self.jsonl_path = jsonl_path
        self.data = data
        self.jsonl_base_dir = os.path.dirname(os.path.abspath(jsonl_path))

        self.param_import = None
        self._parse_import_from_jsonl()

        self.layers = []
        self.models_v2 = []
        self.models_v3 = []
        self.temp_files = []

        self.base_width = 2560.0
        self.base_height = 1440.0
        preview_scale = 0.4
        self.canvas_width = int(self.base_width * preview_scale)
        self.canvas_height = int(self.base_height * preview_scale)
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.base_x = 0.0
        self.base_y = 0.0

    def _parse_import_from_jsonl(self):
        try:
            with open(self.jsonl_path, "r", encoding="utf-8") as f:
                manifest = parse_composite_jsonl(f.read(), source=self.jsonl_path)
            import_value = manifest.get("summary", {}).get("import")
            if import_value is not None:
                self.param_import = int(import_value)
                print(f"检测到汇总 import = {self.param_import}")
        except Exception as e:
            print(f"解析 import 参数失败: {e}")

    def _resolve_path(self, path: str) -> str:
        normalized = path.replace("\\", "/").lstrip("./")

        if os.path.isabs(normalized) or normalized.startswith(("http://", "https://")):
            return normalized

        if normalized.startswith("game/"):
            rel_path = normalized[5:]
            current_dir = self.jsonl_base_dir
            while current_dir and current_dir != os.path.dirname(current_dir):
                game_dir = os.path.join(current_dir, "game")
                if os.path.isdir(game_dir):
                    full_path = os.path.join(game_dir, rel_path)
                    if os.path.isfile(full_path):
                        return os.path.normpath(full_path)
                current_dir = os.path.dirname(current_dir)
            return normalized

        return os.path.normpath(os.path.join(self.jsonl_base_dir, normalized))

    def _infer_part_type(self, obj, full_path: str) -> str:
        part_type = str(obj.get("type", "")).strip().lower()
        if part_type in {"live2d", "image", "gif", "video"}:
            return part_type

        ext = os.path.splitext(full_path)[1].lower()
        if ext == ".gif":
            return "gif"
        if ext in MEDIA_VIDEO_EXTS:
            return "video"
        if ext in MEDIA_IMAGE_EXTS:
            return "image"
        return "live2d"

    def _part_config(self, obj):
        return {
            "x": float(obj.get("x", 0.0)),
            "y": float(obj.get("y", 0.0)),
            "xscale": float(obj.get("xscale", 1.0)),
            "yscale": float(obj.get("yscale", 1.0)),
            "loop": bool(obj.get("loop", True)),
            "autoplay": bool(obj.get("autoplay", True)),
            "muted": bool(obj.get("muted", True)),
            "playsinline": bool(obj.get("playsinline", True)),
        }

    def _has_live2d_layers(self):
        for obj in self.data:
            model_path = obj.get("path", "")
            if not model_path:
                continue
            full_path = self._resolve_path(model_path)
            if self._infer_part_type(obj, full_path) == "live2d":
                return True
        return False

    def _has_media_layers(self):
        for obj in self.data:
            model_path = obj.get("path", "")
            if not model_path:
                continue
            full_path = self._resolve_path(model_path)
            if self._infer_part_type(obj, full_path) != "live2d":
                return True
        return False

    def _upload_pil_texture(self, image: Image.Image, texture_id=None):
        if not OPENGL_AVAILABLE:
            raise RuntimeError("OpenGL 不可用，无法上传媒体纹理。")

        rgba = image.convert("RGBA").transpose(Image.FLIP_TOP_BOTTOM)
        width, height = rgba.size
        raw = rgba.tobytes()

        if texture_id is None:
            texture_id = glGenTextures(1)

        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(
            GL_TEXTURE_2D,
            0,
            GL_RGBA,
            width,
            height,
            0,
            GL_RGBA,
            GL_UNSIGNED_BYTE,
            raw,
        )
        glBindTexture(GL_TEXTURE_2D, 0)
        return texture_id, width, height

    def _setup_2d_render_state(self):
        glViewport(0, 0, self.canvas_width, self.canvas_height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, self.canvas_width, self.canvas_height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_TEXTURE_2D)

    def _draw_texture(self, texture_id, width, height, x, y, xscale, yscale):
        if not OPENGL_AVAILABLE:
            return

        target_width = width * xscale * self.scale_x
        target_height = height * yscale * self.scale_y
        center_x = self.base_x + x * self.scale_x
        center_y = self.base_y + y * self.scale_y
        left = center_x - target_width / 2.0
        top = center_y - target_height / 2.0
        right = left + target_width
        bottom = top + target_height

        self._setup_2d_render_state()
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glColor4f(1.0, 1.0, 1.0, 1.0)
        glBegin(GL_QUADS)
        glTexCoord2f(0.0, 0.0)
        glVertex2f(left, top)
        glTexCoord2f(1.0, 0.0)
        glVertex2f(right, top)
        glTexCoord2f(1.0, 1.0)
        glVertex2f(right, bottom)
        glTexCoord2f(0.0, 1.0)
        glVertex2f(left, bottom)
        glEnd()
        glBindTexture(GL_TEXTURE_2D, 0)

    def _create_live2d_layer(self, obj, full_path):
        is_v3 = full_path.endswith(".model3.json")
        temp_path = _load_json_without_motions_expressions(full_path)
        self.temp_files.append(temp_path)

        if is_v3:
            if not LIVE2D_V3_AVAILABLE:
                print(f"警告: 模型 {full_path} 是 v3 格式，但 live2d.v3 不可用，跳过")
                return None
            model = live2d_v3.LAppModel()
        else:
            if not LIVE2D_V2_AVAILABLE:
                print(f"警告: live2d.v2 不可用，无法加载模型 {full_path}")
                return None
            model = live2d_v2.LAppModel()

        model.LoadModelJson(temp_path)
        config = self._part_config(obj)

        if self.param_import is not None:
            try:
                if hasattr(model, "SetParameterValue"):
                    model.SetParameterValue("PARAM_IMPORT", float(self.param_import), 1.0)
                    print(f"✅ 设置 PARAM_IMPORT={self.param_import} 给模型: {obj.get('path', full_path)}")
                else:
                    param_count = model.GetParameterCount()
                    for i in range(param_count):
                        param = model.GetParameter(i)
                        param_id = getattr(param, "id", None) or str(getattr(param, "id", ""))
                        if param_id == "PARAM_IMPORT" and hasattr(model, "SetParameter"):
                            model.SetParameter(i, float(self.param_import))
                            break
            except Exception as e:
                print(f"❌ 设置 PARAM_IMPORT 失败: {e}")

        try:
            self._initialize_opacity_parameters(model, full_path)
        except Exception as e:
            print(f"❌ 设置透明度参数失败: {e}")

        if is_v3:
            self.models_v3.append(model)
        else:
            self.models_v2.append(model)

        return {
            "kind": "live2d",
            "model": model,
            "is_v3": is_v3,
            "path": full_path,
            **config,
        }

    def _create_image_layer(self, obj, full_path):
        image = Image.open(full_path)
        texture_id, width, height = self._upload_pil_texture(image)
        config = self._part_config(obj)
        return {
            "kind": "image",
            "path": full_path,
            "texture_id": texture_id,
            "width": width,
            "height": height,
            **config,
        }

    def _create_gif_layer(self, obj, full_path):
        gif = Image.open(full_path)
        frames = []
        for frame in ImageSequence.Iterator(gif):
            texture_id, width, height = self._upload_pil_texture(frame)
            duration_ms = frame.info.get("duration", gif.info.get("duration", 100)) or 100
            frames.append({
                "texture_id": texture_id,
                "width": width,
                "height": height,
                "duration": max(float(duration_ms) / 1000.0, 0.02),
            })

        if not frames:
            raise RuntimeError(f"GIF 中没有可用帧: {full_path}")

        config = self._part_config(obj)
        now = pygame.time.get_ticks() / 1000.0
        return {
            "kind": "gif",
            "path": full_path,
            "frames": frames,
            "frame_index": 0,
            "next_frame_at": now + frames[0]["duration"],
            **config,
        }

    def _open_video_reader(self, full_path):
        if not IMAGEIO_AVAILABLE:
            raise RuntimeError("缺少 imageio / imageio-ffmpeg，无法读取 webm/mp4 视频。")
        return imageio.get_reader(full_path, format="ffmpeg")

    def _create_video_layer(self, obj, full_path):
        reader = self._open_video_reader(full_path)
        meta = reader.get_meta_data() or {}
        fps = float(meta.get("fps") or 24.0)
        first_frame = reader.get_next_data()
        first_image = Image.fromarray(first_frame).convert("RGBA")
        texture_id, width, height = self._upload_pil_texture(first_image)
        config = self._part_config(obj)
        now = pygame.time.get_ticks() / 1000.0
        return {
            "kind": "video",
            "path": full_path,
            "reader": reader,
            "texture_id": texture_id,
            "width": width,
            "height": height,
            "frame_duration": 1.0 / max(fps, 1.0),
            "next_frame_at": now + (1.0 / max(fps, 1.0)),
            **config,
        }

    def _load_layers(self):
        loaded_count = 0

        for idx, obj in enumerate(self.data):
            model_path = obj.get("path", "")
            if not model_path:
                print(f"警告: 第 {idx + 1} 行缺少 path 字段")
                continue

            full_path = self._resolve_path(model_path)
            part_type = self._infer_part_type(obj, full_path)

            try:
                layer = None
                if part_type == "live2d":
                    layer = self._create_live2d_layer(obj, full_path)
                elif part_type == "image":
                    layer = self._create_image_layer(obj, full_path)
                elif part_type == "gif":
                    layer = self._create_gif_layer(obj, full_path)
                elif part_type == "video":
                    layer = self._create_video_layer(obj, full_path)

                if layer:
                    self.layers.append(layer)
                    loaded_count += 1
                    print(f"✅ 已加载图层 {idx + 1}/{len(self.data)}: {model_path} [{part_type}]")
            except Exception as e:
                print(f"❌ 加载图层失败 {model_path}: {e}")
                import traceback
                traceback.print_exc()

        return loaded_count > 0

    def _initialize_opacity_parameters(self, model, model_path):
        try:
            with open(model_path, "r", encoding="utf-8") as f:
                original_data = json.load(f)

            if "init_opacities" not in original_data:
                return

            init_opacities = original_data["init_opacities"]
            part_id_to_index = {pid: idx for idx, pid in enumerate(model.GetPartIds())}

            set_opacity = (
                model.SetPartOpacity if hasattr(model, "SetPartOpacity")
                else model.setPartsOpacity if hasattr(model, "setPartsOpacity")
                else None
            )
            if set_opacity is None:
                return

            for item in init_opacities:
                part_id = item.get("id", "")
                opacity_value = float(item.get("value", 1.0))
                if part_id in part_id_to_index:
                    try:
                        set_opacity(part_id_to_index[part_id], opacity_value)
                    except Exception as e:
                        print(f"❌ 设置部件 {part_id} 透明度失败: {e}")
        except Exception as e:
            print(f"❌ 读取原始 JSON 文件失败: {e}")

    def _apply_live2d_layouts(self):
        display = (self.canvas_width, self.canvas_height)
        for layer in self.layers:
            if layer["kind"] != "live2d":
                continue

            model = layer["model"]
            x = layer["x"]
            y = layer["y"]
            xscale = layer["xscale"]
            yscale = layer["yscale"]

            model.Resize(*display)
            normalized_x = -x / (self.base_width / 2.0) if self.base_width > 0 else 0.0
            normalized_y = -y / (self.base_height / 2.0) if self.base_height > 0 else 0.0
            model.SetOffset(normalized_x, normalized_y)
            model.SetScale(xscale)

            if abs(yscale - xscale) > 0.001:
                print(f"警告: 模型 yscale ({yscale}) 与 xscale ({xscale}) 不同，但 SetScale 可能只支持统一缩放")

    def _update_gif_layer(self, layer, now):
        if not layer["autoplay"] or len(layer["frames"]) <= 1 or now < layer["next_frame_at"]:
            return

        next_index = layer["frame_index"] + 1
        if next_index >= len(layer["frames"]):
            if not layer["loop"]:
                next_index = len(layer["frames"]) - 1
            else:
                next_index = 0

        layer["frame_index"] = next_index
        layer["next_frame_at"] = now + layer["frames"][next_index]["duration"]

    def _update_video_layer(self, layer, now):
        if not layer["autoplay"] or now < layer["next_frame_at"]:
            return

        while now >= layer["next_frame_at"]:
            try:
                frame = layer["reader"].get_next_data()
            except Exception:
                if not layer["loop"]:
                    return
                try:
                    layer["reader"].close()
                except Exception:
                    pass
                layer["reader"] = self._open_video_reader(layer["path"])
                try:
                    frame = layer["reader"].get_next_data()
                except Exception:
                    return

            image = Image.fromarray(frame).convert("RGBA")
            _, width, height = self._upload_pil_texture(image, texture_id=layer["texture_id"])
            layer["width"] = width
            layer["height"] = height
            layer["next_frame_at"] += layer["frame_duration"]

    def _render_media_layer(self, layer):
        if not OPENGL_AVAILABLE:
            return

        if layer["kind"] == "image":
            self._draw_texture(
                layer["texture_id"],
                layer["width"],
                layer["height"],
                layer["x"],
                layer["y"],
                layer["xscale"],
                layer["yscale"],
            )
            return

        if layer["kind"] == "gif":
            frame = layer["frames"][layer["frame_index"]]
            self._draw_texture(
                frame["texture_id"],
                frame["width"],
                frame["height"],
                layer["x"],
                layer["y"],
                layer["xscale"],
                layer["yscale"],
            )
            return

        if layer["kind"] == "video":
            self._draw_texture(
                layer["texture_id"],
                layer["width"],
                layer["height"],
                layer["x"],
                layer["y"],
                layer["xscale"],
                layer["yscale"],
            )

    def run(self):
        has_live2d = self._has_live2d_layers()
        has_media = self._has_media_layers()

        if has_live2d and not LIVE2D_AVAILABLE:
            print("错误: live2d 库不可用，无法预览 Live2D 图层")
            return

        if has_media and not OPENGL_AVAILABLE:
            print("错误: PyOpenGL 不可用，无法预览 image/gif/webm 图层")
            return

        pygame.init()

        if has_live2d:
            try:
                if LIVE2D_V2_AVAILABLE:
                    live2d_v2.init()
                if LIVE2D_V3_AVAILABLE:
                    live2d_v3.init()
            except Exception as e:
                print(f"初始化 live2d 失败: {e}")
                pygame.quit()
                return

        display = (self.canvas_width, self.canvas_height)
        try:
            pygame.display.set_mode(display, pygame.DOUBLEBUF | pygame.OPENGL | pygame.HWSURFACE)
        except Exception:
            pygame.display.set_mode(display, pygame.DOUBLEBUF | pygame.OPENGL)
        pygame.display.set_caption("JSONL 模型预览 - 按 ESC 退出")

        self.scale_x = self.canvas_width / self.base_width
        self.scale_y = self.canvas_height / self.base_height
        self.base_x = self.canvas_width / 2
        self.base_y = self.canvas_height / 2

        if has_live2d:
            try:
                if LIVE2D_V2_AVAILABLE:
                    live2d_v2.glewInit()
                if LIVE2D_V3_AVAILABLE:
                    if hasattr(live2d_v3, "glInit"):
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

        if not self._load_layers():
            print("错误: 没有成功加载任何图层")
            if LIVE2D_V2_AVAILABLE:
                live2d_v2.dispose()
            if LIVE2D_V3_AVAILABLE:
                live2d_v3.dispose()
            pygame.quit()
            return

        self._apply_live2d_layouts()

        print("预览窗口已启动，按 ESC 或关闭窗口退出")
        print(f"窗口尺寸: {self.canvas_width}x{self.canvas_height}")

        frame_count = 0
        last_fps_time = pygame.time.get_ticks()

        while self.running:
            events = pygame.event.get()
            mouse_moved = False
            mouse_x, mouse_y = 0, 0

            for event in events:
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.type == pygame.MOUSEMOTION:
                    mouse_moved = True
                    mouse_x, mouse_y = pygame.mouse.get_pos()

            if mouse_moved:
                for layer in self.layers:
                    if layer["kind"] != "live2d":
                        continue
                    if not layer["is_v3"] and LIVE2D_V2_AVAILABLE:
                        layer["model"].Drag(mouse_x, mouse_y)
                    elif layer["is_v3"] and LIVE2D_V3_AVAILABLE:
                        layer["model"].Drag(mouse_x, mouse_y)

            if OPENGL_AVAILABLE:
                glClearColor(0.0, 0.0, 0.0, 0.0)
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            else:
                if self.models_v3 and LIVE2D_V3_AVAILABLE:
                    live2d_v3.clearBuffer()
                elif self.models_v2 and LIVE2D_V2_AVAILABLE:
                    live2d_v2.clearBuffer()

            now = pygame.time.get_ticks() / 1000.0

            for layer in self.layers:
                if layer["kind"] == "live2d":
                    layer["model"].Update()
                    layer["model"].Draw()
                elif layer["kind"] == "gif":
                    self._update_gif_layer(layer, now)
                    self._render_media_layer(layer)
                elif layer["kind"] == "video":
                    self._update_video_layer(layer, now)
                    self._render_media_layer(layer)
                else:
                    self._render_media_layer(layer)

            pygame.display.flip()
            pygame.time.wait(10)

            frame_count += 1
            if frame_count % 100 == 0:
                current_time = pygame.time.get_ticks()
                elapsed = (current_time - last_fps_time) / 1000.0
                if elapsed > 0:
                    fps = 100 / elapsed
                    print(f"当前 FPS: {fps:.1f}")
                last_fps_time = current_time

        self.running = False
        print("正在清理资源...")

        for layer in self.layers:
            try:
                if layer["kind"] == "image":
                    glDeleteTextures([layer["texture_id"]])
                elif layer["kind"] == "gif":
                    glDeleteTextures([frame["texture_id"] for frame in layer["frames"]])
                elif layer["kind"] == "video":
                    glDeleteTextures([layer["texture_id"]])
                    layer["reader"].close()
            except Exception:
                pass

        self.layers.clear()
        self.models_v2.clear()
        self.models_v3.clear()

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
