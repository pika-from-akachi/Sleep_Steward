from vlm_detector import BlanketDetector

API_KEY = "42bzP32Fu4tI7lQlQPUU22jdfYiPvr2qSVVP7Mzmmfa5yjLfD4rwFjgrW5ST2Jl47"
d = BlanketDetector(API_KEY)
result = d.analyze("/tmp/cam0.jpg")
if result:
    for k, v in result.items():
        print(f"{k}: {v}")
else:
    print("VLM FAIL")
