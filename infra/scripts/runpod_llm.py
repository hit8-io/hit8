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
MODEL_REPO = "stelterlab/Mistral-Small-24B-Instruct-2501-AWQ"
VLLM_IMAGE = "vllm/vllm-openai:v0.6.3"

def start_ephemeral_pod():
    print(f"🚀 Launching GPU Pod ...")
    
    # vLLM API key from environment variable (optional, defaults to empty if not set)
    vllm_api_key = os.getenv("VLLM_API_KEY", "")
    
    # Standard vLLM command (No bash tricks needed)
    cmd = (
        f"--model {MODEL_REPO} "
        "--quantization awq_marlin "
        "--dtype float16 "
        "--max-model-len 16384 "
        "--gpu-memory-utilization 0.95 "
        "--host 0.0.0.0 "
        "--port 8000 "
        f"--api-key {vllm_api_key}"
    )

    try:
        pod = runpod.create_pod(
            name="Mistral-Small-24B-vllm-4090",
            image_name=VLLM_IMAGE,
            gpu_type_id=GPU_TYPE,
            cloud_type=CLOUD_TYPE,
            data_center_id=DATA_CENTER_ID,
            network_volume_id=None,
            gpu_count=1,
            
            # --- STORAGE SETTINGS ---
            volume_in_gb=0,            # Disable persistent volume (No Stop button)
            container_disk_in_gb=40,   # Increase to 40GB to fit Model + OS
            
            ports="8000/http",
            docker_args=cmd,
        )
        print(f"✅ Success! Pod ID: {pod['id']}")
        return pod['id']

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    start_ephemeral_pod()
