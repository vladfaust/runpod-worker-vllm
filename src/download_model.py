import os
import json
import logging
import glob
from shutil import rmtree
from huggingface_hub import snapshot_download, hf_hub_download
from functools import wraps
from time import time

BASE_DIR = "/" 
TOKENIZER_PATTERNS = [["*.json", "tokenizer*"]]
MODEL_PATTERNS = [["*.safetensors"], ["*.bin"], ["*.pt"]]


def timer_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time()
        result = func(*args, **kwargs)
        end = time()
        logging.info(f"{func.__name__} completed in {end - start:.2f} seconds")
        return result
    return wrapper

def setup_env():
    if os.getenv("TESTING_DOWNLOAD") == "1":
        BASE_DIR = "tmp"
        os.makedirs(BASE_DIR, exist_ok=True)
        os.environ.update({
            "HF_HOME": f"{BASE_DIR}/hf_cache",
            "MODEL_NAME": "openchat/openchat-3.5-0106",
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
            "TENSORIZE": "1",
            "TENSORIZER_NUM_GPUS": "1",
            "DTYPE": "auto"
        })

@timer_decorator
def download(name, revision, type, cache_dir):
    if type == "model":
        pattern_sets = [model_pattern + TOKENIZER_PATTERNS[0] for model_pattern in MODEL_PATTERNS]
    elif type == "tokenizer":
        pattern_sets = TOKENIZER_PATTERNS
    else:
        raise ValueError(f"Invalid type: {type}")
    try:
        for pattern_set in pattern_sets:
            path = snapshot_download(name, revision=revision, cache_dir=cache_dir, 
                                    allow_patterns=pattern_set)
            for pattern in pattern_set:
                if glob.glob(os.path.join(path, pattern)):
                    logging.info(f"Successfully downloaded {pattern} model files.")
                    return path
    except ValueError:
        raise ValueError(f"No patterns matching {pattern_sets} found for download.")
        
@timer_decorator
def download_gguf(repo_id, filename, revision, cache_dir):
    return hf_hub_download(repo_id=repo_id, filename=filename, revision=revision, cache_dir=cache_dir)
          
# @timer_decorator
# def tensorize_model(model_path): TODO: Add back once tensorizer is ready
#     from vllm.engine.arg_utils import EngineArgs
#     from vllm.model_executor.model_loader.tensorizer import TensorizerConfig, tensorize_vllm_model
#     from torch.cuda import device_count

#     tensorizer_num_gpus = int(os.getenv("TENSORIZER_NUM_GPUS", "1"))
#     if tensorizer_num_gpus > device_count():
#         raise ValueError(f"TENSORIZER_NUM_GPUS ({tensorizer_num_gpus}) exceeds available GPUs ({device_count()})")

#     dtype = os.getenv("DTYPE", "auto")
#     serialized_dir = f"{BASE_DIR}/serialized_model"
#     os.makedirs(serialized_dir, exist_ok=True)
#     serialized_uri = f"{serialized_dir}/model{'-%03d' if tensorizer_num_gpus > 1 else ''}.tensors"
    
#     tensorize_vllm_model(
#         EngineArgs(model=model_path, tensor_parallel_size=tensorizer_num_gpus, dtype=dtype),
#         TensorizerConfig(tensorizer_uri=serialized_uri)
#     )
#     logging.info("Successfully serialized model to %s", str(serialized_uri))
#     logging.info("Removing HF Model files after serialization")
#     rmtree("/".join(model_path.split("/")[:-2]))
#     return serialized_uri, tensorizer_num_gpus, dtype

if __name__ == "__main__":
    setup_env()
    cache_dir = os.getenv("HF_HOME")
    model_name, model_revision, model_filename = os.getenv("MODEL_NAME"), os.getenv("MODEL_REVISION"), os.getenv("MODEL_FILENAME")  or None
    tokenizer_name, tokenizer_revision = os.getenv("TOKENIZER_NAME") or None, os.getenv("TOKENIZER_REVISION") or None
    quantization = os.getenv("QUANTIZATION") or None

    logging.info(f"Downloading model {model_name} (filename {model_filename}) revision {model_revision} with quantization {quantization}.")
   
    if quantization == "gguf":
        if model_filename is None:
            raise ValueError("MODEL_FILENAME must be provided for gguf quantization.")

        model_path = download_gguf(model_name, model_filename, model_revision, cache_dir)
        metadata = {
            "MODEL_NAME": model_path,
            "MODEL_REVISION": model_revision,
            "QUANTIZATION": quantization,
        }
    else:
        model_path = download(model_name, model_revision, "model", cache_dir)
        tokenizer_path = download(tokenizer_name, tokenizer_revision, "tokenizer", cache_dir)
        metadata = {
            "MODEL_NAME": model_path,
            "MODEL_REVISION": model_revision,
            "QUANTIZATION": quantization,
            "TOKENIZER_NAME": tokenizer_path,
            "TOKENIZER_REVISION": tokenizer_revision
        }
    
    # if os.getenv("TENSORIZE") == "1": TODO: Add back once tensorizer is ready
    #     serialized_uri, tensorizer_num_gpus, dtype = tensorize_model(model_path)
    #     metadata.update({
    #         "MODEL_NAME": serialized_uri,
    #         "TENSORIZER_URI": serialized_uri,
    #         "TENSOR_PARALLEL_SIZE": tensorizer_num_gpus,
    #         "DTYPE": dtype
    #     })
        
    with open(f"{BASE_DIR}/local_model_args.json", "w") as f:
        json.dump({k: v for k, v in metadata.items() if v not in (None, "")}, f)