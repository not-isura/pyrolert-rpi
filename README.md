# PyroLert Fire Alert System (Raspberry Pi)

PyroLert is a smart smoke detection system deployed on a Raspberry Pi, designed to accurately distinguish between harmless smoke sources—such as those produced by culinary activities and scientific experiments—and dangerous fire-related smoke. The system is further integrated with a camera-based monitoring component to support and enhance evacuation protocols in a classroom setting, while also aiming to reduce false alarms through multi-sensor environmental analysis and decision logic.


The system continuously reads environmental data at approximately **1 Hz (one reading per second)** from the following sensors:

- **CO (Carbon Monoxide) Sensor**
- **NO₂ (Nitrogen Dioxide) Sensor**
- **O₂ (Oxygen) Sensor**
- **PM2.5 (Particulate Matter) Sensor**
- **Temperature Sensor**

To determine potential fire-related incidents, PyroLert uses a combination of **instantaneous decision logic** and a **sliding-window detection algorithm**. Every second, the system evaluates sensor readings and classifies the environment into **Normal, Warning, or High Alert** based on predefined thresholds.

Beyond real-time classification, the system evaluates the **most recent 20 seconds of sensor activity** using a sliding-window approach to improve reliability and reduce false alarms. Since readings are collected per second, the system analyzes the **latest 20 instantaneous classifications** and applies a **60% confidence threshold (12 out of 20 samples)** before triggering an alert episode.

The alert evaluation follows these conditions:

- **Warning Episode** – Triggered when the combined count of **Warning** and **High Alert** classifications reaches **≥12 out of 20 samples**
- **High Alert Episode** – Triggered when **High Alert** classifications alone reach **≥12 out of 20 samples**

Once triggered, PyroLert activates the corresponding alert mechanisms.

During an active alert, PyroLert activates the **local buzzer alarm** and triggers a **real-time website alert** for monitoring personnel. Simultaneously, the Raspberry Pi requests an image capture from the **ESP32-CAM module** and performs **YOLO-based person headcount detection** to estimate the number of occupants within the monitored area.

The system generates two separate email notifications during an alert event:

- **Alert Notification Email** – sent immediately when an alert is triggered (Warning or High Alert)
- **Headcount Notification Email** – sent after YOLO processing, containing the detected number of occupants

All sensor readings, instantaneous classifications, alert transitions, alert episodes, and headcount detection results are stored locally in an **SQLite database** and synchronized with **Supabase** for remote monitoring through the web platform.

The final database schema consists of the following tables:

- **sensor_readings** – stores per-second sensor data and instantaneous classifications  
- **alert_episodes** – stores consolidated alert events from sliding-window detection  
- **alert_transitions** – records changes in system state during an alert episode(Warning, High Alert)  
- **headcount_logs** – stores YOLO-based headcount detection results with timestamps  


## Setup

**1. Create a virtual environment with system site-packages**
```bash
python3 -m venv --system-site-packages venv
```

**2. Activate the virtual environment**
```bash
source venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Configure environment variables**

Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```

**5. Run**
```bash
cd __pyrolert-v1.0.0
python main.py
```
