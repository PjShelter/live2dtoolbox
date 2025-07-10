import os
import json
from collections import defaultdict


def find_json_files(folder_path, max_depth=2):
    json_files = []
    found_first_json = [False]

    def _walk(path, current_depth):
        if current_depth > max_depth or found_first_json[0]:
            return
        try:
            entries = sorted(os.listdir(path))
            for entry in entries:
                full_path = os.path.join(path, entry)
                if os.path.isfile(full_path) and entry.endswith(".json"):
                    json_files.append(full_path)
                    found_first_json[0] = True
                    return
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
    motions_by_name = defaultdict(int)
    expressions_by_name = set()
    index1_json_path = None

    with open(output_path, 'w', encoding='utf-8') as outfile:
        for folder_name in folder_list:
            folder_path = os.path.join(root_dir, folder_name)
            json_files = find_json_files(folder_path, max_depth=2)

            for abs_path in json_files:
                relative_path = os.path.relpath(abs_path, root_dir).replace("\\", "/")
                record = {
                    "index": index,
                    "id": f"{id_prefix}{index}",
                    "path": relative_path,
                    "folder": folder_name
                }
                outfile.write(json.dumps(record, ensure_ascii=False) + '\n')
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
                            expressions_by_name.add(exp["name"])
                except Exception as e:
                    print(f"❌ JSON解析失败: {abs_path}, 错误: {e}")

                if index == 1:
                    index1_json_path = abs_path

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
