import urllib.request
import json

repos = ["Eric-23xd/MobileSam_Onnx", "PulpCut/mobilesam-onnx", "gifty-so/mobilesam-onnx", "mantaur/mobile-sam-onnx"]

for repo in repos:
    print(f"\n--- {repo} ---")
    url = f"https://huggingface.co/api/models/{repo}/tree/main"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            for file in data:
                print(f"File: {file['path']} - Size: {file.get('size')}")
    except Exception as e:
        print(f"Error: {e}")
