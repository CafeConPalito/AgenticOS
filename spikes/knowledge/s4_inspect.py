import sys

import onnxruntime as ort

sys.stdout.reconfigure(encoding="utf-8")
for name, f in (
    ("e5-small", "model_quantized"),
    ("gemma2", "model_quantized"),
    ("gemma2", "model_q4"),
    ("bge-m3", "model_quantized"),
):
    s = ort.InferenceSession(f"models/{name}/onnx/{f}.onnx", providers=["CPUExecutionProvider"])
    print(
        name,
        f,
        "IN",
        [(i.name, i.shape) for i in s.get_inputs()],
        "OUT",
        [(o.name, o.shape) for o in s.get_outputs()],
    )
