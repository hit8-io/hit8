import os
import runpod

# RunPod API key from environment variable (set via Doppler or system env)
API_KEY = os.getenv("RUNPOD_API_KEY")
if not API_KEY:
    raise ValueError("RUNPOD_API_KEY is required but not set")
runpod.api_key = API_KEY

GPU_TYPE = "NVIDIA GeForce RTX 4090"
DATA_CENTER_ID = "EU-RO-1"
CLOUD_TYPE = "SECURE"
MODEL_REPO = "BAAI/bge-m3"

# "turing" tag is optimized for RTX 4090 (Ada Lovelace / Turing architecture features)
# UPDATED IMAGE: 'turing-1.6' fixes the "relative URL" download bug
# You can also use 'ghcr.io/huggingface/text-embeddings-inference:turing-1.7' if 1.6 fails
# "89" refers to Compute Capability 8.9 (RTX 4090 / Ada Lovelace)
TEI_IMAGE = "ghcr.io/huggingface/text-embeddings-inference:89-1.6"

def start():
    print(f"🚀 Launching GPU Pod ...")
    
    # TEI specific command
    # --pooling cls: BGE-M3 usually uses CLS pooling for dense vectors
    # --max-batch-tokens: Controls throughput (adjust based on load)
    cmd = (
        f"--model-id {MODEL_REPO} "
        "--max-client-batch-size 128 "
        "--max-batch-tokens 16384 "
        "--port 8000 "
        "--hostname 0.0.0.0 "
        "--dtype float16 "  # TEI handles fp16/bf16 automatically usually, but explicit is good
    )

    try:
        pod = runpod.create_pod(
            name="BGE-M3-TEI-4090",
            image_name=TEI_IMAGE,
            gpu_type_id=GPU_TYPE,
            cloud_type=CLOUD_TYPE,
            data_center_id=DATA_CENTER_ID,
            network_volume_id=None,
            gpu_count=1,
            volume_in_gb=0,
            container_disk_in_gb=40,
            ports="8000/http",
            docker_args=cmd,
            env={
                # TEI typically needs this for gated models or high throughput settings
                "MAX_CONCURRENT_REQUESTS": "512" 
            },
        )
        print(f"✅ Success! Pod ID: {pod['id']}")
        return pod['id']

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    start()
