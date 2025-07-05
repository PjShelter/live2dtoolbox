import os
import json


def get_sorted_subfolders(path):
    return sorted(
        [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))],
        key=lambda x: x
    )


def collect_jsons_to_jsonl(root_dir, output_path, id_prefix, base_folder_name):
    index = 0
    records = []
    root_parent = os.path.dirname(root_dir)
    index1_json_path = None  # ✅ index == 1 对应的 JSON 文件路径

    with open(output_path, 'w', encoding='utf-8') as outfile:
        for folder_name in get_sorted_subfolders(root_dir):
            folder_path = os.path.join(root_dir, folder_name)
            for file in sorted(os.listdir(folder_path)):
                if file.endswith('.json'):
                    abs_path = os.path.join(folder_path, file)

                    # 回溯到 "game" 目录
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
                        index1_json_path = abs_path  # ✅ 记录 index=1 的 JSON 路径

                    index += 1

    # ✅ 将 index=1 的 json 内容保存为 base_folder_name.json 文件
    if index1_json_path and os.path.exists(index1_json_path):
        with open(index1_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        json_output_path = os.path.splitext(output_path)[0] + ".json"
        with open(json_output_path, 'w', encoding='utf-8') as jsonfile:
            json.dump(data, jsonfile, indent=2, ensure_ascii=False)
