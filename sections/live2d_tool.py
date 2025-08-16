import os
import json
from collections import defaultdict


def safe_relpath(path, start):
    """跨盘符 fallback：同盘符正常相对路径，否则使用文件名"""
    try:
        return os.path.relpath(path, start).replace("\\", "/")
    except ValueError:
        return os.path.basename(path)

def _compact_motion_groups(motions_dict: dict) -> dict:
    """删除 value 为空列表的动作分组"""
    return {k: v for k, v in motions_dict.items() if isinstance(v, list) and len(v) > 0}

def sanitize_path(path):
    """去除路径两侧的引号，防止误识别"""
    return path.strip().strip('"')

def remove_duplicates_and_check_files(model_json_path,
                                      skip_check: bool = False,
                                      auto_remove_missing: bool = True):
    with open(model_json_path, "r", encoding="utf-8") as f:
        model = json.load(f)

    base_dir = os.path.dirname(model_json_path)

    new_motions = defaultdict(list)
    seen_motion_files = set()
    missing_motion_entries = []

    for motion_name, motion_list in (model.get("motions") or {}).items():
        reversed_list = list(reversed(motion_list))
        clean_list = []
        for motion in reversed_list:
            file_path = motion.get("file", "")
            if not file_path:
                # 没有 file 字段的异常数据直接丢弃
                continue
            abs_path = os.path.normpath(os.path.join(base_dir, file_path))
            if file_path in seen_motion_files:
                continue
            if (not skip_check) and (not os.path.isfile(abs_path)):
                missing_motion_entries.append((motion_name, motion))
            else:
                seen_motion_files.add(file_path)
                clean_list.insert(0, motion)
        new_motions[motion_name] = clean_list

    seen_expression_files = set()
    new_expressions = []
    missing_expressions = []

    reversed_exps = list(reversed(model.get("expressions") or []))
    for expression in reversed_exps:
        file_path = expression.get("file", "")
        if not file_path:
            continue
        abs_path = os.path.normpath(os.path.join(base_dir, file_path))
        if file_path in seen_expression_files:
            continue
        if (not skip_check) and (not os.path.isfile(abs_path)):
            missing_expressions.append(expression)
        else:
            seen_expression_files.add(file_path)
            new_expressions.insert(0, expression)

    # ✅ 无交互：按参数决定是否删除缺失项
    if skip_check:
        for motion_name, motion in missing_motion_entries:
            new_motions[motion_name].append(motion)
        model["motions"] = _compact_motion_groups(new_motions)
        model["expressions"] = new_expressions + missing_expressions


    # 2) auto_remove_missing=True 的分支（删除缺失项，并删除空分组）

    elif auto_remove_missing:

        model["motions"] = _compact_motion_groups(new_motions)  # ← 这里

        model["expressions"] = new_expressions


    # 3) auto_remove_missing=False 的分支（保留缺失项，但仍然删除空分组）

    else:

        for motion_name, motion in missing_motion_entries:
            new_motions[motion_name].append(motion)

        model["motions"] = _compact_motion_groups(new_motions)  # ← 这里

        model["expressions"] = new_expressions + missing_expressions

    with open(model_json_path, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, indent=2)


def scan_live2d_directory(directory):
    """遍历 Live2D 资源目录并生成 model.json"""
    model_json = {
        "version": "Sample 1.0.0",
        "layout": {"center_x": 0, "center_y": 0, "width": 2},
        "hit_areas_custom": {
            "head_x": [-0.25, 1], "head_y": [0.25, 0.2],
            "body_x": [-0.3, 0.2], "body_y": [0.3, -1.9]
        },
        "model": "",
        "textures": [],
        "motions": {},
        "expressions": []
    }

    physics_found = False

    for root, _, files in os.walk(directory):
        for file in files:
            relative_path = os.path.relpath(os.path.join(root, file), directory).replace("\\", "/")

            if file.endswith(".moc"):
                model_json["model"] = relative_path
            elif file.endswith(".physics.json"):
                model_json["physics"] = relative_path
                physics_found = True
            elif file.endswith(".png"):
                model_json["textures"].append(relative_path)
            elif file.endswith(".mtn"):
                motion_name = os.path.splitext(file)[0]
                model_json["motions"].setdefault(motion_name, []).append({"file": relative_path})
            elif file.endswith(".exp.json"):
                model_json["expressions"].append({"name": os.path.splitext(file)[0], "file": relative_path})

    # 如果没有找到 physics，则确保它不出现在最终 JSON 中
    if not physics_found and "physics" in model_json:
        del model_json["physics"]

    return model_json
