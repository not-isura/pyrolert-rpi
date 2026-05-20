from gmail_smtp_email import send_alert_email, send_escalation_email
from datetime import datetime
from pathlib import Path

recipients = [
    #"aleannchrizelyabut@gmail.com",
    #"pyrolert.system@gmail.com",
    "maxcoronel4@gmail.com",
    "isla.russell.21@gmail.com",
    "christiansaludo.laca@gmail.com",
    "hatdogudih12jdd1@gmail.com"
]

#local_headcount_path = Path(__file__).with_name("headcount.jpg")
supabase_headcount_url = "https://pitxuzpklqycpybtdfvt.supabase.co/storage/v1/object/public/headcount-captures/esp32_20260513_152317_annotated.jpg"

# for recipient in recipients:
#     send_alert_email(
#         recipient,
#         status="Warning",
#         triggered_at=datetime.now(),
#         headcount=7,
#         headcount_image_path=str(local_headcount_path),
#     )

for recipient in recipients:
    success = send_alert_email(
        recipient,
        status="High Alert",
        triggered_at=datetime.now(),
        headcount=9,
        headcount_image_url=supabase_headcount_url,
    )
    print(f"[{'OK' if success else 'FAILED'}] {recipient}")

# for recipient in recipients:
#     send_escalation_email(
#         recipient,
#         status="High Alert",
#         triggered_at=datetime.now(),
#         escalation_ts=datetime.now(),
#         headcount=9,
#     )