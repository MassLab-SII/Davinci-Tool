"""查询 MaaS API 可用模型列表，并测试每个模型是否真正可用"""

import os
import sys
import concurrent.futures
import requests
from dotenv import load_dotenv

load_dotenv()

PROFILE = os.getenv("MODEL_PROFILE", "EXPLORATION").upper()
BASE_URL = os.getenv(f"{PROFILE}_MODEL_BASE_URL", "")
API_KEY = os.getenv(f"{PROFILE}_MODEL_API_KEY", "")
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def list_models():
    resp = requests.get(f"{BASE_URL}/models", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    models = sorted(m["id"] for m in resp.json().get("data", []))
    print(f"共 {len(models)} 个模型 ({BASE_URL}):\n")
    for name in models:
        print(f"  - {name}")
    return models


def test_model(model: str) -> tuple[str, bool, str]:
    """向模型发送一条简单请求，返回 (model, ok, detail)"""
    try:
        resp = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=HEADERS,
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            return model, True, ""
        return model, False, f"HTTP {resp.status_code}: {resp.text[:120]}"
    except Exception as e:
        return model, False, str(e)[:120]


def test_all(models: list[str], workers: int = 5):
    """并发测试所有模型可用性"""
    ok_list, fail_list = [], []

    print(f"\n正在测试 {len(models)} 个模型（并发 {workers}）...\n")
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(test_model, m): m for m in models}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            name, ok, detail = fut.result()
            status = "✓" if ok else "✗"
            suffix = "" if ok else f"  ({detail})"
            print(f"  [{i}/{len(models)}] {status} {name}{suffix}")
            (ok_list if ok else fail_list).append((name, detail))

    # 汇总
    print(f"\n{'='*60}")
    print(f"可用: {len(ok_list)}  |  不可用: {len(fail_list)}  |  总计: {len(models)}")
    print(f"{'='*60}")

    if ok_list:
        print("\n可用模型:")
        for name, _ in sorted(ok_list):
            print(f"  ✓ {name}")

    if fail_list:
        print("\n不可用模型:")
        for name, detail in sorted(fail_list):
            print(f"  ✗ {name}  — {detail}")


if __name__ == "__main__":
    models = list_models()
    if "--test" in sys.argv:
        test_all(models)
