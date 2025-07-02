import os
from PIL import Image
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import json
matplotlib.use('TkAgg')


def match_color(source: Image.Image, target: Image.Image) -> Image.Image:
    source_array = np.asarray(source).astype(np.float32)
    target_array = np.asarray(target).astype(np.float32)

    matched = np.zeros_like(source_array)
    for c in range(3):  # R, G, B
        src_mean, src_std = source_array[..., c].mean(), source_array[..., c].std()
        tgt_mean, tgt_std = target_array[..., c].mean(), target_array[..., c].std()
        src_std = max(src_std, 1e-6)
        matched[..., c] = (source_array[..., c] - src_mean) / src_std * tgt_std + tgt_mean
        matched[..., c] = np.clip(matched[..., c], 0, 255)

    return Image.fromarray(matched.astype(np.uint8))


def extract_webgal_full_transform(source: Image.Image, target: Image.Image) -> dict:
    source_np = np.asarray(source).astype(np.float32) / 255.0
    target_np = np.asarray(target).astype(np.float32) / 255.0

    # 亮度
    src_lum = source_np.mean()
    tgt_lum = target_np.mean()
    brightness = tgt_lum / src_lum if src_lum > 1e-6 else 1.0

    # 对比度
    src_contrast = source_np.std()
    tgt_contrast = target_np.std()
    contrast = tgt_contrast / src_contrast if src_contrast > 1e-6 else 1.0

    # 饱和度
    def rgb_to_saturation(rgb):
        maxc = rgb.max(axis=2)
        minc = rgb.min(axis=2)
        sat = (maxc - minc) / (maxc + 1e-6)
        return np.mean(sat)

    saturation = rgb_to_saturation(target_np) / rgb_to_saturation(source_np)

    # 伽马
    def estimate_gamma(img_np):
        img_np = np.clip(img_np, 1e-6, 1.0)
        return np.log(img_np.mean()) / np.log(0.5)

    gamma = estimate_gamma(target_np) / estimate_gamma(source_np)

    # RGB 差值
    source_array = (source_np * 255).astype(np.float32)
    target_array = (target_np * 255).astype(np.float32)

    rgb_adjust = {}
    for c, key in enumerate(["colorRed", "colorGreen", "colorBlue"]):
        src_mean = source_array[..., c].mean()
        tgt_mean = target_array[..., c].mean()
        rgb_adjust[key] = int(255 - (src_mean - tgt_mean))  # 允许超出 255

    return {
        "brightness": float(round(brightness, 2)),
        "contrast": float(round(np.power(contrast, 0.6), 2)),
        "saturation": float(round(np.clip(saturation, 0.0, 2.0), 2)),
        "gamma": float(round(np.clip(np.sqrt(1.0 / gamma), 0.5, 2.0), 2)),
        **{k: int(v) for k, v in rgb_adjust.items()}
    }



def visualize(source, target, matched):
    plt.figure(figsize=(15, 5))

    plt.subplot(1, 3, 1)
    plt.title("Source Image")
    plt.imshow(source)
    plt.axis("off")

    plt.subplot(1, 3, 2)
    plt.title("Reference Image")
    plt.imshow(target)
    plt.axis("off")

    plt.subplot(1, 3, 3)
    plt.title("Matched Result")
    plt.imshow(matched)
    plt.axis("off")

    plt.tight_layout()
    plt.show()
def plot_parameter_comparison(source: Image.Image, target: Image.Image):
    source_np = np.asarray(source).astype(np.float32) / 255.0
    target_np = np.asarray(target).astype(np.float32) / 255.0

    def get_metrics(img_np):
        brightness = img_np.mean()
        contrast = img_np.std()

        def rgb_to_saturation(rgb):
            maxc = rgb.max(axis=2)
            minc = rgb.min(axis=2)
            sat = (maxc - minc) / (maxc + 1e-6)
            return np.mean(sat)

        saturation = rgb_to_saturation(img_np)

        def estimate_gamma(img_np):
            img_np = np.clip(img_np, 1e-6, 1.0)
            return np.log(img_np.mean()) / np.log(0.5)

        gamma = estimate_gamma(img_np)

        rgb_mean = [img_np[..., c].mean() for c in range(3)]
        return [brightness, contrast, saturation, gamma] + rgb_mean

    source_metrics = get_metrics(source_np)
    target_metrics = get_metrics(target_np)

    labels = [
        "Brightness", "Contrast", "Saturation", "Gamma",
        "Red Mean", "Green Mean", "Blue Mean"
    ]

    x = np.arange(len(labels))
    width = 0.35

    plt.figure(figsize=(10, 6))
    plt.bar(x - width / 2, source_metrics, width, label='Source', color='skyblue')
    plt.bar(x + width / 2, target_metrics, width, label='Target', color='salmon')
    plt.xticks(x, labels, rotation=20)
    plt.ylabel("Normalized Value")
    plt.title("Image Metrics Comparison")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.show()


def main():
    print("制作者：东山燃灯寺")
    print("🎯 Please enter the path to the source image:")
    source_path = input("Source image path: ").strip().strip('"').strip("'")
    if not os.path.isfile(source_path):
        print("❌ File not found.")
        return
    source_img = Image.open(source_path).convert("RGB")

    png_dir = "png"
    if not os.path.isdir(png_dir):
        print(f"❌ Directory '{png_dir}' does not exist. Please create it and put reference images inside.")
        return

    candidates = [f for f in os.listdir(png_dir) if f.lower().endswith(".png")]
    if not candidates:
        print(f"❌ No PNG files found in '{png_dir}'.")
        return

    print("\n📂 Select a reference image:")
    for idx, name in enumerate(candidates):
        print(f"{idx+1}. {name}")
    index = int(input(f"Enter number (1 ~ {len(candidates)}): ").strip()) - 1
    if not (0 <= index < len(candidates)):
        print("❌ Invalid selection.")
        return

    target_path = os.path.join(png_dir, candidates[index])
    target_img = Image.open(target_path).convert("RGB").resize(source_img.size)

    matched_img = match_color(source_img, target_img)

    # 自动构造输出路径
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    source_name = os.path.splitext(os.path.basename(source_path))[0]
    target_name = os.path.splitext(os.path.basename(target_path))[0]
    output_path = os.path.join(output_dir, f"matched_{source_name}_{target_name}.png")

    matched_img.save(output_path)
    print(f"\n✅ Color matching done. Saved to: {output_path}")

    # ✅ 输出完整 WebGAL 转换指令
    transform_params = extract_webgal_full_transform(source_img, target_img)
    webgal_code = f'setTransform:{json.dumps(transform_params)} -target=bg-main -duration=0 -next;'
    print("\n🎬 Suggested WebGAL Transform Command:")
    print(webgal_code)

    preview = input("📷 Preview result? (y/n): ").strip().lower()
    if preview.startswith("y"):
        visualize(source_img, target_img, matched_img)
        plot_parameter_comparison(source_img, target_img)


if __name__ == "__main__":
    main()
