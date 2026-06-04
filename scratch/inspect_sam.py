import os
from huggingface_hub import hf_hub_download
import onnxruntime as ort

repo_id = "PulpCut/mobilesam-onnx"
try:
    print("Downloading encoder...")
    enc_path = hf_hub_download(repo_id=repo_id, filename="mobilesam.encoder.onnx")
    print("Downloading decoder...")
    dec_path = hf_hub_download(repo_id=repo_id, filename="mobilesam.decoder.onnx")

    def inspect_onnx(path, name):
        print(f"\n--- {name} ---")
        session = ort.InferenceSession(path, providers=['CPUExecutionProvider'])
        print("INPUTS:")
        for i in session.get_inputs():
            print(f"  {i.name}: {i.shape} ({i.type})")
        print("OUTPUTS:")
        for o in session.get_outputs():
            print(f"  {o.name}: {o.shape} ({o.type})")

    inspect_onnx(enc_path, "Encoder")
    inspect_onnx(dec_path, "Decoder")

except Exception as e:
    print(f"Error: {e}")
