
import numpy as np

from PIL import Image
from PyQt5.QtGui import QImage, QPixmap

def parse_cube_lut(cube_path: str) -> np.ndarray:
    """
    解析 .cube 3D LUT -> ndarray (size, size, size, 3), 值域 [0,1]
    支持注释/空行/LUT_3D_SIZE/TITLE/DOMAIN_MIN/MAX（目前按 0~1 使用）
    """
    size = None
    data = []
    with open(cube_path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            u = line.upper()
            if u.startswith("LUT_3D_SIZE"):
                size = int(line.split()[-1])
                continue
            if u.startswith(("DOMAIN_MIN", "DOMAIN_MAX", "TITLE")):
                continue
            toks = line.split()
            if len(toks) >= 3:
                r, g, b = map(float, toks[:3])
                data.append([r, g, b])

    if size is None:
        # 未提供 size 时，尝试立方根推断
        n = int(round(len(data) ** (1/3)))
        size = n

    expected = size * size * size
    if len(data) != expected:
        raise ValueError(f".cube 数据数量不匹配：期待 {expected}，实际 {len(data)}")

    lut = np.array(data, dtype=np.float32).reshape((size, size, size, 3))
    return np.clip(lut, 0.0, 1.0)


def apply_lut_rgb_uint8(img_rgb_u8: np.ndarray, lut: np.ndarray, trilinear: bool = True) -> np.ndarray:
    """
    对 RGB uint8 图像应用 3D LUT，返回 RGB uint8。
    img_rgb_u8: (H,W,3), dtype=uint8
    lut: (S,S,S,3), 值域[0,1]
    """
    if img_rgb_u8.dtype != np.uint8:
        raise ValueError("输入图像必须为 uint8")
    S = lut.shape[0]

    # 归一化到 LUT 索引空间 [0, S-1]
    img = img_rgb_u8.astype(np.float32) / 255.0
    r_idx = img[..., 0] * (S - 1)
    g_idx = img[..., 1] * (S - 1)
    b_idx = img[..., 2] * (S - 1)

    if not trilinear:
        ri = np.clip(np.rint(r_idx).astype(np.int32), 0, S - 1)
        gi = np.clip(np.rint(g_idx).astype(np.int32), 0, S - 1)
        bi = np.clip(np.rint(b_idx).astype(np.int32), 0, S - 1)
        mapped = lut[ri, gi, bi]  # RGB in [0,1]
    else:
        r0 = np.clip(np.floor(r_idx).astype(np.int32), 0, S - 1)
        g0 = np.clip(np.floor(g_idx).astype(np.int32), 0, S - 1)
        b0 = np.clip(np.floor(b_idx).astype(np.int32), 0, S - 1)
        r1 = np.clip(r0 + 1, 0, S - 1)
        g1 = np.clip(g0 + 1, 0, S - 1)
        b1 = np.clip(b0 + 1, 0, S - 1)

        fr = (r_idx - r0).astype(np.float32)
        fg = (g_idx - g0).astype(np.float32)
        fb = (b_idx - b0).astype(np.float32)

        c000 = lut[r0, g0, b0]
        c001 = lut[r0, g0, b1]
        c010 = lut[r0, g1, b0]
        c011 = lut[r0, g1, b1]
        c100 = lut[r1, g0, b0]
        c101 = lut[r1, g0, b1]
        c110 = lut[r1, g1, b0]
        c111 = lut[r1, g1, b1]

        c00 = c000 * (1 - fb)[..., None] + c001 * fb[..., None]
        c01 = c010 * (1 - fb)[..., None] + c011 * fb[..., None]
        c10 = c100 * (1 - fb)[..., None] + c101 * fb[..., None]
        c11 = c110 * (1 - fb)[..., None] + c111 * fb[..., None]

        c0 = c00 * (1 - fg)[..., None] + c01 * fg[..., None]
        c1 = c10 * (1 - fg)[..., None] + c11 * fg[..., None]

        mapped = c0 * (1 - fr)[..., None] + c1 * fr[..., None]  # RGB in [0,1]

    out = (mapped * 255.0).round().astype(np.uint8)
    return out


def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    rgba = img.convert("RGBA")
    w, h = rgba.size
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(data, w, h, 4 * w, QImage.Format_RGBA8888)
    qimg._buf = data  # 防止 Python 回收内存
    return QPixmap.fromImage(qimg)


def numpy_to_pil_rgb(img_rgb_u8: np.ndarray) -> Image.Image:
    return Image.fromarray(img_rgb_u8, mode="RGB")