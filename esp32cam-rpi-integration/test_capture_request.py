import time
from pathlib import Path
# from esp32_capture import capture_image_from_esp32  # old: two requests (/capture + /saved-photo)
from esp32_capture import capture_image_stream         # new: single request (/capture-stream)

ESP32_URL = "http://pyrolert-esp32cam.local"  # <-- change this to your ESP32-CAM IP
OUTPUT_DIR = Path("captured_images")

if __name__ == "__main__":
    while True:
        answer = input("Capture picture? (y/n): ").strip().lower()

        if answer == "n":
            print("Exiting.")
            break
        elif answer == "y":
            print("Capturing...")
            start = time.time()

            # -- old way (two requests) --
            # result = capture_image_from_esp32(
            #     esp32_url=ESP32_URL,
            #     output_dir=OUTPUT_DIR,
            #     capture_delay=0,
            #     retries=3,
            # )

            # -- new way (single request, no SPIFFS) --
            result = capture_image_stream(
                esp32_url=ESP32_URL,
                output_dir=OUTPUT_DIR,
            )

            elapsed = time.time() - start
            if result:
                print(f"Saved: {result.saved_path} ({result.bytes_written} bytes) — took {elapsed:.2f}s")
            else:
                print("Capture failed. Check ESP32-CAM connection.")
        else:
            print("Please enter y or n.")