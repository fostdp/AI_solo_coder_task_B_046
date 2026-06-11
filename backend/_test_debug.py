import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.digital_display import DigitalReconstructionPipeline

pipeline = DigitalReconstructionPipeline()
photo_urls = [f'https://example.com/photo{i}.jpg' for i in range(20)]
random.seed(42)
result = pipeline.run_full_pipeline(photo_urls=photo_urls, method='摄影测量', generate_vr=False)
print('Status:', result['status'])
if result['status'] == 'failed':
    print('Error:', result.get('error', 'N/A'))
    print('Log keys:', list(result.get('reconstruction_log', {}).keys()))
    step2 = result.get('reconstruction_log', {}).get('step_2_照片预处理', {})
    print('Step 2:', step2)
