import onnxruntime as ort
import sys

model_path = "models/normal/model.onnx"
try:
    session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
    for i, input in enumerate(session.get_inputs()):
        print(f"Input {i}: Name='{input.name}', Shape={input.shape}, Type={input.type}")
    for i, output in enumerate(session.get_outputs()):
        print(f"Output {i}: Name='{output.name}', Shape={output.shape}, Type={output.type}")
except Exception as e:
    print(f"Error: {e}")