def _normalize_rel(p: str) -> str:
    # 去引号、去前导 ./ 、统一斜杠
    return p.strip().strip('"').strip("'").lstrip("./").replace("\\", "/")

def _find_game_root(start_dir: str) -> str:
    """从 jsonl 文件所在目录向上找名为 game 的目录；找不到就返回 start_dir"""
    cur = start_dir
    while True:
        if os.path.basename(cur) == "game":
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            # 到顶了
            return start_dir
        cur = parent

def _resolve_model_path(jsonl_dir: str, raw_path: str) -> str or None:
    """
    解析 JSONL 的 path，尽量找到真实的 model.json 绝对路径。
    尝试顺序：
      1) 若 raw_path 是绝对路径且存在 -> 直接返回
      2) 规范化 raw_path；若以 'game/' 开头 -> 去掉该前缀
      3) 以 game_root 作为基底，尝试:
         a) game_root / rel
         b) game_root / 'figure' / rel
      4) 若仍不存在：在 game_root 下全局扫描，按“尾部匹配”寻找末尾是 rel 的路径
    命中返回绝对路径；否则返回 None
    """
    raw_path = raw_path.strip()
    if not raw_path:
        return None

    # 绝对路径直接验证
    if os.path.isabs(raw_path) and os.path.isfile(raw_path):
        return os.path.normpath(raw_path)

    rel = _normalize_rel(raw_path)
    game_root = _find_game_root(jsonl_dir)

    # 兼容 'game/...' 前缀
    if rel.startswith("game/"):
        rel = rel[len("game/"):]

    # 候选 1：<game_root>/<rel>
    cand1 = os.path.normpath(os.path.join(game_root, rel))
    if os.path.isfile(cand1):
        return cand1

    # 候选 2：<game_root>/figure/<rel>
    cand2 = os.path.normpath(os.path.join(game_root, "figure", rel))
    if os.path.isfile(cand2):
        return cand2

    # 候选 3：在 game_root 下扫描尾部匹配
    # 例如 rel = '祥子妈后发/model.json'，找到以该尾部结尾的真实路径
    tail = rel.replace("/", os.sep)
    for dirpath, _, files in os.walk(game_root):
        for fn in files:
            if fn.lower() != "model.json":
                continue
            full = os.path.normpath(os.path.join(dirpath, fn))
            # 尾部匹配：full 以 .../<tail> 结尾
            if full.lower().endswith(tail.lower()):
                return full

    return None


def update_model_json_bulk(model_json_path, new_files_or_dir, prefix=""):
    """批量更新 model.json，添加多个动作或表情（支持添加前缀）"""
    model_json_path = sanitize_path(model_json_path)

    # ✅ 判断 new_files_or_dir 是列表、目录、还是字符串
    if isinstance(new_files_or_dir, list):
        new_files = new_files_or_dir
    elif os.path.isdir(new_files_or_dir):
        new_files_or_dir = sanitize_path(new_files_or_dir)
        new_files = []
        for root, _, files in os.walk(new_files_or_dir):
            for file in files:
                if file.endswith((".mtn", ".exp.json")):
                    new_files.append(os.path.join(root, file))
    else:
        new_files_or_dir = sanitize_path(new_files_or_dir)
        new_files = new_files_or_dir.split(";")

    if not os.path.exists(model_json_path):
        print("错误：model.json 文件不存在！")
        return

    with open(model_json_path, "r", encoding="utf-8") as f:
        model_data = json.load(f)

    base_dir = os.path.dirname(model_json_path)

    # ✅ 确保字段存在
    if "motions" not in model_data:
        model_data["motions"] = {}
    if "expressions" not in model_data:
        model_data["expressions"] = []

    added_count = 0
    for new_file in new_files:
        new_file = sanitize_path(new_file)
        if not os.path.exists(new_file):
            print(f"警告：文件 {new_file} 不存在，跳过。")
            continue

        relative_path = safe_relpath(new_file, base_dir)
        file_name = os.path.basename(new_file)

        if file_name.endswith(".mtn"):
            motion_name = prefix + os.path.splitext(file_name)[0]
            model_data["motions"].setdefault(motion_name, []).append({"file": relative_path})
            print(f"添加动作: {relative_path}（名称: {motion_name}）")
        elif file_name.endswith(".exp.json"):
            exp_name = os.path.splitext(os.path.splitext(file_name)[0])[0]
            exp_name = prefix + exp_name
            model_data["expressions"].append({"name": exp_name, "file": relative_path})
            print(f"添加表情: {relative_path}（名称: {exp_name}）")
        else:
            print(f"跳过不支持的文件: {relative_path}")
            continue

        added_count += 1

    if added_count > 0:
        with open(model_json_path, "w", encoding="utf-8") as f:
            json.dump(model_data, f, indent=4, ensure_ascii=False)
        print(f"✅ 批量更新完成，共添加 {added_count} 个文件，已保存到 {model_json_path}")
    else:
        print("⚠️ 没有可添加的文件，未修改 model.json")


