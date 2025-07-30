import os
import json
from collections import defaultdict

def is_valid_live2d_json(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        required_keys = ["version", "layout", "model", "motions"]
        return all(k in data for k in required_keys) and isinstance(data["motions"], dict)
    except Exception as e:
        # print(f"is_valid_live2d_json check failed for {file_path}: {e}") # For debugging

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
    expressions_by_name = set()
    index1_json_path = None

    with open(output_path, 'w', encoding='utf-8') as outfile:
        for relative_path_with_file in selected_relative_paths:
            # Construct the absolute path using os.path.join.
            # os.path.normpath will clean up redundant slashes and ensure
            # platform-appropriate separators.
            abs_path = os.path.normpath(os.path.join(root_dir, relative_path_with_file))

            # Extract the actual folder name from the relative path for the "folder" field
            # e.g., "爱音比心/爱音.model.json" -> "爱音比心"
            folder_part = os.path.dirname(relative_path_with_file).replace("\\", "/") # Ensure folder name uses forward slashes in JSONL
            if not folder_part: # If the file is directly in root_dir, folder_part would be empty
                folder_part = "." # Or you can use a placeholder like "root" or ""


            record = {
                "index": index,
                "id": f"{id_prefix}{index}",
                "path": relative_path_with_file, # Keep relative path with forward slashes for JSONL output
                "folder": folder_part
            }
            outfile.write(json.dumps(record, ensure_ascii=False) + '\n')
            records.append(record)

            try:
                # Use the normalized absolute path to open the file
                with open(abs_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                motions = data.get("motions", {})
                for motion_name in motions:
                    motions_by_name[motion_name] += 1

                expressions = data.get("expressions", [])
                for exp in expressions:
                    if isinstance(exp, dict) and "name" in exp:
                        expressions_by_name.add(exp["name"])
            except Exception as e:
                print(f"❌ JSON解析失败: {abs_path}, 错误: {e}") # Print abs_path to debug if it fails again

            if index == 1:
                index1_json_path = abs_path # Store the normalized absolute path

            index += 1

        # motions: 必须所有模型都有的
        required_count = len(records)
        filtered_motion_names = sorted([
            name for name, count in motions_by_name.items()
            if count == required_count
        ])
        filtered_expression_names = sorted(list(expressions_by_name))

        # 添加 motions + expressions 行
        meta_record = {
            "motions": filtered_motion_names,
            "expressions": filtered_expression_names
        }
        outfile.write(json.dumps(meta_record, ensure_ascii=False) + '\n')

    # ✅ 额外生成 index==1 的 JSON 文件
    if index1_json_path and os.path.exists(index1_json_path):
        try:
            with open(index1_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            json_output_path = os.path.splitext(output_path)[0] + ".json"
            with open(json_output_path, 'w', encoding='utf-8') as jsonfile:
                json.dump(data, jsonfile, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ 写入 JSON 文件失败: {e}")