import numpy as np
import cv2
import onnxruntime as ort

def debug():
    img_path = "c:/Users/pisci/Desktop/apps/pyqt_gallery/tests/test.png" # Assuming we just read some test image
    
    # We will just generate a dummy image for testing the max density value
    img = np.ones((512, 512, 3), dtype=np.uint8) * 255 # White square
    cv2.circle(img, (256, 256), 100, (0, 0, 255), -1) # Red circle
    
    arr = img.astype(np.float32) / 255.0
    arr = arr.transpose(2, 0, 1)[np.newaxis, ...]
    
    print("Loading models...")
    triplane_sess = ort.InferenceSession("models/generative/base_models/TripoSR/triplane.onnx", providers=['CPUExecutionProvider'])
    nerf_sess = ort.InferenceSession("models/generative/base_models/TripoSR/nerf.onnx", providers=['CPUExecutionProvider'])
    
    print("Running triplane...")
    triplane = triplane_sess.run(None, {"image": arr})[0]
    
    # Sample a small grid to check density max/min
    print("Running nerf sample...")
    coords = np.linspace(-0.87, 0.87, 32, dtype=np.float32)
    xx, yy, zz = np.meshgrid(coords, coords, coords, indexing="ij")
    xyz = np.stack([xx, yy, zz], axis=-1).reshape(-1, 3)
    
    d, _ = nerf_sess.run(None, {"triplane": triplane, "xyz": xyz})
    
    print(f"Density max: {d.max()}, min: {d.min()}, mean: {d.mean()}")
    
if __name__ == "__main__":
    debug()
