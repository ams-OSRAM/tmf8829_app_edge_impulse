# *****************************************************************************
# * Copyright by ams OSRAM AG                                                 *
# * All rights are reserved.                                                  *
# *                                                                           *
# *FOR FULL LICENSE TEXT SEE LICENSES-MIT.TXT                                 *
# *****************************************************************************
"""
Edge impulse live classification functions
"""

# Create API Key in https://studio.edgeimpulse.com/
# Goto Project Dashboard -> Keys -> New API key and copy the number from the browser to below line
# and copy it into file tmf8829_edge_impulse.py
# additionally create a development HMAC key (need to check this checkbox) in the webclient, but the API_KEY stays the same

import tmf8829_edge_impulse   # to get the API key
import tmf8829_zeromq_client_class as zeromq_client  # to get the measurement results
import json
import time
import requests
import asyncio
import websockets


# --- CONFIGURATION ---
API_KEY = tmf8829_edge_impulse.API_KEY       # Your Edge Impulse project API Key
DEVICE_ID = "tmf8829_evm"  # Name that will show up inside your browser
DEVICE_TYPE = "CUSTOM_MATRIX_NODE"

async def edge_impulse_daemon_bridge(tmf8829_evm):
    uri = "wss://remote-mgmt.edgeimpulse.com"
    
    async with websockets.connect(uri) as ws:
        print(f"[WebSocket] Connected to Edge Impulse Ingestion Network.")

        # 1. Send the Hello Handshake to register your script as an active device
        hello_payload = {
            "hello": {
                "version": 3,
                "apiKey": API_KEY,
                "deviceId": DEVICE_ID,
                "deviceType": DEVICE_TYPE,
                "connection": "daemon",
                "supportsSnapshotStreaming": False,
                "sensors": [
                    {
                        "name": "TMF8829 48x32 dToF Sensor",
                        "frequencies": [5],  # 5Hz target (200ms intervals)
                        "maxSampleLengthS": 60
                    }
                ]
            }
        }
        await ws.send(json.dumps(hello_payload))
        print(f"[WebSocket] Handshake sent! Go look at your Edge Impulse Studio Dashboard—'{DEVICE_ID}' is now green and online.")

        # 2. Wait for the browser client to click "Start Sampling"
        async for message in ws:
            server_event = json.loads(message)

            # DIAGNOSTIC PRINT: This exposes exactly what Edge Impulse thinks of your connection
            print(f"\n[Server Message Received] -> {json.dumps(server_event, indent=2)}")

           
            if "sample" in server_event:
                sample_config = server_event["sample"]
                label = sample_config.get("label", "live_capture")
                length_ms = sample_config.get("length", 2000)
                interval_ms = sample_config.get("interval", 400)

                # 1. DYNAMIC ROUTING: Detect whether the web client wants training or testing data
                # Default to "testing" if triggered from the Live Classification tab
                category = sample_config.get("category", "testing")
                
                print(f"\n[Remote Control] Web client triggered recording! Target Vault: {category.upper()}")
                print(f"[Remote Control] Label: '{label}' ({length_ms}ms window)")

                # Signal the website interface that the hardware is active
                await ws.send(json.dumps({"sampleStarted": True}))
                
                # Calculate how many slices of data the timeline needs
                total_target_frames = int(length_ms / interval_ms)
                frame_buffer = []
                
                print(f"[Sensor] Capturing {total_target_frames} chronological frames...")
                for _ in range(total_target_frames):
                    pixelResults, *_ = tmf8829_evm.measure()
                    rows = len(pixelResults)
                    cols = len(pixelResults[0])
                    frame_buffer.append([pixel['peaks'][0]['z'] for row in pixelResults for pixel in row])
                tmf8829_evm.stop_measurement()

                # Inform browser UI that data is compiling
                await ws.send(json.dumps({"sampleUploading": True}))
                
                # 2. Construct and Post Data Acquisition JSON directly via HTTP Requests
                # sensors = [{"name": f"p_{r}_{c}", "units": "mm"} for r in range(tof_rows) for c in range(tof_cols)]
                sensors = [{"name": f"a{r*rows+c}", "units": "mm"} for r in range(cols) for c in range(rows)]

                payload = {
                    "protected": {"ver": "v1", "alg": "none"},
                    "signature": "0000000000000000000000000000000000000000000000000000000000000000",
                    "payload": {
                        "device_name": DEVICE_ID,
                        "device_type": DEVICE_TYPE,
                        "interval_ms": interval_ms,
                        "sensors": sensors,
                        "values": frame_buffer
                    }
                }
                
                filename = f"{label}_{int(time.time())}.json"
                headers = {
                    "x-api-key": API_KEY,
                    "x-label": label,
                    "x-file-name": filename,
                    "Content-Type": "application/json"
                }
                
                # 3. DYNAMIC ENDPOINT: Select training or testing URL dynamically
                ingestion_url = f"https://ingestion.edgeimpulse.com/api/{category}/data"
                
                # print(f"[HTTP Ingestion] Transferring payload package directly to {ingestion_url}...")
                response = requests.post(ingestion_url, headers=headers, json=payload)

                if response.status_code == 200:
                    print(f"[HTTP Ingestion] Success! Data sent. {response.text}")
                else:
                    print(f"[HTTP Ingestion] Server error: {response.text}")


if __name__ == "__main__":

    # connect to EVM
    tmf8829_evm = zeromq_client.tmf8829_evm_connector()

    # start communication to Edge Impulse and publish data
    try:
        asyncio.run(edge_impulse_daemon_bridge(tmf8829_evm))
    except KeyboardInterrupt:
        print("\nScript closed. Terminating active website connection channel.")

    # close EVM
    tmf8829_evm.end_connection()

    time.sleep(4)
