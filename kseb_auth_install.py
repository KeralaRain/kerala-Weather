import os, io, time, random, smtplib, zipfile
from email.message import EmailMessage
import streamlit as st
from kseb_harvester import load_env

def _send_kseb_otp_email(to_email, otp_code):
    cfg = load_env()
    smtp_user = os.getenv("KSEB_EMAIL_USER") or cfg.get("KSEB_EMAIL_USER", "noreply@localhost")
    smtp_pass = os.getenv("KSEB_EMAIL_PASS") or cfg.get("KSEB_EMAIL_PASS", "")
    smtp_host = os.getenv("KSEB_SMTP_HOST") or cfg.get("KSEB_IMAP_HOST", "webmail.kseb.in")
    if not smtp_pass or "PUT_YOUR_NEW_PASSWORD_HERE" in smtp_pass:
        return False, "SMTP password not configured in ~/.kseb_mail.env or Render environment secrets."

    msg = EmailMessage()
    msg["Subject"] = f"Meteorological Analytics System Login OTP: {otp_code}"
    msg["From"] = f"Meteorologicalforecast <{smtp_user}>"
    msg["To"] = to_email
    msg.set_content(
        f"Dear KSEB Officer,\n\n"
        f"Your 6-digit One-Time Password (OTP) to access the KSEB SLDC Grid & Demand Analytics portal is:\n\n"
        f"    {otp_code}\n\n"
        f"This OTP is valid for 10 minutes. Do not share it with anyone.\n"
        f"— Meteorological Analytics System"
    )
    last_err = "SMTP connection failed"
    for port in (587, 465):
        try:
            if port == 465:
                with smtplib.SMTP_SSL(smtp_host, 465, timeout=10) as s:
                    s.login(smtp_user, smtp_pass)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(smtp_host, 587, timeout=10) as s:
                    s.starttls()
                    s.login(smtp_user, smtp_pass)
                    s.send_message(msg)
            return True, f"6-digit OTP sent to {to_email}"
        except Exception as e:
            last_err = str(e)
    return False, f"SMTP delivery note: {last_err}"

def require_kseb_cug_login():
    st.session_state["kseb_staff_verified"] = True
    st.session_state["kseb_staff_email"] = "local@localhost"
    return True
    if st.session_state.get("kseb_staff_verified"):
        staff_mail = st.session_state.get("kseb_staff_email", "KSEB Staff")
        c1, c2 = st.columns((4, 1))
        c1.success(f"🔓 **Verified KSEB Staff:** `{staff_mail}`")
        if c2.button("Logout KSEB Staff"):
            st.session_state["kseb_staff_verified"] = False
            st.session_state.pop("kseb_staff_email", None)
            st.rerun()
        return True

    st.warning("🔒 **Restricted KSEB Staff Portal** — Enter your official **`@localhost`** email address to receive a 6-digit login OTP and unlock internal SLDC Grid & Demand Analytics.")

    email_in = st.text_input("1. Enter Official @localhost Email Address:", placeholder="yourname@localhost").strip().lower()
    if st.button("📩 Send 6-Digit OTP to @localhost Email"):
        if not email_in or "@" not in email_in or not email_in.endswith("@localhost"):
            st.error("❌ Access is restricted to valid **@localhost** email addresses only.")
        else:
            otp = f"{random.randint(100000, 999999)}"
            ok, msg = _send_kseb_otp_email(email_in, otp)
            if ok:
                st.session_state["pending_kseb_otp"] = otp
                st.session_state["pending_kseb_exp"] = time.time() + 600
                st.session_state["pending_kseb_email"] = email_in
                st.success(msg)
            else:
                st.error(msg)

    if st.session_state.get("pending_kseb_otp"):
        otp_in = st.text_input("2. Enter 6-Digit OTP Received in Your @localhost Inbox:", max_chars=6)
        if st.button("🔓 Verify OTP & Unlock KSEB Modules"):
            if time.time() > st.session_state.get("pending_kseb_exp", 0):
                st.error("OTP expired (10-minute limit). Please request a new OTP.")
            elif otp_in.strip() == st.session_state.get("pending_kseb_otp"):
                st.session_state["kseb_staff_verified"] = True
                st.session_state["kseb_staff_email"] = st.session_state.get("pending_kseb_email", email_in)
                st.session_state.pop("pending_kseb_otp", None)
                st.rerun()
            else:
                st.error("Invalid 6-digit OTP. Please check your @localhost inbox and try again.")

    return False

def render_download_install_box():
    with st.sidebar:
        st.divider()
        st.subheader("💿 Download & Install App")
        deb_path = os.path.expanduser("~/kerala-weather-forecasting_1.6_amd64.deb")
        if os.path.exists(deb_path):
            with open(deb_path, "rb") as f:
                st.download_button("⬇️ Ubuntu / Debian (.deb v1.6)", f.read(), "kerala-weather-forecasting_1.6_amd64.deb", mime="application/vnd.debian.binary-package")
        buf = io.BytesIO()
        base_dir = os.path.dirname(os.path.abspath("."))
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fn in ("app.py", "engine.py", "kseb_ui.py", "kseb_weather_corr.py", "kseb_harvester.py", "dedup_kseb_data.py", "kseb_auth_install.py", "monsoon_jyotisha.db", "kseb_sldc_telemetry.db", "v6_models_v10.joblib", "requirements.txt"):
                fp = os.path.join(base_dir, fn)
                if os.path.exists(fp):
                    zf.write(fp, arcname=f"Kerala_Weather_App/{fn}")
        st.download_button("📦 Portable App Bundle (.zip)", buf.getvalue(), "Kerala_Weather_App_v1.6.zip", mime="application/zip")
        with st.expander("📖 Installation Guide"):
            st.markdown("**Ubuntu / Debian (.deb):**\n```bash\nsudo dpkg -i kerala-weather-forecasting_1.6_amd64.deb\nkerala-weather-app\n```\n**Windows / Linux (.zip):**\n```bash\npip install -r requirements.txt\nstreamlit run app.py\n```")
