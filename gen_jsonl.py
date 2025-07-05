import os
import json


def get_sorted_subfolders(path):
    return sorted(
        [d for d in os.listdir(path)
         if os.path.isdir(os.path.join(path, d))],
        key=lambda x: x
    )


def collect_jsons_to_jsonl(root_dir, output_path, id_prefix, base_folder_name):
    index = 0
    root_parent = os.path.dirname(root_dir)
    with open(output_path, 'w', encoding='utf-8') as outfile:
        for folder_name in get_sorted_subfolders(root_dir):
            folder_path = os.path.join(root_dir, folder_name)
            for file in sorted(os.listdir(folder_path)):
                if file.endswith('.json'):
                    abs_path = os.path.join(folder_path, file)
                    # 定位到 "game" 目录为相对根目录
                    while os.path.basename(root_parent) != "game" and os.path.dirname(root_parent) != root_parent:
                        root_parent = os.path.dirname(root_parent)

                    relative_path = os.path.relpath(abs_path, root_parent).replace("\\", "/")
                    record = {
                        "index": index,
                        "id": f"{id_prefix}{index}",
                        "path": relative_path,
                        "folder": folder_name
                    }
                    outfile.write(json.dumps(record, ensure_ascii=False) + '\n')
                    index += 1


def main():
    print("🔍 请输入要处理的目录路径（如：.../figure/该涩子样子）：")
    input_dir = input(">>> ").strip().strip('"')

    input_dir = os.path.abspath(input_dir)
    if not os.path.isdir(input_dir):
        print(f"❌ 路径无效或不是目录: {input_dir}")
        return

    base_folder_name = os.path.basename(input_dir.rstrip(os.sep))

    print("🆔 请输入 ID 前缀（如 sakiko）：")
    id_prefix = input(">>> ").strip()

    output_path = os.path.join(input_dir, f"{base_folder_name}.jsonl")

    print(f"\n📁 目录：{input_dir}")
    print(f"📄 输出：{output_path}")
    print(f"🆔 ID 前缀：{id_prefix}\n")

    collect_jsons_to_jsonl(input_dir, output_path, id_prefix, base_folder_name)
    print("\n✅ JSON 路径列表已生成！")


if __name__ == "__main__":
    main()
