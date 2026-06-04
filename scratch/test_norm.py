import numpy as np
import cv2
import onnxruntime as ort
import mcubes
import trimesh

def process(img_path, out_path, normalize=False):
    # Load image
    img = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"Failed to load {img_path}")
        return
        
    # Crop and pad
    if img.shape[2] == 4:
        alpha = img[:, :, 3]
        y_idx, x_idx = np.where(alpha > 10)
        if len(y_idx) > 0:
            y_min, y_max = y_idx.min(), y_idx.max()
            x_min, x_max = x_idx.min(), x_idx.max()
            img = img[y_min:y_max+1, x_min:x_max+1]
            
    h, w = img.shape[:2]
    max_dim = max(h, w)
    scale = (512 * 0.85) / max_dim
    new_w, new_h = int(w * scale), int(h * scale)
    img_resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    
    final_img = np.ones((512, 512, 3), dtype=np.float32) * 255.0
    y_off = (512 - new_h) // 2
    x_off = (512 - new_w) // 2
    
    if img_resized.shape[2] == 4:
        fg_alpha = img_resized[:, :, 3].astype(np.float32) / 255.0
        fg_color = img_resized[:, :, :3].astype(np.float32)
        for c in range(3):
            final_img[y_off:y_off+new_h, x_off:x_off+new_w, c] = (
                fg_color[:, :, c] * fg_alpha + 
                final_img[y_off:y_off+new_h, x_off:x_off+new_w, c] * (1.0 - fg_alpha)
            )
    else:
        final_img[y_off:y_off+new_h, x_off:x_off+new_w] = cv2.cvtColor(img_resized, cv2.COLOR_BGRA2RGB)
        
    arr = final_img / 255.0
    arr = arr.transpose(2, 0, 1)[np.newaxis, ...]  # 1x3x512x512
    
    if normalize:
        # ImageNet normalization
        mean = np.array([0.485, 0.456, 0.406]).reshape(1, 3, 1, 1)
        std = np.array([0.229, 0.224, 0.225]).reshape(1, 3, 1, 1)
        arr = (arr - mean) / std

    print(f"Norm={normalize}, Arr mean: {arr.mean():.4f}")
    
    print("Loading ONNX...")
    triplane_sess = ort.InferenceSession("models/generative/hf_cache/models--onnx-community--TripoSR-ONNX/snapshots/main/triplane.onnx", providers=['CPUExecutionProvider'])
    nerf_sess = ort.InferenceSession("models/generative/hf_cache/models--onnx-community--TripoSR-ONNX/snapshots/main/nerf.onnx", providers=['CPUExecutionProvider'])
    
    print("Running triplane...")
    triplane = triplane_sess.run(None, {"image": arr.astype(np.float32)})[0]
    
    RESOLUTION = 64 # Low res for quick test
    RADIUS = 0.87
    coords = np.linspace(-RADIUS, RADIUS, RESOLUTION, dtype=np.float32)
    xx, yy, zz = np.meshgrid(coords, coords, coords, indexing="ij")
    xyz = np.stack([xx, yy, zz], axis=-1).reshape(-1, 3)
    
    print("Running nerf...")
    densities = np.empty(xyz.shape[0], dtype=np.float32)
    CHUNK = 32768
    for i in range(0, xyz.shape[0], CHUNK):
        chunk = xyz[i : i + CHUNK]
        d, _ = nerf_sess.run(None, {"triplane": triplane, "xyz": chunk})
        densities[i : i + chunk.shape[0]] = d.reshape(-1)
        
    print(f"Max density: {densities.max():.4f}, Min density: {densities.min():.4f}")
    density_grid = densities.reshape(RESOLUTION, RESOLUTION, RESOLUTION)
    
    try:
        vertices, triangles = mcubes.marching_cubes(density_grid, 15.0)
        print(f"Extracted {len(vertices)} vertices, {len(triangles)} faces")
    except Exception as e:
        print(f"Marching cubes failed: {e}")

if __name__ == "__main__":
    # Let's test with the provided user image, or a placeholder
    process("c:/Users/pisci/Desktop/apps/pyqt_gallery/scratch/test.png", "out_unnorm.obj", normalize=False)
    process("c:/Users/pisci/Desktop/apps/pyqt_gallery/scratch/test.png", "out_norm.obj", normalize=True)
