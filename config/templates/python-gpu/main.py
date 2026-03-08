"""GPU detection and PyTorch benchmark starter."""

import torch


def check_gpu():
    """Check CUDA availability and print device info."""
    if torch.cuda.is_available():
        device = torch.cuda.get_device_name(0)
        mem_total = torch.cuda.get_device_properties(0).total_mem / 1024**3
        mem_free, _ = torch.cuda.mem_get_info()
        mem_free_gb = mem_free / 1024**3
        print(f"GPU: {device}")
        print(f"Memory: {mem_free_gb:.1f} GB free / {mem_total:.1f} GB total")
        print(f"CUDA: {torch.version.cuda}")
    else:
        print("No CUDA GPU detected")
    return torch.cuda.is_available()


def benchmark(size: int = 2048, iterations: int = 100):
    """Run a simple matrix multiplication benchmark."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"\nBenchmark: {size}x{size} matmul x{iterations} on {device}")

    a = torch.randn(size, size, device=device)
    b = torch.randn(size, size, device=device)

    # Warmup
    for _ in range(10):
        torch.mm(a, b)
    if device == "cuda":
        torch.cuda.synchronize()

    # Benchmark
    start = torch.cuda.Event(enable_timing=True) if device == "cuda" else None
    end = torch.cuda.Event(enable_timing=True) if device == "cuda" else None

    if start and end:
        start.record()
        for _ in range(iterations):
            torch.mm(a, b)
        end.record()
        torch.cuda.synchronize()
        elapsed_ms = start.elapsed_time(end)
    else:
        import time

        t0 = time.perf_counter()
        for _ in range(iterations):
            torch.mm(a, b)
        elapsed_ms = (time.perf_counter() - t0) * 1000

    print(f"Total: {elapsed_ms:.0f} ms ({elapsed_ms / iterations:.1f} ms/iter)")
    tflops = 2 * size**3 * iterations / elapsed_ms / 1e9
    print(f"Throughput: {tflops:.2f} TFLOPS")


if __name__ == "__main__":
    check_gpu()
    benchmark()
