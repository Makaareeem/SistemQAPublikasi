"""Client-only benchmark. Start the backend first; no server settings are changed."""
import argparse
import json
import statistics
import time
import requests

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default="llama3.2-finetuned")
    parser.add_argument("--question", default="Apa yang dimaksud dengan Tingkat Partisipasi Angkatan Kerja?")
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 20:
        parser.error("--repeat harus 1 sampai 20")
    elapsed = []
    for i in range(args.repeat):
        started = time.perf_counter()
        response = requests.post(args.url.rstrip("/")+"/api/ask",
                                 json={"question":args.question,"model_key":args.model},timeout=(5,600))
        response.raise_for_status()
        data = response.json()
        wall = time.perf_counter()-started
        elapsed.append(wall)
        print(json.dumps({"run":i+1,"client_s":round(wall,3),"latency":data["latency"],
                          "cache":data["cache"],"generation_metrics":data["generation_metrics"],
                          "answer_status":data["answer_status"],"config":data["config"]},ensure_ascii=False))
    print(json.dumps({"median_client_s":round(statistics.median(elapsed),3),
                      "note":"Run pertama belum tentu cold start; periksa load_duration dan cache."}))

if __name__ == "__main__":
    main()
