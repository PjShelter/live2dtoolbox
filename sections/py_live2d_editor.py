import os
import json
import tempfile
import pygame
import live2d.v2 as live2d

from utils.common import _norm_id


def _load_json_without_motions_expressions(model_json_path):
    """读取 JSON 文件，移除 motions 和 expressions 字段，返回临时文件路径"""
    with open(model_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 移除 motions 和 expressions 字段
    if "motions" in data:
        del data["motions"]
    if "expressions" in data:
        del data["expressions"]
    
    
    # 2. 保留 groups 数组（可能包含透明度组设置）
    if "groups" in data:
        # 保持 groups 数组完整
        pass
    
    if "init_opacities" in data:
        # 保持 init_opacities 完整
        pass
    
    # 创建临时文件
    temp_dir = os.path.dirname(model_json_path)
    temp_fd, temp_path = tempfile.mkstemp(suffix=".json", dir=temp_dir, text=True)
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return temp_path
    except Exception:
        os.close(temp_fd)
        raise

def get_all_parts(model_path):
    temp_path = None
    try:
        # 创建不包含 motions 和 expressions 的临时 JSON 文件
        temp_path = _load_json_without_motions_expressions(model_path)
        
        pygame.init()
        pygame.display.set_mode((1, 1), pygame.OPENGL | pygame.HIDDEN)
        live2d.init()
        live2d.glewInit()
        model = live2d.LAppModel()
        model.LoadModelJson(temp_path)
        part_ids = model.GetPartIds()
        live2d.dispose()
        pygame.quit()
        return part_ids
    finally:
        # 清理临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

def get_all_param_info_list(model_json_path):
    temp_path = None
    try:
        # 创建不包含 motions 和 expressions 的临时 JSON 文件
        temp_path = _load_json_without_motions_expressions(model_json_path)
        
        pygame.init()
        pygame.display.set_mode((1, 1), pygame.OPENGL | pygame.HIDDEN)
        live2d.init()
        live2d.glewInit()

        model = live2d.LAppModel()
        model.LoadModelJson(temp_path)

        info_list = []
        try:
            count = model.GetParameterCount()
            for i in range(count):
                p = model.GetParameter(i)
                pid = _norm_id(getattr(p, "id", ""))
                pdefault = float(getattr(p, "default", 0.0) or 0.0)
                pmin = float(getattr(p, "min", 0.0) or 0.0)
                pmax = float(getattr(p, "max", 1.0) or 1.0)
                pvalue = float(getattr(p, "value", pdefault) or pdefault)

                info_list.append({
                    "id": pid,
                    "default": pdefault,
                    "min": pmin,
                    "max": pmax,
                    "value": pvalue,
                })
        finally:
            # 先抽取完，再释放上下文
            live2d.dispose()
            pygame.quit()

        return info_list
    finally:
        # 清理临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

def list_model_info(model_json_path):
    temp_path = None
    try:
        # 创建不包含 motions 和 expressions 的临时 JSON 文件
        temp_path = _load_json_without_motions_expressions(model_json_path)
        
        pygame.init()
        pygame.display.set_mode((1, 1), pygame.OPENGL | pygame.HIDDEN)
        live2d.init()
        live2d.glewInit()

        model = live2d.LAppModel()
        model.LoadModelJson(temp_path)

        part_ids = model.GetPartIds()

        param_info_list = []
        for i in range(model.GetParameterCount()):
            param = model.GetParameter(i)
            param_info_list.append(param)  # 是 Parameter 类型，含 default/value/id 等

        live2d.dispose()
        pygame.quit()

        return part_ids, param_info_list
    finally:
        # 清理临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass



if __name__ == "__main__":
    user_input = input("请输入 model.json 的完整路径：\n> ")
    path = os.path.normpath(user_input.strip().strip('"').strip("'"))

    if not os.path.isfile(path):
        print("❌ 路径无效")
    else:
        parts, params = list_model_info(path)

        print("🧩 部件名列表：")
        for i, name in enumerate(parts):
            print(f"  {i+1}. {name}")

        print("\n🎛 参数名列表（含默认值）：")
        for i, param in enumerate(params):
            print(f"  {i+1}. {param.id} | 默认值: {param.default} | 当前值: {param.value}")