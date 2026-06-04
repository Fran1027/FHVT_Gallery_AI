import urllib.request
import json

url = "https://huggingface.co/api/models/Heliosoph/moge-2-vits-normal-onnx/tree/main"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        for file in data:
            print(f"File: {file['path']} - Size: {file.get('size')}")
except Exception as e:
    print(f"Error: {e}")
