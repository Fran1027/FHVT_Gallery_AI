import urllib.request
import json

url = "https://huggingface.co/api/models?search=MobileSAM-ONNX"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        for model in data:
            print(model['id'])
except Exception as e:
    print(f"Error: {e}")
