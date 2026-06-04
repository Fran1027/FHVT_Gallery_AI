import os
import onnxruntime as ort
import numpy as np
import cv2
import time
from huggingface_hub import hf_hub_download

os.environ["HF_HOME"] = "c:/Users/pisci/Desktop/apps/pyqt_gallery/models/generative/hf_cache"
repo_id = "PulpCut/mobilesam-onnx"

try:
    enc_path = hf_hub_download(repo_id=repo_id, filename="mobilesam.encoder.onnx")
    dec_path = hf_hub_download(repo_id=repo_id, filename="mobilesam.decoder.onnx")

    print(f"Encoder: {enc_path}")
    
    enc_sess = ort.InferenceSession(enc_path, providers=['CPUExecutionProvider'])
    dec_sess = ort.InferenceSession(dec_path, providers=['CPUExecutionProvider'])

    h, w = 1024, 1024
    image = np.random.randint(0, 255, (h, w, 3)).astype(np.float32)

    t0 = time.time()
    enc_output = enc_sess.run(None, {"input_image": image})
    emb = enc_output[0]
    print(f"Encoder Time: {time.time() - t0:.3f}s, Output shape: {emb.shape}")

    t0 = time.time()
    point_coords = np.array([[[512.0, 512.0]]], dtype=np.float32)
    point_labels = np.array([[1.0]], dtype=np.float32)
    mask_input = np.zeros((1, 1, 256, 256), dtype=np.float32)
    has_mask_input = np.zeros((1,), dtype=np.float32)
    orig_im_size = np.array([float(h), float(w)], dtype=np.float32)

    dec_output = dec_sess.run(None, {
        "image_embeddings": emb,
        "point_coords": point_coords,
        "point_labels": point_labels,
        "mask_input": mask_input,
        "has_mask_input": has_mask_input,
        "orig_im_size": orig_im_size
    })
    masks = dec_output[0]
    print(f"Decoder Time: {time.time() - t0:.3f}s, Output shape: {masks.shape}")

except Exception as e:
    print(f"Error: {e}")
