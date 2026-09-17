"""
SMS sending, abstracted behind SMS_MODE so the rest of the app never
branches on sandbox vs live.

Sandbox mode never calls out to Africa's Talking at all -- it just logs
the message to the server console, which is where you read OTPs during
local development. This deliberately means the OTP is never returned in
any API response body, even in sandbox: that code path should look
identical to production so a habit doesn't get built that would leak an
OTP over HTTP if sandbox mode were ever left on by mistake.
"""

from flask import current_app


def send_sms(phone_number: str, message: str) -> None:
    mode = current_app.config.get("SMS_MODE", "sandbox")

    if mode == "sandbox":
        current_app.logger.info(f"[SANDBOX SMS to {phone_number}] {message}")
        return

    import africastalking
    africastalking.initialize(
        current_app.config["AT_USERNAME"],
        current_app.config["AT_API_KEY"],
    )
    sms = africastalking.SMS
    sms.send(message, [phone_number])