def batch_update_mtn_param_text(directory, param_name, new_value):
    """批量更新指定目录下所有 .mtn 文件中的指定参数值为新值（文本格式）"""
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".mtn"):
                file_path = os.path.join(root, file)
                try:
                    # 读取文件所有行
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    # 修改包含指定参数的行
                    modified = False
                    for i, line in enumerate(lines):
                        if line.strip().startswith(f"{param_name}="):
                            lines[i] = f"{param_name}={new_value}\n"
                            modified = True
                            print(f"已更新 {param_name} 在 {file_path} 为 {new_value}")
                            break

                    if not modified:
                        # 如果没有找到就添加
                        lines.append(f"{param_name}={new_value}\n")
                        print(f"未找到 {param_name}，已在 {file_path} 添加为 {new_value}")

                    # 写回文件
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)

                except Exception as e:
                    print(f"处理 {file_path} 时出错: {e}")

# 一念神魔
def merge_exp_faces_with_mapping(left_exp_path, right_exp_path, exps_json_path, output_path):
    """
    根据 exps.json 的左右脸分类，合并两个 exp.json 表情文件：
    - 左脸参数使用左文件
    - 右脸参数使用右文件
    - 中心参数使用左文件
    - 其他未分类参数统一使用右文件
    """

    # 清理路径
    left_exp_path = sanitize_path(left_exp_path)
    right_exp_path = sanitize_path(right_exp_path)
    exps_json_path = sanitize_path(exps_json_path)
    output_path = sanitize_path(output_path)

    # 加载文件
    with open(left_exp_path, "r", encoding="utf-8") as f:
        left_data = json.load(f)
    with open(right_exp_path, "r", encoding="utf-8") as f:
        right_data = json.load(f)
    with open(exps_json_path, "r", encoding="utf-8") as f:
        face_map = json.load(f)

    # 参数映射表
    left_params = {p["id"]: p for p in left_data.get("params", [])}
    right_params = {p["id"]: p for p in right_data.get("params", [])}

    # 已知分类
    left_ids = set(face_map.get("left_face", []))
    right_ids = set(face_map.get("right_face", []))
    center_ids = set(face_map.get("center_face", []))

    all_ids = set(left_params) | set(right_params)
    merged_params = []

    for pid in all_ids:
        if pid in left_ids:
            if pid in left_params:
                merged_params.append(left_params[pid])
        elif pid in right_ids:
            if pid in right_params:
                merged_params.append(right_params[pid])
        elif pid in center_ids:
            if pid in left_params:
                merged_params.append(left_params[pid])
            elif pid in right_params:
                merged_params.append(right_params[pid])
        else:
            # 未分类 → 使用右脸的值
            if pid in right_params:
                merged_params.append(right_params[pid])

    # 构建新表情
    merged_data = {
        "fade_in": left_data.get("fade_in", 500),
        "fade_out": left_data.get("fade_out", 500),
        "params": merged_params
    }

    # 保存文件
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=2)

    print(f"✅ 合并完成：{output_path}")


