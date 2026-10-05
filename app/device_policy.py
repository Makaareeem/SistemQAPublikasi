"""Keep retrieval models off small GPUs shared with the answer service."""
import logging
from functools import lru_cache
import torch

log = logging.getLogger(__name__)
SMALL_GPU_BYTES = 6 * 1024**3


@lru_cache(maxsize=8)
def retrieval_device(requested=""):
    if requested:
        return requested  # Respect explicit deployment settings.
    if not torch.cuda.is_available():
        return "cpu"
    total = torch.cuda.get_device_properties(torch.cuda.current_device()).total_memory
    if total <= SMALL_GPU_BYTES:
        log.info("Retrieval uses CPU: %.1f GiB GPU reserved for answer generation", total / 1024**3)
        return "cpu"
    return None  # Let the library select the available device on other machines.
