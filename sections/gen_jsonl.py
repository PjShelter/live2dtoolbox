# sections/gen_jsonl.py
import codecs
import os
import json
from collections import defaultdict
from typing import List

from utils.composite_jsonl import stringify_composite_jsonl


def is_valid_live2d_json(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        required_keys = ["version", "layout", "model"]
        return all(k in data for k in required_keys)
    except Exception:
        return False


def find_live2d_json_file(folder_path, max_depth=2):
    json_files = []
    found_valid_json = [False]

    def _walk(path, current_depth):
        if current_depth > max_depth or found_valid_json[0]:
            return
        try:
            entries = sorted(os.listdir(path))
            for entry in entries:
                full_path = os.path.join(path, entry)
                if os.path.isfile(full_path) and entry.lower().endswith(".json"): # Use lower() for robustness
                    # Ensure path is normalized before validation
                    normalized_full_path = os.path.normpath(full_path)
                    if is_valid_live2d_json(normalized_full_path):
                        json_files.append(normalized_full_path)
                        found_valid_json[0] = True
                        return
            for entry in entries:
                full_path = os.path.join(path, entry)
                if os.path.isdir(full_path):
                    _walk(full_path, current_depth + 1)
                    if found_valid_json[0]:
                        return
        except Exception as e:
            print(f"❌ 访问失败: {path}, 错误: {e}")

    _walk(folder_path, 0)
    return json_files

def collect_jsons_to_jsonl(root_dir, output_path, id_prefix, base_folder_name, selected_relative_paths):
    # Rename 'folder_list' to 'selected_relative_paths' for clarity as it contains relative file paths.
    index = 0
    records = []
    motions_by_name = defaultdict(int)
    expressions_by_name = []
    expression_seen = set()

    for relative_path_with_file in selected_relative_paths:
        abs_path = os.path.normpath(os.path.join(root_dir, relative_path_with_file))
        folder_part = os.path.dirname(relative_path_with_file).replace("\\", "/")
        if not folder_part:
            folder_part = "."

        record = {
            "index": index,
            "id": f"{id_prefix}{index}",
            "path": relative_path_with_file.replace("\\", "/"),
            "folder": folder_part
        }
        records.append(record)

        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            motions = data.get("motions", {})
            for motion_name in motions:
                motions_by_name[motion_name] += 1

            expressions = data.get("expressions", [])
            for exp in expressions:
                if isinstance(exp, dict) and "name" in exp:
                    name = exp["name"]
                    if name not in expression_seen:
                        expression_seen.add(name)
                        expressions_by_name.append(name)
                elif isinstance(exp, str) and exp.strip():
                    name = exp.strip()
                    if name not in expression_seen:
                        expression_seen.add(name)
                        expressions_by_name.append(name)
        except Exception as e:
            print(f"❌ JSON解析失败: {abs_path}, 错误: {e}")

        index += 1

    required_count = len(records)
    filtered_motion_names = [
        name for name, count in motions_by_name.items()
        if count == required_count
    ]
    filtered_expression_names = list(expressions_by_name)

    text = stringify_composite_jsonl(
        records,
        {
            "motions": filtered_motion_names,
            "expressions": filtered_expression_names,
        },
    )
    with open(output_path, 'w', encoding='utf-8') as outfile:
        outfile.write(text + '\n')



import os
import json


def conf_to_jsonl_with_summary(conf_path, figure_root_dir):
    output_dir = os.path.join(os.path.dirname(conf_path), "converted_jsonl")
    os.makedirs(output_dir, exist_ok=True)

    with open(conf_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    if len(lines) < 8:
        raise ValueError("conf 文件格式不正确，至少需要 8 行")

    name = lines[0]
    change_lines = lines[1].split("\\n")
    main_path = lines[2]
    transform_lines = lines[3].split("\\n")
    # lines[4] 是 transform 的基础行，跳过
    other_paths = lines[5].split("\\n") if lines[5] else []
    offsets = list(map(float, lines[6].split(","))) if lines[6] else []
    import_value = int(lines[7]) if lines[7].isdigit() else None

    all_paths = [main_path] + other_paths
    jsonl_lines = []

    for idx, full_path in enumerate(all_paths):
        id_str = f"myid{idx}"
        filename = os.path.basename(full_path)
        entry = {
            "index": idx,
            "id": id_str,
            "path": filename,
            "folder": "."
        }

        # 动态偏移，只在非主模型上添加 y 值
        if idx > 0 and (2 * (idx - 1) + 1) < len(offsets):
            entry["y"] = float(offsets[2 * (idx - 1) + 1])

        jsonl_lines.append(entry)

    # 扫描 motion / expression
    motions_set = set()
    expressions_set = set()
    for path in all_paths:
        model_dir = os.path.join(figure_root_dir, os.path.dirname(path))
        model_json_path = os.path.join(model_dir, "model.json")
        if os.path.exists(model_json_path):
            try:
                with open(model_json_path, "r", encoding="utf-8") as mf:
                    model_data = json.load(mf)
                    motions = model_data.get("motions", {})
                    expressions = model_data.get("expressions", {})

                    for key in motions.keys():
                        motions_set.add(key)
                    for key in expressions.keys():
                        expressions_set.add(key)
            except Exception:
                pass

    summary = {
        "motions": sorted(motions_set),
        "expressions": sorted(expressions_set),
    }
    if import_value is not None:
        summary["import"] = import_value

    jsonl_output_path = os.path.join(output_dir, f"{name}.jsonl")
    with open(jsonl_output_path, "w", encoding="utf-8") as f:
        f.write(stringify_composite_jsonl(jsonl_lines, summary) + "\n")

    return jsonl_output_path


def jsonl_to_wmdl(jsonl_path):
    """
    将 JSONL 转换为 WMDL 格式
    """
    with open(jsonl_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    if not lines:
        raise ValueError("JSONL 文件为空")

    # 解析普通行和 summary 行
    data_entries = []
    summary = {}
    for line in lines:
        obj = json.loads(line)
        if "motions" in obj or "expressions" in obj:
            summary = obj
        else:
            data_entries.append(obj)

    if not data_entries:
        raise ValueError("JSONL 文件中没有有效的模型数据")

    main_model = data_entries[0]
    name = os.path.splitext(os.path.basename(jsonl_path))[0]

    # 构建 wmdl 结构
    wmdl = {
        "name": name,
        "modelRelativePath": main_model.get("path", ""),
        "figureTemplate": f"changeFigure:%conf_path% -id={name}_0 -zIndex=0 %me_0%;",
        "transformTemplate": f"setTransform:%me_0% -target={name}_0 -duration=750 -writeDefault;",
        "subModels": [],
        "x": main_model.get("x", 0),
        "y": main_model.get("y", 0),
        "scale": main_model.get("scale", main_model.get("xscale", 1)),
        "rotation": main_model.get("rotation", 0),
        "reverseX": main_model.get("reverseX", False),
        "live2dBounds": [0, 0, 0, 0]
    }

    # 添加子模型
    for entry in data_entries[1:]:
        sub_model = {
            "modelRelativePath": entry.get("path", ""),
            "offsetX": entry.get("x", 0) - wmdl["x"],
            "offsetY": entry.get("y", 0) - wmdl["y"]
        }
        wmdl["subModels"].append(sub_model)

    output_path = os.path.join(os.path.dirname(jsonl_path), f"{name}.wmdl")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(wmdl, f, ensure_ascii=False, indent="\t")

    return output_path


def wmdl_to_jsonl(wmdl_path, figure_root_dir=None):
    """
    将 WMDL 转换为 JSONL 格式
    """
    with open(wmdl_path, "r", encoding="utf-8") as f:
        wmdl = json.load(f)

    name = wmdl.get("name", "model")
    jsonl_lines = []

    # 主模型
    main_entry = {
        "index": 0,
        "id": "dao0",
        "path": wmdl.get("modelRelativePath", ""),
        "folder": os.path.dirname(wmdl.get("modelRelativePath", "")).replace("\\", "/"),
        "x": wmdl.get("x", 0),
        "y": wmdl.get("y", 0),
        "scale": wmdl.get("scale", 1)
    }
    jsonl_lines.append(main_entry)

    # 子模型
    for idx, sub in enumerate(wmdl.get("subModels", []), 1):
        sub_entry = {
            "index": idx,
            "id": f"dao{idx}",
            "path": sub.get("modelRelativePath", ""),
            "folder": os.path.dirname(sub.get("modelRelativePath", "")).replace("\\", "/"),
            "x": wmdl.get("x", 0) + sub.get("offsetX", 0),
            "y": wmdl.get("y", 0) + sub.get("offsetY", 0)
        }
        jsonl_lines.append(sub_entry)

    # 扫描动画和表情 (如果有 figure_root_dir)
    motions_set = set()
    expressions_set = set()
    if figure_root_dir:
        all_paths = [wmdl.get("modelRelativePath", "")] + [sub.get("modelRelativePath", "") for sub in wmdl.get("subModels", [])]
        for rel_path in all_paths:
            abs_path = os.path.join(figure_root_dir, rel_path)
            if os.path.exists(abs_path):
                try:
                    with open(abs_path, "r", encoding="utf-8") as mf:
                        model_data = json.load(mf)
                        motions = model_data.get("motions", {})
                        expressions = model_data.get("expressions", [])
                        for k in motions.keys():
                            motions_set.add(k)
                        for exp in expressions:
                            if isinstance(exp, dict) and "name" in exp:
                                expressions_set.add(exp["name"])
                            elif isinstance(exp, str):
                                expressions_set.add(exp)
                except Exception:
                    pass

    summary = {
        "motions": sorted(list(motions_set)),
        "expressions": sorted(list(expressions_set))
    }

    output_path = os.path.join(os.path.dirname(wmdl_path), f"{name}.jsonl")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(stringify_composite_jsonl(jsonl_lines, summary) + "\n")

    return output_path
