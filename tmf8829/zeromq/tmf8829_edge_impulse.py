# *****************************************************************************
# * Copyright by ams OSRAM AG                                                 *
# * All rights are reserved.                                                  *
# *                                                                           *
# *FOR FULL LICENSE TEXT SEE LICENSES-MIT.TXT                                 *
# *****************************************************************************
"""
Edge impulse data communications functions for uploading training data sets
"""

# Create API Key in https://studio.edgeimpulse.com/
# Goto Project Dashboard -> Keys -> New API key and copy the number from the browser to below line
API_KEY = "ei_<insert_key_here>"
# additionally create a development HMAC key (need to check this checkbox) in the webclient, but the API_KEY stays the same


# Set Training Label
TRAINING_LABEL = 'Empty_cup'


from typing import List
import requests
import time


class EdgeImpulseStreamer:
    def __init__(self, api_key: str = API_KEY, window_size_frames: int = 1, sensor_interval_ms: int = 420):
        """
        Initializes the Edge Impulse SDK streaming collector.
        
        :param api_key: Your Edge Impulse project API Key.
        :param window_size_frames: How many sequential frames to bundle into a single sample.
                                   Set this to 1 if every frame is an isolated static snapshot.
        """
        self.api_key = api_key
        self.window_size_frames = window_size_frames
        self.sensor_interval_ms = sensor_interval_ms
        self.frame_buffer = []
        self.url = "https://ingestion.edgeimpulse.com/api/training/data"


    def feed_frame(self, frame_2d: list, label: str = TRAINING_LABEL) -> bool:
        """
        Feed a 2D ToF array frame-by-frame. 
        Flattens and buffers locally.
        """
        if not frame_2d or not frame_2d[0]:
            return False

        # 1. Flatten the 2D grid into a simple 1D row using a list comprehension
        flattened_frame = [pixel['peaks'][0]['z'] for row in frame_2d for pixel in row]
        self.frame_buffer.append(flattened_frame)

        # 2. Once the target window frame count is achieved, trigger the upload
        if len(self.frame_buffer) >= self.window_size_frames:
            rows = len(frame_2d)
            cols = len(frame_2d[0])
            return self._upload_window(rows, cols, label)
            
        return False

    def _upload_window(self, rows: int, cols: int, label: str) -> bool:
        print(f"[Streamer] Buffer full ({len(self.frame_buffer)} frames). Sending directly to Edge Impulse...")
        
        # 3. Map out names for your sensor axes dynamically
        # pick ordering to your liking, either in rows/cols or pixel numbered
        #sensors = [{"name": f"p_{r}_{c}", "units": "mm"} for r in range(rows) for c in range(cols)]
        sensors = [{"name": f"a{r*cols+c}", "units": "mm"} for r in range(rows) for c in range(cols)]

        # 4. Construct the lean JSON payload exactly how Edge Impulse expects it
        payload = {
            "protected": {"ver": "v1", "alg": "none"},
            "signature": "0000000000000000000000000000000000000000000000000000000000000000",
            "payload": {
                "device_name": "TMF8829-tof-sensor-node",
                "device_type": "TMF8829",
                "interval_ms": self.sensor_interval_ms,
                "sensors": sensors,
                "values": self.frame_buffer  # List of flattened list rows
            }
        }

        filename = f"{label}_{int(time.time())}.json"

        headers = {
            "x-api-key": self.api_key,
            "x-label": label,
            "x-file-name": filename,
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(self.url, headers=headers, json=payload)
            if response.status_code == 200:
                print("[Success] Upload complete!")
                return True
            else:
                print(f"[Error] Server rejected data: {response.text}")
                return False
        except Exception as e:
            print(f"[Exception] Failed to send network request: {e}")
            return False
        finally:
            # Reset your frame accumulator for the next sequence window
            self.frame_buffer = []


if __name__ == "__main__":
    print('Start tmf8829_zeromq_training_client instead of this file')
    time.sleep(4)
