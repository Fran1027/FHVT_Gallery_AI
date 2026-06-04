import onnxruntime as ort
import sys
import numpy as np

model_path = "models/normal/model.onnx"
try:
    session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
    
    # create dummy image
    image = np.random.randn(1, 3, 518, 518).astype(np.float32)
    num_tokens = np.array(1369, dtype=np.int64)
    
    outputs = session.run(None, {
        "image": image,
        "num_tokens": num_tokens
    })
    
    print(f"Normal output shape: {outputs[1].shape}")
except Exception as e:
    print(f"Error: {e}")
