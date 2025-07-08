import os
import json


def get_sorted_subfolders(path):
    return sorted(
        [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))],
        key=lambda x: x
    )

def find_json_files(folder_path, max_depth=2):
    json_files = []
    found_first_json = [False]  # 用于跨作用域标记已找到

    def _walk(path, current_depth):
        if current_depth > max_depth or found_first_json[0]:
            return
        try:
            entries = sorted(os.listdir(path))
            # 1️⃣ 优先处理当前目录的文件（不递归）
            for entry in entries:
                full_path = os.path.join(path, entry)
                if os.path.isfile(full_path) and entry.endswith(".json"):
                    json_files.append(full_path)
                    found_first_json[0] = True
                    return  # ✅ 当前目录找到 JSON 即返回

            # 2️⃣ 当前目录未找到，再递归进入子目录
            for entry in entries:
                full_path = os.path.join(path, entry)
                if os.path.isdir(full_path):
                    _walk(full_path, current_depth + 1)
                    if found_first_json[0]:
                        return
        except Exception as e:
            print(f"❌ 访问失败: {path}, 错误: {e}")

    _walk(folder_path, 0)
    return json_files



def collect_jsons_to_jsonl(root_dir, output_path, id_prefix, base_folder_name, folder_list):
    index = 0
    records = []
    root_parent = os.path.dirname(root_dir)
    index1_json_path = None

    with open(output_path, 'w', encoding='utf-8') as outfile:
        for folder_name in folder_list:
            folder_path = os.path.join(root_dir, folder_name)
            json_files = find_json_files(folder_path, max_depth=2)

            for abs_path in json_files:
                temp_parent = root_parent
                while os.path.basename(temp_parent) != "game" and os.path.dirname(temp_parent) != temp_parent:
                    temp_parent = os.path.dirname(temp_parent)

                relative_path = os.path.relpath(abs_path, temp_parent).replace("\\", "/")
                relative_path = f"game/{relative_path}"

                record = {
                    "index": index,
                    "id": f"{id_prefix}{index}",
                    "path": relative_path,
                    "folder": folder_name
                }
                outfile.write(json.dumps(record, ensure_ascii=False) + '\n')
                records.append(record)

                if index == 1:
                    index1_json_path = abs_path

                index += 1

    if index1_json_path and os.path.exists(index1_json_path):
        with open(index1_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        json_output_path = os.path.splitext(output_path)[0] + ".json"
        with open(json_output_path, 'w', encoding='utf-8') as jsonfile:
            json.dump(data, jsonfile, indent=2, ensure_ascii=False)
