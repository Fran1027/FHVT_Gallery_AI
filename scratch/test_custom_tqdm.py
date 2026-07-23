from huggingface_hub import snapshot_download
from tqdm.auto import tqdm

is_cancelled = False

class CustomTqdm(tqdm):
    def update(self, n=1):
        super().update(n)
        if is_cancelled:
            raise Exception("Cancelled by user")
        
        # progress report
        if getattr(self, "unit", "") == "B":
            print(f"{self.desc}: {self.n}/{self.total}")

print("Starting download...")
try:
    snapshot_download(
        repo_id="Lykon/dreamshaper-8",
        allow_patterns=["*.json"],
        tqdm_class=CustomTqdm,
        max_workers=1
    )
    print("Done!")
except Exception as e:
    print(f"Error: {e}")