def batch_remove_mtn_param_text(directory, param_name="PARAM_IMPORT"):
    """批量删除指定目录下所有 .mtn 文件中的指定参数行"""
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".mtn"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    new_lines = [line for line in lines if not line.strip().startswith(f"{param_name}=")]

                    if len(new_lines) < len(lines):
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.writelines(new_lines)
                        print(f"✅ 删除了 {file_path} 中的 {param_name} 参数行")
                    else:
                        print(f"⏭️ 未发现 {param_name} 于 {file_path}，跳过")

                except Exception as e:
                    print(f"处理 {file_path} 时出错: {e}")


def main():
    while True:
        print("\n欢迎使用东山燃灯寺的live2d工具箱")
        print("具体教程请参考本人在B站上的视频")
        print("关注东山燃灯谢谢喵")
        print("1. 生成新的 model.json")
        print("2. 添加单个动作/表情到 model.json")
        print("3. 批量添加动作/表情到 model.json")
        print("4. 去重 model.json 中重复的动作/表情,并删除不存在的动作和表情路径")
        print("5. 批量更改 mtn 文件中的 PARAM_IMPORT 参数")
        print("6. 新功能！断手断脚和一念神魔！")
        print("q. 退出程序")
        choice = input("请选择操作 (1/2/3/4/5/q): ").strip()

        if choice == "1":
            directory = sanitize_path(input("请输入 Live2D 资源目录路径: "))
            save_path = os.path.join(directory, "model.json")
            model_data = scan_live2d_directory(directory)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(model_data, f, indent=4, ensure_ascii=False)
            print(f"model.json 已生成: {save_path}")

        elif choice == "2":
            model_json_path = input("请输入 model.json 文件路径: ")
            new_file_path = input("请输入要添加的动作 (.mtn) 或表情 (.exp.json) 文件路径: ")
            update_model_json_bulk(model_json_path, new_file_path)

        elif choice == "3":
            model_json_path = input("请输入 model.json 文件路径: ")
            new_files_or_dir = input("请输入包含多个动作/表情的目录路径或多个文件（用 ; 分隔）: ")
            prefix = input("请输入添加到动作/表情名称前的前缀（可留空）: ").strip()
            update_model_json_bulk(model_json_path, new_files_or_dir, prefix=prefix)


        elif choice == "4":

            from collections import defaultdict


            path = input("请输入 model.json 的路径（例如 ./model3.json）：").strip().strip('"').strip("'")

            if not os.path.isfile(path):

                print("❌ 文件不存在，请检查路径是否正确。")

            else:

                remove_duplicates_and_check_files(path)



        elif choice == "5":
            directory = sanitize_path(input("请输入包含 .mtn 文件的目录路径: "))
            if not os.path.isdir(directory):
                print("错误：指定的路径不是一个目录或不存在。")
            else:
                new_value_str = input("请输入新的 PARAM_IMPORT 值（整数）: ")
                try:
                    new_value = int(new_value_str)
                    batch_update_mtn_param_text(directory, "PARAM_IMPORT", new_value)
                except ValueError:
                    print("错误：请输入一个有效的整数值。")
        elif choice == "6":
            print("🎭 一念神魔功能启动！")
            left_exp = sanitize_path(input("请输入左脸表情文件路径 (.exp.json): ").strip())
            right_exp = sanitize_path(input("请输入右脸表情文件路径 (.exp.json): ").strip())
            exps_json = "exps.json"

            if not all(os.path.isfile(p) for p in [left_exp, right_exp, exps_json]):
                print("❌ 输入的文件路径有误，请检查所有文件是否存在！")
            else:
                save_name = input("你想保存的文件名字是什么？（不要加 .exp.json）: ").strip()
                if not save_name:
                    print("❌ 文件名不能为空！")
                else:
                    # 自动生成输出路径：存放在左脸同目录下
                    left_dir = os.path.dirname(left_exp)
                    output_exp = os.path.join(left_dir, save_name + ".exp.json")
                    merge_exp_faces_with_mapping(left_exp, right_exp, exps_json, output_exp)

        elif choice.lower() == "q":
            print("感谢使用，再见喵~")
            break
        else:
            print("无效输入，请输入 1、2、3、5 或 q。")


if __name__ == "__main__":
    main()
