import huggingface_hub.utils
import shutil
import os
from core.utils import get_base_path

original_tqdm = huggingface_hub.utils.tqdm

class CustomTqdm(original_tqdm):
    def update(self, n=1):
        super().update(n)
        if getattr(self, "unit", "") == "B":
            print(f"PATCHED: {self.desc}: {self.n}/{self.total}")

huggingface_hub.utils.tqdm = CustomTqdm

from huggingface_hub import snapshot_download

# remove cache for a specific tiny repo to force download
repo = "hf-internal-testing/tiny-random-stable-diffusion"
cache_dir = os.path.join(get_base_path(), "models", "generative", "hf_cache")
folder_name = f"models--{repo.replace('/', '--')}"
model_path = os.path.join(cache_dir, folder_name)
if os.path.exists(model_path):
    shutil.rmtree(model_path)

print("Starting download with patched tqdm...")
snapshot_download(
    repo_id=repo,
    allow_patterns=["*.json", "*.txt"],
    cache_dir=cache_dir
)
print("Done!")
