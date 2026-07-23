import cv2
import numpy as np
import onnxruntime as ort

# Load model
sess = ort.InferenceSession('models/restore/1x-CodeFormer.onnx', providers=['CPUExecutionProvider'])

# Load a test image (just a random small RGB array for testing math, or an actual image)
# We will just see the range of the output
test_in = np.random.rand(1, 3, 512, 512).astype(np.float32)

# Case 1: [0, 1] input
out_01 = sess.run(None, {'input': test_in})[0]

# Case 2: [-1, 1] input
test_in_neg1 = (test_in - 0.5) / 0.5
out_neg1 = sess.run(None, {'input': test_in_neg1})[0]

print("Case 1 [0, 1] input -> Output min/max:", out_01.min(), out_01.max(), out_01.mean())
print("Case 2 [-1, 1] input -> Output min/max:", out_neg1.min(), out_neg1.max(), out_neg1.mean())
